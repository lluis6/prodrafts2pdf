# prodrafts2pdf

**Convert [Pro Drafts](https://prodrafts.app) notes to vector PDF and SVG, keeping the names and folder structure you have in the app.**

[Español](README.es.md)

Pro Drafts stores each note as an opaque `UUID.prodrafts` package (or, if you export over WebDAV, a package named after
the document). `prodrafts2pdf` reads that package and rebuilds
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
- [Ways to get your notes](#ways-to-get-your-notes)
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
  (`Subject A/Exercises/Topic 1 - Exercises.pdf`) under the output directory.
- **Works with WebDAV exports too.** Notes exported over WebDAV are named after the document and carry no UUID in the file
  name, but they embed a `prodrafts-backup.json` with the UUID, name and folders. The script reads it, so the tree is
  rebuilt even without the library database.
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
git clone https://github.com/lluis6/prodrafts2pdf.git
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

## Ways to get your notes

There are two ways to feed `prodrafts2pdf`. The script and the output are the same; what changes is where the notes
come from and where their names and folders are read from. Pick the one that fits your setup.

| | A. iCloud directory (macOS) | B. Scheduled WebDAV exports |
|---|---|---|
| Where the notes live | The folder macOS publishes for the iCloud-synced app | A WebDAV server that Pro Drafts exports to on a schedule: a local one (NAS, home server, container) or a cloud service |
| File names | `<UUID>.prodrafts` | `<document name>.prodrafts` (a zip) |
| Name and folders come from | The Pro Drafts library database (`MainDrawBoardFile.sqlite`) | `prodrafts-backup.json` inside each note (or the library database, if you have it) |
| Needs a Mac | Yes, signed in to the same iCloud account | No: any machine that can read the exported files |
| Best when | You have a Mac that is always syncing | You want a server or cloud workflow, or have no Mac to run the script on |

### Method A: iCloud directory on macOS

With iCloud sync enabled, macOS publishes every note as a `<UUID>.prodrafts` package in
`~/Library/Mobile Documents/iCloud~draft/Documents`. Point the script at that folder; it reads the notes in place
(read-only) and takes names and folders from the library database that Pro Drafts keeps on the same Mac.

```sh
python3 prodrafts2pdf.py "$HOME/Library/Mobile Documents/iCloud~draft/Documents" --out-dir "$HOME/PDFs"
```

Run it by hand, or schedule it on the Mac (`launchd` or `cron`). The terminal or scheduler needs Full Disk Access,
and the notes must be fully downloaded from iCloud. Details in [Where are my notes?](#where-are-my-notes).

### Method B: scheduled WebDAV exports

Configure Pro Drafts to export your notes to a WebDAV location on a schedule. The destination can be a server on your
own network or a cloud service that speaks WebDAV. Each export is a zip file named after the document and containing a
`prodrafts-backup.json` with the UUID, name and folders, so no library database is needed.

Run the script on any machine that can see the exported files as a normal folder: the server itself, a mounted
WebDAV share, or a folder synced from the cloud service.

```sh
python3 prodrafts2pdf.py /path/to/webdav/folder --out-dir /path/to/PDFs -r
```

Then schedule it (for example a `cron` entry or `systemd` timer shortly after the Pro Drafts export). Thanks to the
incremental fingerprint, notes that did not change since the last run are skipped. Details in
[WebDAV exports](#webdav-exports).

### Tips for both methods

- Use **one source per `--out-dir`**. Do not feed the same output folder from both the iCloud directory and a WebDAV export.
- The output directory must be outside the source folder.
- To combine both, use two separate output folders.

## Quick start

Convert one exported note, choosing the output file yourself:

```sh
python3 prodrafts2pdf.py note_prodrafts.zip note.pdf
```

Convert one note and let the library decide name and folders:

```sh
python3 prodrafts2pdf.py 11111111-2222-4333-8444-555555555555_prodrafts.zip --out-dir ~/Desktop/PDFs
# -> ~/Desktop/PDFs/Subject A/Exercises/Topic 1 - Exercises.pdf
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
├── Subject A/
│   ├── Overview.svg               # infinite-canvas note -> SVG
│   └── Exercises/
│       └── Topic 1 - Exercises.pdf
├── Subject B/
│   └── Labs/Lab 1/Lab 1 - Preview.pdf
└── _sin_biblioteca/               # notes with no name in the database nor in prodrafts-backup.json
    └── 99999999-8888-4777-8666-555555555555.pdf
```

Convert a folder of notes exported over WebDAV (files named after the document, no UUID):

```sh
python3 prodrafts2pdf.py ~/webdav-export --out-dir ~/Desktop/PDFs
# Notes A.prodrafts          -> ~/Desktop/PDFs/Folder A/Notes A.svg
# Topic 2 - Summary.prodrafts -> ~/Desktop/PDFs/Subject B/Topic 2 - Summary.pdf
```

> The note's UUID is read from the file or folder name (`<UUID>.prodrafts`, `<UUID>_prodrafts.zip`) or, when the name has
> none (WebDAV export), from the `prodrafts-backup.json` inside the package. Do not rename UUID-named notes before
> converting. Console messages are in Spanish.

## Where are my notes?

The path you pass as `SRC` to export everything is the folder that holds one package per note: `<UUID>.prodrafts`
(iCloud / normal export) or `<document name>.prodrafts` (WebDAV export, see [below](#webdav-exports)).

**macOS with iCloud sync (the usual case):**

```
~/Library/Mobile Documents/iCloud~draft/Documents
```

It contains entries like `AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE.prodrafts`, one per note. To check it, open Terminal and run:

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

### WebDAV exports

Pro Drafts can also export notes over WebDAV. Those files differ from the normal export:

| | Normal export / iCloud | WebDAV export |
|---|---|---|
| File name | `<UUID>.prodrafts` or `<UUID>.prodrafts.zip` | The document name, e.g. `Topic 2 - Summary.prodrafts` |
| Format | Folder or `.zip` | A zip file with the `.prodrafts` extension |
| Extra file inside | none | `prodrafts-backup.json` |
| Name and folders come from | Library database | Library database if the note is in it, otherwise `prodrafts-backup.json` |

`prodrafts-backup.json` looks like this (the `files` entry, with size and SHA-256 of every file, is omitted):

```json
{"format": "com.emmo.prodrafts.document-backup", "version": 1,
 "uuid": "1B2C3D4E-5F60-4A7B-8C9D-0E1F2A3B4C5D", "name": "Topic 2 - Summary",
 "folders": ["Subject B"], "noteType": 2,
 "createdAt": "2026-11-25T17:45:07Z", "modifiedAt": 1793634905.853619}
```

Usage is the same as before: pass the folder (use `-r` if WebDAV left subfolders) or a single file. No `--db` is needed
unless you want the current library names (for example if you renamed a note after exporting it).

## Command-line reference

```
prodrafts2pdf.py SRC [OUT] [--out-dir DIR] [--db FILE] [--force] [--skip-existing]
                     [--width F] [--canvas-scale F] [--hide-masked] [-r]
```

| Argument | Description |
|---|---|
| `SRC` | A `.prodrafts` folder or file, a `.zip` export, or a folder containing many of them (batch mode). Add `-r` / `--recursive` to also search subfolders. |
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

1. **Open the package.** A `.zip` (or a WebDAV `.prodrafts` file, which is a zip) is extracted to a temporary directory; a folder is read in place. The format is
   detected by its files (see [Supported content](#supported-content)).
2. **Parse the drawing.** The binary drawing file is decoded into strokes with their points, widths and colors.
   Records of erased and moved strokes are applied so the page looks like it does in the app.
3. **Read the items.** Shapes, text boxes, images and link cards come from the note's SQLite database
   (`ZDRAFTBOARDITEM`), with their frame, rotation and opacity.
4. **Detect the paper.** Dark pages are turned into white paper with neutrals inverted; colors are kept.
5. **Draw.** Everything is drawn through one drawing layer, which writes either a reportlab PDF canvas or an SVG canvas
   with the same calls, so both outputs match. PDF pages are merged over the original background page with pypdf.
6. **Resolve name and folders.** First the UUID is found: in the file name, or, if the name has none (WebDAV), in the
   `uuid` field of `prodrafts-backup.json` inside the package. Then it is looked up in the library database
   (`ZBOARDFILE`: `ZNAME`, `ZUUID`, `ZFATHERFILE`), and parents are followed up to the first folder. The database, plus its
   `-wal` and `-shm` files, is copied to a temporary directory first, once per run. If the note is not in the database,
   `name` and `folders` from `prodrafts-backup.json` are used instead (`folders` is read from outermost to innermost).
   Only if neither source knows the note does it go to `_sin_biblioteca/`.
7. **Skip what has not changed.** A SHA-1 fingerprint (note contents, rendering options, and the script itself) is
   stored in `.prodrafts2pdf.json` inside `--out-dir`, written after every note so interrupted runs resume.
   For zip files the fingerprint is computed from the files inside, not from the zip itself, and ignores
   `prodrafts-backup.json` (its `createdAt` changes on every export), `search/` and `.DS_Store`. Exporting an unchanged
   note again over WebDAV therefore does not regenerate it.

### Where the library lives

On macOS the database is:

```
~/Library/Containers/emmo.prodrafts/Data/Library/Application Support/Prodrafts/MainDrawBoardFile.sqlite
```

Reading it may require granting your terminal **Full Disk Access** (System Settings → Privacy & Security).
Normal exports do not store the name or folders inside the `.prodrafts` package, which is why this database is needed.
WebDAV exports do (in `prodrafts-backup.json`), so they work without it.
If neither source has the note, the script warns and falls back to the UUID as the file name, under `_sin_biblioteca/`.

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
├── prodrafts-backup.json           only in WebDAV exports: uuid, name, folders
└── search/
```

**Legacy format** (single-page infinite canvas): `draw.data`, `draft.database.sqlite`, `draft.data.model` and `File/`.
WebDAV exports of this format also include `prodrafts-backup.json`.
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
| Name/folder lookup | Automatic (default path) | Copy `MainDrawBoardFile.sqlite` (and `-wal`, `-shm`) from a Mac and pass `--db`. Not needed for WebDAV exports | Same as Linux |
| Getting the notes | iCloud Drive: `~/Library/Mobile Documents/iCloud~draft/Documents`, or a WebDAV export | Copy them from a Mac, or use a WebDAV export | Copy them from a Mac, or use a WebDAV export |

The library only exists on the Apple devices where Pro Drafts runs, so on other systems you bring the notes and the
database over from a Mac, or use WebDAV exports, which carry their own name and folders.

## Limitations

- Unofficial, reverse-engineered format; app updates can break it.
- Stroke width and canvas scale are calibrated against specific notes. If strokes look thinner or thicker than in the app,
  adjust `--width` and `--canvas-scale`.
- Some app features (for example certain shape types or mind maps) may not be supported. Open an issue with a sample note.
- A package with neither `pageIndex.plist` nor `draw.data` (for example one not fully downloaded from iCloud) cannot be converted and is reported as a failure.
- Moving or renaming a note in the app produces a new output path; the old file is not deleted.
- For WebDAV exports, the name and folders are those at export time unless the library database says otherwise.
  Notes deleted in the app are only detected through the library database, since `prodrafts-backup.json` has no such flag.
- The order of `folders` in `prodrafts-backup.json` is assumed to be outermost first. It has only been checked with
  one-level folders; if nested folders come out reversed, please open an issue.
- Console messages and some output names (`_sin_biblioteca`, SVG `fondo` id) are in Spanish.

## Troubleshooting

| Message / symptom | Cause and fix |
|---|---|
| `Faltan dependencias para ...` | A required package is missing in the Python that runs the script. Run the printed `pip install` command, or activate your virtual environment. |
| `no encuentro la nota en la biblioteca ... ni prodrafts-backup.json` | Neither the database nor the note itself knows its name. Pass `--db`, or export it again over WebDAV. For UUID-named files, keep the UUID in the file name. |
| WebDAV notes end up in `_sin_biblioteca/` | The package has no `prodrafts-backup.json` (older export). Pass `--db`, and keep the UUID in the file name. |
| `Operation not permitted` (macOS) | Give your terminal Full Disk Access. |
| `No encuentro pageIndex.plist ni draw.data` | The folder is not a complete note (for example, not fully downloaded from iCloud). |
| Everything is re-exported every time | The fingerprint changed: the script, the rendering options or the note changed. Check that `.prodrafts2pdf.json` is present in `--out-dir`. |
| HEIC images are missing | Install `pillow-heif`, or make sure `sips`, `heif-convert`, ImageMagick or `ffmpeg` is available. |

## Contributing

Issues and pull requests are welcome. When reporting a rendering problem, a small sample note (or its zip export)
and a screenshot of how it looks in Pro Drafts make it much easier to reproduce. Please remove any personal content first.

## License

Add your license here (for example MIT) and include a `LICENSE` file in the repository.
