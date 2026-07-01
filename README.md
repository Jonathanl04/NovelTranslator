# Novel Translator

Local web app for translating downloaded Chinese or Korean novel chapters into English one chapter at a time.

## Features

- Lists novels from `data/<novel name>/source/`.
- Translates one selected `.txt` chapter at a time.
- Saves translated chapters to `data/<novel name>/translated/<same filename>`.
- Exports translated chapters to EPUB with a linked table of contents and the downloaded cover image.
- Keeps a novel-specific glossary in `data/<novel name>/glossary/glossary.json`.
- Can translate normally with a glossary-first pass, or use `Translate Only` with the current glossary.
- Uses DeepSeek chat completions directly from the Python backend.
- Uses a Vite React frontend with shadcn/ui components.
- Rejects translation output that still contains Chinese or Korean source-language text instead of saving partial output.
- Runs a compact fragment-replacement repair pass when the model leaves Chinese or Korean fragments untranslated.

## Requirements

- Python 3.11 or newer.
- Node.js 22.22.2, 24.15.0, 26.0.0, or newer for frontend development. The current app also builds on Node 24.12.0 with an npm engine warning from a transitive CLI package.
- An OpenRouter API key.
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

Paste your OpenRouter API key in the UI and click `Save`. The key is stored locally in `data/translator_config.json`, which is ignored by git.

## Docker

Build and start the app:

```powershell
docker compose up --build
```

Open:

```text
http://127.0.0.1:8765
```

The compose file mounts local `data/` into the container. It contains each novel's `source/`, `translated/`, and `glossary/` folders, plus `logs/` and `translator_config.json`.

The scraper scripts and their Python dependencies are included in the image. The image installs `scrapling[fetchers]` and runs `scrapling install` so `StealthyFetcher` has its browser dependencies. Run the scrapers through Compose so downloaded chapters land under `data/<book name>/source/`:

```powershell
docker compose run --rm novel-translator python scraper/download_uukanshu.py https://uukanshu.cc/book/25771/ 1 30
docker compose run --rm novel-translator python scraper/download_69shuba.py https://www.69shuba.com/book/77582.htm 1 30
```

## Settings

Use the Settings page to configure:

- OpenRouter API key
- Glossary model
- Translation model

Requests use the OpenRouter chat completions API.

Defaults:

- Glossary: `deepseek-v4-flash`
- Translation: `deepseek-v4-flash`

Supported models:

- `deepseek-v4-flash`
- `deepseek-v4-pro`
- `mimo-v2.5`
- `mimo-v2.5-pro`

Using the same model for both can improve cache-hit opportunities because glossary and translation prompts share a stable prefix.

Estimated cost:

- About `$0.002` per chapter for roughly `10,000` characters when using `DeepSeek Flash` or `Mimo 2.5`.
- Actual cost may vary with chapter length, glossary size, and repair passes.

## Translation Flow

`Translate Selected Chapter`:

1. Reads the selected source chapter.
2. Extracts glossary entries for the selected novel.
3. Saves/merges glossary entries into `data/<novel>/glossary/glossary.json`.
4. Translates the chapter using the updated glossary.
5. If Chinese or Korean source-language text remains, asks the model for compact replacements only.
6. Falls back to a full repair pass only if compact replacement fails.
7. Saves the final English chapter under `data/<novel>/translated/`.

`Translate Only`:

1. Skips glossary extraction.
2. Translates using the current novel glossary.
3. Runs the same untranslated source-language validation and repair flow.

## EPUB Export

After at least one chapter has been translated, click `Export EPUB` in the novel sidebar. The generated `.epub` contains:

- All translated chapters for the selected novel.
- A reader-visible table of contents with links to each chapter.
- EPUB navigation metadata for compatible readers.
- The novel cover from `data/<novel>/source/cover.<ext>` when one exists.

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
data/<novel>/source/   Downloaded source chapters and cover, ignored by git
data/<novel>/translated/ Translated chapters and EPUB exports
data/<novel>/glossary/ Novel-specific glossary files
data/logs/             DeepSeek failure logs
tests/                 Unit tests
data/translator_config.json Local API key/model config, ignored by git
```

## Downloader

Use the scraper to download a chapter range from a UU看書 novel into `data/<book name>/source/`:

```powershell
python .\scraper\download_uukanshu.py https://uukanshu.cc/book/25771/ 1 30
```

The script only accepts `uukanshu.cc` URLs.

Use the 69书吧 scraper the same way:

```powershell
python .\scraper\download_69shuba.py https://www.69shuba.com/book/77582.htm 1 30
```

Both scrapers also save the novel cover as `cover.<ext>` in the same source directory.

## Tests

Run:

```powershell
python -m unittest
cd frontend
npm run build
```
