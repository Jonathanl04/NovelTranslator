# Novel Translator

Local web app for translating Chinese or Korean web novels into English. It supports single-chapter and bulk translation, keeps terminology consistent with a novel-specific glossary, and exports completed chapters as EPUB.

## Features

- Translate one chapter or a selected chapter range.
- Extract and maintain names, places, ranks, techniques, artifacts, and other recurring terms.
- Use OpenRouter or a ChatGPT-authenticated Codex backend independently for glossary extraction and translation.
- Reject incomplete translations that still contain Chinese or Korean text and attempt an automatic repair.
- Export translated chapters, navigation, and cover art as EPUB.
- Track token usage, OpenRouter-reported cost, and available Codex quota.

## Quick Start

Requirements:

- Python 3.11 or newer
- Node.js 22 or newer
- An OpenRouter API key, an eligible ChatGPT/Codex account, or both

Start the app from PowerShell:

```powershell
.\run_app.ps1
```

Then open [http://127.0.0.1:8765](http://127.0.0.1:8765). The script installs frontend packages when needed and builds the frontend before starting the server.

Optional flags:

```powershell
.\run_app.ps1 -Port 8770
.\run_app.ps1 -SkipBuild
```

Open Settings to save an OpenRouter API key or sign in with ChatGPT for Codex access. Local configuration is stored in the ignored `data/translator_config.json`; ChatGPT credentials remain in Codex's credential store.

## Docker

Build and start the app:

```powershell
docker compose up --build
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765). The local `data/` directory is mounted into the container, so books, translations, glossaries, and configuration persist between runs.

## Translation

Place source `.txt` chapters under:

```text
data/<novel name>/source/
```

Each chapter should have its title on the first line and the body below it.

Two translation modes are available:

- **Translate + Glossary** extracts or updates terminology first, then translates with the updated glossary.
- **Translate Only** skips glossary extraction and translates with the current glossary.

Translated chapters are saved under `data/<novel name>/translated/` using the original filename. Bulk progress is saved automatically and can resume after an interruption.

## Glossary Context

Each novel has its own glossary at:

```text
data/<novel name>/glossary/glossary.json
```

Glossary entries contain a source term, its established English rendering, a category, and optional gender or pronoun information.

Settings provides two glossary context strategies:

- **Full glossary** sends every established entry to glossary extraction.
- **Recent 100 chapters** freezes terms found in the previous 100 chapters during bulk translation, rebuilds the snapshot every 50 translated chapters, and appends newly created or returning exact-match terms. Banked updates to existing entries are saved at each refresh. This limits context growth while preserving a stable prompt prefix between refreshes.

Single-chapter translation in recent mode uses the previous 100 chapters plus exact glossary matches from the selected chapter.

## EPUB Export

After translating at least one chapter, use **Export EPUB** from the novel sidebar. The EPUB includes all available translated chapters, a linked table of contents, navigation metadata, and the downloaded cover when present.

## Downloaders

The app supports downloads from UU看書, 69书吧, Bookto, TWKAN, and Qidian. Bookto
domain changes are handled automatically. Standalone scripts are available under
`scraper/`:

```powershell
python .\scraper\download_uukanshu.py https://uukanshu.cc/book/25771/ 1 30
python .\scraper\download_69shuba.py https://www.69shuba.com/book/77582.htm 1 30
python .\scraper\download_bookto.py "https://bookto24.com/bbs/board.php?bo_table=novel&wr_id=27341&spage=1" 1 30
```

Run the same commands through Docker when using the containerized app so files are written to the mounted `data/` directory:

```powershell
docker compose run --rm novel-translator python scraper/download_uukanshu.py https://uukanshu.cc/book/25771/ 1 30
```

Downloaders save chapters and available cover art under the novel's `source/` directory.

## Data Layout

```text
data/<novel>/source/       Source chapters and cover
data/<novel>/translated/   English chapters and EPUB exports
data/<novel>/glossary/     Novel-specific glossary
data/bulk/                 Saved bulk translation progress
data/logs/                 LLM failure logs
data/translator_config.json Local settings and API key
```

Deleting a novel from the Books page removes its source chapters, translations, glossary, and saved bulk state.

## Development

For frontend hot reload, start the backend on port `8765`, then run:

```powershell
cd frontend
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173).

Run backend tests and verify the frontend build with:

```powershell
python -m unittest discover -s tests -p "test_*.py"
cd frontend
npm run build
```
