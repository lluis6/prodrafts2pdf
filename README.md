# prodrafts2pdf

**Convert [Pro Drafts](https://prodrafts.app) notes to vector PDF and SVG, keeping the names and folder structure you have in the app.**

[Español](README.es.md)

Pro Drafts stores each note as an opaque `UUID.prodrafts` package. `prodrafts2pdf` reads that package and rebuilds
the note as a standard file: Apple Pencil strokes become real vector paths (infinite zoom, editable in Illustrator,
Affinity or Inkscape), the original PDF background is kept untouched, and the output lands in the same
folder tree and under the same name you see in the app.

> **Unofficial project.** Not affiliated with, or endorsed by, Pro Drafts or its developer. The `.prodrafts`
> format is undocumented and was reverse-engineered from real notes, so a future app update may break it.
> The tool never modifies your notes, but keep your own backups anyway.

## Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Where are my notes?](#where-are-my-notes)
- [Command-line reference](#command-line-reference)
- [How it works](#how-it-works)
- [Supported content](#supported-content)
- [Platform support](#platform-support)
- [Limitations](#limitations)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Features

- **Vector output.** Strokes, shapes and text are vector objects, not images. PDFs keep the original background PDF of every page.
- **Two output formats, chosen per note.** Notes with page backgrounds become **PDF**. Notes on an infinite canvas
  (the older Pro Drafts format) become **SVG**.
- **Single note or the whole library.** Pass one `.prodrafts` package, an exported `.zip`, or the folder that holds
  all your notes.
- **Real names and folders.** Resolves each note's UUID against the Pro Drafts library database and recreates the folder tree
  (`IC/Exercicis/Tema 7 - Exercicis en paper.pdf`) under the output directory.
- **Read-only on your data.** Your iCloud notes are only read. The library database is copied to a temporary
  directory before it is queried.
- **Incremental exports.** A content fingerprint per note means unchanged notes are skipped on later runs.
- **Safe batch runs.** One broken note does not stop the batch, duplicate names never overwrite each other, and the
  output directory can never be inside the source folder.
- **Faithful rendering.** Variable-width strokes, translucent highlighters, erased and moved strokes, images (including
  HEIC), RTF text boxes with tables, shapes and lines, link cards, and dark-paper pages.
- **Few dependencies.** Three pure-Python-installable packages; everything else is the standard library.

## Requirements

### Python

Python **3.8 or newer** (developed and tested on 3.12).

### Python packages (required)

| Package | Minimum | Used for |
|---|---|---|
| [`reportlab`](https://pypi.org/project/reportlab/) | 4.0 | Drawing the vector layer and writing PDF pages |
| [`pypdf`](https://pypi.org/project/pypdf/) | 4.0 | Reading the background PDFs and merging them under the vector layer |
| [`pillow`](https://pypi.org/project/pillow/) | 10.0 | Loading and converting embedded images |

Tested with reportlab 4.4, pypdf 5.9 and Pillow 12.1. Everything else the script imports is part of the Python
standard library (`sqlite3`, `plistlib`, `zipfile`, `hashlib`, `json`, ...).

### Optional

| What | Why | How |
|---|---|---|
| [`pillow-heif`](https://pypi.org/project/pillow-heif/) | Decode HEIC photos (iPhone images) embedded in notes | `python -m pip install pillow-heif` |
| `pdftoppm` (Poppler) | Detect dark paper on scanned background PDFs that have no page fill. Without it that specific case is treated as light paper | macOS: `brew install poppler` · Debian/Ubuntu: `sudo apt install poppler-utils` · Windows: [Poppler builds](https://github.com/oschwartz10612/poppler-windows) on `PATH` |

If `pillow-heif` is not installed, HEIC images are converted with the first available system tool: `sips` (macOS, built in),
`heif-convert` (`libheif-examples` on Linux), ImageMagick (`magick` / `convert`) or `ffmpeg`. If none is found,
that image is skipped with a warning and the rest of the note is still exported.

## Installation

```sh
git clone https://github.com/<your-user>/prodrafts2pdf.git
cd prodrafts2pdf

python3 -m venv .venv
source .venv/bin/activate            # Windows (PowerShell): .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

# optional: HEIC support
python -m pip install pillow-heif
```

> Do not copy a virtual environment between machines. A `venv` stores absolute paths and platform-specific compiled
> wheels (for example Pillow), so it does not work on another OS, architecture or even another path.
> Share `requirements.txt` and let each machine create its own environment, as above.

On macOS/Linux you can make the script executable and run it directly:

```sh
chmod +x prodrafts2pdf.py
./prodrafts2pdf.py --help
```

The shebang uses `python3` from your `PATH`, so activate the virtual environment first or the packages will not be found.
If a dependency is missing, the script says so once, with the exact install command for the interpreter it runs under,
instead of failing note by note.

## Quick start

Convert one exported note, choosing the output file yourself:

```sh
python3 prodrafts2pdf.py note_prodrafts.zip note.pdf
```

Convert one note and let the library decide name and folders:

```sh
python3 prodrafts2pdf.py 2131F525-4DFE-472E-9468-6925DEA840C6_prodrafts.zip --out-dir ~/Desktop/PDFs
# -> ~/Desktop/PDFs/IC/Exercicis/Tema 7 - Exercicis en paper.pdf
```

Export **all** your notes at once (macOS, notes synced through iCloud):

```sh
python3 prodrafts2pdf.py "$HOME/Library/Mobile Documents/iCloud~draft/Documents" --out-dir "$HOME/Desktop/PDFs"
```

See [Where are my notes?](#where-are-my-notes) for how to find that folder and what to change if yours is different.

Example result:

```
PDFs/
├── .prodrafts2pdf.json            # fingerprints for incremental runs
├── IC/
│   ├── About IC.svg               # infinite-canvas note -> SVG
│   └── Exercicis/
│       └── Tema 7 - Exercicis en paper.pdf
├── Física/
│   └── Pràctiques/Pràctica 1/PR01-Previ.pdf
└── _sin_biblioteca/               # notes missing from the library database
    └── 86C7FDDF-E6B6-4870-92E4-C7BB8220DA66.pdf
```

> The note's UUID is read from the file or folder name (`<UUID>.prodrafts`, `<UUID>_prodrafts.zip`), so do not rename
> notes before converting. Console messages are in Spanish.

## Where are my notes?

The path you pass as `SRC` to export everything is the folder that holds one `<UUID>.prodrafts` package per note.

**macOS with iCloud sync (the usual case):**

```
~/Library/Mobile Documents/iCloud~draft/Documents
```

It contains entries like `036452E6-C7E7-48CC-9E99-F00B73AC8F81.prodrafts`, one per note. To check it, open Terminal and run:

```sh
ls "$HOME/Library/Mobile Documents/iCloud~draft/Documents" | head
```

or, in Finder, press `Shift + Cmd + G` and paste the path. Then export everything:

```sh
python3 prodrafts2pdf.py "$HOME/Library/Mobile Documents/iCloud~draft/Documents" --out-dir "$HOME/Desktop/PDFs"
```

Notes:

- Keep the path **in double quotes**: `Mobile Documents` contains a space. Use `"$HOME/..."` instead of `~/...`,
  because `~` is not expanded inside quotes.
- Choose an `--out-dir` **outside** that folder (the script refuses otherwise), such as `~/Desktop/PDFs`.
- If some notes are not fully downloaded from iCloud, they may be reported as failures. Open the folder in Finder,
  let iCloud finish, and run the command again; notes already exported are skipped.
- If your notes are somewhere else (a copy on another disk, exports from another device), pass that folder instead.
  Any folder that directly contains `.prodrafts` packages or `.zip` exports works.

**Library database** (names and folders), used automatically on macOS:

```
~/Library/Containers/emmo.prodrafts/Data/Library/Application Support/Prodrafts/MainDrawBoardFile.sqlite
```

On another computer, copy that file (and its `-wal` and `-shm` companions) and add `--db /path/to/MainDrawBoardFile.sqlite`.

## Command-line reference

```
prodrafts2pdf.py SRC [OUT] [--out-dir DIR] [--db FILE] [--force] [--skip-existing]
                     [--width F] [--canvas-scale F] [--hide-masked]
```

| Argument | Description |
|---|---|
| `SRC` | A `.prodrafts` folder, a `.zip` export, or a folder containing many of them (batch mode). |
| `OUT` | Output file (`.pdf`, or `.svg` for infinite-canvas notes). If omitted, name and folders come from the library. Always exports. Not allowed in batch mode (use `--out-dir`). |
| `--out-dir DIR` | Root of the generated tree when `OUT` is omitted. Defaults to the current directory. In batch mode it may not be inside `SRC` or contain it. |
| `--db FILE` | Pro Drafts library database (`MainDrawBoardFile.sqlite`). Defaults to the macOS app container path. |
| `--force` | Re-export even if the note is unchanged. |
| `--skip-existing` | Batch mode: skip any note whose output file already exists, changed or not. |
| `--width F` | Stroke width factor (default `0.55`, calibrated against the notes' own thumbnails). |
| `--canvas-scale F` | Canvas-to-page scale (default `0.5`). |
| `--hide-masked` | Hide fully any stroke that has an edit range, instead of removing only the erased segments. |

## How it works

```
 .prodrafts package ──► parse pages, strokes, shapes, text, images
        │                                   │
        │                                   ▼
        │                    apply erase / move records, detect dark paper
        │                                   │
        ▼                                   ▼
 library database ──► name + folder   vector drawing  ──► PDF (page background + vector layer)
 (read-only copy)      path                              └► SVG (infinite canvas)
```

1. **Open the package.** A `.zip` is extracted to a temporary directory; a folder is read in place. The format is
   detected by its files (see [Supported content](#supported-content)).
2. **Parse the drawing.** The binary drawing file is decoded into strokes with their points, widths and colors.
   Records of erased and moved strokes are applied so the page looks like it does in the app.
3. **Read the items.** Shapes, text boxes, images and link cards come from the note's SQLite database
   (`ZDRAFTBOARDITEM`), with their frame, rotation and opacity.
4. **Detect the paper.** Dark pages are turned into white paper with neutrals inverted; colors are kept.
5. **Draw.** Everything is drawn through one drawing layer, which writes either a reportlab PDF canvas or an SVG canvas
   with the same calls, so both outputs match. PDF pages are merged over the original background page with pypdf.
6. **Resolve name and folders.** The note's UUID is looked up in the library database (`ZBOARDFILE`: `ZNAME`,
   `ZUUID`, `ZFATHERFILE`), and parents are followed up to the first folder. The database, plus its `-wal` and `-shm`
   files, is copied to a temporary directory first, once per run.
7. **Skip what has not changed.** A SHA-1 fingerprint (note contents, rendering options, and the script itself) is
   stored in `.prodrafts2pdf.json` inside `--out-dir`, written after every note so interrupted runs resume.

### Where the library lives

On macOS the database is:

```
~/Library/Containers/emmo.prodrafts/Data/Library/Application Support/Prodrafts/MainDrawBoardFile.sqlite
```

Reading it may require granting your terminal **Full Disk Access** (System Settings → Privacy & Security).
Names and folders are not stored inside the `.prodrafts` package, which is why this database is needed.
If it cannot be found, the script warns and falls back to the UUID as the file name.

Characters that are invalid in file names (`/`, `:`) are replaced with `-`. Duplicate names in the same folder get a
` (2)`, ` (3)` suffix, compared case-insensitively as macOS does.

## Supported content

**Current format** (pages with PDF backgrounds):

```
<UUID>.prodrafts/
├── meta.plist
├── pageIndex.plist                 page order and background PDF of each page
├── drawings/*.com.apple.drawing    strokes of each page
├── attachments/                    background PDFs, images (PNG, HEIC, ...)
├── note.database.sqlite            shapes, RTF text, placed images
├── thumbnail.jpeg
└── search/
```

**Legacy format** (single-page infinite canvas): `draw.data`, `draft.database.sqlite`, `draft.data.model` and `File/`.
There is no background page, so the page is sized to the bounding box of the content plus a margin and exported as SVG.

| Content | Support |
|---|---|
| Pencil strokes | Vector, variable width, translucent highlighters |
| Eraser and moved strokes | Erased segments removed, moved strokes drawn in place |
| Background PDFs | Preserved as the page background |
| Images | PNG, JPEG, HEIC, with position, rotation and opacity |
| Text boxes | RTF as real text, including tables |
| Shapes and lines | Fills, borders, dashes, rounded corners |
| Link cards | Drawn as a card with title and domain |
| Dark paper | Converted to white paper with neutrals inverted |

SVG output uses page-sized coordinates for paths (not the huge raw canvas coordinates, which lose precision in some
viewers), carries a matrix on text and images, and includes a white rectangle with `id="fondo"` that you can delete
for a transparent background. Text is set in Helvetica/Arial from the viewer's system fonts.

## Platform support

| | macOS | Linux | Windows |
|---|---|---|---|
| Script and Python packages | Tested | Tested | Not tested; expected to work (pure Python + wheels) |
| Name/folder lookup | Automatic (default path) | Copy `MainDrawBoardFile.sqlite` (and `-wal`, `-shm`) from a Mac and pass `--db` | Same as Linux |
| Getting the notes | iCloud Drive: `~/Library/Mobile Documents/iCloud~draft/Documents` | Copy them from a Mac | Copy them from a Mac |

The library only exists on the Apple devices where Pro Drafts runs, so on other systems you bring the notes and the
database over from a Mac.

## Limitations

- Unofficial, reverse-engineered format; app updates can break it.
- Stroke width and canvas scale are calibrated against specific notes. If strokes look thinner or thicker than in the app,
  adjust `--width` and `--canvas-scale`.
- Some app features (for example certain shape types or mind maps) may not be supported. Open an issue with a sample note.
- A package with neither `pageIndex.plist` nor `draw.data` (for example one not fully downloaded from iCloud) cannot be converted and is reported as a failure.
- Moving or renaming a note in the app produces a new output path; the old file is not deleted.
- Console messages and some output names (`_sin_biblioteca`, SVG `fondo` id) are in Spanish.

## Troubleshooting

| Message / symptom | Cause and fix |
|---|---|
| `Faltan dependencias para ...` | A required package is missing in the Python that runs the script. Run the printed `pip install` command, or activate your virtual environment. |
| `no encuentro la nota en la biblioteca` | Database not found, or the note is not in it. Pass `--db`, and keep the UUID in the file name. |
| `Operation not permitted` (macOS) | Give your terminal Full Disk Access. |
| `No encuentro pageIndex.plist ni draw.data` | The folder is not a complete note (for example, not fully downloaded from iCloud). |
| Everything is re-exported every time | The fingerprint changed: the script, the rendering options or the note changed. Check that `.prodrafts2pdf.json` is present in `--out-dir`. |
| HEIC images are missing | Install `pillow-heif`, or make sure `sips`, `heif-convert`, ImageMagick or `ffmpeg` is available. |

## Contributing

Issues and pull requests are welcome. When reporting a rendering problem, a small sample note (or its zip export)
and a screenshot of how it looks in Pro Drafts make it much easier to reproduce. Please remove any personal content first.

## License

Add your license here (for example MIT) and include a `LICENSE` file in the repository.
