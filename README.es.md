# prodrafts2pdf

**Convierte las notas de [Pro Drafts](https://prodrafts.app) a PDF y SVG vectoriales, conservando los nombres y la estructura de carpetas que tienes en la app.**

[English](README.md)

Pro Drafts guarda cada nota como un paquete opaco `UUID.prodrafts` (o, si exportas por WebDAV, un paquete con el nombre
del documento). `prodrafts2pdf` lee ese paquete y reconstruye la nota como un archivo estándar: los trazos del Apple Pencil
pasan a ser trazados vectoriales reales (zoom ilimitado, editables en Illustrator, Affinity o Inkscape), el PDF de fondo
original se conserva intacto y el resultado se guarda en el mismo árbol de carpetas y con el mismo nombre que ves en la app.

> **Proyecto no oficial.** No está afiliado ni respaldado por Pro Drafts ni por su desarrollador. El formato `.prodrafts`
> no está documentado y se ha averiguado por ingeniería inversa a partir de notas reales, así que una actualización
> futura de la app puede romperlo. La herramienta nunca modifica tus notas, pero conserva tus propias copias de seguridad.

## Contenido

- [Características](#características)
- [Requisitos](#requisitos)
- [Instalación](#instalación)
- [Formas de obtener tus notas](#formas-de-obtener-tus-notas)
- [Inicio rápido](#inicio-rápido)
- [¿Dónde están mis notas?](#dónde-están-mis-notas)
- [Referencia de línea de comandos](#referencia-de-línea-de-comandos)
- [Cómo funciona](#cómo-funciona)
- [Contenido admitido](#contenido-admitido)
- [Plataformas](#plataformas)
- [Limitaciones](#limitaciones)
- [Solución de problemas](#solución-de-problemas)
- [Contribuir](#contribuir)
- [Licencia](#licencia)

## Características

- **Salida vectorial.** Trazos, formas y texto son objetos vectoriales, no imágenes. Los PDF conservan el PDF de fondo original de cada página.
- **Dos formatos de salida, según la nota.** Las notas con fondo de página salen en **PDF**. Las notas de lienzo infinito
  (el formato antiguo de Pro Drafts) salen en **SVG**.
- **Una nota o toda la biblioteca.** Pasa un paquete `.prodrafts`, un `.zip` exportado o la carpeta que contiene
  todas tus notas.
- **Nombres y carpetas reales.** Busca el UUID de cada nota en la base de datos de la biblioteca de Pro Drafts y recrea el árbol de carpetas
  (`Asignatura A/Ejercicios/Tema 1 - Ejercicios.pdf`) dentro del directorio de salida.
- **También con exports por WebDAV.** Las notas exportadas por WebDAV se llaman como el documento y no llevan UUID en el
  nombre del archivo, pero incluyen un `prodrafts-backup.json` con el UUID, el nombre y las carpetas. El script lo lee, de modo
  que el árbol se reconstruye incluso sin la base de datos de la biblioteca.
- **Solo lectura sobre tus datos.** Tus notas de iCloud solo se leen. La base de datos de la biblioteca se copia a un
  directorio temporal antes de consultarla.
- **Exportaciones incrementales.** Una huella del contenido de cada nota hace que las notas sin cambios se omitan en las siguientes ejecuciones.
- **Ejecuciones por lotes seguras.** Una nota rota no detiene el lote, los nombres duplicados nunca se sobrescriben y el
  directorio de salida no puede estar dentro de la carpeta de origen.
- **Renderizado fiel.** Trazos de grosor variable, marcadores translúcidos, trazos borrados y movidos, imágenes (incluido
  HEIC), cuadros de texto RTF con tablas, formas y líneas, tarjetas de enlace y páginas de papel oscuro.
- **Pocas dependencias.** Tres paquetes instalables con pip; todo lo demás es la biblioteca estándar.

## Requisitos

### Python

Python **3.8 o superior** (desarrollado y probado con 3.12).

### Paquetes de Python (obligatorios)

| Paquete | Mínimo | Para qué se usa |
|---|---|---|
| [`reportlab`](https://pypi.org/project/reportlab/) | 4.0 | Dibujar la capa vectorial y escribir las páginas PDF |
| [`pypdf`](https://pypi.org/project/pypdf/) | 4.0 | Leer los PDF de fondo y combinarlos bajo la capa vectorial |
| [`pillow`](https://pypi.org/project/pillow/) | 10.0 | Cargar y convertir las imágenes incrustadas |

Probado con reportlab 4.4, pypdf 5.9 y Pillow 12.1. Todo lo demás que importa el script forma parte de la biblioteca
estándar de Python (`sqlite3`, `plistlib`, `zipfile`, `hashlib`, `json`, ...).

### Opcionales

| Qué | Para qué | Cómo |
|---|---|---|
| [`pillow-heif`](https://pypi.org/project/pillow-heif/) | Decodificar fotos HEIC (imágenes del iPhone) incrustadas en las notas | `python -m pip install pillow-heif` |
| `pdftoppm` (Poppler) | Detectar papel oscuro en PDF de fondo escaneados que no tienen relleno de página. Sin él, ese caso concreto se trata como papel claro | macOS: `brew install poppler` · Debian/Ubuntu: `sudo apt install poppler-utils` · Windows: [builds de Poppler](https://github.com/oschwartz10612/poppler-windows) en el `PATH` |

Si `pillow-heif` no está instalado, las imágenes HEIC se convierten con la primera herramienta del sistema disponible: `sips` (macOS, incluida),
`heif-convert` (`libheif-examples` en Linux), ImageMagick (`magick` / `convert`) o `ffmpeg`. Si no hay ninguna,
esa imagen se omite con un aviso y el resto de la nota se exporta igualmente.

## Instalación

```sh
git clone https://github.com/lluis6/prodrafts2pdf.git
cd prodrafts2pdf

python3 -m venv .venv
source .venv/bin/activate            # Windows (PowerShell): .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

# opcional: soporte HEIC
python -m pip install pillow-heif
```

> No copies un entorno virtual entre máquinas. Un `venv` guarda rutas absolutas y ruedas compiladas específicas de la
> plataforma (por ejemplo Pillow), así que no funciona en otro sistema operativo, otra arquitectura ni siquiera en otra ruta.
> Comparte `requirements.txt` y deja que cada máquina cree su propio entorno, como arriba.

En macOS/Linux puedes hacer el script ejecutable y lanzarlo directamente:

```sh
chmod +x prodrafts2pdf.py
./prodrafts2pdf.py --help
```

El shebang usa el `python3` de tu `PATH`, así que activa antes el entorno virtual o no se encontrarán los paquetes.
Si falta una dependencia, el script lo avisa una sola vez, con el comando de instalación exacto para el intérprete con el que se ejecuta,
en lugar de fallar nota por nota.

## Formas de obtener tus notas

Hay dos maneras de dar notas a `prodrafts2pdf`. El script y el resultado son los mismos; lo que cambia es de dónde salen las
notas y de dónde se leen sus nombres y carpetas. Elige la que encaje con tu configuración.

| | A. Directorio de iCloud (macOS) | B. Exports programados por WebDAV |
|---|---|---|
| Dónde están las notas | La carpeta que publica macOS para la app sincronizada con iCloud | Un servidor WebDAV al que Pro Drafts exporta de forma programada: uno local (NAS, servidor casero, contenedor) o un servicio en la nube |
| Nombre de los archivos | `<UUID>.prodrafts` | `<nombre del documento>.prodrafts` (un zip) |
| Nombre y carpetas salen de | La base de datos de la biblioteca de Pro Drafts (`MainDrawBoardFile.sqlite`) | `prodrafts-backup.json` dentro de cada nota (o la base de datos de la biblioteca, si la tienes) |
| Necesita un Mac | Sí, con la misma cuenta de iCloud | No: cualquier equipo que pueda leer los archivos exportados |
| Mejor cuando | Tienes un Mac que sincroniza siempre | Quieres un flujo con servidor o nube, o no tienes un Mac donde ejecutar el script |

### Método A: directorio de iCloud en macOS

Con la sincronización de iCloud activada, macOS publica cada nota como un paquete `<UUID>.prodrafts` en
`~/Library/Mobile Documents/iCloud~draft/Documents`. Apunta el script a esa carpeta; lee las notas en su sitio
(solo lectura) y toma nombres y carpetas de la base de datos de la biblioteca que Pro Drafts guarda en el mismo Mac.

```sh
python3 prodrafts2pdf.py "$HOME/Library/Mobile Documents/iCloud~draft/Documents" --out-dir "$HOME/PDFs"
```

Ejecútalo a mano o prográmalo en el Mac (`launchd` o `cron`). El terminal o el programador necesita Acceso total al disco,
y las notas deben estar totalmente descargadas de iCloud. Más detalles en [¿Dónde están mis notas?](#dónde-están-mis-notas).

### Método B: exports programados por WebDAV

Configura Pro Drafts para exportar tus notas a una ubicación WebDAV de forma programada. El destino puede ser un servidor de
tu propia red o un servicio en la nube compatible con WebDAV. Cada export es un archivo zip con el nombre del documento que contiene un
`prodrafts-backup.json` con el UUID, el nombre y las carpetas, así que no hace falta la base de datos de la biblioteca.

Ejecuta el script en cualquier equipo que vea los archivos exportados como una carpeta normal: el propio servidor, un
recurso WebDAV montado o una carpeta sincronizada desde el servicio en la nube.

```sh
python3 prodrafts2pdf.py /ruta/a/la/carpeta/webdav --out-dir /ruta/a/PDFs -r
```

Después prográmalo (por ejemplo con una entrada de `cron` o un temporizador de `systemd` poco después del export de Pro Drafts). Gracias a la
huella incremental, las notas que no han cambiado desde la última ejecución se omiten. Más detalles en
[Exports por WebDAV](#exports-por-webdav).

### Consejos para ambos métodos

- Usa **una sola fuente por `--out-dir`**. No alimentes la misma carpeta de salida con el directorio de iCloud y con un export por WebDAV.
- El directorio de salida debe estar fuera de la carpeta de origen.
- Para combinar ambos, usa dos carpetas de salida distintas.

## Inicio rápido

Convertir una nota exportada, eligiendo tú el archivo de salida:

```sh
python3 prodrafts2pdf.py note_prodrafts.zip note.pdf
```

Convertir una nota y dejar que la biblioteca decida nombre y carpetas:

```sh
python3 prodrafts2pdf.py 11111111-2222-4333-8444-555555555555_prodrafts.zip --out-dir ~/Desktop/PDFs
# -> ~/Desktop/PDFs/Asignatura A/Ejercicios/Tema 1 - Ejercicios.pdf
```

Exportar **todas** tus notas de una vez (macOS, notas sincronizadas con iCloud):

```sh
python3 prodrafts2pdf.py "$HOME/Library/Mobile Documents/iCloud~draft/Documents" --out-dir "$HOME/Desktop/PDFs"
```

Consulta [¿Dónde están mis notas?](#dónde-están-mis-notas) para saber cómo encontrar esa carpeta y qué cambiar si la tuya es distinta.

Ejemplo de resultado:

```
PDFs/
├── .prodrafts2pdf.json            # huellas para las ejecuciones incrementales
├── Asignatura A/
│   ├── Resumen.svg               # nota de lienzo infinito -> SVG
│   └── Ejercicios/
│       └── Tema 1 - Ejercicios.pdf
├── Asignatura B/
│   └── Prácticas/Práctica 1/Práctica 1 - Previo.pdf
└── _sin_biblioteca/               # notas sin nombre en la base de datos ni en prodrafts-backup.json
    └── 99999999-8888-4777-8666-555555555555.pdf
```

Convertir una carpeta de notas exportadas por WebDAV (archivos con el nombre del documento, sin UUID):

```sh
python3 prodrafts2pdf.py ~/webdav-export --out-dir ~/Desktop/PDFs
# Apuntes A.prodrafts        -> ~/Desktop/PDFs/Carpeta A/Apuntes A.svg
# Tema 2 - Resumen.prodrafts -> ~/Desktop/PDFs/Asignatura B/Tema 2 - Resumen.pdf
```

> El UUID de la nota se lee del nombre del archivo o carpeta (`<UUID>.prodrafts`, `<UUID>_prodrafts.zip`) o, cuando el nombre
> no lo lleva (export por WebDAV), del `prodrafts-backup.json` que hay dentro del paquete. No renombres las notas
> con UUID en el nombre antes de convertirlas. Los mensajes de la consola están en español.

## ¿Dónde están mis notas?

La ruta que pasas como `SRC` para exportarlo todo es la carpeta que contiene un paquete por nota: `<UUID>.prodrafts`
(iCloud / export normal) o `<nombre del documento>.prodrafts` (export por WebDAV, ver [más abajo](#exports-por-webdav)).

**macOS con sincronización de iCloud (el caso habitual):**

```
~/Library/Mobile Documents/iCloud~draft/Documents
```

Contiene entradas como `AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE.prodrafts`, una por nota. Para comprobarlo, abre Terminal y ejecuta:

```sh
ls "$HOME/Library/Mobile Documents/iCloud~draft/Documents" | head
```

o, en Finder, pulsa `Shift + Cmd + G` y pega la ruta. Luego exporta todo:

```sh
python3 prodrafts2pdf.py "$HOME/Library/Mobile Documents/iCloud~draft/Documents" --out-dir "$HOME/Desktop/PDFs"
```

Notas:

- Mantén la ruta **entre comillas dobles**: `Mobile Documents` contiene un espacio. Usa `"$HOME/..."` en lugar de `~/...`,
  porque `~` no se expande dentro de comillas.
- Elige un `--out-dir` **fuera** de esa carpeta (el script se niega en caso contrario), como `~/Desktop/PDFs`.
- Si algunas notas no están totalmente descargadas de iCloud, pueden aparecer como fallos. Abre la carpeta en Finder,
  deja que iCloud termine y vuelve a ejecutar el comando; las notas ya exportadas se omiten.
- Si tus notas están en otro sitio (una copia en otro disco, exports de otro dispositivo), pasa esa carpeta. Sirve
  cualquier carpeta que contenga directamente paquetes `.prodrafts` o exports `.zip`.

**Base de datos de la biblioteca** (nombres y carpetas), usada automáticamente en macOS:

```
~/Library/Containers/emmo.prodrafts/Data/Library/Application Support/Prodrafts/MainDrawBoardFile.sqlite
```

En otro ordenador, copia ese archivo (y sus compañeros `-wal` y `-shm`) y añade `--db /ruta/a/MainDrawBoardFile.sqlite`.

### Exports por WebDAV

Pro Drafts también puede exportar notas por WebDAV. Esos archivos se diferencian del export normal:

| | Export normal / iCloud | Export por WebDAV |
|---|---|---|
| Nombre del archivo | `<UUID>.prodrafts` o `<UUID>.prodrafts.zip` | El nombre del documento, p. ej. `Tema 2 - Resumen.prodrafts` |
| Formato | Carpeta o `.zip` | Un archivo zip con extensión `.prodrafts` |
| Archivo extra dentro | ninguno | `prodrafts-backup.json` |
| Nombre y carpetas salen de | Base de datos de la biblioteca | Base de datos de la biblioteca si la nota está en ella; si no, `prodrafts-backup.json` |

`prodrafts-backup.json` tiene este aspecto (se omite la entrada `files`, con el tamaño y el SHA-256 de cada archivo):

```json
{"format": "com.emmo.prodrafts.document-backup", "version": 1,
 "uuid": "1B2C3D4E-5F60-4A7B-8C9D-0E1F2A3B4C5D", "name": "Tema 2 - Resumen",
 "folders": ["Asignatura B"], "noteType": 2,
 "createdAt": "2026-11-25T17:45:07Z", "modifiedAt": 1793634905.853619}
```

El uso es el mismo de siempre: pasa la carpeta (usa `-r` si WebDAV ha dejado subcarpetas) o un archivo suelto. No hace falta
`--db`, salvo que quieras los nombres actuales de la biblioteca (por ejemplo, si renombraste una nota después de exportarla).

## Referencia de línea de comandos

```
prodrafts2pdf.py SRC [OUT] [--out-dir DIR] [--db FILE] [--force] [--skip-existing]
                     [--width F] [--canvas-scale F] [--hide-masked] [-r]
```

| Argumento | Descripción |
|---|---|
| `SRC` | Una carpeta o archivo `.prodrafts`, un export `.zip` o una carpeta que contenga varios (modo lote). Añade `-r` / `--recursive` para buscar también en subcarpetas. |
| `OUT` | Archivo de salida (`.pdf`, o `.svg` para notas de lienzo infinito). Si se omite, el nombre y las carpetas salen de la biblioteca. Siempre exporta. No se admite en modo lote (usa `--out-dir`). |
| `--out-dir DIR` | Raíz del árbol generado cuando se omite `OUT`. Por defecto, el directorio actual. En modo lote no puede estar dentro de `SRC` ni contenerlo. |
| `--db FILE` | Base de datos de la biblioteca de Pro Drafts (`MainDrawBoardFile.sqlite`). Por defecto, la ruta del contenedor de la app en macOS. |
| `--force` | Re-exporta aunque la nota no haya cambiado. |
| `--skip-existing` | Modo lote: omite cualquier nota cuyo archivo de salida ya exista, haya cambiado o no. |
| `--width F` | Factor de grosor de trazo (por defecto `0.55`, calibrado con las miniaturas de las propias notas). |
| `--canvas-scale F` | Escala lienzo→página (por defecto `0.5`). |
| `--hide-masked` | Oculta por completo cualquier trazo que tenga un rango de edición, en lugar de quitar solo los tramos borrados. |

## Cómo funciona

```
 paquete .prodrafts ──► páginas, trazos, formas, texto, imágenes
        │                                   │
        │                                   ▼
        │                    aplicar borrados/movimientos, detectar papel oscuro
        │                                   │
        ▼                                   ▼
 base de datos ──► nombre + carpeta   dibujo vectorial  ──► PDF (fondo de página + capa vectorial)
 (copia de solo lectura)  ruta                              └► SVG (lienzo infinito)
```

1. **Abrir el paquete.** Un `.zip` (o un archivo `.prodrafts` de WebDAV, que es un zip) se extrae a un directorio temporal; una carpeta
   se lee en su sitio. El formato se detecta por sus archivos (ver [Contenido admitido](#contenido-admitido)).
2. **Interpretar el dibujo.** El archivo binario del dibujo se decodifica en trazos con sus puntos, grosores y colores.
   Se aplican los registros de trazos borrados y movidos para que la página se vea como en la app.
3. **Leer los elementos.** Formas, cuadros de texto, imágenes y tarjetas de enlace salen de la base de datos SQLite de la nota
   (`ZDRAFTBOARDITEM`), con su marco, rotación y opacidad.
4. **Detectar el papel.** Las páginas oscuras se pasan a papel blanco invirtiendo los neutros; los colores se respetan.
5. **Dibujar.** Todo se dibuja a través de una única capa de dibujo, que escribe un lienzo PDF de reportlab o un lienzo SVG
   con las mismas llamadas, así que ambas salidas coinciden. Las páginas PDF se combinan sobre la página de fondo original con pypdf.
6. **Resolver nombre y carpetas.** Primero se localiza el UUID: en el nombre del archivo o, si el nombre no lo lleva (WebDAV), en el
   campo `uuid` de `prodrafts-backup.json` dentro del paquete. Después se busca en la base de datos de la biblioteca
   (`ZBOARDFILE`: `ZNAME`, `ZUUID`, `ZFATHERFILE`) y se sigue a los padres hasta la primera carpeta. La base de datos, junto con sus archivos
   `-wal` y `-shm`, se copia antes a un directorio temporal, una vez por ejecución. Si la nota no está en la base de datos,
   se usan `name` y `folders` de `prodrafts-backup.json` (`folders` se lee de la carpeta más externa a la más interna).
   Solo si ninguna de las dos fuentes conoce la nota, va a `_sin_biblioteca/`.
7. **Omitir lo que no ha cambiado.** Una huella SHA-1 (contenido de la nota, opciones de renderizado y el propio script) se
   guarda en `.prodrafts2pdf.json` dentro de `--out-dir`, y se escribe tras cada nota para que las ejecuciones interrumpidas se reanuden.
   En los archivos zip la huella se calcula con los archivos de dentro, no con el zip en sí, y no tiene en cuenta
   `prodrafts-backup.json` (su `createdAt` cambia en cada export), `search/` ni `.DS_Store`. Por eso, volver a exportar por WebDAV
   una nota sin cambios no la regenera.

### Dónde vive la biblioteca

En macOS la base de datos es:

```
~/Library/Containers/emmo.prodrafts/Data/Library/Application Support/Prodrafts/MainDrawBoardFile.sqlite
```

Leerla puede requerir dar **Acceso total al disco** a tu terminal (Ajustes del Sistema → Privacidad y seguridad).
Los exports normales no guardan el nombre ni las carpetas dentro del paquete `.prodrafts`, y por eso hace falta esta base de datos.
Los exports por WebDAV sí los guardan (en `prodrafts-backup.json`), así que funcionan sin ella.
Si ninguna de las dos fuentes tiene la nota, el script avisa y usa el UUID como nombre de archivo, dentro de `_sin_biblioteca/`.

Los caracteres no válidos en nombres de archivo (`/`, `:`) se sustituyen por `-`. Los nombres duplicados en la misma carpeta llevan un
sufijo ` (2)`, ` (3)`, comparados sin distinguir mayúsculas, como hace macOS.

## Contenido admitido

**Formato actual** (páginas con PDF de fondo):

```
<UUID>.prodrafts/
├── meta.plist
├── pageIndex.plist                 orden de las páginas y PDF de fondo de cada una
├── drawings/*.com.apple.drawing    trazos de cada página
├── attachments/                    PDF de fondo, imágenes (PNG, HEIC, ...)
├── note.database.sqlite            formas, texto RTF, imágenes colocadas
├── thumbnail.jpeg
├── prodrafts-backup.json           solo en exports por WebDAV: uuid, name, folders
└── search/
```

**Formato antiguo** (lienzo infinito de una sola página): `draw.data`, `draft.database.sqlite`, `draft.data.model` y `File/`.
Los exports por WebDAV de este formato también incluyen `prodrafts-backup.json`.
No hay página de fondo, así que la página se ajusta a la caja que ocupa el contenido más un margen y se exporta como SVG.

| Contenido | Soporte |
|---|---|
| Trazos del lápiz | Vectoriales, grosor variable, marcadores translúcidos |
| Borrador y trazos movidos | Se quitan los tramos borrados; los trazos movidos se dibujan en su sitio |
| PDF de fondo | Se conservan como fondo de página |
| Imágenes | PNG, JPEG, HEIC, con posición, rotación y opacidad |
| Cuadros de texto | RTF como texto real, incluidas las tablas |
| Formas y líneas | Rellenos, bordes, guiones, esquinas redondeadas |
| Tarjetas de enlace | Se dibujan como una tarjeta con título y dominio |
| Papel oscuro | Se convierte a papel blanco invirtiendo los neutros |

La salida SVG usa coordenadas del tamaño de página para los trazados (no las enormes coordenadas en bruto del lienzo, que pierden
precisión en algunos visores), lleva una matriz en texto e imágenes e incluye un rectángulo blanco con `id="fondo"` que puedes borrar
para tener fondo transparente. El texto se compone en Helvetica/Arial con las fuentes del sistema del visor.

## Plataformas

| | macOS | Linux | Windows |
|---|---|---|---|
| Script y paquetes de Python | Probado | Probado | No probado; se espera que funcione (Python puro + ruedas) |
| Búsqueda de nombre/carpetas | Automática (ruta por defecto) | Copia `MainDrawBoardFile.sqlite` (y `-wal`, `-shm`) desde un Mac y pasa `--db`. No hace falta con exports por WebDAV | Igual que Linux |
| Obtener las notas | iCloud Drive: `~/Library/Mobile Documents/iCloud~draft/Documents`, o un export por WebDAV | Cópialas desde un Mac o usa un export por WebDAV | Cópialas desde un Mac o usa un export por WebDAV |

La biblioteca solo existe en los dispositivos Apple donde se ejecuta Pro Drafts, así que en otros sistemas llevas las notas y la
base de datos desde un Mac, o usas exports por WebDAV, que llevan su propio nombre y carpetas.

## Limitaciones

- Formato no oficial y obtenido por ingeniería inversa; las actualizaciones de la app pueden romperlo.
- El grosor de trazo y la escala del lienzo están calibrados con notas concretas. Si los trazos se ven más finos o más gruesos que en la app,
  ajusta `--width` y `--canvas-scale`.
- Algunas funciones de la app (por ejemplo ciertos tipos de formas o mapas mentales) pueden no estar soportadas. Abre una incidencia con una nota de muestra.
- Un paquete sin `pageIndex.plist` ni `draw.data` (por ejemplo, uno no descargado del todo de iCloud) no se puede convertir y se informa como fallo.
- Mover o renombrar una nota en la app produce una ruta de salida nueva; el archivo antiguo no se borra.
- En los exports por WebDAV, el nombre y las carpetas son los del momento de la exportación, salvo que la base de datos de la biblioteca diga otra cosa.
  Las notas eliminadas en la app solo se detectan a través de la base de datos de la biblioteca, porque `prodrafts-backup.json` no tiene ese indicador.
- Se asume que el orden de `folders` en `prodrafts-backup.json` es de la carpeta más externa a la más interna. Solo se ha comprobado con
  carpetas de un nivel; si las carpetas anidadas salen invertidas, abre una incidencia.
- Los mensajes de la consola y algunos nombres de salida (`_sin_biblioteca`, el id `fondo` del SVG) están en español.

## Solución de problemas

| Mensaje / síntoma | Causa y solución |
|---|---|
| `Faltan dependencias para ...` | Falta un paquete obligatorio en el Python que ejecuta el script. Ejecuta el comando `pip install` que se muestra o activa tu entorno virtual. |
| `no encuentro la nota en la biblioteca ... ni prodrafts-backup.json` | Ni la base de datos ni la propia nota conocen su nombre. Pasa `--db` o vuelve a exportarla por WebDAV. En archivos con UUID en el nombre, conserva el UUID. |
| Las notas de WebDAV acaban en `_sin_biblioteca/` | El paquete no tiene `prodrafts-backup.json` (export antiguo). Pasa `--db` y conserva el UUID en el nombre del archivo. |
| `Operation not permitted` (macOS) | Da Acceso total al disco a tu terminal. |
| `No encuentro pageIndex.plist ni draw.data` | La carpeta no es una nota completa (por ejemplo, no está del todo descargada de iCloud). |
| Todo se re-exporta cada vez | La huella ha cambiado: el script, las opciones de renderizado o la nota han cambiado. Comprueba que `.prodrafts2pdf.json` existe en `--out-dir`. |
| Faltan las imágenes HEIC | Instala `pillow-heif` o asegúrate de tener `sips`, `heif-convert`, ImageMagick o `ffmpeg`. |

## Contribuir

Se agradecen incidencias y pull requests. Al informar de un problema de renderizado, una pequeña nota de muestra (o su export en zip)
y una captura de cómo se ve en Pro Drafts facilitan mucho reproducirlo. Elimina antes cualquier contenido personal.

## Licencia

Añade aquí tu licencia (por ejemplo MIT) e incluye un archivo `LICENSE` en el repositorio.
