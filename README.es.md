# prodrafts2pdf

**Convierte notas de [Pro Drafts](https://prodrafts.app) a PDF y SVG vectoriales, conservando los nombres y la estructura de carpetas que tienes en la app.**

[English](README.md)

Pro Drafts guarda cada nota como un paquete opaco `UUID.prodrafts`. `prodrafts2pdf` lee ese paquete y reconstruye la
nota como un archivo estándar: los trazos del Apple Pencil pasan a ser trazados vectoriales (zoom infinito, editables en
Illustrator, Affinity o Inkscape), el PDF de fondo original se conserva intacto y el resultado se guarda en el mismo
árbol de carpetas y con el mismo nombre que ves en la app.

> **Proyecto no oficial.** Sin relación con Pro Drafts ni con su desarrollador. El formato `.prodrafts` no está
> documentado y se ha deducido a partir de notas reales, así que una actualización de la app podría romperlo.
> La herramienta nunca modifica tus notas, pero conviene que tengas tus propias copias de seguridad.

## Contenido

- [Funciones](#funciones)
- [Requisitos](#requisitos)
- [Instalación](#instalación)
- [Inicio rápido](#inicio-rápido)
- [¿Dónde están mis notas?](#dónde-están-mis-notas)
- [Referencia de la línea de comandos](#referencia-de-la-línea-de-comandos)
- [Cómo funciona](#cómo-funciona)
- [Contenido admitido](#contenido-admitido)
- [Compatibilidad por plataforma](#compatibilidad-por-plataforma)
- [Limitaciones](#limitaciones)
- [Solución de problemas](#solución-de-problemas)
- [Contribuir](#contribuir)
- [Licencia](#licencia)

## Funciones

- **Salida vectorial.** Trazos, formas y texto son objetos vectoriales, no imágenes. Los PDF conservan el PDF de fondo de cada página.
- **Dos formatos de salida, según la nota.** Las notas con fondo de página salen en **PDF**. Las de lienzo infinito
  (el formato antiguo de Pro Drafts) salen en **SVG**.
- **Una nota o toda la biblioteca.** Puedes pasar un paquete `.prodrafts`, un `.zip` exportado o la carpeta que contiene
  todas tus notas.
- **Nombres y carpetas reales.** Busca el UUID de cada nota en la base de datos de la biblioteca de Pro Drafts y recrea el árbol de
  carpetas (`IC/Exercicis/Tema 7 - Exercicis en paper.pdf`) dentro de la carpeta de salida.
- **Solo lectura sobre tus datos.** Las notas de iCloud solo se leen. La base de datos de la biblioteca se copia a un
  directorio temporal antes de consultarla.
- **Exportaciones incrementales.** Una huella del contenido de cada nota permite omitir las que no han cambiado en ejecuciones posteriores.
- **Procesos por lotes seguros.** Una nota rota no detiene el lote, los nombres repetidos no se pisan entre sí y la
  carpeta de salida no puede estar dentro de la de origen.
- **Dibujo fiel.** Trazos de ancho variable, marcadores translúcidos, trazos borrados y movidos, imágenes (incluido HEIC),
  cuadros de texto RTF con tablas, formas y líneas, tarjetas de enlace y páginas de papel oscuro.
- **Pocas dependencias.** Tres paquetes instalables con pip; todo lo demás es biblioteca estándar.

## Requisitos

### Python

Python **3.8 o superior** (desarrollado y probado con 3.12).

### Paquetes de Python (obligatorios)

| Paquete | Mínimo | Para qué se usa |
|---|---|---|
| [`reportlab`](https://pypi.org/project/reportlab/) | 4.0 | Dibujar la capa vectorial y escribir las páginas PDF |
| [`pypdf`](https://pypi.org/project/pypdf/) | 4.0 | Leer los PDF de fondo y combinarlos bajo la capa vectorial |
| [`pillow`](https://pypi.org/project/pillow/) | 10.0 | Cargar y convertir las imágenes incrustadas |

Probado con reportlab 4.4, pypdf 5.9 y Pillow 12.1. Todo lo demás que importa el script es biblioteca estándar de
Python (`sqlite3`, `plistlib`, `zipfile`, `hashlib`, `json`, ...).

### Opcionales

| Qué | Para qué | Cómo |
|---|---|---|
| [`pillow-heif`](https://pypi.org/project/pillow-heif/) | Decodificar fotos HEIC (imágenes del iPhone) incrustadas en las notas | `python -m pip install pillow-heif` |
| `pdftoppm` (Poppler) | Detectar papel oscuro en PDF de fondo escaneados sin relleno de página. Sin él, ese caso concreto se trata como papel claro | macOS: `brew install poppler` · Debian/Ubuntu: `sudo apt install poppler-utils` · Windows: [compilaciones de Poppler](https://github.com/oschwartz10612/poppler-windows) en el `PATH` |

Si `pillow-heif` no está instalado, las imágenes HEIC se convierten con la primera herramienta del sistema que haya: `sips`
(macOS, ya incluido), `heif-convert` (`libheif-examples` en Linux), ImageMagick (`magick` / `convert`) o `ffmpeg`.
Si no hay ninguna, esa imagen se omite con un aviso y el resto de la nota se exporta igualmente.

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

> No copies un entorno virtual de una máquina a otra. Un `venv` guarda rutas absolutas y paquetes compilados para cada
> plataforma (por ejemplo Pillow), así que no funciona en otro sistema operativo, otra arquitectura ni siquiera en otra ruta.
> Comparte `requirements.txt` y deja que cada máquina cree su propio entorno, como arriba.

En macOS/Linux puedes hacer el script ejecutable y lanzarlo directamente:

```sh
chmod +x prodrafts2pdf.py
./prodrafts2pdf.py --help
```

El shebang usa el `python3` de tu `PATH`, así que activa antes el entorno virtual o no se encontrarán los paquetes.
Si falta una dependencia, el script lo avisa una sola vez, con el comando de instalación exacto para el intérprete con el que se
ejecuta, en vez de fallar nota por nota.

## Inicio rápido

Convertir una nota exportada, eligiendo tú el fichero de salida:

```sh
python3 prodrafts2pdf.py nota_prodrafts.zip nota.pdf
```

Convertir una nota y dejar que la biblioteca decida nombre y carpetas:

```sh
python3 prodrafts2pdf.py 2131F525-4DFE-472E-9468-6925DEA840C6_prodrafts.zip --out-dir ~/Desktop/PDFs
# -> ~/Desktop/PDFs/IC/Exercicis/Tema 7 - Exercicis en paper.pdf
```

Exportar **todas** tus notas de una vez (macOS, notas sincronizadas con iCloud):

```sh
python3 prodrafts2pdf.py "$HOME/Library/Mobile Documents/iCloud~draft/Documents" --out-dir "$HOME/Desktop/PDFs"
```

Mira [¿Dónde están mis notas?](#dónde-están-mis-notas) para saber cómo encontrar esa carpeta y qué cambiar si la tuya es distinta.

Ejemplo de resultado:

```
PDFs/
├── .prodrafts2pdf.json            # huellas para las ejecuciones incrementales
├── IC/
│   ├── About IC.svg               # nota de lienzo infinito -> SVG
│   └── Exercicis/
│       └── Tema 7 - Exercicis en paper.pdf
├── Física/
│   └── Pràctiques/Pràctica 1/PR01-Previ.pdf
└── _sin_biblioteca/               # notas que no están en la base de datos de la biblioteca
    └── 86C7FDDF-E6B6-4870-92E4-C7BB8220DA66.pdf
```

> El UUID de la nota se toma del nombre del fichero o de la carpeta (`<UUID>.prodrafts`, `<UUID>_prodrafts.zip`), así que no
> cambies el nombre de las notas antes de convertirlas. Los mensajes de consola están en español.

## ¿Dónde están mis notas?

La ruta que debes pasar como `SRC` para exportarlo todo es la carpeta que contiene un paquete `<UUID>.prodrafts` por nota.

**macOS con sincronización de iCloud (el caso habitual):**

```
~/Library/Mobile Documents/iCloud~draft/Documents
```

Contiene entradas como `036452E6-C7E7-48CC-9E99-F00B73AC8F81.prodrafts`, una por nota. Para comprobarlo, abre la Terminal y ejecuta:

```sh
ls "$HOME/Library/Mobile Documents/iCloud~draft/Documents" | head
```

o, en el Finder, pulsa `Mayús + Cmd + G` y pega la ruta. Después, exporta todo:

```sh
python3 prodrafts2pdf.py "$HOME/Library/Mobile Documents/iCloud~draft/Documents" --out-dir "$HOME/Desktop/PDFs"
```

Notas:

- Pon la ruta **entre comillas dobles**: `Mobile Documents` lleva un espacio. Usa `"$HOME/..."` en lugar de `~/...`,
  porque `~` no se expande dentro de comillas.
- Elige un `--out-dir` **fuera** de esa carpeta (el script se niega si no), por ejemplo `~/Desktop/PDFs`.
- Si algunas notas no están descargadas del todo desde iCloud, pueden aparecer como fallos. Abre la carpeta en el Finder,
  deja que iCloud termine y vuelve a lanzar el comando; las notas ya exportadas se omiten.
- Si tus notas están en otro sitio (una copia en otro disco, exportaciones de otro dispositivo), pasa esa carpeta. Sirve
  cualquier carpeta que contenga directamente paquetes `.prodrafts` o exportaciones `.zip`.

**Base de datos de la biblioteca** (nombres y carpetas), que se usa automáticamente en macOS:

```
~/Library/Containers/emmo.prodrafts/Data/Library/Application Support/Prodrafts/MainDrawBoardFile.sqlite
```

En otro ordenador, copia ese fichero (y sus acompañantes `-wal` y `-shm`) y añade `--db /ruta/a/MainDrawBoardFile.sqlite`.

## Referencia de la línea de comandos

```
prodrafts2pdf.py SRC [OUT] [--out-dir DIR] [--db FILE] [--force] [--skip-existing]
                     [--width F] [--canvas-scale F] [--hide-masked]
```

| Argumento | Descripción |
|---|---|
| `SRC` | Una carpeta `.prodrafts`, una exportación `.zip` o una carpeta que contenga muchas (modo lote). |
| `OUT` | Fichero de salida (`.pdf`, o `.svg` para notas de lienzo infinito). Si se omite, el nombre y las carpetas salen de la biblioteca. Siempre exporta. No se admite en modo lote (usa `--out-dir`). |
| `--out-dir DIR` | Raíz del árbol generado cuando se omite `OUT`. Por defecto, el directorio actual. En modo lote no puede estar dentro de `SRC` ni contenerla. |
| `--db FILE` | Base de datos de la biblioteca de Pro Drafts (`MainDrawBoardFile.sqlite`). Por defecto, la ruta del contenedor de la app en macOS. |
| `--force` | Re-exporta aunque la nota no haya cambiado. |
| `--skip-existing` | Modo lote: omite cualquier nota cuyo fichero de salida ya exista, haya cambiado o no. |
| `--width F` | Factor de grosor del trazo (por defecto `0.55`, calibrado con las miniaturas de las propias notas). |
| `--canvas-scale F` | Escala del lienzo a la página (por defecto `0.5`). |
| `--hide-masked` | Oculta por completo cualquier trazo que tenga un rango de edición, en lugar de quitar solo los tramos borrados. |

## Cómo funciona

```
 paquete .prodrafts ──► lee páginas, trazos, formas, texto, imágenes
        │                                   │
        │                                   ▼
        │                    aplica borrados/movidos, detecta papel oscuro
        │                                   │
        ▼                                   ▼
 base de datos  ──► nombre + ruta     dibujo vectorial  ──► PDF (página de fondo + capa vectorial)
 (copia de solo lectura)                                  └► SVG (lienzo infinito)
```

1. **Abrir el paquete.** Un `.zip` se extrae a un directorio temporal; una carpeta se lee en su sitio. El formato se
   detecta por sus ficheros (mira [Contenido admitido](#contenido-admitido)).
2. **Leer el dibujo.** El fichero binario de dibujo se decodifica en trazos con sus puntos, anchos y colores.
   Se aplican los registros de trazos borrados y movidos para que la página se vea como en la app.
3. **Leer los elementos.** Formas, cuadros de texto, imágenes y tarjetas de enlace salen de la base de datos SQLite de la nota
   (`ZDRAFTBOARDITEM`), con su marco, giro y opacidad.
4. **Detectar el papel.** Las páginas oscuras se pasan a papel blanco invirtiendo los neutros; los colores se respetan.
5. **Dibujar.** Todo se dibuja a través de una única capa de dibujo que escribe un lienzo PDF de reportlab o un lienzo SVG
   con las mismas llamadas, de modo que ambas salidas coinciden. Las páginas PDF se combinan con pypdf sobre la página de fondo original.
6. **Resolver nombre y carpetas.** El UUID de la nota se busca en la base de datos de la biblioteca (`ZBOARDFILE`: `ZNAME`,
   `ZUUID`, `ZFATHERFILE`) y se sube por los padres hasta la primera carpeta. Antes, la base de datos y sus ficheros
   `-wal` y `-shm` se copian a un directorio temporal, una vez por ejecución.
7. **Omitir lo que no ha cambiado.** Una huella SHA-1 (contenido de la nota, opciones de dibujo y el propio script) se guarda
   en `.prodrafts2pdf.json` dentro de `--out-dir`, y se escribe tras cada nota para que una ejecución interrumpida pueda continuar.

### Dónde está la biblioteca

En macOS la base de datos es:

```
~/Library/Containers/emmo.prodrafts/Data/Library/Application Support/Prodrafts/MainDrawBoardFile.sqlite
```

Leerla puede requerir dar a tu terminal **Acceso total al disco** (Ajustes del Sistema → Privacidad y seguridad).
Los nombres y las carpetas no se guardan dentro del paquete `.prodrafts`, y por eso hace falta esta base de datos.
Si no se encuentra, el script avisa y usa el UUID como nombre de fichero.

Los caracteres no válidos en nombres de fichero (`/`, `:`) se sustituyen por `-`. Los nombres repetidos en la misma carpeta
reciben un sufijo ` (2)`, ` (3)`, comparados sin distinguir mayúsculas, como hace macOS.

## Contenido admitido

**Formato actual** (páginas con PDF de fondo):

```
<UUID>.prodrafts/
├── meta.plist
├── pageIndex.plist                 orden de páginas y PDF de fondo de cada una
├── drawings/*.com.apple.drawing    trazos de cada página
├── attachments/                    PDF de fondo, imágenes (PNG, HEIC, ...)
├── note.database.sqlite            formas, texto RTF, imágenes colocadas
├── thumbnail.jpeg
└── search/
```

**Formato antiguo** (lienzo infinito de una sola página): `draw.data`, `draft.database.sqlite`, `draft.data.model` y `File/`.
No hay página de fondo, así que la página se ajusta a la caja que ocupa el contenido más un margen y se exporta como SVG.

| Contenido | Soporte |
|---|---|
| Trazos del lápiz | Vectoriales, de ancho variable, con marcadores translúcidos |
| Goma y trazos movidos | Se quitan los tramos borrados y los movidos se dibujan en su sitio |
| PDF de fondo | Se conservan como fondo de la página |
| Imágenes | PNG, JPEG, HEIC, con posición, giro y opacidad |
| Cuadros de texto | RTF como texto real, incluidas tablas |
| Formas y líneas | Rellenos, bordes, guiones, esquinas redondeadas |
| Tarjetas de enlace | Se dibujan como tarjeta con título y dominio |
| Papel oscuro | Se convierte a papel blanco invirtiendo los neutros |

La salida SVG usa para los trazados coordenadas del tamaño de la página (no las coordenadas enormes del lienzo, que pierden
precisión en algunos visores), lleva una matriz en el texto y las imágenes e incluye un rectángulo blanco con `id="fondo"`
que puedes borrar para tener el fondo transparente. El texto usa Helvetica/Arial de las fuentes del sistema del visor.

## Compatibilidad por plataforma

| | macOS | Linux | Windows |
|---|---|---|---|
| Script y paquetes de Python | Probado | Probado | Sin probar; se espera que funcione (Python puro + wheels) |
| Búsqueda de nombre/carpetas | Automática (ruta por defecto) | Copia `MainDrawBoardFile.sqlite` (y `-wal`, `-shm`) desde un Mac y pasa `--db` | Igual que Linux |
| Conseguir las notas | iCloud Drive: `~/Library/Mobile Documents/iCloud~draft/Documents` | Cópialas desde un Mac | Cópialas desde un Mac |

La biblioteca solo existe en los dispositivos Apple donde se ejecuta Pro Drafts, así que en otros sistemas tienes que llevar
las notas y la base de datos desde un Mac.

## Limitaciones

- Formato no oficial y deducido por ingeniería inversa; las actualizaciones de la app pueden romperlo.
- El grosor del trazo y la escala del lienzo están calibrados con notas concretas. Si los trazos salen más finos o más gruesos que en la app,
  ajusta `--width` y `--canvas-scale`.
- Algunas funciones de la app (por ejemplo ciertos tipos de formas o mapas mentales) pueden no estar soportadas. Abre un issue con una nota de ejemplo.
- Un paquete sin `pageIndex.plist` ni `draw.data` (por ejemplo uno no descargado del todo desde iCloud) no se puede convertir y se informa como fallo.
- Mover o renombrar una nota en la app genera una ruta de salida nueva; el fichero antiguo no se borra.
- Los mensajes de consola y algunos nombres de la salida (`_sin_biblioteca`, el id `fondo` del SVG) están en español.

## Solución de problemas

| Mensaje / síntoma | Causa y solución |
|---|---|
| `Faltan dependencias para ...` | Falta un paquete obligatorio en el Python que ejecuta el script. Ejecuta el comando `pip install` que se muestra, o activa tu entorno virtual. |
| `no encuentro la nota en la biblioteca` | No se encontró la base de datos o la nota no está en ella. Pasa `--db` y conserva el UUID en el nombre del fichero. |
| `Operation not permitted` (macOS) | Da Acceso total al disco a tu terminal. |
| `No encuentro pageIndex.plist ni draw.data` | La carpeta no es una nota completa (por ejemplo, no descargada del todo desde iCloud). |
| Todo se re-exporta cada vez | La huella cambió: cambió el script, las opciones de dibujo o la nota. Comprueba que `.prodrafts2pdf.json` esté en `--out-dir`. |
| Faltan imágenes HEIC | Instala `pillow-heif`, o asegúrate de tener `sips`, `heif-convert`, ImageMagick o `ffmpeg`. |

## Contribuir

Se agradecen los issues y los pull requests. Al informar de un problema de dibujo, una nota de ejemplo pequeña (o su exportación en zip)
y una captura de cómo se ve en Pro Drafts facilitan mucho reproducirlo. Quita antes cualquier contenido personal.

## Licencia

Añade aquí tu licencia (por ejemplo MIT) e incluye un fichero `LICENSE` en el repositorio.
