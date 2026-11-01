# prodrafts2pdf

Convierte notas de **Pro Drafts** (`.prodrafts`) a **PDF vectorial** o **SVG vectorial**, conservando la
organización de carpetas y los nombres que tienen en la biblioteca de la app.

Los trazos del Apple Pencil se dibujan como trazados vectoriales (zoom ilimitado y editables en Illustrator,
Affinity, Inkscape…), y el PDF de fondo de cada página se conserva tal cual.

> Proyecto no oficial, sin relación con Pro Drafts ni con su desarrollador. El formato `.prodrafts` no está
> documentado: este script se ha hecho observando notas reales, así que una versión futura de la app podría
> cambiarlo. Revisa el resultado antes de borrar nada.

## Qué hace

- **Una nota o toda la biblioteca.** Le pasas un `.prodrafts`, un `.zip` exportado o la carpeta con todas las notas.
- **Nombre y carpetas reales.** Dentro de cada `.prodrafts` solo hay un UUID. El nombre ("Tema 7 - Exercicis en
  paper") y las carpetas ("IC/Exercicis/…") están en la biblioteca de la app; el script los lee de ahí y recrea el
  árbol en la salida.
- **PDF para las notas normales.** Cada página lleva su PDF de fondo, los trazos, formas, imágenes (incluido HEIC),
  cuadros de texto RTF con tablas y tarjetas de enlace.
- **SVG para las notas de lienzo infinito** (formato antiguo de Pro Drafts, sin PDF de fondo).
- **Solo lee el origen.** No escribe ni modifica nada en la carpeta de iCloud de las notas, y trabaja sobre una
  copia temporal de la base de datos de la biblioteca.
- **No repite trabajo.** Guarda una huella del contenido de cada nota y solo re-exporta las que han cambiado.
- **Sin pisarse.** Si dos notas acaban con el mismo nombre en la misma carpeta, la segunda se llama `nombre (2)`.

## Instalación

Necesitas Python 3 (probado con 3.12) y tres paquetes:

```sh
git clone <url-del-repo>
cd prodrafts2pdf

python3 -m venv .venv
source .venv/bin/activate          # Windows (PowerShell): .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### ¿Puedo copiar el entorno (el `.venv`) desde mi Mac?

No. Un entorno virtual **no es portable**: guarda rutas absolutas de tu máquina y paquetes compilados para tu
sistema y arquitectura (por ejemplo Pillow). Copiarlo a otro Mac con otra ruta, a Linux o a Windows no funciona, y
tampoco conviene subirlo a GitHub (está en el `.gitignore`).

Lo que sí es multiplataforma es la **lista de dependencias** (`requirements.txt`): cada persona o máquina crea su
propio entorno con los comandos de arriba.

### Dependencias opcionales

| Para qué | Qué instalar |
|---|---|
| Imágenes HEIC (fotos del iPhone dentro de las notas) | `python -m pip install pillow-heif`. En macOS, si no está, usa `sips`; en Linux, `heif-convert`, ImageMagick o `ffmpeg`. |
| Detectar papel oscuro en PDFs escaneados | `pdftoppm` de Poppler (`brew install poppler` / `apt install poppler-utils`). Sin él, ese caso concreto se trata como papel claro. |

## Uso

### Una nota

```sh
python3 prodrafts2pdf.py nota.prodrafts.zip salida.pdf
```

`nota` puede ser el `.zip` exportado o la carpeta `.prodrafts`. Con `salida.pdf` explícito se exporta siempre.

Sin fichero de salida, usa el nombre y las carpetas de la biblioteca:

```sh
python3 prodrafts2pdf.py 2131F525-4DFE-472E-9468-6925DEA840C6_prodrafts.zip --out-dir ~/Desktop/PDFs
# -> ~/Desktop/PDFs/IC/Exercicis/Tema 7 - Exercicis en paper.pdf
```

El UUID de la nota se toma del nombre del fichero o de la carpeta, así que no lo renombres antes de convertir.

### Toda la biblioteca

```sh
python3 prodrafts2pdf.py ~/Library/Mobile\ Documents/iCloud~draft/Documents --out-dir ~/Desktop/PDFs
```

Convierte cada `.prodrafts` y `.zip` de la carpeta y recrea el árbol de la biblioteca bajo `--out-dir`.
`--out-dir` **no puede estar dentro de la carpeta de origen** (ni contenerla): así los PDF no se mezclan con las notas.
Si una nota falla, el proceso sigue y al final se listan los fallos.

### Opciones

| Opción | Efecto |
|---|---|
| `salida.pdf` / `salida.svg` | Fichero de salida. Si se omite, se usan el nombre y las carpetas de la biblioteca. |
| `--out-dir DIR` | Carpeta raíz de la salida cuando no se da fichero (por defecto, la actual). |
| `--db RUTA` | `MainDrawBoardFile.sqlite` de la biblioteca (por defecto, el del contenedor de Pro Drafts en macOS). |
| `--force` | Re-exporta aunque la nota no haya cambiado. |
| `--skip-existing` | (Modo carpeta) no rehace los ficheros que ya existen. |
| `--width F` | Factor de grosor del trazo (por defecto 0.55, calibrado con las miniaturas de las notas). |
| `--canvas-scale F` | Escala del lienzo a la página (por defecto 0.5). |
| `--hide-masked` | Oculta por completo los trazos borrados que tengan algún rango, en lugar de quitar solo los tramos borrados. |

## Cómo se decide el nombre y las carpetas

La app guarda su biblioteca en `MainDrawBoardFile.sqlite`. En macOS está en:

```
~/Library/Containers/emmo.prodrafts/Data/Library/Application Support/Prodrafts/MainDrawBoardFile.sqlite
```

La tabla `ZBOARDFILE` tiene una fila por nota y por carpeta, con `ZNAME` (nombre), `ZUUID` (el UUID del
`.prodrafts`) y `ZFATHERFILE` (la fila de la carpeta padre). El script busca la nota por UUID y sube por los padres
hasta la primera carpeta para construir la ruta.

- Se copian a un directorio temporal la base de datos y sus ficheros `-wal` y `-shm`; el original no se abre.
- Los caracteres `/` y `:` de los nombres se sustituyen por `-`.
- Las notas que no aparecen en la biblioteca van a `_sin_biblioteca/<UUID>`.
- Si no se encuentra la base de datos, avisa y usa el UUID como nombre.

En macOS, leer `~/Library/Containers` puede requerir dar **Acceso total al disco** a tu Terminal
(Ajustes del Sistema → Privacidad y seguridad). Si ves `Operation not permitted`, es eso.

## Detección de cambios

En `--out-dir` se crea `.prodrafts2pdf.json`, con la huella (SHA-1) de cada nota exportada y la ruta de su salida.
Una nota se omite si coinciden la huella y la ruta y el fichero existe. La huella incluye:

- el contenido de la nota, salvo `search/` y `.DS_Store` (cuenta el contenido, no las fechas, así que iCloud tocando
  fechas no fuerza nada);
- los ajustes `--width`, `--canvas-scale` y `--hide-masked`;
- el propio código del script: si lo actualizas, la siguiente pasada re-exporta todo.

Si renombras o mueves una nota en Pro Drafts, la ruta cambia y se exporta a la nueva. El fichero de la ruta
antigua **no se borra**. Si el proceso se interrumpe, el manifiesto se guarda tras cada nota y al relanzar continúa.

## Formatos de entrada

**Formato actual** (páginas con PDF de fondo):

```
<UUID>.prodrafts/
├── meta.plist
├── pageIndex.plist            # páginas en orden y PDF de fondo de cada una
├── drawings/*.com.apple.drawing   # trazos de cada página
├── attachments/               # PDF de fondo, imágenes (PNG, HEIC…)
├── note.database.sqlite       # formas, texto RTF, imágenes colocadas (ZDRAFTBOARDITEM)
├── thumbnail.jpeg
└── search/
```

**Formato antiguo** (lienzo infinito, una sola página): `draw.data`, `draft.database.sqlite`,
`draft.data.model` y `File/`, sin `pageIndex.plist`. La página se calcula como la caja que ocupa el contenido
más un margen, y el resultado sale en SVG.

## Cómo se dibuja

- **Trazos.** Se leen del fichero de dibujo y se pintan con ancho variable según la presión. Los marcadores
  translúcidos conservan su transparencia.
- **Borrados y movidos.** Los trazos con registro de edición se interpretan para quitar los tramos borrados y dibujar
  los movidos en su sitio.
- **Fondo oscuro.** Si el papel de la página es oscuro, se pasa a papel blanco invirtiendo los neutros (blanco a
  negro) y se respetan los colores.
- **Texto.** Los cuadros de texto RTF se dibujan como texto real, con tablas.
- **Imágenes.** PNG, JPEG y HEIC, con su posición, giro y opacidad.
- **Tarjetas de enlace.** Se dibujan como tarjeta con título y dominio; el icono guardado es de 16 px y no se estira.
- **PDF.** Cada página: PDF de fondo + capa vectorial encima.
- **SVG.** Los trazados se escriben ya con coordenadas de la página (sin los números enormes del lienzo, que dan
  problemas de precisión en algunos visores); texto e imágenes llevan su matriz. Lleva un rectángulo blanco
  `id="fondo"` que puedes borrar si lo quieres transparente.

## Multiplataforma

| Parte | macOS | Linux | Windows |
|---|---|---|---|
| El script (Python y los tres paquetes) | Sí | Sí | Sí |
| Leer el nombre y las carpetas desde la app | Directo (ruta por defecto) | Copia `MainDrawBoardFile.sqlite` (y `-wal`, `-shm`) y usa `--db` | Igual que Linux |
| Tener las notas `.prodrafts` | iCloud Drive: `~/Library/Mobile Documents/iCloud~draft/Documents` | Cópialas desde el Mac | Cópialas desde el Mac |

La biblioteca solo existe en los dispositivos Apple donde corre Pro Drafts. En otros sistemas el script funciona,
pero necesitas llevar las notas y la base de datos desde el Mac.

## Limitaciones conocidas

- Formato no oficial: puede dejar de funcionar con versiones nuevas de la app.
- Las constantes de grosor y escala están calibradas contra notas concretas; si el trazo sale más fino o más
  grueso de lo esperado, ajusta `--width` y `--canvas-scale`.
- Algunos elementos de la app (por ejemplo ciertos tipos de formas o mapas mentales) pueden no estar soportados.
  Si alguno falta en tu salida, abre un issue con una nota de ejemplo.
- Una nota sin `pageIndex.plist` ni `draw.data` no se puede convertir y aparece en la lista de fallos.
- En el SVG, la tipografía es Helvetica/Arial del sistema, no la de la nota.

## Solución de problemas

| Mensaje | Qué pasa |
|---|---|
| `Faltan dependencias para …` | Falta algún paquete en el Python que ejecuta el script. Usa el comando que muestra, o activa el entorno virtual. |
| `no encuentro la nota en la biblioteca` | No se encontró la base de datos o la nota no está en ella. Usa `--db` o revisa que el nombre del fichero conserve el UUID. |
| `Operation not permitted` | En macOS, da acceso total al disco a la Terminal. |
| `No encuentro pageIndex.plist ni draw.data` | La carpeta no es una nota completa (a veces pasa con notas aún sin descargar de iCloud). |
| Todo se re-exporta cada vez | Cambia la huella: cambió el script, los ajustes o el contenido. Mira si `.prodrafts2pdf.json` está en `--out-dir`. |

## Licencia

Añade aquí la licencia que prefieras (por ejemplo MIT).
