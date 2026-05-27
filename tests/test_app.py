from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import app
from novel_translator import settings


class TranslatorAppTests(unittest.TestCase):
    def test_glossary_and_translation_prompts_share_stable_prefix(self) -> None:
        glossary = [
            {
                "source_term": "太玄界",
                "english_term": "Taixuan Realm",
                "category": "place",
                "gender_or_pronoun": "",
            }
        ]

        translation = app.build_messages("第1章", "正文", glossary)[0]["content"]
        glossary_messages = app.build_glossary_messages("第1章", "正文", glossary)[0][
            "content"
        ]

        self.assertTrue(translation.startswith(app.SHARED_PROMPT_PREFIX))
        self.assertTrue(glossary_messages.startswith(app.SHARED_PROMPT_PREFIX))
        self.assertEqual(translation, glossary_messages)
        self.assertIn("Taixuan Realm", translation)

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

            metadata = app.novel_metadata("Book One", output)

            self.assertEqual(app.cover_path("Book One", output), novel_dir / "cover.jpg")
            self.assertEqual(metadata["name"], "Book One")
            self.assertEqual(metadata["cover_url"], "/api/cover?novel=Book%20One")

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

    def test_glossary_prompt_does_not_hardcode_category_options(self) -> None:
        messages = app.build_glossary_messages("第1章", "正文", [])
        user_prompt = messages[1]["content"]

        self.assertIn("AI-chosen concise category label", user_prompt)
        self.assertNotIn("character|place|sect", user_prompt)

    def test_glossary_category_ui_is_free_text(self) -> None:
        app_source = (Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.tsx").read_text(
            encoding="utf-8"
        )

        self.assertIn("entry.category", app_source)
        self.assertNotIn("categories.map", app_source)
        self.assertNotIn("proper_noun", app_source)

    def test_glossary_page_is_rendered(self) -> None:
        app_source = (Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.tsx").read_text(
            encoding="utf-8"
        )

        self.assertIn("GlossaryPage", app_source)
        self.assertIn("Save Glossary", app_source)
        self.assertIn("Add Entry", app_source)

    def test_epub_export_ui_is_rendered(self) -> None:
        app_source = (Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.tsx").read_text(
            encoding="utf-8"
        )
        api_source = (Path(__file__).resolve().parents[1] / "frontend" / "src" / "api.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn("Export EPUB", app_source)
        self.assertIn("exportEpub", app_source)
        self.assertIn("exportEpubUrl", api_source)
        self.assertIn("/api/export/epub", api_source)

    def test_bulk_translation_progress_ui_is_rendered(self) -> None:
        app_source = (Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.tsx").read_text(
            encoding="utf-8"
        )

        self.assertIn("runBulkTranslation", app_source)
        self.assertIn("Bulk Translate", app_source)
        self.assertIn("BulkProgress", app_source)
        self.assertIn("api.translate(novel, item.filename)", app_source)
        self.assertIn('status: "pending"', app_source)

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
