#!/usr/bin/env python3
"""
prodrafts2pdf.py - Convierte un archivo Pro Drafts (.prodrafts / .prodrafts.zip)
en un PDF con los trazos del Apple Pencil como VECTORES (calidad ilimitada al
hacer zoom), conservando el PDF de fondo de cada página.
Incluye también los cuadros de texto (RTF, con tablas).

Fondo oscuro: se detecta por página (relleno del PDF, color de papel de Pro Drafts o brillo) y, si es oscuro,
se pasa a papel blanco invirtiendo los neutros (blanco->negro); los colores se respetan.

Uso:
    python3 prodrafts2pdf.py nota.prodrafts.zip [salida.pdf] [--out-dir DIR] [--db BIBLIOTECA.sqlite]
                             [--width 0.55] [--canvas-scale 0.5] [--hide-masked]

Carpeta con muchas notas (modo carpeta): python3 prodrafts2pdf.py CARPETA --out-dir DESTINO [--skip-existing]
convierte cada .prodrafts / .zip de CARPETA (solo lectura) y recrea el árbol de carpetas de la biblioteca bajo DESTINO.
Las notas que no han cambiado desde la última exportación (huella en DESTINO/.prodrafts2pdf.json) no se re-exportan; --force lo fuerza.

Las notas de lienzo infinito (formato antiguo de Pro Drafts, sin PDF de fondo) salen como SVG vectorial (.svg); el resto como PDF
vectorial (el PDF de fondo se conserva y los trazos son trazados, no imágenes). Con 'salida.pdf' explícito, las infinitas también pueden ir a PDF.

Sin 'salida.pdf': el PDF se llama como la nota en Pro Drafts (no el UUID) y se guarda dentro de las mismas carpetas
que tiene en la biblioteca, bajo --out-dir (por defecto, el directorio actual). El nombre y las carpetas salen de
MainDrawBoardFile.sqlite (tabla ZBOARDFILE) del contenedor de Pro Drafts; se trabaja sobre una COPIA temporal,
nunca se abre ni se modifica el original. El UUID de la nota se toma del nombre del .zip / .prodrafts.

Dependencias: pip install reportlab pypdf pillow   (HEIC: pillow-heif, o sips en macOS / heif-convert, ImageMagick o ffmpeg en Linux)
"""
import argparse, glob, io, math, os, plistlib, struct, sys, tempfile, zipfile

# ---------------------------------------------------------------- protobuf mínimo
def _varint(b, i):
    r = s = 0
    while True:
        c = b[i]; i += 1
        r |= (c & 127) << s; s += 7
        if c < 128:
            return r, i

def pb(b):
    """Devuelve [(campo, wiretype, valor)]"""
    i, out = 0, []
    while i < len(b):
        k, i = _varint(b, i); f, t = k >> 3, k & 7
        if t == 0:
            v, i = _varint(b, i)
        elif t == 2:
            l, i = _varint(b, i); v = b[i:i + l]; i += l
        elif t == 1:
            v = b[i:i + 8]; i += 8
        elif t == 5:
            v = b[i:i + 4]; i += 4
        else:
            raise ValueError("wire type %d" % t)
        out.append((f, t, v))
    return out

def pbd(b):
    d = {}
    for f, t, v in pb(b):
        d.setdefault(f, []).append(v)
    return d

# ---------------------------------------------------------------- PencilKit (.drawing)
# Formato: "wrd\xf0" + versión + protobuf.
#   campo 4 (repetido) = tintas  {1: color RGBA floats, 2: nombre 'com.apple.ink.pen'...}
#   campo 5 (repetido) = trazos  {4: índice de tinta, 5: trayectoria, 7: transformación afín}
#   trayectoria: 3 = nº de puntos, 4 = máscara de atributos presentes por punto,
#                6 = valores constantes de los atributos ausentes, 7 = puntos
#   punto: x,y (f32) + [t f32][tamaño f32][3 x u16][u16 ...] según máscara
# Borrados y movimientos:
#   - trazo SIN campo 5 (trayectoria)  -> trazo eliminado (lápida): no se dibuja.
#   - trazo con campos 9 + 11 = registro de edición (movido y/o recortado/borrado con goma o garabato):
#       * 11.7  = transformación afín (a b c d tx ty) de la posición nueva (sustituye a la del campo 7)
#       * 11.12 = parejas (inicio, fin) de la trayectoria que SIGUEN VISIBLES.
#         Sin parejas -> no queda nada (garabato/trazo borrado). Parejas parciales -> solo esos tramos.
#   - campo 13/14 = trazo enderezado/forma (mantener el lápiz al final): NO es un borrado.
# Imágenes insertadas (PNG/JPEG/HEIC) y formas: tabla ZDRAFTBOARDITEM de note.database.sqlite.
BIT_SIZE = {0: 8, 1: 4, 2: 4, 5: 2, 6: 2, 7: 2, 8: 2}

def parse_drawing(path):
    raw = open(path, 'rb').read()
    if raw[:3] != b'wrd':
        raise ValueError("No es un PKDrawing: %s" % path)
    top = pbd(raw[8:])
    inks = []
    for v in top.get(4, []):
        d = pbd(v)
        col = [struct.unpack('<f', x)[0] for f, t, x in pb(d[1][0])] if 1 in d else [0, 0, 0, 1]
        thick = struct.unpack('<d', d[8][0])[0] if 8 in d and len(d[8][0]) == 8 else 0.0
        inks.append({'color': col, 'name': d[2][0].decode('utf8', 'replace') if 2 in d else '',
                     'fixed': 4 in d and d[4][0] == b'fixed-width', 'thick': thick})
    strokes = []
    for v in top.get(5, []):
        m = pbd(v)
        if 5 not in m:           # lápida de un trazo borrado
            continue
        p = pbd(m[5][0])
        if 3 not in p or 7 not in p:
            continue
        n, mask = p[3][0], p[4][0]
        data, desc = p[7][0], (p[6][0] if 6 in p else b'')
        rec = sum(sz for b_, sz in BIT_SIZE.items() if mask >> b_ & 1)
        if rec * n != len(data):
            rec = len(data) // n          # respaldo si hay un bit desconocido
        # valores constantes (orden: t, tamaño, ...)
        off = 0
        if not mask & 2: off += 4
        const_size = None
        if not mask & 4:
            const_size = struct.unpack('<f', desc[off:off + 4])[0]
        pts = []
        for i in range(n):
            r = data[i * rec:(i + 1) * rec]
            x, y = struct.unpack('<ff', r[:8]); o = 8
            t = 0.0
            if mask & 2:
                t, = struct.unpack('<f', r[o:o + 4]); o += 4
            w = const_size
            if mask & 4:
                w, = struct.unpack('<f', r[o:o + 4]); o += 4
            pts.append((x, y, w))
        # pluma de ancho fijo: el grosor lo marca el ajuste de la pluma (0.5, 0.8...), no el 'tamaño'
        # guardado (2 + grosor), que apenas distingue 0.5 de 0.8. 0.8 -> 2.8 (como antes), 0.5 -> 1.75
        ink0 = inks[m[4][0]] if 4 in m and m[4][0] < len(inks) else None
        if ink0 and ink0['fixed'] and ink0['thick'] > 0:
            pts = [(x, y, FIXED_UNIT * ink0['thick']) for x, y, _ in pts]
        # transformación afín propia del trazo (a b c d tx ty)
        a, b, c, d_, tx, ty = 1, 0, 0, 1, 0, 0
        if 7 in m:
            vals = [struct.unpack('<f', x)[0] for f, t, x in pb(m[7][0])]
            if len(vals) == 6:
                a, b, c, d_, tx, ty = vals
        ink = inks[m[4][0]] if 4 in m and m[4][0] < len(inks) else {'color': [0, 0, 0, 1], 'name': ''}

        def place(T):
            # el escalado del trazo (p.ej. un título agrandado x1.43) también engrosa la línea
            a_, b_, c_, d2, tx_, ty_ = T
            k = math.sqrt(abs(a_ * d2 - b_ * c_)) or 1.0
            return [(a_ * x + c_ * y + tx_, b_ * x + d2 * y + ty_, None if w is None else w * k) for x, y, w in pts]

        def entry(p, ranges, masked, moved):
            return {'pts': p, 'ink': ink, 'ts': m[8][0] if 8 in m else 0, 'ranges': ranges, 'masked': masked,
                    'moved': moved, 'has11': 11 in m, 'r11': [x for r in ranges for x in r]}

        if 11 not in m:
            if 10 in m:
                # trazo con máscara propia (campos 6/10/12 en el propio trazo): 12 = tramos visibles.
                # Sin 12 no queda nada visible (son los puntitos sueltos que deja la goma): no se dibuja.
                fl = [struct.unpack('<f', x)[0] for x in m.get(12, [])]
                rg = [(fl[i], fl[i + 1]) for i in range(0, len(fl) - 1, 2)]
                strokes.append(entry(place((a, b, c, d_, tx, ty)), rg, True, False))
            else:
                strokes.append(entry(place((a, b, c, d_, tx, ty)), [], None, False))
            continue
        # Campo 11 (REPETIDO) = fragmentos que siguen visibles tras editar el trazo (goma, lazo, rayas de borrar).
        # Cada fragmento puede anidar su historial (11 > 11.11 > ...; el más externo es el más reciente):
        #   7  = transformación afín ABSOLUTA (trayectoria original -> posición actual) de la última edición que la define
        #   12 = parejas (inicio, fin) de la trayectoria original que ocupa ese fragmento
        found = False
        for raw in m[11]:
            chain, cur = [pbd(raw)], pbd(raw)
            while 11 in cur:
                cur = pbd(cur[11][0]); chain.append(cur)
            T, moved, ranges = (a, b, c, d_, tx, ty), False, []
            # El nivel más PROFUNDO es la edición más reciente; los exteriores guardan estados anteriores
            # (p.ej. un círculo movido dos veces o un arco ya borrado reaparecían en su sitio viejo).
            #  - transformación: la del nivel más profundo que la defina
            #  - tramos visibles: los del nivel más profundo; si no trae pareja 12, ya no queda nada visible
            for q in reversed(chain):
                if 7 in q:
                    mv = [struct.unpack('<f', x)[0] for f, t, x in pb(q[7][0])]
                    if len(mv) == 6:
                        T, moved = tuple(mv), True
                        break
            fl = [struct.unpack('<f', x)[0] for x in chain[-1].get(12, [])]
            ranges = [(fl[i], fl[i + 1]) for i in range(0, len(fl) - 1, 2)]
            if ranges:
                found = True
                strokes.append(entry(place(T), ranges, True, moved))
        if not found:      # ningún fragmento con rangos: era un garabato / trazo borrado
            strokes.append(entry(place((a, b, c, d_, tx, ty)), [], True, False))
    return strokes

def apply_mask(st, hide=False):
    """Trazos con campo 11 (registro de edición; el trazo original lleva el campo 9 de 'sustituido'):
         - 11.12 = parejas (inicio, fin) de la trayectoria que SIGUEN VISIBLES (índices fraccionarios de punto)
         - sin parejas      -> no queda nada visible: era un garabato/trazo borrado -> no se dibuja
         - rango = todo     -> el trazo se dibuja entero
         - rangos parciales -> se dibujan solo esos tramos (el resto lo borró la goma / el garabato de borrado)
       Si además hay 11.7 el trazo se movió: parse_drawing ya aplicó esa transformación.
       hide=True (--hide-masked): oculta todo trazo con campo 11."""
    if not st.get('masked'):
        return [st]
    rg = sorted(st.get('ranges') or [])
    if hide or not rg:
        return []
    pts = st['pts']; n = len(pts)
    if n == 1:
        return [st]
    def lerp(a, b, t):
        w = None if (a[2] is None or b[2] is None) else a[2] + (b[2] - a[2]) * t
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, w)
    def at(t):
        t = max(0.0, min(t, n - 1.0)); i = min(int(t), n - 2); return lerp(pts[i], pts[i + 1], t - i)
    out = []
    for lo, hi in rg:
        lo, hi = max(lo, 0.0), min(hi, n - 1.0)
        if hi - lo < 1e-3:
            continue
        seg = [at(lo)] + [pts[i] for i in range(n) if lo < i < hi] + [at(hi)]
        partial = lo > 1e-3 or hi < n - 1.0 - 1e-3
        if partial and sum(math.hypot(seg[i + 1][0] - seg[i][0], seg[i + 1][1] - seg[i][1])
                           for i in range(len(seg) - 1)) < MIN_FRAGMENT:
            continue          # restos minúsculos que deja la goma / el garabato: puntitos sueltos
        out.append(dict(st, pts=seg))
    return out

# ---------------------------------------------------------------- geometría
def _ccw(poly):
    a = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
            for i in range(len(poly)))
    return poly if a >= 0 else poly[::-1]

def _disc(cx, cy, r, k=14):
    return [(cx + r * math.cos(2 * math.pi * i / k), cy + r * math.sin(2 * math.pi * i / k)) for i in range(k)]

def dedupe(pts, eps=0.05):
    out = [pts[0]]
    for p in pts[1:]:
        if abs(p[0] - out[-1][0]) > eps or abs(p[1] - out[-1][1]) > eps:
            out.append(p)
    return out

WIDTH_SCALE = 0.55   # calibrado contra la miniatura del propio archivo
FIXED_UNIT = 3.5     # unidades de lienzo por cada 1.0 de grosor de pluma fija (0.8 -> 2.8)
CANVAS_SCALE = 0.5   # lienzo del bloc -> página PDF (medido: el lienzo mide el doble que el A4)
HIDE_MASKED = False  # False: movidos (11.7) se dibujan en su sitio y los borrados se quitan según sus rangos; --hide-masked: oculta todo trazo con campo 11
MIN_FRAGMENT = 4.0   # unidades de lienzo: los tramos visibles de un trazo recortado más cortos que esto se descartan
DARK_PAPER = False   # si el fondo es oscuro: blanco->negro (texto) y fondo->blanco

def map_rgb(r, g, b):
    if DARK_PAPER:
        if max(r, g, b) - min(r, g, b) < 0.3:     # neutros (blanco, gris, negro) se invierten
            return 1 - r, 1 - g, 1 - b
    return r, g, b

def draw_stroke(c, st, H, ox, oy, eraser_color):
    from reportlab.lib.colors import Color
    ink = st['ink']; name = ink['name']
    pts = dedupe(st['pts']) if len(st['pts']) > 1 else st['pts']
    r, g, b, a = ink['color'][:4]
    if 'eraser' in name:
        r, g, b, a = eraser_color + (1.0,)
    else:
        r, g, b = map_rgb(r, g, b)
    if 'marker' in name:
        a = min(a, 0.40)
    elif 'pencil' in name:
        a = min(a, 0.85)
    c.setFillColor(Color(r, g, b, alpha=a)); c.setStrokeColor(Color(r, g, b, alpha=a))
    X = lambda x: x - ox
    Y = lambda y: H - (y - oy)
    ws = [(p[2] or 1.0) * WIDTH_SCALE for p in pts]
    if len(pts) == 1:
        c.circle(X(pts[0][0]), Y(pts[0][1]), ws[0] / 2, stroke=0, fill=1); return
    if max(ws) - min(ws) <= 0.04 * max(ws):          # grosor constante → trazo nativo
        c.setLineWidth(sum(ws) / len(ws)); c.setLineCap(1); c.setLineJoin(1)
        path = c.beginPath(); path.moveTo(X(pts[0][0]), Y(pts[0][1]))
        if len(pts) == 2:
            path.lineTo(X(pts[1][0]), Y(pts[1][1]))
        else:
            for i in range(1, len(pts) - 1):          # curvas por puntos medios
                mx, my = (pts[i][0] + pts[i + 1][0]) / 2, (pts[i][1] + pts[i + 1][1]) / 2
                if i == 1:
                    sx, sy = pts[0][0], pts[0][1]
                p0 = (sx, sy) if i == 1 else prev
                q = pts[i]; e = (mx, my)
                # cuadrática → cúbica
                c1 = (p0[0] + 2 / 3 * (q[0] - p0[0]), p0[1] + 2 / 3 * (q[1] - p0[1]))
                c2 = (e[0] + 2 / 3 * (q[0] - e[0]), e[1] + 2 / 3 * (q[1] - e[1]))
                path.curveTo(X(c1[0]), Y(c1[1]), X(c2[0]), Y(c2[1]), X(e[0]), Y(e[1]))
                prev = e
            path.lineTo(X(pts[-1][0]), Y(pts[-1][1]))
        c.drawPath(path, stroke=1, fill=0)
        return
    # grosor variable → unión de cuadriláteros + discos (relleno no-cero)
    path = c.beginPath()
    def add(poly):
        poly = _ccw(poly)
        path.moveTo(X(poly[0][0]), Y(poly[0][1]))
        for q in poly[1:]:
            path.lineTo(X(q[0]), Y(q[1]))
        path.close()
    for i in range(len(pts) - 1):
        (x1, y1, _), (x2, y2, _) = pts[i], pts[i + 1]
        dx, dy = x2 - x1, y2 - y1; l = math.hypot(dx, dy) or 1
        nx, ny = -dy / l, dx / l; w1, w2 = ws[i] / 2, ws[i + 1] / 2
        add([(x1 + nx * w1, y1 + ny * w1), (x2 + nx * w2, y2 + ny * w2),
             (x2 - nx * w2, y2 - ny * w2), (x1 - nx * w1, y1 - ny * w1)])
    for (x, y, _), w in zip(pts, ws):
        add(_disc(x, y, w / 2))
    # fillMode 1 = nonzero winding
    c.drawPath(path, stroke=0, fill=1, fillMode=1)
    # reportlab usa even-odd por defecto en drawPath(fillMode)
    # (se corrige abajo con fillMode)

# ---------------------------------------------------------------- formas (rectángulos, resaltados...)
def board_items(root, page_uuid, legacy=False):
    """Formas de la tabla ZDRAFTBOARDITEM (p.ej. el recuadro de color translúcido)."""
    import sqlite3, re
    db = os.path.join(root, 'draft.database.sqlite' if legacy else 'note.database.sqlite')
    out = []
    if not os.path.isfile(db):
        return out
    def ka(b):
        try:
            o = plistlib.loads(b)['$objects']; return o
        except Exception:
            return None
    con = sqlite3.connect(db)
    cols = [r[1] for r in con.execute('pragma table_info(ZDRAFTBOARDITEM)')]
    for row in con.execute('select * from ZDRAFTBOARDITEM'):
        r = dict(zip(cols, row))
        if (not legacy and r.get('ZPAGEID') != page_uuid) or r.get('ZISDELETE'):
            continue
        fo = ka(r['ZFRAMEVALUE']) if r.get('ZFRAMEVALUE') else None
        if not fo:
            continue
        nums = [float(x) for x in re.findall(r'-?\d+(?:\.\d+)?(?:e-?\d+)?', next(x for x in fo if isinstance(x, str) and x.startswith('{')))]
        if len(nums) != 4:
            continue
        def col(key):
            o = ka(r[key]) if r.get(key) else None
            d = next((x for x in (o or []) if isinstance(x, dict) and ('UIRed' in x or 'UIWhite' in x)), None)
            if not d:
                return None
            if 'UIRed' in d:
                return (d['UIRed'], d['UIGreen'], d['UIBlue'], d.get('UIAlpha', 1.0))
            # color en escala de grises (p.ej. whiteColor): solo trae UIWhite + UIAlpha
            return (d['UIWhite'], d['UIWhite'], d['UIWhite'], d.get('UIAlpha', 1.0))
        tr = (1, 0, 0, 1, 0, 0)
        try:
            to = plistlib.loads(r['ZTRANSFORMVALUE'])['$objects']
            dd = next(x for x in to if isinstance(x, dict) and 'NS.atval.a' in x)
            tr = tuple(float(dd['NS.atval.' + k]) for k in ('a', 'b', 'c', 'd', 'tx', 'ty'))
        except Exception:
            pass
        ctr = None
        try:
            co = ka(r['ZCENTER'])
            sx = next(x for x in co if isinstance(x, str) and x.startswith('{'))
            ctr = tuple(float(v) for v in re.findall(r'-?\d+(?:\.\d+)?', sx))[:2]
        except Exception:
            pass
        pts_ = {}
        if r.get('ZTYPE') == 5:          # línea / conector (p.ej. separador discontinuo)
            for key in ('ZSTARTPOINT', 'ZENDPOINT'):
                try:
                    po = ka(r[key])
                    sp = next(x for x in po if isinstance(x, str) and x.startswith('{'))
                    pts_[key] = tuple(float(v) for v in re.findall(r'-?\d+(?:\.\d+)?(?:e-?\d+)?', sp))[:2]
                except Exception:
                    pass
        out.append({'line': pts_ if len(pts_) == 2 else None, 'dash': (r.get('ZLINEDASHWIDTH') or 0, r.get('ZLINEDASHSPACE') or 0) if r.get('ZLINETYPE') else None,
                    'cap': r.get('ZLINECAP'), 'type': r.get('ZTYPE'), 'title': r.get('ZNAME'), 'url': r.get('ZLINKURL'), 'frame': nums, 'image': r.get('ZFILENAME') or None, 'tr': tr, 'center': ctr,
                    'alpha': r['ZALPHA'] if r.get('ZALPHA') is not None else 1.0,
                    'fill': col('ZFILLCOLOR') if r.get('ZFILLCOLORENABLE') else None,
                    'stroke': col('ZSTOKECOLOR') if r.get('ZSTOKECOLORENABLE') else None,
                    'lw': r.get('ZLINEWIDTH') or 0, 'radius': r.get('ZCORNERRADIUS') or 0,
                    'rtf': r['ZATTRIBUTEDTEXT'] if r.get('ZTYPE') == 4 and r.get('ZATTRIBUTEDTEXT') else None,
                    'order': r.get('ZZLEVEL') or 0})
    return sorted(out, key=lambda d: d['order'])

# ---------------------------------------------------------------- cuadros de texto (RTF)
# Los cuadros de texto (ZTYPE 4) guardan ZATTRIBUTEDTEXT: un RTFD "plano" cuyo RTF empieza en '{\rtf'.
# Se interpreta un subconjunto de RTF suficiente para el texto de Pro Drafts: tamaño (\fs / \fsmilli), color (\cf),
# negrita/cursiva/subrayado, alineación, espacio tras párrafo y TABLAS (\trowd ... \cell ... \row).
# Detalles del formato:
#   - los acentos van como bytes \'hh en la codificación del tipo de letra: PingFang SC (\fcharset134) => GBK, no cp1252.
#   - la fuente real (PingFang SC) no está disponible: se sustituye por Helvetica (métricas parecidas).
TEXT_INSET = 5.0     # margen del cuadro (unidades de lienzo): coincide con el relleno de línea de Cocoa
LINE_HEIGHT = 1.4    # interlineado de PingFang SC (x tamaño de letra), medido sobre el cuadro de texto de la página 4
CELL_PAD = 3.0       # margen horizontal del texto dentro de una celda

def rtf_extract(blob):
    """Devuelve el texto RTF (bytes) incrustado en el RTFD, o None."""
    i = blob.find(b'{\\rtf')
    if i < 0:
        return None
    depth, j = 0, i
    while j < len(blob):
        ch = blob[j:j + 1]
        if ch == b'\\':
            j += 2; continue
        if ch == b'{':
            depth += 1
        elif ch == b'}':
            depth -= 1
            if depth == 0:
                return blob[i:j + 1]
        j += 1
    return blob[i:]

_RTF_SKIP = {'stylesheet', 'info', 'pict', 'header', 'footer', 'object', 'fldinst', 'listtable', 'listoverridetable',
             'generator', 'expandedcolortbl'}
_RTF_TOKEN = None

def parse_rtf(blob):
    """RTF -> lista de bloques: ('p', párrafo) o ('row', fila).
       párrafo = {'runs': [(texto, fmt)], 'align', 'sa', 'sb', 'fs'}   fmt = {'size','color','b','i','u'}
       fila    = {'cells': [{'paras': [...], 'w': ancho_pt}], 'left': pt, 'border': (color rgb | None, ancho_pt) | None}"""
    import re
    global _RTF_TOKEN
    if _RTF_TOKEN is None:
        _RTF_TOKEN = re.compile(r"\\([a-zA-Z]+)(-?\d+)? ?|\\'([0-9a-fA-F]{2})|\\([^a-zA-Z])|([{}])|([^\\{}\r\n]+)")
    s = rtf_extract(blob)
    if s is None:
        return []
    s = s.decode('latin-1')
    fonts, colors = {}, []          # colors[0] = color automático (la tabla empieza con un ";" vacío)
    cs = dict(size=12.0, milli=None, cf=0, b=False, i=False, u=False, font=0, uc=1)
    ps = dict(align='l', sa=0.0, sb=0.0, intbl=False)
    stack, dest = [], None
    blocks = []
    cur = []                       # runs del párrafo en curso
    cell_paras, row_cells = [], []
    rowdef = dict(left=0.0, cw=[], cx=[], border=None)
    pend = bytearray()
    pend_font = [0]
    cur_color = [None, None, None]
    cur_font = [None]
    border_target = [None]
    pending_cw = [None]
    skip_n = [0]

    def fmt():
        size = cs['milli'] / 1000.0 if cs['milli'] else cs['size']
        col = colors[cs['cf']] if 0 <= cs['cf'] < len(colors) else None
        return dict(size=size, color=col, b=cs['b'], i=cs['i'], u=cs['u'])

    def flush_bytes():
        if pend:
            enc = 'gbk' if fonts.get(pend_font[0]) == 134 else 'cp1252'
            try:
                txt = bytes(pend).decode(enc)
            except Exception:
                txt = bytes(pend).decode('cp1252', 'replace')
            add_text(txt)
            pend.clear()

    def add_text(t):
        if not t:
            return
        f = fmt()
        if cur and cur[-1][1] == f:
            cur[-1] = (cur[-1][0] + t, f)
        else:
            cur.append((t, f))

    def end_para():
        flush_bytes()
        p = dict(runs=list(cur), align=ps['align'], sa=ps['sa'], sb=ps['sb'], fs=fmt()['size'])
        cur.clear()
        (cell_paras if ps['intbl'] else blocks).append(p if ps['intbl'] else ('p', p))

    pos = 0
    skip_depth = None
    for m in _RTF_TOKEN.finditer(s):
        word, num, hx, sym, brace, text = m.groups()
        if brace == '{':
            stack.append((dict(cs), dest));
            if skip_depth is not None: skip_depth += 1
            continue
        if brace == '}':
            flush_bytes()
            if stack:
                cs, dest = stack.pop()
            if skip_depth is not None:
                skip_depth -= 1
                if skip_depth <= 0: skip_depth = None
            continue
        if skip_depth is not None:
            continue
        if sym is not None:
            if sym == '*':
                skip_depth = 1; continue            # destino opcional: se ignora el grupo entero
            if sym in ('\n', '\r'):
                if dest is None: end_para()
            elif sym in '\\{}':
                if dest is None: add_text(sym)
            elif sym == '~':
                if dest is None: add_text('\u00a0')
            elif sym == '_':
                if dest is None: add_text('-')
            continue
        if hx is not None:
            if skip_n[0]:
                skip_n[0] -= 1; continue
            if dest is None:
                pend_font[0] = cs['font']; pend.append(int(hx, 16))
            continue
        if text is not None:
            if dest == 'fonttbl':
                continue
            if dest == 'colortbl':
                if ';' in text:
                    colors.append(tuple(c / 255.0 for c in cur_color) if None not in cur_color else None)
                    cur_color[:] = [None, None, None]
                continue
            if skip_n[0]:
                k = min(skip_n[0], len(text)); text = text[k:]; skip_n[0] -= k
            if dest is None:
                flush_bytes(); add_text(text)
            continue
        # palabra de control
        w = word
        if w in _RTF_SKIP:
            skip_depth = 1; continue
        if w == 'fonttbl':
            dest = 'fonttbl'; continue
        if w == 'colortbl':
            dest = 'colortbl'; cur_color[:] = [None, None, None]; continue
        if dest == 'fonttbl':
            if w == 'f' and num is not None:
                cur_font[0] = int(num)
            elif w == 'fcharset' and num is not None and cur_font[0] is not None:
                fonts[cur_font[0]] = int(num)
            continue
        if dest == 'colortbl':
            if w in ('red', 'green', 'blue') and num is not None:
                idx = ('red', 'green', 'blue').index(w)
                if cur_color[0] is None: cur_color[:] = [0, 0, 0]
                cur_color[idx] = int(num)
            continue
        n = int(num) if num is not None else None
        if w in ('par', 'line'):
            if w == 'par': end_para()
            else: add_text('\n')
        elif w == 'tab':
            flush_bytes(); add_text('    ')
        elif w == 'pard':
            ps.update(align='l', sa=0.0, sb=0.0, intbl=False)
        elif w == 'plain':
            cs.update(b=False, i=False, u=False, cf=0)
        elif w == 'f' and n is not None:
            flush_bytes(); cs['font'] = n
        elif w == 'fs' and n is not None:
            flush_bytes(); cs['size'] = n / 2.0; cs['milli'] = None
        elif w == 'fsmilli' and n is not None:
            flush_bytes(); cs['milli'] = n
        elif w == 'cf' and n is not None:
            flush_bytes(); cs['cf'] = n
        elif w in ('b', 'i', 'ul'):
            flush_bytes(); cs[{'b': 'b', 'i': 'i', 'ul': 'u'}[w]] = (n is None or n != 0)
        elif w == 'ulnone':
            flush_bytes(); cs['u'] = False
        elif w == 'qc': ps['align'] = 'c'
        elif w == 'qr': ps['align'] = 'r'
        elif w in ('ql', 'qj'): ps['align'] = 'l'
        elif w == 'sa' and n is not None: ps['sa'] = n / 20.0
        elif w == 'sb' and n is not None: ps['sb'] = n / 20.0
        elif w == 'intbl': ps['intbl'] = True
        elif w == 'u' and n is not None:
            flush_bytes(); add_text(chr(n + 65536 if n < 0 else n))
            skip_n[0] = cs['uc']          # \uN va seguido de \ucN caracteres de sustitución (Cocoa: \uc0 = ninguno)
        elif w == 'uc' and n is not None: cs['uc'] = n
        # ---- tablas
        elif w == 'trowd':
            rowdef = dict(left=0.0, cw=[], cx=[], border=None); row_cells = []; pending_cw[0] = None
        elif w == 'trleft' and n is not None: rowdef['left'] = n / 20.0
        elif w in ('clbrdrt', 'clbrdrl', 'clbrdrb', 'clbrdrr', 'trbrdrt', 'trbrdrl', 'trbrdrb', 'trbrdrr'):
            border_target[0] = w
        elif w == 'brdrs':
            rowdef['border'] = rowdef['border'] or dict(cf=None, w=0.5)
        elif w == 'brdrcf' and n is not None and rowdef['border'] and rowdef['border']['cf'] is None:
            rowdef['border']['cf'] = n
        elif w == 'brdrw' and n is not None and rowdef['border'] and not rowdef['border'].get('wset'):
            rowdef['border']['w'] = n / 20.0; rowdef['border']['wset'] = True
        elif w == 'clwWidth' and n is not None: pending_cw[0] = n / 20.0
        elif w == 'cellx' and n is not None:
            rowdef['cx'].append(n / 20.0); rowdef['cw'].append(pending_cw[0]); pending_cw[0] = None
        elif w == 'cell':
            flush_bytes()
            ps['intbl'] = True; end_para()
            row_cells.append(dict(paras=list(cell_paras))); cell_paras.clear()
        elif w == 'row':
            cw = []
            prev = 0.0
            for k, c_ in enumerate(rowdef['cw']):
                x = rowdef['cx'][k]
                cw.append(c_ if c_ else x - prev); prev = x
            for k, cell in enumerate(row_cells):
                cell['w'] = cw[k] if k < len(cw) else (cw[-1] if cw else 40.0)
            b = rowdef['border']
            if b:
                ci = b['cf']
                b = (colors[ci] if ci is not None and 0 <= ci < len(colors) else None, b['w'])
            blocks.append(('row', dict(cells=list(row_cells), left=rowdef['left'], border=b)))
            row_cells = []; ps['intbl'] = False
    if cur:
        end_para()
    return blocks

def _pdf_font(f):
    return ('Helvetica-BoldOblique' if f['b'] and f['i'] else 'Helvetica-Bold' if f['b']
            else 'Helvetica-Oblique' if f['i'] else 'Helvetica')

def _latin(t):
    return t.encode('cp1252', 'replace').decode('cp1252')       # Helvetica estándar = WinAnsi

def layout_para(p, width):
    """Parte un párrafo en líneas. Cada línea = {'segs': [(texto, fmt, ancho)], 'w', 'h'}."""
    import re
    from reportlab.pdfbase.pdfmetrics import stringWidth
    words = []                       # (texto, fmt, ancho)
    for txt, f in p['runs']:
        for tok in re.findall(r'\s+|\S+', _latin(txt).replace('\u00a0', ' ')):
            words.append((tok, f, stringWidth(tok, _pdf_font(f), f['size'])))
    lines, line, lw = [], [], 0.0
    for tok, f, w in words:
        if tok == '\n':
            lines.append(line); line, lw = [], 0.0; continue
        if tok.isspace():
            line.append((tok, f, w)); lw += w; continue
        if line and lw + w > width + 1e-6:
            while line and line[-1][0].isspace():
                line.pop()
            lines.append(line); line, lw = [], 0.0
        line.append((tok, f, w)); lw += w
    lines.append(line)
    out = []
    for ln in lines:
        while ln and ln[-1][0].isspace():
            ln = ln[:-1]
        size = max([f['size'] for _, f, _ in ln] or [p['fs']])
        out.append(dict(segs=ln, w=sum(w for _, _, w in ln), h=LINE_HEIGHT * size, size=size))
    return out

def draw_text_item(c, it):
    """Dibuja un cuadro de texto RTF (con tablas) dentro de su marco, en coordenadas del lienzo."""
    from reportlab.lib.colors import Color
    blocks = parse_rtf(it['rtf'])
    if not blocks:
        return
    x, y, w, h = it['frame']
    a, b, cc, d, _, _ = it['tr']
    cx, cy = it['center'] or (x + w / 2, y + h / 2)

    def rgb(col):
        r, g, b_ = col if col else (0.0, 0.0, 0.0)
        return map_rgb(r, g, b_)

    c.saveState()
    try:
        c.setFillAlpha(it.get('alpha', 1.0)); c.setStrokeAlpha(it.get('alpha', 1.0))
    except Exception:
        pass
    c.translate(cx, -cy)
    c.transform(a, -b, -cc, d, 0, 0)
    ytop = h / 2                     # origen local: esquina superior izquierda del marco = (-w/2, h/2)
    X0 = -w / 2 + TEXT_INSET
    cursor = [TEXT_INSET]            # distancia desde el borde superior

    def draw_lines(lines, left, avail, top, align):
        yy = top
        for ln in lines:
            base = ytop - (yy + 0.77 * ln['h'])
            off = {'l': 0.0, 'c': (avail - ln['w']) / 2, 'r': avail - ln['w']}[align]
            px = left + off
            for tok, f, tw in ln['segs']:
                col = rgb(f['color'])
                c.setFillColor(Color(col[0], col[1], col[2])); c.setStrokeColor(Color(col[0], col[1], col[2]))
                c.setFont(_pdf_font(f), f['size'])
                c.drawString(px, base, tok)
                if f['u']:
                    c.setLineWidth(f['size'] * 0.06); c.line(px, base - f['size'] * 0.12, px + tw, base - f['size'] * 0.12)
                px += tw
            yy += ln['h']
        return yy

    for kind, blk in blocks:
        if kind == 'p':
            cursor[0] += blk['sb']
            lines = layout_para(blk, w - 2 * TEXT_INSET)
            cursor[0] = draw_lines(lines, X0, w - 2 * TEXT_INSET, cursor[0], blk['align']) + blk['sa']
        else:
            cells = blk['cells']
            laid, rowh = [], 0.0
            for cell in cells:
                hh, parts = 0.0, []
                for p in cell['paras']:
                    hh += p['sb']
                    ls = layout_para(p, max(cell['w'] - 2 * CELL_PAD, 1.0))
                    parts.append((p, ls, hh)); hh += sum(l['h'] for l in ls) + p['sa']
                laid.append(parts); rowh = max(rowh, hh)
            left = X0 + blk['left']
            xx = left
            bd = blk['border']
            for cell, parts in zip(cells, laid):
                if bd:
                    c.setStrokeColor(Color(*rgb(bd[0]))); c.setLineWidth(max(bd[1], 0.3))
                    c.rect(xx, ytop - (cursor[0] + rowh), cell['w'], rowh, stroke=1, fill=0)
                for p, ls, off in parts:
                    draw_lines(ls, xx + CELL_PAD, cell['w'] - 2 * CELL_PAD, cursor[0] + off, p['align'])
                xx += cell['w']
            cursor[0] += rowh
    c.restoreState()

_IMG_CACHE = {}

def load_image(path):
    """Abre una imagen adjunta (PNG/JPEG/HEIC...) como PIL RGBA. None si no se puede leer."""
    if path in _IMG_CACHE:
        return _IMG_CACHE[path]
    from PIL import Image
    im = None
    try:
        try:
            im = Image.open(path); im.load()
        except Exception:
            im = None
            if path.lower().endswith(('.heic', '.heif')):
                im = _open_heic(path)
        if im is not None:
            im = im.convert('RGBA')
    except Exception:
        im = None
    _IMG_CACHE[path] = im
    return im

def _open_heic(path):
    import subprocess, shutil
    from PIL import Image
    try:
        import pillow_heif; pillow_heif.register_heif_opener()
        return Image.open(path)
    except Exception:
        pass
    tmp = os.path.join(tempfile.mkdtemp(prefix='heic_'), 'o.png')
    cmds = []
    if shutil.which('sips'):
        cmds.append(['sips', '-s', 'format', 'png', path, '--out', tmp])      # macOS
    if shutil.which('heif-convert'):
        cmds.append(['heif-convert', path, tmp])                              # Linux (libheif-examples)
    if shutil.which('magick'):
        cmds.append(['magick', path, tmp])
    elif shutil.which('convert'):
        cmds.append(['convert', path, tmp])
    if shutil.which('ffmpeg'):
        cmds.append(['ffmpeg', '-loglevel', 'error', '-y', '-i', path, tmp])
    for cmd in cmds:
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            if os.path.isfile(tmp):
                return Image.open(tmp)
        except Exception:
            continue
    return None

def draw_image_item(c, it, root, H, ox, oy):
    from reportlab.lib.utils import ImageReader
    im = load_image(next((q for q in (os.path.join(root, d, it['image']) for d in ('attachments', 'File')) if os.path.isfile(q)),
                         os.path.join(root, 'attachments', it['image'])))
    x, y, w, h = it['frame']
    if im is None:
        print("  aviso: no puedo leer la imagen %s (se omite)" % it['image'], file=sys.stderr)
        return
    a, b, cc, d, _, _ = it['tr']
    cx, cy = it['center'] or (x + w / 2, y + h / 2)
    c.saveState()
    try:
        c.setFillAlpha(it.get('alpha', 1.0))
    except Exception:
        pass
    # centro del elemento y transformación (rotación/escala) alrededor de él; eje y invertido (y hacia arriba = -y)
    c.translate(cx - ox, H - (cy - oy))
    c.transform(a, -b, -cc, d, 0, 0)
    c.drawImage(ImageReader(im), -w / 2, -h / 2, w, h, mask='auto')
    c.restoreState()

def draw_link_card(c, it):
    """Tarjeta de enlace (ZTYPE 13): el icono guardado es un favicon de 16 px, así que no se estira; se dibuja
       una tarjeta redondeada con el título (hasta 2 líneas) y el dominio."""
    from reportlab.lib.colors import Color
    from reportlab.pdfbase.pdfmetrics import stringWidth
    x, y, w, h = it['frame']
    a, b, cc, d, _, _ = it['tr']
    cx, cy = it['center'] or (x + w / 2, y + h / 2)
    c.saveState()
    c.translate(cx, -cy); c.transform(a, -b, -cc, d, 0, 0)
    r = min(it.get('radius') or 14.0, w / 2, h / 2)
    c.setFillColor(Color(*map_rgb(0.95, 0.95, 0.95))); c.setStrokeColor(Color(*map_rgb(0.75, 0.75, 0.75))); c.setLineWidth(1)
    c.roundRect(-w / 2, -h / 2, w, h, r, stroke=1, fill=1)
    fs = max(6.0, min(16.0, h * 0.16)); pad = min(14.0, w * 0.06)
    words = _latin(it.get('title') or it.get('url') or '').split()
    lines, cur = [], ''
    for wd in words:
        t = (cur + ' ' + wd).strip()
        if stringWidth(t, 'Helvetica-Bold', fs) <= w - 2 * pad or not cur:
            cur = t
        else:
            lines.append(cur); cur = wd
    lines.append(cur)
    if len(lines) > 2:
        lines = lines[:2]
        while lines[1] and stringWidth(lines[1] + '...', 'Helvetica-Bold', fs) > w - 2 * pad:
            lines[1] = lines[1][:-1]
        lines[1] += '...'
    col = map_rgb(0.1, 0.1, 0.1); c.setFillColor(Color(*col)); c.setFont('Helvetica-Bold', fs)
    yy = h / 2 - pad - fs
    for ln in lines:
        c.drawString(-w / 2 + pad, yy, ln); yy -= fs * 1.25
    m = _re.match(r'https?://([^/]+)', it.get('url') or '')
    if m:
        c.setFont('Helvetica', fs * 0.8); c.setFillColor(Color(*map_rgb(0.4, 0.4, 0.4)))
        c.drawString(-w / 2 + pad, -h / 2 + pad, m.group(1)[:60])
    c.restoreState()

def draw_item(c, it, H, ox, oy):
    from reportlab.lib.colors import Color
    x, y, w, h = it['frame']
    X, Y = x - ox, H - (y - oy) - h
    if it.get('line'):                     # línea (continua o discontinua), sin relleno
        if not it['stroke']:
            return
        r, g, b, a = it['stroke']; r, g, b = map_rgb(r, g, b)
        c.saveState(); c.setStrokeColor(Color(r, g, b, alpha=a)); c.setLineWidth(it['lw'])
        c.setLineCap({'round': 1, 'square': 2}.get(it.get('cap'), 0))
        if it.get('dash') and it['dash'][0] and it['dash'][1]:
            c.setDash(it['dash'][0], it['dash'][1])
        (x1, y1), (x2, y2) = it['line']['ZSTARTPOINT'], it['line']['ZENDPOINT']
        c.line(x1 - ox, H - (y1 - oy), x2 - ox, H - (y2 - oy)); c.restoreState(); return
    if it['fill']:
        r, g, b, a = it['fill']; r, g, b = map_rgb(r, g, b); c.setFillColor(Color(r, g, b, alpha=a))
    if it['stroke']:
        r, g, b, a = it['stroke']; r, g, b = map_rgb(r, g, b); c.setStrokeColor(Color(r, g, b, alpha=a)); c.setLineWidth(it['lw'])
    c.roundRect(X, Y, w, h, min(it['radius'], w / 2, h / 2),
                stroke=1 if it['stroke'] and it['lw'] else 0, fill=1 if it['fill'] else 0)

# ---------------------------------------------------------------- paquete
_PKG_CACHE = {}

def open_package(src):
    if src in _PKG_CACHE:
        return _PKG_CACHE[src]
    r = _open_package(src)
    _PKG_CACHE[src] = r
    return r

def _open_package(src):
    if os.path.isdir(src):
        root = src
    else:
        tmp = tempfile.mkdtemp(prefix='prodrafts_')
        zipfile.ZipFile(src).extractall(tmp)
        root = tmp
    cand = [p for p in glob.glob(os.path.join(root, '**', 'pageIndex.plist'), recursive=True)
            if '__MACOSX' not in p]
    if not cand:
        old = [p for p in glob.glob(os.path.join(root, '**', 'draw.data'), recursive=True) if '__MACOSX' not in p]
        if old:                       # formato antiguo: una sola página (lienzo infinito) en draw.data
            return os.path.dirname(old[0])
        raise SystemExit("No encuentro pageIndex.plist ni draw.data: ¿es un .prodrafts?")
    return os.path.dirname(cand[0])

def hex2rgb(h, default=(0.2, 0.2, 0.2)):
    try:
        h = h.lstrip('#'); return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except Exception:
        return default

def _lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]

def _pdf_page_info(bgpdf, idx):
    """(¿la página del PDF tiene contenido?, color del relleno que cubre casi toda la página o None)."""
    import re
    from pypdf import PdfReader
    try:
        pg = PdfReader(bgpdf).pages[idx]
        cont = pg.get_contents()
        data = cont.get_data().decode('latin-1') if cont is not None else ''
        W, H = float(pg.mediabox.width), float(pg.mediabox.height)
    except Exception:
        return True, None
    if not data.strip():
        return False, None                       # página vacía: papel transparente
    num = r'(-?[\d.]+)'
    sp = r'\s+'
    col = None
    # alternativas: color RGB | gris | rectángulo 're' relleno | rectángulo como trazado 'm l l l h f' relleno
    rx = (num + sp + num + sp + num + sp + r'(?:rg|sc|scn)\b|' + num + sp + r'(?:g)\b|'
          + num + sp + num + sp + num + sp + num + sp + r're\s+(?:f\*?|B\*?)\b|'
          + num + sp + num + sp + r'm' + sp + num + sp + num + sp + r'l' + sp + num + sp + num + sp + r'l' + sp
          + num + sp + num + sp + r'l' + sp + r'h' + sp + r'(?:f\*?|B\*?)\b')
    for m in re.finditer(rx, data):
        g = m.groups()
        if g[0] is not None:
            col = (float(g[0]), float(g[1]), float(g[2]))
        elif g[3] is not None:
            v = float(g[3]); col = (v, v, v)
        else:
            if g[4] is not None:
                w, h = abs(float(g[6])), abs(float(g[7]))
            else:
                xs_ = [float(g[k]) for k in range(8, 16, 2)]; ys_ = [float(g[k]) for k in range(9, 16, 2)]
                w, h = max(xs_) - min(xs_), max(ys_) - min(ys_)
            if col and w >= 0.9 * W and h >= 0.9 * H:
                return True, col
    return True, None

def _raster_is_dark(bgpdf, idx):
    """Rasteriza la página (pdftoppm, sobre blanco) y mide el brillo medio. None si no se puede."""
    import subprocess, shutil
    if not shutil.which('pdftoppm'):
        return None
    try:
        tmp = os.path.join(tempfile.mkdtemp(prefix='pdbg_'), 'bg')
        subprocess.run(['pdftoppm', '-r', '8', '-f', str(idx + 1), '-l', str(idx + 1), '-gray', '-singlefile',
                        bgpdf, tmp], check=True, capture_output=True)
        px = open(tmp + '.pgm', 'rb').read().split(b'\n', 3)[3]      # P5 / w h / 255 / pixeles
        return sum(px) / len(px) < 110
    except Exception:
        return None

def bg_is_dark(bgpdf, idx, ext_hex):
    """¿El papel de la página es oscuro?  Orden de decisión:
         1. relleno de página completa del PDF de fondo (es lo que realmente se ve);
         2. PDF vacío/transparente -> color de papel que Pro Drafts guarda en la ficha de la página
            (extensionBackgroundColorHex); sin él, el papel es blanco;
         3. PDF con contenido pero sin relleno (p.ej. una página escaneada como imagen) -> brillo medio rasterizado.
       Un PDF vacío NO se rasteriza: algunos visores lo pintan en negro y la página saldría marcada como oscura."""
    paper = hex2rgb(ext_hex, None) if ext_hex else None
    if not os.path.isfile(bgpdf):
        return paper is not None and _lum(paper) < 0.45
    has_content, fill = _pdf_page_info(bgpdf, idx)
    if fill is not None:
        return _lum(fill) < 0.45
    if not has_content:
        return paper is not None and _lum(paper) < 0.45
    if paper is not None and _lum(paper) < 0.45:
        return True                              # PDF transparente (solo texto) sobre papel oscuro
    r = _raster_is_dark(bgpdf, idx)
    return bool(r)


# ---------------------------------------------------------------- nombre y carpetas desde la biblioteca de Pro Drafts
import re as _re
_UUID_RE = _re.compile(r'[0-9A-Fa-f]{8}-(?:[0-9A-Fa-f]{4}-){3}[0-9A-Fa-f]{12}')
DEFAULT_DB = os.path.expanduser('~/Library/Containers/emmo.prodrafts/Data/Library/Application Support/Prodrafts/MainDrawBoardFile.sqlite')

def note_uuid(src):
    m = _UUID_RE.search(os.path.basename(os.path.normpath(src)))
    return m.group(0).upper() if m else None

def safe_name(s):
    s = _re.sub(r'[\\/:\x00-\x1f]', '-', s or '').strip().lstrip('.').strip()
    return s

_LIB_CACHE = {}

def _load_library(db):
    """Copia temporal de la biblioteca (+ -wal/-shm), leída una sola vez: ({pk: (nombre, padre)}, {uuid_hex: pk}) o None."""
    import sqlite3, shutil
    if db in _LIB_CACHE:
        return _LIB_CACHE[db]
    res = None
    if os.path.isfile(db):
        tmp = tempfile.mkdtemp(prefix='pdlib_')
        cp = os.path.join(tmp, 'lib.sqlite')
        try:
            for ext in ('', '-wal', '-shm'):
                if os.path.isfile(db + ext):
                    shutil.copy2(db + ext, cp + ext)
            con = sqlite3.connect(cp)
            rows = {r[0]: (r[1], r[2]) for r in con.execute('select Z_PK, ZNAME, ZFATHERFILE from ZBOARDFILE')}
            ids = {bytes(r[1]).hex(): r[0] for r in con.execute('select Z_PK, ZUUID from ZBOARDFILE where ZUUID is not null')}
            con.close()
            res = (rows, ids)
        except Exception as e:
            print("aviso: no puedo leer la biblioteca de Pro Drafts (%s)" % e, file=sys.stderr)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    _LIB_CACHE[db] = res
    return res

def library_path(uuid_str, db=None):
    """(lista de carpetas de fuera a dentro, nombre de la nota) según la biblioteca, o None si no se encuentra.
       Trabaja sobre una copia temporal de la base de datos: el original no se toca."""
    lib = _load_library(db or DEFAULT_DB) if uuid_str else None
    if not lib:
        return None
    rows, ids = lib
    pk0 = ids.get(uuid_str.replace('-', '').lower())
    if pk0 is None or not safe_name(rows[pk0][0]):
        return None
    name = safe_name(rows[pk0][0])
    folders, seen, pk = [], {pk0}, rows[pk0][1]
    while pk and pk in rows and pk not in seen:
        seen.add(pk)
        nm, pk = rows[pk]
        if safe_name(nm):
            folders.append(safe_name(nm))
    return folders[::-1], name

def default_out(src, out_dir, db=None, ext='.pdf'):
    uid = note_uuid(src)
    info = library_path(uid, db)
    if info:
        folders, name = info
        return os.path.join(out_dir or '.', *folders, name + ext)
    base = os.path.basename(os.path.normpath(src))
    for suf in ('.zip', '.prodrafts', '_prodrafts'):
        if base.lower().endswith(suf):
            base = base[:-len(suf)]
    print("aviso: no encuentro la nota en la biblioteca de Pro Drafts (--db); uso '%s%s'" % (uid or base, ext), file=sys.stderr)
    return os.path.join(out_dir or '.', (uid or base) + ext)

# ---------------------------------------------------------------- lienzo SVG (notas de lienzo infinito)
def _mat_mul(m1, m2):
    """Aplica m1 y luego m2 (convención PDF/SVG: x' = a x + c y + e, y' = b x + d y + f)."""
    a1, b1, c1, d1, e1, f1 = m1; a2, b2, c2, d2, e2, f2 = m2
    return (a1 * a2 + b1 * c2, a1 * b2 + b1 * d2, c1 * a2 + d1 * c2, c1 * b2 + d1 * d2,
            e1 * a2 + f1 * c2 + e2, e1 * b2 + f1 * d2 + f2)

def _n(v):
    t = ('%.2f' % v).rstrip('0').rstrip('.')
    return '0' if t in ('-0', '') else t

def _hex(rgb):
    return '#%02x%02x%02x' % tuple(max(0, min(255, int(round(v * 255)))) for v in rgb)

class _SvgPath:
    def __init__(self): self.ops = []
    def moveTo(self, x, y): self.ops.append(('M', x, y))
    def lineTo(self, x, y): self.ops.append(('L', x, y))
    def curveTo(self, x1, y1, x2, y2, x3, y3): self.ops.append(('C', x1, y1, x2, y2, x3, y3))
    def close(self): self.ops.append(('Z',))
    def rect(self, *a): pass                      # (solo se usa para el recorte de página; en SVG no hace falta)

class SvgCanvas:
    """Imita las llamadas de reportlab.Canvas que usa el dibujo de trazos, formas, texto e imágenes y las escribe como SVG.
       Las figuras se escriben ya con coordenadas de página (sin números enormes del lienzo); texto e imágenes llevan matriz."""
    def __init__(self, W, H):
        self.W, self.H = W, H; self.out = []; self.stack = []
        self.st = dict(ctm=(1, 0, 0, 1, 0, 0), fill=(0, 0, 0), stroke=(0, 0, 0), fa=1.0, sa=1.0, lw=1.0, cap=0, join=0,
                       dash=None, font=('Helvetica', 12))
    # --- estado
    def setPageCompression(self, *a): pass
    def showPage(self): pass
    def save(self): pass
    def clipPath(self, *a, **k): pass
    def beginPath(self): return _SvgPath()
    def saveState(self): self.stack.append(dict(self.st))
    def restoreState(self): self.st = self.stack.pop()
    def transform(self, a, b, c, d, e, f): self.st['ctm'] = _mat_mul((a, b, c, d, e, f), self.st['ctm'])
    def translate(self, x, y): self.transform(1, 0, 0, 1, x, y)
    def scale(self, x, y): self.transform(x, 0, 0, y, 0, 0)
    def setFillColor(self, col):
        self.st['fill'] = (col.red, col.green, col.blue)
        if getattr(col, 'alpha', None) is not None: self.st['fa'] = col.alpha
    def setStrokeColor(self, col):
        self.st['stroke'] = (col.red, col.green, col.blue)
        if getattr(col, 'alpha', None) is not None: self.st['sa'] = col.alpha
    def setFillColorRGB(self, r, g, b, alpha=None):
        self.st['fill'] = (r, g, b)
        if alpha is not None: self.st['fa'] = alpha
    def setFillAlpha(self, a): self.st['fa'] = a
    def setStrokeAlpha(self, a): self.st['sa'] = a
    def setLineWidth(self, w): self.st['lw'] = w
    def setLineCap(self, v): self.st['cap'] = v
    def setLineJoin(self, v): self.st['join'] = v
    def setDash(self, on=None, off=None):
        self.st['dash'] = None if not on else ((on, off if off is not None else on) if not isinstance(on, (list, tuple)) else tuple(on))
    def setFont(self, name, size): self.st['font'] = (name, size)
    # --- geometría
    def _k(self):
        a, b, c, d = self.st['ctm'][:4]
        return math.sqrt(abs(a * d - b * c)) or 1.0
    def _pt(self, x, y):
        a, b, c, d, e, f = self.st['ctm']
        return a * x + c * y + e, self.H - (b * x + d * y + f)
    def _paint(self, stroke, fill, evenodd=False):
        s_ = self.st; k = self._k(); at = []
        if fill:
            at.append('fill="%s"' % _hex(s_['fill']))
            if s_['fa'] < 0.999: at.append('fill-opacity="%s"' % _n(s_['fa']) if s_['fa'] > 0.01 else 'fill-opacity="%.3f"' % s_['fa'])
            if evenodd: at.append('fill-rule="evenodd"')
        else:
            at.append('fill="none"')
        if stroke:
            at.append('stroke="%s" stroke-width="%s"' % (_hex(s_['stroke']), _n(max(s_['lw'] * k, 0.01))))
            if s_['sa'] < 0.999: at.append('stroke-opacity="%.3f"' % s_['sa'])
            at.append('stroke-linecap="%s" stroke-linejoin="%s"' % (('butt', 'round', 'square')[s_['cap'] if s_['cap'] in (0, 1, 2) else 0],
                                                                     ('miter', 'round', 'bevel')[s_['join'] if s_['join'] in (0, 1, 2) else 0]))
            if s_['dash']:
                at.append('stroke-dasharray="%s"' % ' '.join(_n(v * k) for v in s_['dash']))
        return ' '.join(at)
    def _emit_path(self, ops, stroke, fill, evenodd=False):
        if not (stroke or fill) or not ops: return
        d = []
        for op in ops:
            if op[0] == 'Z': d.append('Z'); continue
            pts = []
            for i in range(1, len(op), 2):
                X, Y = self._pt(op[i], op[i + 1]); pts.append('%s %s' % (_n(X), _n(Y)))
            d.append(op[0] + ' '.join(pts))
        self.out.append('<path d="%s" %s/>' % (''.join(d), self._paint(stroke, fill, evenodd)))
    def drawPath(self, path, stroke=1, fill=0, fillMode=None):
        self._emit_path(path.ops, stroke, fill, evenodd=(fillMode == 0))
    def line(self, x1, y1, x2, y2): self._emit_path([('M', x1, y1), ('L', x2, y2)], 1, 0)
    def rect(self, x, y, w, h, stroke=1, fill=0):
        self._emit_path([('M', x, y), ('L', x + w, y), ('L', x + w, y + h), ('L', x, y + h), ('Z',)], stroke, fill)
    def roundRect(self, x, y, w, h, r, stroke=1, fill=0):
        r = max(0.0, min(r, w / 2, h / 2)); q = r * (1 - 0.5523)
        o = [('M', x + r, y), ('L', x + w - r, y), ('C', x + w - q, y, x + w, y + q, x + w, y + r), ('L', x + w, y + h - r),
             ('C', x + w, y + h - q, x + w - q, y + h, x + w - r, y + h), ('L', x + r, y + h),
             ('C', x + q, y + h, x, y + h - q, x, y + h - r), ('L', x, y + r), ('C', x, y + q, x + q, y, x + r, y), ('Z',)]
        self._emit_path(o, stroke, fill)
    def circle(self, cx, cy, r, stroke=1, fill=0):
        X, Y = self._pt(cx, cy)
        self.out.append('<circle cx="%s" cy="%s" r="%s" %s/>' % (_n(X), _n(Y), _n(r * self._k()), self._paint(stroke, fill)))
    # --- texto e imágenes (con matriz; el eje y se vuelve a girar para que salgan derechos)
    def _matrix_flipped(self):
        a, b, c, d, e, f = _mat_mul(self.st['ctm'], (1, 0, 0, -1, 0, self.H))      # usuario(y arriba) -> página SVG(y abajo)
        return '%s %s %s %s %s %s' % tuple(_n(v) if i > 3 else '%.5f' % v for i, v in enumerate((a, b, -c, -d, e, f)))
    def drawString(self, x, y, text):
        name, size = self.st['font']
        fam = 'Helvetica, Arial, sans-serif'
        extra = (' font-weight="bold"' if 'Bold' in name else '') + (' font-style="italic"' if 'Oblique' in name or 'Italic' in name else '')
        t = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        op = '' if self.st['fa'] >= 0.999 else ' fill-opacity="%.3f"' % self.st['fa']
        self.out.append('<text transform="matrix(%s)" x="%s" y="%s" font-family="%s" font-size="%s"%s fill="%s"%s xml:space="preserve">%s</text>'
                        % (self._matrix_flipped(), _n(x), _n(-y), fam, _n(size), extra, _hex(self.st['fill']), op, t))
    def drawImage(self, img, x, y, w, h, mask=None):
        import base64
        im = getattr(img, '_image', img)
        buf = io.BytesIO()
        if im.mode == 'RGBA' and im.getchannel('A').getextrema()[0] < 255:
            im.save(buf, 'PNG'); mime = 'image/png'
        else:
            im.convert('RGB').save(buf, 'JPEG', quality=92); mime = 'image/jpeg'
        op = '' if self.st['fa'] >= 0.999 else ' opacity="%.3f"' % self.st['fa']
        self.out.append('<image transform="matrix(%s)" x="%s" y="%s" width="%s" height="%s" preserveAspectRatio="none"%s xlink:href="data:%s;base64,%s"/>'
                        % (self._matrix_flipped(), _n(x), _n(-(y + h)), _n(w), _n(h), op, mime, base64.b64encode(buf.getvalue()).decode()))
    def background(self, rgb=(1, 1, 1)):
        self.out.append('<rect id="fondo" width="%s" height="%s" fill="%s"/>' % (_n(self.W), _n(self.H), _hex(rgb)))
    def tostring(self):
        return ('<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                'width="%spt" height="%spt" viewBox="0 0 %s %s">\n%s\n</svg>\n' % (_n(self.W), _n(self.H), _n(self.W), _n(self.H), '\n'.join(self.out)))

def note_ext(src):
    """'.svg' para las notas de lienzo infinito (formato antiguo, sin PDF de fondo), '.pdf' para el resto."""
    try:
        return '.pdf' if os.path.isfile(os.path.join(open_package(src), 'pageIndex.plist')) else '.svg'
    except (Exception, SystemExit):
        return '.pdf'

def legacy_board_hex(root):
    """Color de papel (boardColor) del formato antiguo, '#RRGGBB'; blanco si no se puede leer."""
    try:
        o = plistlib.load(open(os.path.join(root, 'draft.data.model'), 'rb'))['$objects']
        c = o[o[1]['boardColor'].data]
        return '#%02X%02X%02X' % tuple(int(round(c[k] * 255)) for k in ('UIRed', 'UIGreen', 'UIBlue'))
    except Exception:
        return '#FFFFFF'

def convert(src, out):
    """Devuelve el nº de páginas (PDF; las notas de lienzo infinito pueden salir como .svg). Cada página sale con el tamaño original del PDF de fondo."""
    global DARK_PAPER
    from reportlab.pdfgen import canvas as rl
    from pypdf import PdfReader, PdfWriter
    root = open_package(src)
    legacy = not os.path.isfile(os.path.join(root, 'pageIndex.plist'))
    if legacy:
        pages = [dict(uuid=None, sourceName='', sourceIndex=0, extensionBackgroundColorHex=legacy_board_hex(root))]
    else:
        pages = plistlib.load(open(os.path.join(root, 'pageIndex.plist'), 'rb'))
    as_svg = legacy and out.lower().endswith('.svg')
    if out.lower().endswith('.svg') and not legacy:
        raise SystemExit("Las notas con PDF de fondo solo se exportan a PDF (%s)" % out)
    writer = PdfWriter()
    for pn, pg in enumerate(pages, 1):
        uid = pg['uuid']
        bgpdf = os.path.join(root, 'attachments', pg.get('sourceName', ''))
        bgpage = PdfReader(bgpdf).pages[pg.get('sourceIndex', 0)] if os.path.isfile(bgpdf) else None
        W0 = float(bgpage.mediabox.width) if bgpage else 595.28
        H0 = float(bgpage.mediabox.height) if bgpage else 841.89
        dfile = os.path.join(root, 'draw.data') if legacy else os.path.join(root, 'drawings', uid + '.com.apple.drawing')
        strokes = parse_drawing(dfile) if os.path.isfile(dfile) else []
        strokes = [p for s_ in strokes for p in apply_mask(s_, HIDE_MASKED) if len(p['pts']) >= 1]
        items = board_items(root, uid, legacy)
        DARK_PAPER = bg_is_dark(bgpdf, pg.get('sourceIndex', 0), pg.get('extensionBackgroundColorHex', '#FFFFFF'))
        xs = [p[0] for s in strokes for p in s['pts']] + [v for it in items for v in (it['frame'][0], it['frame'][0] + it['frame'][2])]
        ys = [p[1] for s in strokes for p in s['pts']] + [v for it in items for v in (it['frame'][1], it['frame'][1] + it['frame'][3])]
        # La página del bloc es el PDF de fondo (tamaño original) y el lienzo se coloca a escala fija
        # desde la esquina superior izquierda: lo que no haya dibujado queda en blanco y lo que
        # caiga fuera de la página no existe en el documento (no se reduce ni se recentra nada).
        if legacy:
            # lienzo infinito sin PDF de fondo: la página es la caja que ocupa el contenido (+ margen)
            items = [it for it in items if it.get('image') or it.get('rtf') or it.get('line') or it.get('fill') or it.get('stroke')]
            xs = [p[0] for s in strokes for p in s['pts']] + [v for it in items for v in (it['frame'][0], it['frame'][0] + it['frame'][2])]
            ys = [p[1] for s in strokes for p in s['pts']] + [v for it in items for v in (it['frame'][1], it['frame'][1] + it['frame'][3])]
            M = 24.0
            if xs:
                ox, oy = min(xs) - M, min(ys) - M
                cw, ch = max(xs) - min(xs) + 2 * M, max(ys) - min(ys) + 2 * M
            else:
                ox = oy = 0.0; cw, ch = W0 / CANVAS_SCALE, H0 / CANVAS_SCALE
            sc = min(CANVAS_SCALE, 14000.0 / max(cw, ch))          # límite de tamaño de página PDF
            W0, H0, tx, ty = cw * sc, ch * sc, -ox * sc, -oy * sc
        else:
            sc, tx, ty = CANVAS_SCALE, 0.0, 0.0
        fuera = sum(1 for s_ in strokes if any(p[0] * sc + tx < -0.5 or p[1] * sc + ty < -0.5 or p[0] * sc + tx > W0 + 0.5 or p[1] * sc + ty > H0 + 0.5
                                                for p in s_['pts']))
        buf = io.BytesIO(); c = SvgCanvas(W0, H0) if as_svg else rl.Canvas(buf, pagesize=(W0, H0)); c.setPageCompression(1)
        if as_svg:
            c.background()
        paper = (1, 1, 1) if (DARK_PAPER and not as_svg) else None
        if paper:
            c.setFillColorRGB(*paper); c.rect(0, 0, W0, H0, stroke=0, fill=1)
        clip = c.beginPath(); clip.rect(0, 0, W0, H0); c.clipPath(clip, stroke=0, fill=0)
        c.saveState(); c.translate(tx, H0 - ty); c.scale(sc, sc)   # a partir de aquí: coordenadas del dibujo, y hacia arriba = -y
        for it in items:
            if it.get('type') == 13 and (it.get('title') or it.get('url')):
                draw_link_card(c, it)
            elif it.get('image'):
                draw_image_item(c, it, root, 0, 0, 0)
            else:
                draw_item(c, it, 0, 0, 0)            # fondo/borde del marco (si los tiene)
                if it.get('rtf'):
                    draw_text_item(c, it)
        er = (1.0, 1.0, 1.0)
        for s in strokes:
            draw_stroke(c, s, 0, 0, 0, er)
        c.restoreState(); c.showPage(); c.save()
        if as_svg:
            with open(out, 'w', encoding='utf8') as fh:
                fh.write(c.tostring())
            print("página 1: %d trazos, lienzo infinito -> SVG %.0fx%.0f pt%s" % (len(strokes), W0, H0, ", fondo oscuro→blanco" if DARK_PAPER else ""))
            return 1
        top = PdfReader(io.BytesIO(buf.getvalue())).pages[0]
        if bgpage is not None and not DARK_PAPER:      # el PDF original va debajo
            base = PdfWriter(); base.add_page(bgpage); b = base.pages[0]; b.merge_page(top); top = b
        writer.add_page(top)
        print("página %d: %d trazos%s, %.0fx%.0f pt%s" % (pn, len(strokes), ", fondo oscuro→blanco" if DARK_PAPER else "", W0, H0,
                                                       ", %d trazos fuera de la página (recortados)" % fuera if fuera else ""))
    writer.write(out)
    return len(pages)

# ---------------------------------------------------------------- detección de cambios
MANIFEST = '.prodrafts2pdf.json'      # en la carpeta de salida: {uuid: {'fp': huella, 'out': ruta relativa del PDF}}

def fingerprint(src):
    """Huella del contenido de la nota (+ ajustes y versión del script): si no cambia, el PDF sería idéntico.
       Se ignoran search/ y los .DS_Store."""
    import hashlib
    h = hashlib.sha1()
    h.update(repr((WIDTH_SCALE, CANVAS_SCALE, HIDE_MASKED)).encode())
    try:
        h.update(open(os.path.abspath(__file__), 'rb').read())
    except Exception:
        pass
    def feed(path):
        with open(path, 'rb') as f:
            for blk in iter(lambda: f.read(1 << 20), b''):
                h.update(blk)
    if os.path.isdir(src):
        for dp, dn, fn in os.walk(src):
            dn[:] = sorted(d for d in dn if d != 'search')
            for n in sorted(fn):
                if n == '.DS_Store':
                    continue
                full = os.path.join(dp, n)
                h.update(os.path.relpath(full, src).encode('utf8', 'replace')); feed(full)
    else:
        feed(src)
    return h.hexdigest()

def load_manifest(out_dir):
    import json
    try:
        return json.load(open(os.path.join(out_dir, MANIFEST), encoding='utf8'))
    except Exception:
        return {}

def save_manifest(out_dir, m):
    import json
    os.makedirs(out_dir, exist_ok=True)
    tmp = os.path.join(out_dir, MANIFEST + '.tmp')
    json.dump(m, open(tmp, 'w', encoding='utf8'), indent=1, ensure_ascii=False)
    os.replace(tmp, os.path.join(out_dir, MANIFEST))

def unchanged(m, key, fp, out, out_dir):
    e = m.get(key)
    return bool(e and e.get('fp') == fp and e.get('out') == os.path.relpath(out, out_dir) and os.path.isfile(out))

def is_batch_dir(src):
    """Carpeta con varios .prodrafts / .zip dentro (y que no es ella misma una nota)."""
    if not os.path.isdir(src) or os.path.normpath(src).endswith('.prodrafts'):
        return False
    if os.path.isfile(os.path.join(src, 'pageIndex.plist')):
        return False
    return any(n.endswith('.prodrafts') or n.lower().endswith('.zip') for n in os.listdir(src))

def convert_all(src, out_dir, db=None, skip_existing=False, force=False):
    notes = sorted(n for n in os.listdir(src) if (n.endswith('.prodrafts') or n.lower().endswith('.zip')) and not n.startswith('.'))
    ok, fail, skipped, orphan, renamed = 0, [], 0, 0, 0
    real_src, real_out = os.path.realpath(src), os.path.realpath(out_dir)
    if real_out == real_src or real_out.startswith(real_src + os.sep) or real_src.startswith(real_out + os.sep):
        sys.exit("--out-dir (%s) no puede estar dentro de la carpeta de origen ni contenerla" % out_dir)
    manifest = load_manifest(out_dir)
    used = set()                       # rutas ya asignadas en esta ejecución (sin distinguir mayúsculas, como macOS)
    for i, n in enumerate(notes, 1):
        path = os.path.join(src, n)
        uid = note_uuid(path)
        info = library_path(uid, db)
        ext = note_ext(path)
        if info:
            out = os.path.join(out_dir, *info[0], info[1] + ext)
        else:
            orphan += 1
            out = os.path.join(out_dir, '_sin_biblioteca', (uid or n) + ext)
        base, k = os.path.splitext(out)[0], 1
        while out.lower() in used:     # dos notas con el mismo nombre en la misma carpeta: no se pisan
            k += 1; out = '%s (%d)%s' % (base, k, ext)
        used.add(out.lower())
        if k > 1:
            renamed += 1
        print("[%d/%d] %s -> %s" % (i, len(notes), n, os.path.relpath(out, out_dir)))
        if skip_existing and os.path.isfile(out):
            skipped += 1; continue
        key = uid or n
        fp = fingerprint(path)
        if not force and unchanged(manifest, key, fp, out, out_dir):
            print("  sin cambios, no se vuelve a exportar"); skipped += 1; continue
        try:
            os.makedirs(os.path.dirname(out), exist_ok=True)
            convert(path, out); ok += 1
            manifest[key] = {'fp': fp, 'out': os.path.relpath(out, out_dir)}
            save_manifest(out_dir, manifest)
        except (Exception, SystemExit) as e:
            fail.append((n, str(e))); print("  ERROR en %s: %s" % (n, e), file=sys.stderr)
    print("\nHecho: %d exportados, %d omitidos (sin cambios), %d fallos, %d sin nombre en la biblioteca (en _sin_biblioteca/), %d renombrados por nombre repetido" % (ok, skipped, len(fail), orphan, renamed))
    for n, e in fail:
        print("  fallo: %s: %s" % (n, e), file=sys.stderr)

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('src')
    ap.add_argument('out', nargs='?', default=None, help='PDF de salida; si se omite, nombre y carpetas de la biblioteca de Pro Drafts')
    ap.add_argument('--out-dir', default='.', help='carpeta raíz donde crear el PDF cuando no se da salida (por defecto: la actual)')
    ap.add_argument('--force', action='store_true', help='re-exportar aunque la nota no haya cambiado')
    ap.add_argument('--skip-existing', action='store_true', help='(modo carpeta) no rehacer los PDF que ya existen')
    ap.add_argument('--db', default=None, help='MainDrawBoardFile.sqlite de Pro Drafts (por defecto: el del contenedor de macOS)')
    ap.add_argument('--width', type=float, default=None, help='factor de grosor (por defecto %.2f)' % WIDTH_SCALE)
    ap.add_argument('--canvas-scale', type=float, default=None, help='escala lienzo->página (por defecto %.2f)' % CANVAS_SCALE)
    ap.add_argument('--hide-masked', action='store_true', help='ocultar por completo los trazos borrados que tengan algún rango (por defecto solo se quitan los tramos borrados)')
    a = ap.parse_args()
    if a.width: WIDTH_SCALE = a.width
    if a.canvas_scale: CANVAS_SCALE = a.canvas_scale
    HIDE_MASKED = a.hide_masked
    faltan = []
    for mod, pkg in (('reportlab', 'reportlab'), ('pypdf', 'pypdf'), ('PIL', 'pillow')):
        try:
            __import__(mod)
        except ImportError:
            faltan.append(pkg)
    if faltan:
        sys.exit("Faltan dependencias para %s. Instálalas con:\n    %s -m pip install %s" % (sys.executable, sys.executable, ' '.join(faltan)))
    if is_batch_dir(a.src):
        if a.out:
            sys.exit("En modo carpeta no se da fichero de salida: usa --out-dir")
        convert_all(a.src, a.out_dir, a.db, a.skip_existing, a.force); sys.exit(0)
    out = a.out or default_out(a.src, a.out_dir, a.db, note_ext(a.src))
    track = not a.out                      # con salida explícita se exporta siempre
    if track:
        man, fp, key = load_manifest(a.out_dir), fingerprint(a.src), note_uuid(a.src) or os.path.basename(a.src)
        if not a.force and unchanged(man, key, fp, out, a.out_dir):
            print("Sin cambios, no se vuelve a exportar: %s" % out); sys.exit(0)
    if os.path.dirname(out):
        os.makedirs(os.path.dirname(out), exist_ok=True)
    convert(a.src, out)
    if track:
        man[key] = {'fp': fp, 'out': os.path.relpath(out, a.out_dir)}; save_manifest(a.out_dir, man)
    print("Salida: %s" % out)
