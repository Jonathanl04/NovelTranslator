# Novel Translator

Local web app for translating downloaded Chinese or Korean novel chapters into English one chapter at a time.

## Features

- Lists novels from `data/<novel name>/source/`.
- Translates one selected `.txt` chapter at a time.
- Saves translated chapters to `data/<novel name>/translated/<same filename>`.
- Exports translated chapters to EPUB with a linked table of contents and the downloaded cover image.
- Keeps a novel-specific glossary in `data/<novel name>/glossary/glossary.json`.
- Can translate normally with a glossary-first pass, or use `Translate Only` with the current glossary.
- Uses OpenRouter chat completions or an experimental Codex backend authenticated with ChatGPT.
- Lets glossary extraction and chapter translation use different backends and models.
- Uses a Vite React frontend with shadcn/ui components.
- Rejects translation output that still contains Chinese or Korean source-language text instead of saving partial output.
- Runs a compact fragment-replacement repair pass when the model leaves Chinese or Korean fragments untranslated.
- Tracks combined token usage, OpenRouter-reported cost, and Codex quota windows.

## Requirements

- Python 3.11 or newer.
- Node.js 22.22.2, 24.15.0, 26.0.0, or newer for frontend development. The current app also builds on Node 24.12.0 with an npm engine warning from a transitive CLI package.
- An OpenRouter API key, an eligible ChatGPT/Codex account, or both.
- Downloader scripts use `requests`, `beautifulsoup4`, and `scrapling`.

The Codex backend uses the pinned beta `openai-codex` Python SDK and its bundled runtime.

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

Paste your OpenRouter API key in Settings and click `Save API Key`, or click `Sign in with ChatGPT` to use Codex. The OpenRouter key is stored in the ignored `data/translator_config.json`; ChatGPT credentials remain in Codex's user credential store.

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
- ChatGPT/Codex connection
- OpenRouter or Codex backend for glossary and translation independently
- Glossary model
- Translation model
- Added custom models

OpenRouter requests use its chat completions API. Codex requests use an experimental minimal direct Responses adapter with no coding tools and the lowest reasoning level accepted by the selected model. Authentication, model discovery, and remaining-usage reporting still use the pinned SDK and its managed ChatGPT credentials. Codex requests consume Codex plan limits or ChatGPT credits rather than general OpenAI API quota.

For OpenRouter, each structured request first uses the same non-strict JSON Schema as Codex. If the selected model/provider rejects schema mode, the app remembers that limitation and falls back to JSON-object mode, then to no response format if necessary. Existing parse and repair retries handle malformed responses after those transport fallbacks.

After signing in, use `Refresh models` to retrieve the current model catalog for that account. A saved model that disappears remains visibly unavailable until another model is selected; the app never switches it silently. `Refresh usage` displays the primary and secondary quota windows, reset times, optional credits, and the last successful refresh time.

Defaults:

- Glossary: `deepseek/deepseek-v4-flash` with provider `deepseek`
- Translation: `deepseek/deepseek-v4-flash` with provider `deepseek`

Default model choices:

- `deepseek/deepseek-v4-flash` with provider `deepseek`
- `deepseek/deepseek-v4-pro` with provider `deepseek`
- `xiaomi/mimo-v2.5` with provider `xiaomi`
- `xiaomi/mimo-v2.5-pro` with provider `xiaomi`

To add another OpenRouter model:

1. Enter the OpenRouter model ID in the separate `Add model` area, such as `tencent/hy3:free`.
2. Click `Load providers`.
3. Select a provider.
4. Click `Add model`.

Added models appear in the Glossary model and Translation model dropdowns. Selecting a model from either dropdown saves that active model immediately. Removing an added model also saves immediately.

Using the same model for both can improve cache-hit opportunities because glossary and translation prompts share a stable prefix.

Usage and cost:

- Token usage is shown as one combined total. Codex rows are prefixed with `codex:`.
- Cost is recorded from OpenRouter `usage.cost`, including upstream BYOK cost when OpenRouter reports it.
- Reported API cost excludes subscription-backed Codex usage because OpenAI does not return a per-request USD cost for it.
- If OpenRouter omits cost, the app records `0` instead of estimating from hardcoded rates.
- Actual cost varies with model, provider, chapter length, glossary size, and repair passes.

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

## Book Management

The Books page lists local novels from `data/<novel>/source/`.

Use the trash button on a book card to delete a local book. Delete removes:

- downloaded source files
- translated chapter files
- the book-specific glossary
- saved bulk translation state

## Glossary Rules

Glossary entries contain:

- `source_term`
- `english_term`
- `category`
- `gender_or_pronoun`

Glossaries are novel-specific. A new novel starts with an empty glossary.

The app asks the configured glossary model to add only terms that need consistency, such as:

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
novel_translator/      Python backend modules, local API, and OpenRouter integration
frontend/              Vite React frontend with shadcn/ui components
scraper/download_uukanshu.py UU看書 chapter downloader
data/<novel>/source/   Downloaded source chapters and cover, ignored by git
data/<novel>/translated/ Translated chapters and EPUB exports
data/<novel>/glossary/ Novel-specific glossary files
data/logs/             LLM/OpenRouter failure logs
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
python -m pytest tests/test_app.py -q
cd frontend
npm run build
```
