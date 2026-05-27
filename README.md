# Novel Translator

Local web app for translating downloaded Chinese or Korean novel chapters into English one chapter at a time.

## Features

- Lists novels from `output/<novel name>/`.
- Translates one selected `.txt` chapter at a time.
- Saves translated chapters to `translated/<novel name>/<same filename>`.
- Exports translated chapters to EPUB with a linked table of contents and the downloaded cover image.
- Keeps a novel-specific glossary in `glossaries/<novel name>.json`.
- Can translate normally with a glossary-first pass, or use `Translate Only` with the current glossary.
- Uses DeepSeek chat completions directly from the Python backend.
- Uses a Vite React frontend with shadcn/ui components.
- Rejects translation output that still contains Chinese or Korean source-language text instead of saving partial output.
- Runs a compact fragment-replacement repair pass when the model leaves Chinese or Korean fragments untranslated.

## Requirements

- Python 3.11 or newer.
- Node.js 22.22.2, 24.15.0, 26.0.0, or newer for frontend development. The current app also builds on Node 24.12.0 with an npm engine warning from a transitive CLI package.
- A DeepSeek API key.
- Downloader scripts use `requests`, `beautifulsoup4`, and `scrapling`.

The backend uses only the Python standard library.

## Setup

Start the local app:

```powershell
.\run_app.ps1
```

Open:

```text
http://127.0.0.1:8765
```

Optional flags:

```powershell
.\run_app.ps1 -Port 8770
.\run_app.ps1 -SkipBuild
```

For frontend development with hot reload, run the backend on port `8765`, then in another terminal:

```powershell
cd frontend
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

Paste your DeepSeek API key in the UI and click `Save`. The key is stored locally in `translator_config.json`, which is ignored by git.

## Model Settings

The UI has two model selectors:

- `Glossary model`: used for extracting novel terms before translation.
- `Translation model`: used for translating the chapter.

Defaults:

- Glossary: `deepseek-v4-pro`
- Translation: `deepseek-v4-flash`

Using the same model for both can improve DeepSeek cache-hit opportunities because glossary and translation prompts share a stable prefix.

## Translation Flow

`Translate Selected Chapter`:

1. Reads the selected source chapter.
2. Extracts glossary entries for the selected novel.
3. Saves/merges glossary entries into `glossaries/<novel>.json`.
4. Translates the chapter using the updated glossary.
5. If Chinese or Korean source-language text remains, asks the model for compact replacements only.
6. Falls back to a full repair pass only if compact replacement fails.
7. Saves the final English chapter under `translated/`.

`Translate Only`:

1. Skips glossary extraction.
2. Translates using the current novel glossary.
3. Runs the same untranslated source-language validation and repair flow.

## EPUB Export

After at least one chapter has been translated, click `Export EPUB` in the novel sidebar. The generated `.epub` contains:

- All translated chapters for the selected novel.
- A reader-visible table of contents with links to each chapter.
- EPUB navigation metadata for compatible readers.
- The novel cover from `output/<novel>/cover.<ext>` when one exists.

## Glossary Rules

Glossary entries contain:

- `source_term`
- `english_term`
- `category`
- `gender_or_pronoun`

Glossaries are novel-specific. A new novel starts with an empty glossary.

The app asks DeepSeek to add only terms that need consistency, such as:

- character names
- places
- sects, clans, organizations, schools, factions
- cultivation realms and ranks
- recurring worldbuilding terms
- techniques, spells, artifacts, weapons, formations, pills, treasures
- recurring titles or address forms
- gender/pronoun facts when inferable

## Project Layout

```text
app.py                 Compatibility entry point for running/importing the app
novel_translator/      Python backend modules, local API, and DeepSeek integration
frontend/              Vite React frontend with shadcn/ui components
scraper/download_uukanshu.py UU看書 chapter downloader
output/                Downloaded source chapters, ignored by git
translated/            Translated chapters
glossaries/            Novel-specific glossary files, ignored by git
tests/                 Unit tests
translator_config.json Local API key/model config, ignored by git
```

## Downloader

Use the scraper to download a chapter range from a UU看書 novel into `output/<book name>/`:

```powershell
python .\scraper\download_uukanshu.py https://uukanshu.cc/book/25771/ 1 30
```

The script only accepts `uukanshu.cc` URLs.

Use the 69书吧 scraper the same way:

```powershell
python .\scraper\download_69shuba.py https://www.69shuba.com/book/77582.htm 1 30
```

Both scrapers also save the novel cover as `cover.<ext>` in the same output directory.

## Tests

Run:

```powershell
python -m unittest
cd frontend
npm run build
```
