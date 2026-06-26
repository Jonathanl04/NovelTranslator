from __future__ import annotations

import json
import tempfile
import time
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import app
from novel_translator import settings


def frontend_source() -> str:
    src = Path(__file__).resolve().parents[1] / "frontend" / "src"
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(src.rglob("*.tsx")))


class TranslatorAppTests(unittest.TestCase):
    def test_translation_prompt_only_includes_chapter_glossary_matches(self) -> None:
        glossary = [
            {
                "source_term": "太玄界",
                "english_term": "Taixuan Realm",
                "category": "place",
                "gender_or_pronoun": "",
            },
            {
                "source_term": "陆阳",
                "english_term": "Lu Yang",
                "category": "character",
                "gender_or_pronoun": "male",
            },
            {
                "source_term": "灵根",
                "english_term": "spiritual root",
                "category": "cultivation",
                "gender_or_pronoun": "",
            },
            {
                "source_term": "单身灵根",
                "english_term": "single-body spiritual root",
                "category": "cultivation",
                "gender_or_pronoun": "it",
            },
            {
                "source_term": "青锋剑",
                "english_term": "Green Edge Sword",
                "category": "artifact",
                "gender_or_pronoun": "it",
            },
        ]

        translation = app.build_messages(
            "第1章 太玄界", "陆阳是单身灵根。", glossary
        )[0]["content"]
        glossary_messages = app.build_glossary_messages("第1章", "正文", glossary)[0][
            "content"
        ]

        self.assertTrue(translation.startswith(app.SHARED_PROMPT_PREFIX))
        self.assertTrue(glossary_messages.startswith(app.SHARED_PROMPT_PREFIX))
        self.assertIn("Taixuan Realm", translation)
        self.assertIn("Lu Yang pronoun=male", translation)
        self.assertIn("spiritual root", translation)
        self.assertIn("single-body spiritual root pronoun=it", translation)
        self.assertNotIn("Green Edge Sword", translation)
        self.assertIn("Green Edge Sword", glossary_messages)

    def test_translation_prompt_uses_empty_glossary_text_when_no_entries_match(self) -> None:
        glossary = [
            {
                "source_term": "太玄界",
                "english_term": "Taixuan Realm",
                "category": "place",
                "gender_or_pronoun": "",
            }
        ]

        translation = app.build_messages("第1章", "正文", glossary)[0]["content"]

        self.assertIn("No established glossary entries yet.", translation)
        self.assertNotIn("Taixuan Realm", translation)

    def test_glossary_prompt_omits_category_annotation(self) -> None:
        glossary = [
            {
                "source_term": "太玄界",
                "english_term": "Taixuan Realm",
                "category": "place",
                "gender_or_pronoun": "",
            }
        ]

        self.assertEqual(app.glossary_prompt(glossary), "太玄界 => Taixuan Realm")

    def test_lists_novels_and_chapters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            translated = root / "translated"
            novel_dir = output / "Book" / "source"
            novel_dir.mkdir(parents=True)
            (novel_dir / "001_Chapter.txt").write_text("第1章\n\n正文", encoding="utf-8")
            (translated / "Book" / "translated").mkdir(parents=True)
            (translated / "Book" / "translated" / "001_Chapter.txt").write_text(
                "Chapter 1\n\nBody\n", encoding="utf-8"
            )

            self.assertEqual(app.list_novels(output), ["Book"])
            chapters = app.list_chapters("Book", output, translated)

            self.assertEqual(chapters[0]["filename"], "001_Chapter.txt")
            self.assertEqual(chapters[0]["title"], "001 Chapter 1")
            self.assertTrue(chapters[0]["translated"])

    def test_novel_metadata_includes_cover_url_when_cover_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            novel_dir = output / "Book One" / "source"
            novel_dir.mkdir(parents=True)
            (novel_dir / "cover.jpg").write_bytes(b"cover")
            (output / "Book One" / "metadata.json").write_text(
                json.dumps({"source_url": "https://uukanshu.cc/book/26855/"}),
                encoding="utf-8",
            )

            metadata = app.novel_metadata("Book One", output)

            self.assertEqual(app.cover_path("Book One", output), novel_dir / "cover.jpg")
            self.assertEqual(metadata["name"], "Book One")
            self.assertEqual(metadata["translated_name"], "Book One")
            self.assertEqual(metadata["cover_url"], "/api/cover?novel=Book%20One")
            self.assertEqual(metadata["source_url"], "https://uukanshu.cc/book/26855/")

    def test_list_novels_queues_new_source_language_name_without_renaming_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            novel_dir = output / "修仙日记" / "source"
            novel_dir.mkdir(parents=True)
            (novel_dir / "001_第1章.txt").write_text("第1章\n\n正文", encoding="utf-8")

            with patch.object(settings, "DATA_ROOT", root / "data"):
                with patch("novel_translator.bulk_translate._start_worker"):
                    self.assertEqual(app.list_novels(output), ["修仙日记"])

                state = app.load_bulk_state("修仙日记")

            self.assertTrue((output / "修仙日记" / "source").is_dir())
            self.assertFalse((output / "Cultivation Diary").exists())
            self.assertEqual(state["items"][0]["title"], "Novel title")
            self.assertEqual(state["items"][0]["mode"], "name")
            self.assertEqual(state["items"][0]["status"], "pending")

    def test_build_translated_epub_includes_toc_links_chapters_and_cover(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            translated = root / "translated"
            novel_dir = output / "Book One" / "source"
            novel_dir.mkdir(parents=True)
            (novel_dir / "cover.jpg").write_bytes(b"cover")
            (novel_dir / "001_Source.txt").write_text("第1章\n\n正文", encoding="utf-8")
            (novel_dir / "002_Source.txt").write_text("第2章\n\n正文", encoding="utf-8")
            (translated / "Book One" / "translated").mkdir(parents=True)
            (translated / "Book One" / "translated" / "001_Source.txt").write_text(
                "Chapter 1\n\nFirst paragraph.\n\nSecond paragraph.", encoding="utf-8"
            )
            (translated / "Book One" / "translated" / "002_Source.txt").write_text(
                "Chapter 2\n\nAnother paragraph.", encoding="utf-8"
            )

            raw, filename = app.build_translated_epub("Book One", output, translated)

            self.assertEqual(filename, "Book One.epub")
            with zipfile.ZipFile(BytesIO(raw)) as epub:
                self.assertEqual(epub.namelist()[0], "mimetype")
                self.assertEqual(epub.read("mimetype"), b"application/epub+zip")
                self.assertIn("OEBPS/images/cover.jpg", epub.namelist())
                self.assertEqual(epub.read("OEBPS/images/cover.jpg"), b"cover")
                nav = epub.read("OEBPS/nav.xhtml").decode("utf-8")
                toc = epub.read("OEBPS/toc.ncx").decode("utf-8")
                opf = epub.read("OEBPS/content.opf").decode("utf-8")

                self.assertIn('href="chapters/chapter-0001.xhtml"', nav)
                self.assertIn(">Chapter 1<", nav)
                self.assertIn('src="chapters/chapter-0002.xhtml"', toc)
                self.assertIn('properties="cover-image"', opf)
                self.assertIn("First paragraph.", epub.read("OEBPS/chapters/chapter-0001.xhtml").decode("utf-8"))

    def test_build_translated_epub_uses_cached_translated_novel_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            translated = root / "translated"
            novel_dir = output / "修仙日记" / "source"
            novel_dir.mkdir(parents=True)
            (output / "修仙日记" / "metadata.json").write_text(
                json.dumps({"translated_name": "Cultivation Diary"}, ensure_ascii=False),
                encoding="utf-8",
            )
            (novel_dir / "001_第1章.txt").write_text("第1章\n\n正文", encoding="utf-8")
            (translated / "修仙日记" / "translated").mkdir(parents=True)
            (translated / "修仙日记" / "translated" / "001_第1章.txt").write_text(
                "Chapter 1\n\nBody.", encoding="utf-8"
            )

            raw, filename = app.build_translated_epub("修仙日记", output, translated)

            self.assertEqual(filename, "Cultivation Diary.epub")
            self.assertTrue((output / "修仙日记" / "source").is_dir())
            with zipfile.ZipFile(BytesIO(raw)) as epub:
                opf = epub.read("OEBPS/content.opf").decode("utf-8")
                nav = epub.read("OEBPS/nav.xhtml").decode("utf-8")
                self.assertIn("<dc:title>Cultivation Diary</dc:title>", opf)
                self.assertIn("<h1>Cultivation Diary</h1>", nav)

    def test_build_translated_epub_requires_translated_chapters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            translated = Path(tmp) / "translated"
            novel_dir = output / "Book" / "source"
            novel_dir.mkdir(parents=True)
            (novel_dir / "001_Source.txt").write_text("第1章\n\n正文", encoding="utf-8")

            with self.assertRaises(app.AppError):
                app.build_translated_epub("Book", output, translated)

    def test_translated_path_preserves_layout(self) -> None:
        root = Path("translated-root")

        self.assertEqual(
            app.translated_path("Novel", "001_Title.txt", root),
            root / "Novel" / "translated" / "001_Title.txt",
        )

    def test_parse_translation_response_from_deepseek_message(self) -> None:
        payload = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "translated_title": "Chapter 1",
                                "translated_body": "Body",
                            }
                        )
                    }
                }
            ]
        }

        parsed = app.parse_translation_response(payload)

        self.assertEqual(parsed["translated_title"], "Chapter 1")
        self.assertEqual(parsed["translated_body"], "Body")

    def test_records_and_resets_deepseek_usage_cost(self) -> None:
        app.reset_usage()

        app.record_deepseek_usage(
            "deepseek-v4-flash",
            {
                "usage": {
                    "prompt_cache_hit_tokens": 100,
                    "prompt_cache_miss_tokens": 200,
                    "prompt_tokens": 300,
                    "completion_tokens": 400,
                    "total_tokens": 700,
                }
            },
        )
        app.record_deepseek_usage(
            "deepseek-v4-pro",
            {
                "usage": {
                    "prompt_cache_hit_tokens": 10,
                    "prompt_cache_miss_tokens": 20,
                    "prompt_tokens": 30,
                    "completion_tokens": 40,
                    "total_tokens": 70,
                }
            },
        )

        usage = app.current_usage()
        flash = usage["by_model"]["deepseek-v4-flash"]
        pro = usage["by_model"]["deepseek-v4-pro"]
        self.assertEqual(flash["prompt_cache_hit_tokens"], 100)
        self.assertEqual(flash["prompt_cache_miss_tokens"], 200)
        self.assertEqual(flash["prompt_tokens"], 300)
        self.assertEqual(flash["completion_tokens"], 400)
        self.assertEqual(flash["total_tokens"], 700)
        self.assertEqual(flash["cost_usd"], 0.00014028)
        self.assertEqual(pro["total_tokens"], 70)
        self.assertEqual(pro["cost_usd"], 0.00004354)
        self.assertEqual(usage["total"]["total_tokens"], 770)
        self.assertEqual(usage["total"]["cost_usd"], 0.00018382)
        self.assertEqual(app.reset_usage()["total"]["total_tokens"], 0)

    def test_parse_translation_response_rejects_malformed_json(self) -> None:
        payload = {"choices": [{"message": {"content": "not json"}}]}

        with self.assertRaises(app.AppError):
            app.parse_translation_response(payload)

    def test_call_deepseek_uses_300_second_timeout(self) -> None:
        from novel_translator.deepseek import DEEPSEEK_TIMEOUT_SECONDS

        seen = {}

        def fake_opener(request, timeout: int):
            seen["timeout"] = timeout
            raise TimeoutError("The read operation timed out")

        with tempfile.TemporaryDirectory() as tmp, patch.object(
            settings, "DEEPSEEK_FAILURE_LOG", Path(tmp) / "deepseek_failures.jsonl"
        ):
            with self.assertRaises(app.AppError):
                app.call_deepseek("secret", "deepseek-v4-flash", [], fake_opener)

        self.assertEqual(DEEPSEEK_TIMEOUT_SECONDS, 300)
        self.assertEqual(seen["timeout"], 300)

    def test_call_deepseek_uses_openrouter_model_id_with_same_parameters(self) -> None:
        seen = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self) -> bytes:
                return b'{"usage": {"prompt_tokens": 1}}'

        def fake_opener(request, timeout: int):
            seen["url"] = request.full_url
            seen["payload"] = json.loads(request.data.decode("utf-8"))
            seen["authorization"] = request.headers["Authorization"]
            return FakeResponse()

        app.call_deepseek("secret", "mimo-v2.5-pro", [{"role": "user", "content": "Hi"}], fake_opener)

        self.assertEqual(seen["url"], settings.OPENROUTER_URL)
        self.assertEqual(seen["authorization"], "Bearer secret")
        self.assertEqual(
            seen["payload"],
            {
                "model": "xiaomi/mimo-v2.5-pro",
                "messages": [{"role": "user", "content": "Hi"}],
                "thinking": {"type": "disabled"},
                "reasoning": {"effort": "none", "exclude": True},
                "temperature": 1,
                "stream": False,
                "response_format": {"type": "json_object"},
                "provider": {
                    "only": ["xiaomi"],
                    "allow_fallbacks": False,
                },
            },
        )

    def test_save_config_accepts_openrouter_model_choices(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            settings, "CONFIG_PATH", Path(tmp) / "translator_config.json"
        ):
            saved = app.save_config(
                {
                    "api_key": "secret",
                    "translation_model": "mimo-v2.5",
                    "glossary_model": "mimo-v2.5-pro",
                }
            )

        self.assertEqual(saved["translation_model"], "mimo-v2.5")
        self.assertEqual(saved["glossary_model"], "mimo-v2.5-pro")

    def test_parse_translation_response_rejects_untranslated_chinese(self) -> None:
        payload = {
            "translated_title": "Chapter 1",
            "translated_body": "太玄界 remains untranslated.",
        }

        with self.assertRaises(app.AppError):
            app.parse_translation_response(payload)

    def test_parse_translation_response_rejects_untranslated_korean(self) -> None:
        payload = {
            "translated_title": "Chapter 1",
            "translated_body": "그는 문을 opened.",
        }

        with self.assertRaises(app.AppError):
            app.parse_translation_response(payload)

    def test_source_language_fragments_include_chinese_and_korean(self) -> None:
        self.assertEqual(
            app.source_language_fragments("Outside 通行 and 안녕하세요 again 通行."),
            ["通行", "안녕하세요"],
        )

    def test_merge_glossary_preserves_existing_and_ai_chosen_categories(self) -> None:
        existing = [
            {
                "source_term": "徐邢",
                "english_term": "Xu Xing",
                "category": "character",
                "gender_or_pronoun": "male",
            }
        ]
        updates = [
            {
                "source_term": "徐邢",
                "english_term": "Xu Heng",
                "category": "character",
                "gender_or_pronoun": "unknown",
            },
            {
                "source_term": "太玄界",
                "english_term": "Taixuan Realm",
                "category": "place",
                "gender_or_pronoun": "",
            },
            {
                "source_term": "今天",
                "english_term": "today",
                "category": "ordinary_vocabulary",
            },
        ]

        merged = app.merge_glossary_entries(existing, updates)

        self.assertEqual(merged[0]["english_term"], "Xu Xing")
        self.assertNotIn("notes", merged[0])
        self.assertEqual(len(merged), 3)
        self.assertEqual(merged[1]["source_term"], "太玄界")
        self.assertEqual(merged[2]["category"], "ordinary_vocabulary")

    def test_populate_glossary_can_defer_existing_entry_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            translated = root / "translated"
            glossaries = root / "glossaries"
            novel_dir = output / "Book" / "source"
            novel_dir.mkdir(parents=True)
            (novel_dir / "001_第1章.txt").write_text("第1章\n\n太玄界。", encoding="utf-8")
            config = root / "translator_config.json"
            global_glossary = root / "glossary.json"
            glossary = glossaries / "Book" / "glossary" / "glossary.json"
            glossary.parent.mkdir(parents=True)
            config.write_text(
                json.dumps(
                    {
                        "api_key": "secret",
                        "translation_model": "deepseek-v4-flash",
                        "glossary_model": "deepseek-v4-pro",
                    }
                ),
                encoding="utf-8",
            )
            glossary.write_text(
                json.dumps(
                    [
                        {
                            "source_term": "徐邢",
                            "english_term": "Xu Xing",
                            "category": "character",
                            "gender_or_pronoun": "",
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            pending: list[dict[str, str]] = []

            def fake_call(api_key: str, model: str, messages: list[dict[str, str]]) -> dict:
                self.assertEqual(model, "deepseek-v4-pro")
                return {
                    "glossary_updates": [
                        {
                            "source_term": "徐邢",
                            "english_term": "Xu Xing",
                            "category": "character",
                            "gender_or_pronoun": "male",
                        },
                        {
                            "source_term": "太玄界",
                            "english_term": "Taixuan Realm",
                            "category": "place",
                            "gender_or_pronoun": "",
                        },
                    ]
                }

            with patch.object(settings, "OUTPUT_ROOT", output), patch.object(
                settings, "TRANSLATED_ROOT", translated
            ), patch.object(settings, "CONFIG_PATH", config), patch.object(
                settings, "GLOSSARY_PATH", global_glossary
            ), patch.object(
                settings, "GLOSSARY_ROOT", glossaries
            ):
                result = app.populate_glossary_for_chapter(
                    "Book",
                    "001_第1章.txt",
                    fake_call,
                    defer_existing_updates=True,
                    deferred_existing_updates=pending,
                )

            self.assertEqual([entry["source_term"] for entry in result], ["徐邢", "太玄界"])
            self.assertEqual(result[0]["gender_or_pronoun"], "")
            self.assertEqual(result[1]["english_term"], "Taixuan Realm")
            self.assertEqual([entry["source_term"] for entry in pending], ["徐邢"])
            self.assertEqual(
                json.loads(glossary.read_text(encoding="utf-8")),
                [
                    {
                        "source_term": "徐邢",
                        "english_term": "Xu Xing",
                        "category": "character",
                        "gender_or_pronoun": "",
                    },
                    {
                        "source_term": "太玄界",
                        "english_term": "Taixuan Realm",
                        "category": "place",
                        "gender_or_pronoun": "",
                    },
                ],
            )

    def test_glossary_prompt_does_not_hardcode_category_options(self) -> None:
        messages = app.build_glossary_messages("第1章", "正文", [])
        user_prompt = messages[1]["content"]

        self.assertIn("AI-chosen concise category label", user_prompt)
        self.assertNotIn("character|place|sect", user_prompt)

    def test_glossary_category_ui_is_free_text(self) -> None:
        app_source = frontend_source()

        self.assertIn("entry.category", app_source)
        self.assertNotIn("categories.map", app_source)
        self.assertNotIn("proper_noun", app_source)

    def test_glossary_page_is_rendered(self) -> None:
        app_source = frontend_source()

        self.assertIn("GlossaryPage", app_source)
        self.assertIn("Save Glossary", app_source)
        self.assertIn("Add Entry", app_source)

    def test_epub_export_ui_is_rendered(self) -> None:
        app_source = frontend_source()
        api_source = (Path(__file__).resolve().parents[1] / "frontend" / "src" / "api.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn("Export EPUB", app_source)
        self.assertIn("disabled={!canExport}", app_source)
        self.assertNotIn("disabled={!canExport || busy}", app_source)
        self.assertIn("exportEpub", app_source)
        self.assertIn("exportEpubUrl", api_source)
        self.assertIn("/api/export/epub", api_source)

    def test_scraper_is_connected_to_api_and_ui(self) -> None:
        root = Path(__file__).resolve().parents[1]
        app_source = frontend_source()
        api_source = (root / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")
        server_source = (root / "novel_translator" / "server.py").read_text(encoding="utf-8")

        self.assertIn("Source URL", app_source)
        self.assertIn("Use Link", app_source)
        self.assertIn("scrapeState", app_source)
        self.assertIn("api.scrape", app_source)
        self.assertIn("api.scrapeState", app_source)
        self.assertIn("/api/scrape", api_source)
        self.assertIn("handle_scrape", server_source)
        self.assertIn("download_69shuba_range", server_source)
        self.assertIn("download_uukanshu_range", server_source)

    def test_bulk_translation_progress_ui_is_rendered(self) -> None:
        app_source = frontend_source()
        api_source = (Path(__file__).resolve().parents[1] / "frontend" / "src" / "api.ts").read_text(
            encoding="utf-8"
        )
        server_source = (Path(__file__).resolve().parents[1] / "novel_translator" / "server.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("runTranslate", app_source)
        self.assertIn("Translate + Glossary", app_source)
        self.assertIn("BulkBadge", app_source)
        self.assertIn("api.startBulkTranslation(novel, queue)", app_source)
        self.assertIn("api.bulkTranslation(nextNovel)", app_source)
        self.assertIn("/api/bulk-translate", api_source)
        self.assertIn("/api/bulk-translate", server_source)

    def test_model_select_changes_are_saved_immediately(self) -> None:
        app_source = frontend_source()

        self.assertIn("onConfigChange({ glossary_model })", app_source)
        self.assertIn("onConfigChange({ translation_model })", app_source)
        self.assertIn("keep_existing_key: true", app_source)

    def test_single_translation_uses_persisted_queue_and_progress_status(self) -> None:
        app_source = frontend_source()

        self.assertIn('onTranslate("full")', app_source)
        self.assertIn('onTranslate("only")', app_source)
        self.assertIn("showStatus(describeBulkProgress(state))", app_source)
        self.assertIn("describeBulkProgress", app_source)

    def test_bulk_translation_state_persists_to_disk(self) -> None:
        from novel_translator import bulk_translate

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seen = []

            def fake_translate(
                novel: str,
                filename: str,
                populate_glossary: bool = True,
                should_abort=None,
                defer_existing_glossary_updates: bool = False,
                deferred_existing_glossary_updates=None,
                **kwargs,
            ) -> dict[str, str]:
                seen.append(
                    (
                        novel,
                        filename,
                        populate_glossary,
                        defer_existing_glossary_updates,
                        deferred_existing_glossary_updates is not None,
                    )
                )
                return {"filename": filename}

            with patch.object(settings, "DATA_ROOT", root / "data"), patch.object(
                bulk_translate, "translate_chapter", fake_translate
            ):
                bulk_translate.start_bulk_translation(
                    "Book One",
                    [
                        {"filename": "001.txt", "title": "Chapter 1", "status": "pending"},
                        {"filename": "002.txt", "title": "Chapter 2", "status": "pending"},
                    ],
                )

                deadline = time.time() + 2
                state = bulk_translate.get_bulk_state("Book One")
                while state["running"] and time.time() < deadline:
                    time.sleep(0.02)
                    state = bulk_translate.get_bulk_state("Book One")

            self.assertFalse(state["running"])
            self.assertEqual(
                seen,
                [
                    ("Book One", "001.txt", True, True, True),
                    ("Book One", "002.txt", True, True, True),
                ],
            )
            self.assertEqual([item["status"] for item in state["items"]], ["done", "done"])
            self.assertEqual(
                json.loads((root / "data" / "bulk" / "Book One.json").read_text(encoding="utf-8"))["items"][0]["message"],
                "Saved",
            )

    def test_failed_bulk_translation_does_not_resume(self) -> None:
        from novel_translator import bulk_translate

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seen = []

            def fake_translate(
                novel: str,
                filename: str,
                populate_glossary: bool = True,
                should_abort=None,
                defer_existing_glossary_updates: bool = False,
                deferred_existing_glossary_updates=None,
                **kwargs,
            ) -> dict[str, str]:
                seen.append(
                    (
                        novel,
                        filename,
                        populate_glossary,
                        defer_existing_glossary_updates,
                        deferred_existing_glossary_updates is not None,
                    )
                )
                raise app.AppError("DeepSeek message was not valid glossary JSON.", 502)

            with patch.object(settings, "DATA_ROOT", root / "data"), patch.object(
                bulk_translate, "translate_chapter", fake_translate
            ):
                bulk_translate.start_bulk_translation(
                    "Book One",
                    [
                        {"filename": "001.txt", "title": "Chapter 1", "status": "pending"},
                        {"filename": "002.txt", "title": "Chapter 2", "status": "pending"},
                    ],
                )

                deadline = time.time() + 2
                state = bulk_translate.get_bulk_state("Book One")
                while state["running"] and time.time() < deadline:
                    time.sleep(0.02)
                    state = bulk_translate.get_bulk_state("Book One")

                self.assertFalse(state["running"])
                self.assertTrue(state["aborted"])
                self.assertEqual(seen, [("Book One", "001.txt", True, True, True)])
                self.assertEqual([item["status"] for item in state["items"]], ["failed", "pending"])

                bulk_translate.get_bulk_state("Book One")
                time.sleep(0.1)

            self.assertEqual(seen, [("Book One", "001.txt", True, True, True)])

    def test_bulk_translation_flushes_deferred_glossary_updates_at_end(self) -> None:
        from novel_translator import bulk_translate

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            translated = root / "translated"
            glossaries = root / "glossaries"
            novel_dir = output / "Book One" / "source"
            novel_dir.mkdir(parents=True)
            (novel_dir / "001.txt").write_text("第1章\n\n太玄界。", encoding="utf-8")
            glossary = glossaries / "Book One" / "glossary" / "glossary.json"
            glossary.parent.mkdir(parents=True)
            glossary.write_text(
                json.dumps(
                    [
                        {
                            "source_term": "徐邢",
                            "english_term": "Xu Xing",
                            "category": "character",
                            "gender_or_pronoun": "",
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            seen = []

            def fake_translate(
                novel: str,
                filename: str,
                populate_glossary: bool = True,
                should_abort=None,
                defer_existing_glossary_updates: bool = False,
                deferred_existing_glossary_updates=None,
                **kwargs,
            ) -> dict[str, str]:
                seen.append(
                    (
                        novel,
                        filename,
                        populate_glossary,
                        defer_existing_glossary_updates,
                        deferred_existing_glossary_updates is not None,
                    )
                )
                self.assertTrue(defer_existing_glossary_updates)
                self.assertIsNotNone(deferred_existing_glossary_updates)
                deferred_existing_glossary_updates.append(
                    {
                        "source_term": "徐邢",
                        "english_term": "Xu Xing",
                        "category": "character",
                        "gender_or_pronoun": "male",
                    }
                )
                app.save_glossary(
                    [
                        *app.load_glossary(novel),
                        {
                            "source_term": "太玄界",
                            "english_term": "Taixuan Realm",
                            "category": "place",
                            "gender_or_pronoun": "",
                        },
                    ],
                    novel,
                )
                return {"filename": filename}

            with patch.object(settings, "DATA_ROOT", root / "data"), patch.object(
                settings, "OUTPUT_ROOT", output
            ), patch.object(settings, "TRANSLATED_ROOT", translated), patch.object(
                settings, "GLOSSARY_ROOT", glossaries
            ), patch.object(
                bulk_translate, "translate_chapter", fake_translate
            ):
                bulk_translate.start_bulk_translation(
                    "Book One",
                    [{"filename": "001.txt", "title": "Chapter 1", "status": "pending"}],
                )

                deadline = time.time() + 2
                state = bulk_translate.get_bulk_state("Book One")
                while state["running"] and time.time() < deadline:
                    time.sleep(0.02)
                    state = bulk_translate.get_bulk_state("Book One")

            self.assertFalse(state["running"])
            self.assertEqual(seen, [("Book One", "001.txt", True, True, True)])
            deadline = time.time() + 2
            while time.time() < deadline:
                current_glossary = json.loads(glossary.read_text(encoding="utf-8"))
                if current_glossary[0]["gender_or_pronoun"] == "male":
                    break
                time.sleep(0.02)
            self.assertEqual(
                json.loads(glossary.read_text(encoding="utf-8")),
                [
                    {
                        "source_term": "徐邢",
                        "english_term": "Xu Xing",
                        "category": "character",
                        "gender_or_pronoun": "male",
                    },
                    {
                        "source_term": "太玄界",
                        "english_term": "Taixuan Realm",
                        "category": "place",
                        "gender_or_pronoun": "",
                    },
                ],
            )

    def test_failed_bulk_translation_still_flushes_deferred_glossary_updates(self) -> None:
        from novel_translator import bulk_translate

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            translated = root / "translated"
            glossaries = root / "glossaries"
            novel_dir = output / "Book One" / "source"
            novel_dir.mkdir(parents=True)
            (novel_dir / "001.txt").write_text("第1章\n\n太玄界。", encoding="utf-8")
            glossary = glossaries / "Book One" / "glossary" / "glossary.json"
            glossary.parent.mkdir(parents=True)
            glossary.write_text(
                json.dumps(
                    [
                        {
                            "source_term": "徐邢",
                            "english_term": "Xu Xing",
                            "category": "character",
                            "gender_or_pronoun": "",
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            def fake_translate(
                novel: str,
                filename: str,
                populate_glossary: bool = True,
                should_abort=None,
                defer_existing_glossary_updates: bool = False,
                deferred_existing_glossary_updates=None,
                **kwargs,
            ) -> dict[str, str]:
                self.assertTrue(defer_existing_glossary_updates)
                self.assertIsNotNone(deferred_existing_glossary_updates)
                deferred_existing_glossary_updates.append(
                    {
                        "source_term": "徐邢",
                        "english_term": "Xu Xing",
                        "category": "character",
                        "gender_or_pronoun": "male",
                    }
                )
                raise app.AppError("DeepSeek message was not valid glossary JSON.", 502)

            with patch.object(settings, "DATA_ROOT", root / "data"), patch.object(
                settings, "OUTPUT_ROOT", output
            ), patch.object(settings, "TRANSLATED_ROOT", translated), patch.object(
                settings, "GLOSSARY_ROOT", glossaries
            ), patch.object(
                bulk_translate, "translate_chapter", fake_translate
            ):
                bulk_translate.start_bulk_translation(
                    "Book One",
                    [{"filename": "001.txt", "title": "Chapter 1", "status": "pending"}],
                )

                deadline = time.time() + 2
                state = bulk_translate.get_bulk_state("Book One")
                while state["running"] and time.time() < deadline:
                    time.sleep(0.02)
                    state = bulk_translate.get_bulk_state("Book One")

            self.assertFalse(state["running"])
            self.assertTrue(state["aborted"])
            self.assertEqual(
                json.loads(glossary.read_text(encoding="utf-8")),
                [
                    {
                        "source_term": "徐邢",
                        "english_term": "Xu Xing",
                        "category": "character",
                        "gender_or_pronoun": "male",
                    }
                ],
            )

    def test_aborted_bulk_translation_stops_and_does_not_resume(self) -> None:
        from novel_translator import bulk_translate

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seen = []

            def fake_translate(
                novel: str,
                filename: str,
                populate_glossary: bool = True,
                should_abort=None,
                defer_existing_glossary_updates: bool = False,
                deferred_existing_glossary_updates=None,
                **kwargs,
            ) -> dict[str, str]:
                seen.append(
                    (
                        novel,
                        filename,
                        populate_glossary,
                        defer_existing_glossary_updates,
                        deferred_existing_glossary_updates is not None,
                    )
                )
                raise app.AppError("Bulk translation aborted.", 409)

            with patch.object(settings, "DATA_ROOT", root / "data"), patch.object(
                bulk_translate, "translate_chapter", fake_translate
            ):
                bulk_translate.start_bulk_translation(
                    "Book One",
                    [
                        {"filename": "001.txt", "title": "Chapter 1", "status": "pending"},
                        {"filename": "002.txt", "title": "Chapter 2", "status": "pending"},
                    ],
                )

                deadline = time.time() + 2
                state = bulk_translate.get_bulk_state("Book One")
                while state["running"] and time.time() < deadline:
                    time.sleep(0.02)
                    state = bulk_translate.get_bulk_state("Book One")

                self.assertFalse(state["running"])
                self.assertTrue(state["aborted"])
                self.assertEqual(seen, [("Book One", "001.txt", True, True, True)])
                self.assertEqual([item["status"] for item in state["items"]], ["aborted", "pending"])

                bulk_translate.get_bulk_state("Book One")
                time.sleep(0.1)

            self.assertEqual(seen, [("Book One", "001.txt", True, True, True)])

    def test_novel_glossary_does_not_fall_back_to_global_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            global_glossary = root / "glossary.json"
            glossaries = root / "glossaries"
            global_glossary.write_text(
                json.dumps(
                    [
                        {
                            "source_term": "太玄界",
                            "english_term": "Taixuan Realm",
                            "category": "place",
                            "gender_or_pronoun": "",
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch.object(settings, "GLOSSARY_PATH", global_glossary), patch.object(
                settings, "GLOSSARY_ROOT", glossaries
            ):
                self.assertEqual(app.load_glossary("Book"), [])
                app.save_glossary(
                    [
                        {
                            "source_term": "徐邢",
                            "english_term": "Xu Xing",
                            "category": "character",
                            "gender_or_pronoun": "male",
                        }
                    ],
                    "Book",
                )
                self.assertEqual(app.load_glossary("Book")[0]["source_term"], "徐邢")
                self.assertTrue((glossaries / "Book" / "glossary" / "glossary.json").exists())

    def test_write_json_replaces_file_without_leaving_temp_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "glossary.json"
            path.write_text(json.dumps([{"source_term": "old"}]), encoding="utf-8")

            app.write_json(path, [{"source_term": "太玄界", "english_term": "Taixuan Realm"}])

            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                [{"source_term": "太玄界", "english_term": "Taixuan Realm"}],
            )
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])

    def test_translate_chapter_writes_output_and_updates_glossary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            translated = root / "translated"
            glossaries = root / "glossaries"
            novel_dir = output / "Book" / "source"
            novel_dir.mkdir(parents=True)
            (novel_dir / "001_第1章.txt").write_text("第1章\n\n太玄界。", encoding="utf-8")
            config = root / "translator_config.json"
            global_glossary = root / "glossary.json"
            glossary = glossaries / "Book" / "glossary" / "glossary.json"
            glossaries.mkdir()
            config.write_text(
                json.dumps(
                    {
                        "api_key": "secret",
                        "translation_model": "deepseek-v4-flash",
                        "glossary_model": "deepseek-v4-pro",
                    }
                ),
                encoding="utf-8",
            )
            calls = []

            def fake_call(api_key: str, model: str, messages: list[dict[str, str]]) -> dict:
                self.assertEqual(api_key, "secret")
                calls.append(model)
                if model == "deepseek-v4-pro":
                    return {
                        "glossary_updates": [
                            {
                                "source_term": "太玄界",
                                "english_term": "Taixuan Realm",
                                "category": "place",
                                "gender_or_pronoun": "",
                            }
                        ]
                    }
                self.assertEqual(model, "deepseek-v4-flash")
                return {
                    "translated_title": "Chapter 1",
                    "translated_body": "The Taixuan Realm.",
                }

            with patch.object(settings, "OUTPUT_ROOT", output), patch.object(
                settings, "TRANSLATED_ROOT", translated
            ), patch.object(settings, "CONFIG_PATH", config), patch.object(
                settings, "GLOSSARY_PATH", global_glossary
            ), patch.object(
                settings, "GLOSSARY_ROOT", glossaries
            ):
                result = app.translate_chapter("Book", "001_第1章.txt", fake_call)

            written = translated / "Book" / "translated" / "001_第1章.txt"
            self.assertTrue(written.exists())
            self.assertIn("The Taixuan Realm.", written.read_text(encoding="utf-8"))
            self.assertEqual(result["glossary"][0]["source_term"], "太玄界")
            self.assertEqual(len(json.loads(glossary.read_text(encoding="utf-8"))), 1)
            self.assertEqual(calls, ["deepseek-v4-pro", "deepseek-v4-flash"])

    def test_translate_only_skips_glossary_population(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            translated = root / "translated"
            glossaries = root / "glossaries"
            novel_dir = output / "Book" / "source"
            novel_dir.mkdir(parents=True)
            (novel_dir / "001_第1章.txt").write_text("第1章\n\n太玄界。", encoding="utf-8")
            config = root / "translator_config.json"
            global_glossary = root / "glossary.json"
            glossary = glossaries / "Book" / "glossary" / "glossary.json"
            glossary.parent.mkdir(parents=True)
            config.write_text(
                json.dumps(
                    {
                        "api_key": "secret",
                        "translation_model": "deepseek-v4-flash",
                        "glossary_model": "deepseek-v4-pro",
                    }
                ),
                encoding="utf-8",
            )
            glossary.write_text(
                json.dumps(
                    [
                        {
                            "source_term": "太玄界",
                            "english_term": "Taixuan Realm",
                            "category": "place",
                            "gender_or_pronoun": "",
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            calls = []

            def fake_call(api_key: str, model: str, messages: list[dict[str, str]]) -> dict:
                calls.append(model)
                self.assertIn("Taixuan Realm", messages[0]["content"])
                return {
                    "translated_title": "Chapter 1",
                    "translated_body": "The Taixuan Realm.",
                }

            with patch.object(settings, "OUTPUT_ROOT", output), patch.object(
                settings, "TRANSLATED_ROOT", translated
            ), patch.object(settings, "CONFIG_PATH", config), patch.object(
                settings, "GLOSSARY_PATH", global_glossary
            ), patch.object(
                settings, "GLOSSARY_ROOT", glossaries
            ):
                app.translate_chapter(
                    "Book", "001_第1章.txt", fake_call, populate_glossary=False
                )

            self.assertEqual(calls, ["deepseek-v4-flash"])

    def test_translate_only_retries_invalid_translation_json_by_continuing_chat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            translated = root / "translated"
            glossaries = root / "glossaries"
            novel_dir = output / "Book" / "source"
            novel_dir.mkdir(parents=True)
            (novel_dir / "001_第1章.txt").write_text("第1章\n\n太玄界。", encoding="utf-8")
            config = root / "translator_config.json"
            global_glossary = root / "glossary.json"
            glossary = glossaries / "Book" / "glossary" / "glossary.json"
            failure_log = root / "deepseek_failures.jsonl"
            glossary.parent.mkdir(parents=True)
            config.write_text(
                json.dumps(
                    {
                        "api_key": "secret",
                        "translation_model": "deepseek-v4-flash",
                        "glossary_model": "deepseek-v4-pro",
                    }
                ),
                encoding="utf-8",
            )
            glossary.write_text("[]", encoding="utf-8")
            calls = []

            def fake_call(api_key: str, model: str, messages: list[dict[str, str]]) -> dict:
                calls.append(json.dumps(messages, ensure_ascii=False))
                if len(calls) < 3:
                    return {"choices": [{"message": {"content": "not json"}}]}
                return {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "translated_title": "Chapter 1",
                                        "translated_body": "The Taixuan Realm.",
                                    }
                                )
                            }
                        }
                    ]
                }

            with patch.object(settings, "OUTPUT_ROOT", output), patch.object(
                settings, "TRANSLATED_ROOT", translated
            ), patch.object(settings, "CONFIG_PATH", config), patch.object(
                settings, "GLOSSARY_PATH", global_glossary
            ), patch.object(
                settings, "GLOSSARY_ROOT", glossaries
            ), patch.object(
                settings, "DEEPSEEK_FAILURE_LOG", failure_log
            ):
                result = app.translate_chapter(
                    "Book", "001_第1章.txt", fake_call, populate_glossary=False
                )

            self.assertEqual(len(calls), 3)
            first_messages = json.loads(calls[0])
            second_messages = json.loads(calls[1])
            third_messages = json.loads(calls[2])
            self.assertEqual(second_messages[:2], first_messages)
            self.assertEqual(second_messages[2], {"role": "assistant", "content": "not json"})
            self.assertIn("not valid JSON", second_messages[3]["content"])
            self.assertEqual(third_messages[:4], second_messages)
            self.assertEqual(third_messages[4], {"role": "assistant", "content": "not json"})
            self.assertIn("resend the corrected translation", third_messages[5]["content"])
            self.assertIn("The Taixuan Realm.", result["translated"])
            log_entries = [json.loads(line) for line in failure_log.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(log_entries), 2)
            self.assertEqual(log_entries[0]["event"], "translation_parse_error")
            self.assertEqual(log_entries[1]["request"]["messages"][:2], log_entries[0]["request"]["messages"])
            self.assertEqual(log_entries[1]["request"]["messages"][2], {"role": "assistant", "content": "not json"})
            self.assertEqual(
                log_entries[0]["response"]["choices"][0]["message"]["content"],
                "not json",
            )

    def test_populate_glossary_retries_invalid_json_by_continuing_chat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            translated = root / "translated"
            glossaries = root / "glossaries"
            novel_dir = output / "Book" / "source"
            novel_dir.mkdir(parents=True)
            (novel_dir / "001_第1章.txt").write_text("第1章\n\n太玄界。", encoding="utf-8")
            config = root / "translator_config.json"
            global_glossary = root / "glossary.json"
            glossary = glossaries / "Book" / "glossary" / "glossary.json"
            failure_log = root / "deepseek_failures.jsonl"
            glossary.parent.mkdir(parents=True)
            config.write_text(
                json.dumps(
                    {
                        "api_key": "secret",
                        "translation_model": "deepseek-v4-flash",
                        "glossary_model": "deepseek-v4-pro",
                    }
                ),
                encoding="utf-8",
            )
            glossary.write_text("[]", encoding="utf-8")
            calls = []

            def fake_call(api_key: str, model: str, messages: list[dict[str, str]]) -> dict:
                calls.append(json.dumps(messages, ensure_ascii=False))
                if len(calls) < 3:
                    return {"choices": [{"message": {"content": "not json"}}]}
                return {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "glossary_updates": [
                                            {
                                                "source_term": "太玄界",
                                                "english_term": "Taixuan Realm",
                                                "category": "place",
                                                "gender_or_pronoun": "",
                                            }
                                        ]
                                    }
                                )
                            }
                        }
                    ]
                }

            with patch.object(settings, "OUTPUT_ROOT", output), patch.object(
                settings, "TRANSLATED_ROOT", translated
            ), patch.object(settings, "CONFIG_PATH", config), patch.object(
                settings, "GLOSSARY_PATH", global_glossary
            ), patch.object(
                settings, "GLOSSARY_ROOT", glossaries
            ), patch.object(
                settings, "DEEPSEEK_FAILURE_LOG", failure_log
            ):
                result = app.populate_glossary_for_chapter("Book", "001_第1章.txt", fake_call)

            self.assertEqual(len(calls), 3)
            first_messages = json.loads(calls[0])
            second_messages = json.loads(calls[1])
            third_messages = json.loads(calls[2])
            self.assertEqual(second_messages[:2], first_messages)
            self.assertEqual(second_messages[2], {"role": "assistant", "content": "not json"})
            self.assertIn("not valid JSON", second_messages[3]["content"])
            self.assertEqual(third_messages[:4], second_messages)
            self.assertEqual(third_messages[4], {"role": "assistant", "content": "not json"})
            self.assertIn("resend the glossary extraction", third_messages[5]["content"])
            self.assertEqual(result[0]["source_term"], "太玄界")
            log_entries = [json.loads(line) for line in failure_log.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(log_entries), 2)
            self.assertEqual(log_entries[0]["event"], "glossary_parse_error")
            self.assertEqual(
                log_entries[0]["response"]["choices"][0]["message"]["content"],
                "not json",
            )

    def test_translate_only_retries_timeout_with_same_messages_and_shared_retry_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            translated = root / "translated"
            glossaries = root / "glossaries"
            novel_dir = output / "Book" / "source"
            novel_dir.mkdir(parents=True)
            (novel_dir / "001_第1章.txt").write_text("第1章\n\n太玄界。", encoding="utf-8")
            config = root / "translator_config.json"
            global_glossary = root / "glossary.json"
            glossary = glossaries / "Book" / "glossary" / "glossary.json"
            glossary.parent.mkdir(parents=True)
            config.write_text(
                json.dumps(
                    {
                        "api_key": "secret",
                        "translation_model": "deepseek-v4-flash",
                        "glossary_model": "deepseek-v4-pro",
                    }
                ),
                encoding="utf-8",
            )
            glossary.write_text("[]", encoding="utf-8")
            calls = []

            def fake_call(api_key: str, model: str, messages: list[dict[str, str]]) -> dict:
                calls.append(json.dumps(messages, ensure_ascii=False))
                if len(calls) == 1:
                    raise app.AppError("DeepSeek request timed out.", 502)
                if len(calls) == 2:
                    return {"choices": [{"message": {"content": "not json"}}]}
                return {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "translated_title": "Chapter 1",
                                        "translated_body": "The Taixuan Realm.",
                                    }
                                )
                            }
                        }
                    ]
                }

            with patch.object(settings, "OUTPUT_ROOT", output), patch.object(
                settings, "TRANSLATED_ROOT", translated
            ), patch.object(settings, "CONFIG_PATH", config), patch.object(
                settings, "GLOSSARY_PATH", global_glossary
            ), patch.object(
                settings, "GLOSSARY_ROOT", glossaries
            ):
                result = app.translate_chapter(
                    "Book", "001_第1章.txt", fake_call, populate_glossary=False
                )

            self.assertEqual(len(calls), 3)
            self.assertEqual(calls[1], calls[0])
            third_messages = json.loads(calls[2])
            self.assertEqual(third_messages[:2], json.loads(calls[0]))
            self.assertEqual(third_messages[2], {"role": "assistant", "content": "not json"})
            self.assertIn("The Taixuan Realm.", result["translated"])

    def test_tiny_translation_with_source_language_uses_incomplete_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            translated = root / "translated"
            glossaries = root / "glossaries"
            novel_dir = output / "Book" / "source"
            novel_dir.mkdir(parents=True)
            long_body = "太玄界。" * 120
            (novel_dir / "001_第1章.txt").write_text(f"第1章\n\n{long_body}", encoding="utf-8")
            config = root / "translator_config.json"
            global_glossary = root / "glossary.json"
            glossary = glossaries / "Book" / "glossary" / "glossary.json"
            glossary.parent.mkdir(parents=True)
            config.write_text(
                json.dumps(
                    {
                        "api_key": "secret",
                        "translation_model": "deepseek-v4-flash",
                        "glossary_model": "deepseek-v4-pro",
                    }
                ),
                encoding="utf-8",
            )
            glossary.write_text("[]", encoding="utf-8")
            calls = []

            def fake_call(api_key: str, model: str, messages: list[dict[str, str]]) -> dict:
                calls.append(messages)
                if len(calls) == 1:
                    return {
                        "translated_title": "Chapter 1",
                        "translated_body": "A streak of 遁光.",
                    }
                self.assertIn("did not provide a complete chapter translation", messages[-1]["content"])
                self.assertIn("translate the entire original chapter again", messages[-1]["content"])
                return {
                    "translated_title": "Chapter 1",
                    "translated_body": "The Taixuan Realm. " * 120,
                }

            with patch.object(settings, "OUTPUT_ROOT", output), patch.object(
                settings, "TRANSLATED_ROOT", translated
            ), patch.object(settings, "CONFIG_PATH", config), patch.object(
                settings, "GLOSSARY_PATH", global_glossary
            ), patch.object(
                settings, "GLOSSARY_ROOT", glossaries
            ):
                result = app.translate_chapter(
                    "Book", "001_第1章.txt", fake_call, populate_glossary=False
                )

            self.assertEqual(len(calls), 2)
            self.assertIn("The Taixuan Realm.", result["translated"])

    def test_translate_only_repairs_remaining_chinese(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            translated = root / "translated"
            glossaries = root / "glossaries"
            novel_dir = output / "Book" / "source"
            novel_dir.mkdir(parents=True)
            (novel_dir / "001_第1章.txt").write_text("第1章\n\n通行區域。", encoding="utf-8")
            config = root / "translator_config.json"
            global_glossary = root / "glossary.json"
            glossary = glossaries / "Book" / "glossary" / "glossary.json"
            glossary.parent.mkdir(parents=True)
            config.write_text(
                json.dumps(
                    {
                        "api_key": "secret",
                        "translation_model": "deepseek-v4-flash",
                        "glossary_model": "deepseek-v4-pro",
                    }
                ),
                encoding="utf-8",
            )
            glossary.write_text("[]", encoding="utf-8")
            calls = []

            def fake_call(api_key: str, model: str, messages: list[dict[str, str]]) -> dict:
                calls.append(messages[0]["content"])
                if len(calls) == 1:
                    return {
                        "translated_title": "Chapter 1",
                        "translated_body": "Outside the 通行 area.",
                    }
                self.assertGreaterEqual(len(messages), 4)
                self.assertEqual(messages[2]["role"], "assistant")
                self.assertIn("Outside the 通行 area.", messages[2]["content"])
                self.assertIn("fragments", messages[-1]["content"])
                return {
                    "replacements": [
                        {"source": "通行", "replacement": "permitted passage"}
                    ]
                }

            with patch.object(settings, "OUTPUT_ROOT", output), patch.object(
                settings, "TRANSLATED_ROOT", translated
            ), patch.object(settings, "CONFIG_PATH", config), patch.object(
                settings, "GLOSSARY_PATH", global_glossary
            ), patch.object(
                settings, "GLOSSARY_ROOT", glossaries
            ):
                result = app.translate_chapter(
                    "Book", "001_第1章.txt", fake_call, populate_glossary=False
                )

            self.assertEqual(len(calls), 2)
            self.assertIn("Outside the permitted passage area.", result["translated"])

    def test_translate_only_repairs_remaining_korean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            translated = root / "translated"
            glossaries = root / "glossaries"
            novel_dir = output / "Book" / "source"
            novel_dir.mkdir(parents=True)
            (novel_dir / "001_1.txt").write_text("1\n\n문.", encoding="utf-8")
            config = root / "translator_config.json"
            global_glossary = root / "glossary.json"
            glossary = glossaries / "Book" / "glossary" / "glossary.json"
            glossary.parent.mkdir(parents=True)
            config.write_text(
                json.dumps(
                    {
                        "api_key": "secret",
                        "translation_model": "deepseek-v4-flash",
                        "glossary_model": "deepseek-v4-pro",
                    }
                ),
                encoding="utf-8",
            )
            glossary.write_text("[]", encoding="utf-8")
            calls = []

            def fake_call(api_key: str, model: str, messages: list[dict[str, str]]) -> dict:
                calls.append(messages)
                if len(calls) == 1:
                    return {
                        "translated_title": "Chapter 1",
                        "translated_body": "He opened the 문.",
                    }
                self.assertIn("Chinese or Korean", messages[-1]["content"])
                return {"replacements": [{"source": "문", "replacement": "door"}]}

            with patch.object(settings, "OUTPUT_ROOT", output), patch.object(
                settings, "TRANSLATED_ROOT", translated
            ), patch.object(settings, "CONFIG_PATH", config), patch.object(
                settings, "GLOSSARY_PATH", global_glossary
            ), patch.object(
                settings, "GLOSSARY_ROOT", glossaries
            ):
                result = app.translate_chapter(
                    "Book", "001_1.txt", fake_call, populate_glossary=False
                )

            self.assertEqual(len(calls), 2)
            self.assertIn("He opened the door.", result["translated"])

    def test_fragment_repair_falls_back_to_full_repair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            translated = root / "translated"
            glossaries = root / "glossaries"
            novel_dir = output / "Book" / "source"
            novel_dir.mkdir(parents=True)
            (novel_dir / "001_第1章.txt").write_text("第1章\n\n遁光。", encoding="utf-8")
            config = root / "translator_config.json"
            global_glossary = root / "glossary.json"
            glossary = glossaries / "Book" / "glossary" / "glossary.json"
            glossary.parent.mkdir(parents=True)
            config.write_text(
                json.dumps(
                    {
                        "api_key": "secret",
                        "translation_model": "deepseek-v4-flash",
                        "glossary_model": "deepseek-v4-pro",
                    }
                ),
                encoding="utf-8",
            )
            glossary.write_text("[]", encoding="utf-8")
            calls = []

            def fake_call(api_key: str, model: str, messages: list[dict[str, str]]) -> dict:
                calls.append(messages[0]["content"])
                if len(calls) == 1:
                    return {
                        "translated_title": "Chapter 1",
                        "translated_body": "A streak of 遁光.",
                    }
                if len(calls) == 2:
                    self.assertGreaterEqual(len(messages), 4)
                    self.assertEqual(messages[2]["role"], "assistant")
                    return {"replacements": [{"source": "遁光", "replacement": "遁 light"}]}
                self.assertIn("repair English novel translation JSON", messages[0]["content"])
                return {
                    "translated_title": "Chapter 1",
                    "translated_body": "A streak of escape light.",
                }

            with patch.object(settings, "OUTPUT_ROOT", output), patch.object(
                settings, "TRANSLATED_ROOT", translated
            ), patch.object(settings, "CONFIG_PATH", config), patch.object(
                settings, "GLOSSARY_PATH", global_glossary
            ), patch.object(
                settings, "GLOSSARY_ROOT", glossaries
            ):
                result = app.translate_chapter(
                    "Book", "001_第1章.txt", fake_call, populate_glossary=False
                )

            self.assertEqual(len(calls), 3)
            self.assertIn("escape light", result["translated"])


if __name__ == "__main__":
    unittest.main()
