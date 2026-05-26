# Novel Translator

Local web app for translating downloaded Chinese or Korean novel chapters into English one chapter at a time.

## Features

- Lists novels from `output/<novel name>/`.
- Translates one selected `.txt` chapter at a time.
- Saves translated chapters to `translated/<novel name>/<same filename>`.
- Keeps a novel-specific glossary in `glossaries/<novel name>.json`.
- Can translate normally with a glossary-first pass, or use `Translate Only` with the current glossary.
- Uses DeepSeek chat completions directly, with no third-party app dependencies.
- Rejects translation output that still contains Chinese or Korean source-language text instead of saving partial output.
- Runs a compact fragment-replacement repair pass when the model leaves Chinese or Korean fragments untranslated.

## Requirements

- Python 3.11 or newer.
- A DeepSeek API key.

The app uses only the Python standard library.

## Setup

Start the local app:

```powershell
python app.py --host 127.0.0.1 --port 8765
```

Open:

```text
http://127.0.0.1:8765
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
app.py                 Local web app and DeepSeek integration
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

## Tests

Run:

```powershell
python -m unittest
```
