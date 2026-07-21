from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError

import app
from novel_translator import settings
from novel_translator.codex_backend import direct_responses_payload, parse_codex_sse
from novel_translator.server import acquire_server_lock, release_server_lock
from novel_translator.translation import codex_cache_key, configured_api_call


def frontend_source() -> str:
    src = Path(__file__).resolve().parents[1] / "frontend" / "src"
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(src.rglob("*.ts*")))


class TranslatorAppTests(unittest.TestCase):
    def test_load_config_defaults_to_openrouter_and_preserves_codex_choices(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({"api_key": "legacy"}), encoding="utf-8")
            with patch.object(settings, "CONFIG_PATH", path):
                loaded = app.load_config()
                self.assertEqual(loaded["translation_backend"], "openrouter")
                self.assertEqual(loaded["glossary_backend"], "openrouter")

                saved = app.save_config(
                    {
                        "translation_backend": "codex",
                        "glossary_backend": "openrouter",
                        "codex_translation_model": "gpt-test",
                    }
                )

            self.assertEqual(saved["translation_backend"], "codex")
            self.assertEqual(saved["codex_translation_model"], "gpt-test")
            self.assertEqual(saved["openrouter_api_key"], "legacy")

    def test_configured_api_call_routes_codex_without_openrouter_fallback(self) -> None:
        expected = {"choices": []}
        with patch("novel_translator.translation.call_codex", return_value=expected) as call:
            result = configured_api_call(
                app.call_openrouter,
                "openrouter-secret",
                "openrouter/model",
                [{"role": "user", "content": "hello"}],
                "provider",
                "codex",
                "gpt-test",
                {"type": "object"},
                "cache-key",
                "low",
            )

        self.assertIs(result, expected)
        call.assert_called_once_with(
            "gpt-test",
            [{"role": "user", "content": "hello"}],
            {"type": "object"},
            "cache-key",
            "low",
        )

    def test_codex_cache_key_is_stable_per_book_and_workload(self) -> None:
        glossary_key = codex_cache_key("Book", "glossary")

        self.assertEqual(glossary_key, codex_cache_key("Book", "glossary"))
        self.assertNotEqual(glossary_key, codex_cache_key("Book", "translation"))
        self.assertNotEqual(glossary_key, codex_cache_key("Other Book", "glossary"))
        self.assertLessEqual(len(glossary_key), 64)

    def test_codex_model_refresh_preserves_stale_catalog_on_failure(self) -> None:
        model = SimpleNamespace(
            model="gpt-test",
            display_name="GPT Test",
            description="Test model",
            is_default=True,
            hidden=False,
        )
        root = SimpleNamespace(type="chatgpt", email="test@example.com", plan_type="plus")

        class FakeCodex:
            def __init__(self) -> None:
                self.fail = False

            def account(self):
                return SimpleNamespace(account=SimpleNamespace(root=root))

            def models(self):
                if self.fail:
                    raise RuntimeError("catalog unavailable")
                return SimpleNamespace(data=[model])

        service = app.CodexService()
        service._codex = FakeCodex()
        fresh = service.models(refresh=True)
        service._codex.fail = True
        stale = service.models(refresh=True)

        self.assertEqual(fresh["models"][0]["id"], "gpt-test")
        self.assertTrue(stale["stale"])
        self.assertIn("catalog unavailable", stale["error"])
        self.assertEqual(stale["models"], fresh["models"])

    def test_codex_usage_reports_remaining_windows_and_optional_credits(self) -> None:
        window = SimpleNamespace(used_percent=25, window_duration_mins=300, resets_at=1234)
        root = SimpleNamespace(type="chatgpt", email="test@example.com", plan_type="plus")
        credits = SimpleNamespace(model_dump=lambda **_: {"balance": "10", "hasCredits": True})
        snapshot = SimpleNamespace(
            plan_type="plus",
            limit_name="Codex",
            primary=window,
            secondary=None,
            rate_limit_reached_type=None,
            credits=credits,
            individual_limit=None,
        )

        class FakeCodex:
            def account(self):
                return SimpleNamespace(account=SimpleNamespace(root=root))

        service = app.CodexService()
        service._codex = FakeCodex()
        service._read_rate_limits = lambda: SimpleNamespace(rate_limits=snapshot)
        usage = service.usage(refresh=True)

        self.assertEqual(usage["primary"]["remaining_percent"], 75)
        self.assertEqual(usage["primary"]["window_duration_mins"], 300)
        self.assertEqual(usage["credits"]["balance"], "10")

    def test_codex_call_uses_direct_responses_adapter(self) -> None:
        app.reset_usage()
        self.addCleanup(app.reset_usage)
        model = SimpleNamespace(
            model="gpt-test",
            display_name="GPT Test",
            description="Test model",
            is_default=True,
            hidden=False,
        )
        root = SimpleNamespace(type="chatgpt", email="test@example.com", plan_type="plus")
        seen = {}

        class FakeCodex:
            def account(self):
                return SimpleNamespace(account=SimpleNamespace(root=root))

            def models(self):
                return SimpleNamespace(data=[model])

        class FakeResponses:
            def call(
                self,
                client,
                selected_model,
                messages,
                output_schema,
                cache_key="",
                reasoning_effort="none",
            ):
                seen["client"] = client
                seen["model"] = selected_model
                seen["messages"] = messages
                seen["output_schema"] = output_schema
                seen["cache_key"] = cache_key
                seen["reasoning_effort"] = reasoning_effort
                return {
                    "choices": [{"message": {"content": '{"translated_name":"Test"}'}}],
                    "usage": {
                        "prompt_tokens": 20,
                        "completion_tokens": 7,
                        "total_tokens": 27,
                        "cost": 0.0,
                    },
                }

        service = app.CodexService()
        service._codex = FakeCodex()
        service._responses = FakeResponses()
        self.addCleanup(service.close)
        service.usage = lambda refresh=False: {}
        response = service.call(
            "gpt-test",
            [{"role": "user", "content": "Translate this"}],
            {"type": "object"},
            "cache-key",
        )

        self.assertIs(seen["client"], service._codex)
        self.assertEqual(seen["model"], "gpt-test")
        self.assertEqual(seen["messages"], [{"role": "user", "content": "Translate this"}])
        self.assertEqual(seen["output_schema"], {"type": "object"})
        self.assertEqual(seen["cache_key"], "cache-key")
        self.assertEqual(seen["reasoning_effort"], "none")
        self.assertEqual(response["usage"]["total_tokens"], 27)

    def test_direct_codex_payload_has_no_tools_and_uses_lowest_reasoning(self) -> None:
        schema = {"type": "object", "properties": {"result": {"type": "string"}}}
        payload = direct_responses_payload(
            "gpt-test",
            [
                {"role": "system", "content": "Translate accurately."},
                {"role": "user", "content": "Text"},
            ],
            schema,
            "cache-key",
        )

        self.assertEqual(payload["instructions"], "Translate accurately.")
        self.assertEqual(payload["reasoning"]["effort"], "none")
        self.assertFalse(payload["text"]["format"]["strict"])
        self.assertEqual(payload["text"]["format"]["schema"], schema)
        self.assertNotIn("tools", payload)
        self.assertEqual(payload["prompt_cache_key"], "cache-key")

        for effort in ("low", "medium", "high"):
            reasoning_payload = direct_responses_payload(
                "gpt-test", [], schema, reasoning_effort=effort
            )
            self.assertEqual(reasoning_payload["reasoning"]["effort"], effort)

    def test_direct_codex_stream_reports_responses_usage(self) -> None:
        events = [
            b'data: {"type":"response.output_text.delta","delta":"{\\"result\\":\\"ok\\"}"}',
            b'data: {"type":"response.completed","response":{"usage":{"input_tokens":12,"input_tokens_details":{"cached_tokens":8},"output_tokens":3,"total_tokens":15}}}',
            b"data: [DONE]",
        ]
        response = SimpleNamespace(iter_lines=lambda decode_unicode=True: iter(events))

        parsed = parse_codex_sse(response)

        self.assertEqual(parsed["choices"][0]["message"]["content"], '{"result":"ok"}')
        self.assertEqual(parsed["usage"]["prompt_tokens"], 12)
        self.assertEqual(parsed["usage"]["total_tokens"], 15)
        self.assertEqual(parsed["usage"]["prompt_tokens_details"]["cached_tokens"], 8)

    def test_successful_codex_login_is_not_failed_by_usage_refresh(self) -> None:
        service = app.CodexService()
        handle = SimpleNamespace(wait=lambda: SimpleNamespace(success=True, error=None))
        service.models = lambda refresh=False: {"models": []}

        def fail_usage(refresh=False):
            raise RuntimeError("usage unavailable")

        service.usage = fail_usage
        service._login_handle = handle
        service._wait_for_login(handle)

        self.assertEqual(service._login_status, "signed_in")
        self.assertEqual(service._login_error, "")

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

    def test_lists_chapters_in_numeric_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            novel_dir = output / "Book" / "source"
            novel_dir.mkdir(parents=True)
            for name in ["099_Chapter.txt", "1000_Chapter.txt", "100_Chapter.txt"]:
                (novel_dir / name).write_text("第1章\n\n正文", encoding="utf-8")

            chapters = app.list_chapters("Book", output)

            self.assertEqual(
                [chapter["filename"] for chapter in chapters],
                ["099_Chapter.txt", "100_Chapter.txt", "1000_Chapter.txt"],
            )

    def test_list_chapters_reuses_persisted_chapter_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            translated = root / "translated"
            source_dir = output / "Book" / "source"
            translated_dir = translated / "Book" / "translated"
            source_dir.mkdir(parents=True)
            translated_dir.mkdir(parents=True)
            (source_dir / "001_Source.txt").write_text("第1章\n\n正文", encoding="utf-8")
            (translated_dir / "001_Source.txt").write_text("Chapter 1\n\nBody", encoding="utf-8")

            expected = app.list_chapters("Book", output, translated)

            self.assertTrue((output / "Book" / "chapter_index.json").is_file())
            with patch(
                "novel_translator.chapters.chapter_label",
                side_effect=AssertionError("index was rebuilt"),
            ):
                self.assertEqual(app.list_chapters("Book", output, translated), expected)

    def test_list_chapters_rebuilds_index_when_source_files_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            source_dir = output / "Book" / "source"
            source_dir.mkdir(parents=True)
            (source_dir / "001_Source.txt").write_text("第1章\n\n正文", encoding="utf-8")
            app.list_chapters("Book", output)

            (source_dir / "002_Source.txt").write_text("第2章\n\n正文", encoding="utf-8")

            self.assertEqual(
                [chapter["filename"] for chapter in app.list_chapters("Book", output)],
                ["001_Source.txt", "002_Source.txt"],
            )

    def test_write_translation_updates_persisted_chapter_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            translated = root / "translated"
            source_dir = output / "Book" / "source"
            source_dir.mkdir(parents=True)
            (source_dir / "001_Source.txt").write_text("第1章\n\n正文", encoding="utf-8")

            with patch.object(settings, "OUTPUT_ROOT", output), patch.object(
                settings, "TRANSLATED_ROOT", translated
            ):
                self.assertFalse(app.list_chapters("Book")[0]["translated"])
                app.write_translation("Book", "001_Source.txt", "Chapter 1", "Body")
                chapter = app.list_chapters("Book")[0]

            self.assertTrue(chapter["translated"])
            self.assertEqual(chapter["title"], "001 Chapter 1")
            self.assertGreater(chapter["translated_size"], 0)

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

    def test_library_metadata_returns_all_books_in_one_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            for name in ("Book One", "Book Two"):
                source = output / name / "source"
                source.mkdir(parents=True)
                (source / "001_Chapter.txt").write_text("Chapter\n\nBody", encoding="utf-8")
            (output / "Book Two" / "source" / "cover.jpg").write_bytes(b"cover")

            library = app.library_metadata(output)

            self.assertEqual(library["novels"], ["Book One", "Book Two"])
            self.assertEqual(set(library["metadata"]), {"Book One", "Book Two"})
            self.assertEqual(library["metadata"]["Book One"]["translated_name"], "Book One")
            self.assertIsNone(library["metadata"]["Book One"]["cover_url"])
            self.assertEqual(
                library["metadata"]["Book Two"]["cover_url"],
                "/api/cover?novel=Book%20Two",
            )

    def test_library_uses_batch_metadata_with_retries(self) -> None:
        root = Path(__file__).resolve().parents[1]
        api_source = (root / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")
        library_source = (root / "frontend" / "src" / "hooks" / "useLibrary.ts").read_text(
            encoding="utf-8"
        )
        server_source = (root / "novel_translator" / "server.py").read_text(encoding="utf-8")

        self.assertIn("/api/novels/metadata", api_source)
        self.assertIn("requestWithRetry<LibraryMetadata>", api_source)
        self.assertIn("api.libraryMetadata()", library_source)
        self.assertNotIn("nextNovels.map(async", library_source)
        self.assertIn('parsed.path == "/api/novels/metadata"', server_source)

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

    def test_delete_novel_removes_source_translation_glossary_and_bulk_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            translated = root / "translated"
            glossary = root / "glossary"
            data = root / "data"
            (output / "Book" / "source").mkdir(parents=True)
            (translated / "Book" / "translated").mkdir(parents=True)
            (glossary / "Book" / "glossary").mkdir(parents=True)
            (data / "bulk").mkdir(parents=True)
            (output / "Book" / "source" / "001.txt").write_text("第1章\n正文", encoding="utf-8")
            (translated / "Book" / "translated" / "001.txt").write_text("Chapter\nBody", encoding="utf-8")
            (glossary / "Book" / "glossary" / "glossary.json").write_text("[]", encoding="utf-8")
            (data / "bulk" / "Book.json").write_text("{}", encoding="utf-8")

            with (
                patch.object(settings, "OUTPUT_ROOT", output),
                patch.object(settings, "TRANSLATED_ROOT", translated),
                patch.object(settings, "GLOSSARY_ROOT", glossary),
                patch.object(settings, "DATA_ROOT", data),
            ):
                self.assertEqual(app.delete_novel("Book"), {"deleted": "Book"})

            self.assertFalse((output / "Book").exists())
            self.assertFalse((translated / "Book").exists())
            self.assertFalse((glossary / "Book").exists())
            self.assertFalse((data / "bulk" / "Book.json").exists())

    def test_delete_novel_rejects_missing_book(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            with patch.object(settings, "OUTPUT_ROOT", output):
                with self.assertRaises(app.AppError) as caught:
                    app.delete_novel("Missing")

            self.assertEqual(caught.exception.status, 404)

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

    def test_parse_translation_response_from_model_message(self) -> None:
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

    def test_records_and_resets_openrouter_usage_cost(self) -> None:
        app.reset_usage()

        app.record_llm_usage(
            "deepseek-v4-flash",
            {
                "usage": {
                    "prompt_cache_hit_tokens": 100,
                    "prompt_cache_miss_tokens": 200,
                    "prompt_tokens": 300,
                    "completion_tokens": 400,
                    "completion_tokens_details": {"reasoning_tokens": 50},
                    "total_tokens": 700,
                    "cost": 0.0123,
                }
            },
        )
        app.record_llm_usage(
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
        self.assertEqual(flash["reasoning_tokens"], 50)
        self.assertEqual(flash["total_tokens"], 700)
        self.assertEqual(flash["cost_usd"], 0.0123)
        self.assertEqual(pro["total_tokens"], 70)
        self.assertEqual(pro["cost_usd"], 0.0)
        self.assertEqual(usage["total"]["total_tokens"], 770)
        self.assertEqual(usage["total"]["reasoning_tokens"], 50)
        self.assertEqual(usage["total"]["cost_usd"], 0.0123)
        self.assertEqual(app.reset_usage()["total"]["total_tokens"], 0)

    def test_records_openrouter_usage_cost_for_custom_models(self) -> None:
        app.reset_usage()

        app.record_llm_usage(
            "custom/model",
            {
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                    "cost": 0,
                    "cost_details": {"upstream_inference_cost": 1.5},
                }
            },
        )

        usage = app.current_usage()
        self.assertEqual(usage["by_model"]["custom/model"]["total_tokens"], 15)
        self.assertEqual(usage["by_model"]["custom/model"]["cost_usd"], 1.5)
        self.assertEqual(usage["total"]["cost_usd"], 1.5)

    def test_records_openrouter_cost_without_double_counting_upstream_cost(self) -> None:
        app.reset_usage()

        app.record_llm_usage(
            "custom/model",
            {
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                    "cost": 0.25,
                    "cost_details": {"upstream_inference_cost": 0.26},
                }
            },
        )

        self.assertEqual(app.current_usage()["total"]["cost_usd"], 0.25)

    def test_parse_translation_response_rejects_malformed_json(self) -> None:
        payload = {"choices": [{"message": {"content": "not json"}}]}

        with self.assertRaises(app.AppError):
            app.parse_translation_response(payload)

    def test_call_openrouter_uses_300_second_timeout(self) -> None:
        from novel_translator.openrouter import OPENROUTER_TIMEOUT_SECONDS

        seen = {}

        def fake_opener(request, timeout: int):
            seen["timeout"] = timeout
            raise TimeoutError("The read operation timed out")

        with tempfile.TemporaryDirectory() as tmp, patch.object(
            settings, "LLM_FAILURE_LOG", Path(tmp) / "llm_failures.jsonl"
        ):
            with self.assertRaises(app.AppError):
                app.call_openrouter("secret", "deepseek-v4-flash", [], fake_opener)

        self.assertEqual(OPENROUTER_TIMEOUT_SECONDS, 300)
        self.assertEqual(seen["timeout"], 300)

    def test_call_openrouter_uses_configured_openrouter_model_id_with_same_parameters(self) -> None:
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

        app.call_openrouter(
            "secret",
            "xiaomi/mimo-v2.5-pro",
            [{"role": "user", "content": "Hi"}],
            "xiaomi",
            fake_opener,
            reasoning_effort="low",
        )

        self.assertEqual(seen["url"], settings.OPENROUTER_URL)
        self.assertEqual(seen["authorization"], "Bearer secret")
        self.assertEqual(
            seen["payload"],
            {
                "model": "xiaomi/mimo-v2.5-pro",
                "messages": [{"role": "user", "content": "Hi"}],
                "reasoning": {"effort": "low", "exclude": True},
                "temperature": 1,
                "stream": False,
                "response_format": {"type": "json_object"},
                "provider": {
                    "only": ["xiaomi"],
                    "allow_fallbacks": False,
                },
            },
        )

    def test_call_openrouter_pins_custom_model_provider(self) -> None:
        seen = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self) -> bytes:
                return b'{"usage": {"prompt_tokens": 1, "cost": 0.01}}'

        def fake_opener(request, timeout: int):
            seen["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        app.call_openrouter(
            "secret",
            "anthropic/claude-sonnet-4.5",
            [{"role": "user", "content": "Hi"}],
            "anthropic",
            fake_opener,
        )

        self.assertEqual(seen["payload"]["model"], "anthropic/claude-sonnet-4.5")
        self.assertEqual(
            seen["payload"]["provider"],
            {"only": ["anthropic"], "allow_fallbacks": False},
        )

    def test_call_openrouter_retries_without_json_object_and_remembers_model_provider(self) -> None:
        payloads = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self) -> bytes:
                return b'{"usage": {"prompt_tokens": 1, "cost": 0.01}}'

        class FakeErrorBody:
            def __init__(self, body: bytes):
                self.body = body

            def read(self) -> bytes:
                return self.body

            def close(self) -> None:
                return None

        def fake_opener(request, timeout: int):
            payload = json.loads(request.data.decode("utf-8"))
            payloads.append(payload)
            if len(payloads) == 1:
                raise HTTPError(
                    request.full_url,
                    400,
                    "Bad Request",
                    {},
                    FakeErrorBody(b'{"error":{"message":"Model does not support json_object response_format."}}'),
                )
            return FakeResponse()

        app.call_openrouter(
            "secret",
            "test/json-object-memory",
            [{"role": "user", "content": "Hi"}],
            "test-provider",
            fake_opener,
        )
        app.call_openrouter(
            "secret",
            "test/json-object-memory",
            [{"role": "user", "content": "Hi"}],
            "test-provider",
            fake_opener,
        )

        self.assertEqual(payloads[0]["response_format"], {"type": "json_object"})
        self.assertNotIn("response_format", payloads[1])
        self.assertNotIn("response_format", payloads[2])
        self.assertEqual(payloads[2]["provider"], {"only": ["test-provider"], "allow_fallbacks": False})

    def test_call_openrouter_falls_back_from_non_strict_schema_to_json_object_to_none(self) -> None:
        payloads = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self) -> bytes:
                return b'{"choices":[{"message":{"content":"{}"}}]}'

        class FakeErrorBody:
            def __init__(self, body: bytes):
                self.body = body

            def read(self) -> bytes:
                return self.body

            def close(self) -> None:
                return None

        def fake_opener(request, timeout: int):
            payload = json.loads(request.data.decode("utf-8"))
            payloads.append(payload)
            response_type = payload.get("response_format", {}).get("type")
            if response_type == "json_schema":
                raise HTTPError(
                    request.full_url,
                    400,
                    "Bad Request",
                    {},
                    FakeErrorBody(b'{"error":{"message":"This response format is unavailable"}}'),
                )
            if response_type == "json_object":
                raise HTTPError(
                    request.full_url,
                    400,
                    "Bad Request",
                    {},
                    FakeErrorBody(b'{"error":{"message":"This response_format type is unavailable"}}'),
                )
            return FakeResponse()

        schema = {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        }
        app.call_openrouter(
            "secret",
            "test/schema-fallback-memory",
            [{"role": "user", "content": "Hi"}],
            "test-provider",
            fake_opener,
            schema,
        )
        app.call_openrouter(
            "secret",
            "test/schema-fallback-memory",
            [{"role": "user", "content": "Hi"}],
            "test-provider",
            fake_opener,
            schema,
        )

        schema_format = payloads[0]["response_format"]
        self.assertEqual(schema_format["type"], "json_schema")
        self.assertFalse(schema_format["json_schema"]["strict"])
        self.assertEqual(schema_format["json_schema"]["schema"], schema)
        self.assertEqual(payloads[1]["response_format"], {"type": "json_object"})
        self.assertNotIn("response_format", payloads[2])
        self.assertNotIn("response_format", payloads[3])

    def test_openrouter_model_providers_returns_endpoint_providers(self) -> None:
        seen = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self) -> bytes:
                return json.dumps(
                    {
                        "data": {
                            "endpoints": [
                                {"tag": "anthropic", "provider_name": "Anthropic"},
                                {"tag": "anthropic", "provider_name": "Anthropic duplicate"},
                                {"tag": "google-vertex", "provider_name": "Google Vertex"},
                            ]
                        }
                    }
                ).encode("utf-8")

        def fake_opener(request, timeout: int):
            seen["url"] = request.full_url
            seen["authorization"] = request.headers["Authorization"]
            return FakeResponse()

        providers = app.openrouter_model_providers(
            "anthropic/claude-sonnet-4.5", "secret", fake_opener
        )

        self.assertEqual(
            seen["url"],
            "https://openrouter.ai/api/v1/models/anthropic/claude-sonnet-4.5/endpoints",
        )
        self.assertEqual(seen["authorization"], "Bearer secret")
        self.assertEqual(
            providers,
            [
                {"provider": "anthropic", "name": "Anthropic"},
                {"provider": "google-vertex", "name": "Google Vertex"},
            ],
        )

    def test_save_config_accepts_openrouter_model_choices(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            settings, "CONFIG_PATH", Path(tmp) / "translator_config.json"
        ):
            saved = app.save_config(
                {
                    "openrouter_api_key": "secret",
                    "translation_model": "xiaomi/mimo-v2.5",
                    "translation_provider": "xiaomi",
                    "glossary_model": "xiaomi/mimo-v2.5-pro",
                    "glossary_provider": "xiaomi",
                    "translation_reasoning_effort": "high",
                    "glossary_reasoning_effort": "medium",
                }
            )

        self.assertEqual(saved["openrouter_api_key"], "secret")
        self.assertEqual(saved["translation_model"], "xiaomi/mimo-v2.5")
        self.assertEqual(saved["translation_provider"], "xiaomi")
        self.assertEqual(saved["glossary_model"], "xiaomi/mimo-v2.5-pro")
        self.assertEqual(saved["glossary_provider"], "xiaomi")
        self.assertEqual(saved["translation_reasoning_effort"], "high")
        self.assertEqual(saved["glossary_reasoning_effort"], "medium")

    def test_save_config_accepts_custom_models_providers_and_added_models(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            settings, "CONFIG_PATH", Path(tmp) / "translator_config.json"
        ):
            saved = app.save_config(
                {
                    "openrouter_api_key": "secret",
                    "translation_model": "anthropic/claude-sonnet-4.5",
                    "translation_provider": "anthropic",
                    "glossary_model": "google/gemini-2.5-flash",
                    "glossary_provider": "google-ai-studio",
                    "added_models": [
                        {"model": "anthropic/claude-sonnet-4.5", "provider": "anthropic"},
                        {"model": "anthropic/claude-sonnet-4.5", "provider": "anthropic"},
                        {"model": "", "provider": "missing"},
                    ],
                }
            )
            loaded = app.load_config()

        self.assertEqual(saved["translation_model"], "anthropic/claude-sonnet-4.5")
        self.assertEqual(saved["translation_provider"], "anthropic")
        self.assertEqual(saved["glossary_model"], "google/gemini-2.5-flash")
        self.assertEqual(saved["glossary_provider"], "google-ai-studio")
        self.assertEqual(
            loaded["added_models"],
            [{"model": "anthropic/claude-sonnet-4.5", "provider": "anthropic"}],
        )

    def test_load_config_migrates_legacy_saved_models_to_added_models(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            settings, "CONFIG_PATH", Path(tmp) / "translator_config.json"
        ):
            (Path(tmp) / "translator_config.json").write_text(
                json.dumps(
                    {
                        "translation_model": "deepseek-v4-flash",
                        "translation_provider": "deepseek",
                        "glossary_model": "deepseek-v4-flash",
                        "glossary_provider": "deepseek",
                        "favorite_models": [
                            {"model": "tencent/hy3:free", "provider": "novita"}
                        ],
                    }
                ),
                encoding="utf-8",
            )

            loaded = app.load_config()

        self.assertEqual(loaded["added_models"], [{"model": "tencent/hy3:free", "provider": "novita"}])

    def test_save_config_rejects_blank_custom_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            settings, "CONFIG_PATH", Path(tmp) / "translator_config.json"
        ):
            with self.assertRaises(app.AppError):
                app.save_config(
                    {
                        "openrouter_api_key": "secret",
                        "translation_model": "anthropic/claude-sonnet-4.5",
                        "translation_provider": "",
                        "glossary_model": "deepseek-v4-flash",
                        "glossary_provider": "deepseek",
                    }
                )

    def test_load_config_migrates_legacy_api_key_to_openrouter_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            settings, "CONFIG_PATH", Path(tmp) / "translator_config.json"
        ):
            settings.CONFIG_PATH.write_text(
                json.dumps({"api_key": "legacy-secret"}), encoding="utf-8"
            )
            loaded = app.load_config()

        self.assertEqual(loaded["openrouter_api_key"], "legacy-secret")

    def test_save_config_preserves_openrouter_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            settings, "CONFIG_PATH", Path(tmp) / "translator_config.json"
        ):
            app.save_config(
                {
                    "openrouter_api_key": "openrouter-secret",
                    "translation_model": "deepseek-v4-flash",
                    "glossary_model": "deepseek-v4-flash",
                }
            )
            saved = app.save_config(
                {
                    "keep_existing_openrouter_key": True,
                    "translation_model": "deepseek-v4-pro",
                    "glossary_model": "mimo-v2.5",
                }
            )

        self.assertEqual(saved["openrouter_api_key"], "openrouter-secret")
        self.assertEqual(saved["translation_model"], "deepseek/deepseek-v4-pro")
        self.assertEqual(saved["glossary_model"], "xiaomi/mimo-v2.5")

    def test_save_config_preserves_omitted_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            settings, "CONFIG_PATH", Path(tmp) / "translator_config.json"
        ):
            app.save_config(
                {
                    "openrouter_api_key": "openrouter-secret",
                    "translation_model": "deepseek-v4-flash",
                    "glossary_model": "deepseek-v4-flash",
                }
            )
            saved = app.save_config(
                {
                    "translation_model": "mimo-v2.5-pro",
                    "glossary_model": "deepseek-v4-pro",
                }
            )

        self.assertEqual(saved["openrouter_api_key"], "openrouter-secret")
        self.assertEqual(saved["translation_model"], "xiaomi/mimo-v2.5-pro")

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
                self.assertEqual(model, "deepseek/deepseek-v4-pro")
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

    def test_loading_a_book_clears_stale_chapters_before_requesting_new_ones(self) -> None:
        app_source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.tsx"
        ).read_text(encoding="utf-8")
        load_start = app_source.index("const loadChapters")
        request_start = app_source.index("await api.chapters(nextNovel)", load_start)
        loading_setup = app_source[load_start:request_start]

        self.assertIn("setChapters([]);", loading_setup)

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

    def test_settings_page_owns_key_and_models(self) -> None:
        root = Path(__file__).resolve().parents[1]
        app_source = frontend_source()
        translate_source = (root / "frontend" / "src" / "pages" / "TranslatePage.tsx").read_text(
            encoding="utf-8"
        )
        glossary_source = (root / "frontend" / "src" / "pages" / "GlossaryPage.tsx").read_text(
            encoding="utf-8"
        )

        self.assertIn('pathname === "/settings"', app_source)
        self.assertIn("SettingsPage", app_source)
        self.assertIn("openrouter_api_key", app_source)
        self.assertNotIn("nvidia_api_key", app_source)
        self.assertIn("translation_provider", app_source)
        self.assertIn("glossary_provider", app_source)
        self.assertIn("added_models", app_source)
        self.assertNotIn("ModelSelect", translate_source)
        self.assertNotIn("OpenRouter API key", glossary_source)

    def test_single_translation_uses_persisted_queue_and_progress_status(self) -> None:
        app_source = frontend_source()

        self.assertIn('onTranslate("full")', app_source)
        self.assertIn('onTranslate("only")', app_source)
        self.assertIn("useBulkTranslation", app_source)
        self.assertIn("Translating ${current}/${state.items.length} chapters", app_source)

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
                raise app.AppError("Model message was not valid glossary JSON.", 502)

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
                raise app.AppError("Model message was not valid glossary JSON.", 502)

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

    def test_new_bulk_translation_can_start_while_aborted_worker_unwinds(self) -> None:
        from novel_translator import bulk_translate

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_started = threading.Event()
            release_first = threading.Event()

            def fake_translate(
                novel: str,
                filename: str,
                populate_glossary: bool = True,
                should_abort=None,
                **kwargs,
            ) -> dict[str, str]:
                if filename == "001.txt":
                    first_started.set()
                    self.assertTrue(release_first.wait(2))
                    self.assertTrue(should_abort())
                    raise app.AppError("Bulk translation aborted.", 409)
                return {"filename": filename}

            with patch.object(settings, "DATA_ROOT", root / "data"), patch.object(
                bulk_translate, "translate_chapter", fake_translate
            ):
                bulk_translate.start_bulk_translation(
                    "Book One",
                    [{"filename": "001.txt", "title": "Chapter 1", "status": "pending"}],
                )
                self.assertTrue(first_started.wait(2))

                aborted = bulk_translate.abort_bulk_translation("Book One")
                self.assertFalse(aborted["running"])
                bulk_translate.start_bulk_translation(
                    "Book One",
                    [{"filename": "002.txt", "title": "Chapter 2", "status": "pending"}],
                )
                release_first.set()

                deadline = time.time() + 2
                state = bulk_translate.get_bulk_state("Book One")
                while state["running"] and time.time() < deadline:
                    time.sleep(0.02)
                    state = bulk_translate.get_bulk_state("Book One")

                self.assertFalse(state["running"])
                self.assertFalse(state["aborted"])
                self.assertEqual([item["filename"] for item in state["items"]], ["002.txt"])
                self.assertEqual([item["status"] for item in state["items"]], ["done"])

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
                if model == "deepseek/deepseek-v4-pro":
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
                self.assertEqual(model, "deepseek/deepseek-v4-flash")
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
            self.assertEqual(calls, ["deepseek/deepseek-v4-pro", "deepseek/deepseek-v4-flash"])

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

            self.assertEqual(calls, ["deepseek/deepseek-v4-flash"])

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
            failure_log = root / "llm_failures.jsonl"
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
                settings, "LLM_FAILURE_LOG", failure_log
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
            failure_log = root / "llm_failures.jsonl"
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
                settings, "LLM_FAILURE_LOG", failure_log
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
                    raise app.AppError("OpenRouter request timed out.", 502)
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

    def test_second_server_cannot_share_an_existing_port(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "novel_translator.server.settings.DATA_ROOT", Path(temp_dir)
        ):
            first = acquire_server_lock(8765)
            try:
                with self.assertRaises(OSError):
                    acquire_server_lock(8765)
            finally:
                release_server_lock(first)


if __name__ == "__main__":
    unittest.main()
