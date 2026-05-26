from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app


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
            glossaries = root / "glossaries"
            novel_dir = output / "Book"
            novel_dir.mkdir(parents=True)
            (novel_dir / "001_Chapter.txt").write_text("第1章\n\n正文", encoding="utf-8")
            (translated / "Book").mkdir(parents=True)
            (translated / "Book" / "001_Chapter.txt").write_text(
                "Chapter 1\n\nBody\n", encoding="utf-8"
            )

            self.assertEqual(app.list_novels(output), ["Book"])
            chapters = app.list_chapters("Book", output, translated)

            self.assertEqual(chapters[0]["filename"], "001_Chapter.txt")
            self.assertTrue(chapters[0]["translated"])

    def test_translated_path_preserves_layout(self) -> None:
        root = Path("translated-root")

        self.assertEqual(
            app.translated_path("Novel", "001_Title.txt", root),
            root / "Novel" / "001_Title.txt",
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

    def test_parse_translation_response_rejects_malformed_json(self) -> None:
        payload = {"choices": [{"message": {"content": "not json"}}]}

        with self.assertRaises(app.AppError):
            app.parse_translation_response(payload)

    def test_parse_translation_response_rejects_untranslated_chinese(self) -> None:
        payload = {
            "translated_title": "Chapter 1",
            "translated_body": "太玄界 remains untranslated.",
        }

        with self.assertRaises(app.AppError):
            app.parse_translation_response(payload)

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
        system_prompt = messages[0]["content"]

        self.assertIn("AI-chosen concise category label", system_prompt)
        self.assertNotIn("character|place|sect", system_prompt)

    def test_glossary_category_ui_is_free_text(self) -> None:
        add_row_start = app.INDEX_HTML.index("function addGlossaryRow")
        add_row_end = app.INDEX_HTML.index("function collectGlossary")
        add_row_script = app.INDEX_HTML[add_row_start:add_row_end]

        self.assertIn('entry.category || ""', add_row_script)
        self.assertNotIn("categories.map", add_row_script)
        self.assertNotIn("proper_noun", add_row_script)

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

            with patch.object(app, "GLOSSARY_PATH", global_glossary), patch.object(
                app, "GLOSSARY_ROOT", glossaries
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
                self.assertTrue((glossaries / "Book.json").exists())

    def test_translate_chapter_writes_output_and_updates_glossary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            translated = root / "translated"
            glossaries = root / "glossaries"
            novel_dir = output / "Book"
            novel_dir.mkdir(parents=True)
            (novel_dir / "001_第1章.txt").write_text("第1章\n\n太玄界。", encoding="utf-8")
            config = root / "translator_config.json"
            global_glossary = root / "glossary.json"
            glossary = glossaries / "Book.json"
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

            with patch.object(app, "OUTPUT_ROOT", output), patch.object(
                app, "TRANSLATED_ROOT", translated
            ), patch.object(app, "CONFIG_PATH", config), patch.object(
                app, "GLOSSARY_PATH", global_glossary
            ), patch.object(
                app, "GLOSSARY_ROOT", glossaries
            ):
                result = app.translate_chapter("Book", "001_第1章.txt", fake_call)

            written = translated / "Book" / "001_第1章.txt"
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
            novel_dir = output / "Book"
            novel_dir.mkdir(parents=True)
            (novel_dir / "001_第1章.txt").write_text("第1章\n\n太玄界。", encoding="utf-8")
            config = root / "translator_config.json"
            global_glossary = root / "glossary.json"
            glossary = glossaries / "Book.json"
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
                self.assertIn("Taixuan Realm", messages[1]["content"])
                return {
                    "translated_title": "Chapter 1",
                    "translated_body": "The Taixuan Realm.",
                }

            with patch.object(app, "OUTPUT_ROOT", output), patch.object(
                app, "TRANSLATED_ROOT", translated
            ), patch.object(app, "CONFIG_PATH", config), patch.object(
                app, "GLOSSARY_PATH", global_glossary
            ), patch.object(
                app, "GLOSSARY_ROOT", glossaries
            ):
                app.translate_chapter(
                    "Book", "001_第1章.txt", fake_call, populate_glossary=False
                )

            self.assertEqual(calls, ["deepseek-v4-flash"])

    def test_translate_only_repairs_remaining_chinese(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            translated = root / "translated"
            glossaries = root / "glossaries"
            novel_dir = output / "Book"
            novel_dir.mkdir(parents=True)
            (novel_dir / "001_第1章.txt").write_text("第1章\n\n通行區域。", encoding="utf-8")
            config = root / "translator_config.json"
            global_glossary = root / "glossary.json"
            glossary = glossaries / "Book.json"
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

            with patch.object(app, "OUTPUT_ROOT", output), patch.object(
                app, "TRANSLATED_ROOT", translated
            ), patch.object(app, "CONFIG_PATH", config), patch.object(
                app, "GLOSSARY_PATH", global_glossary
            ), patch.object(
                app, "GLOSSARY_ROOT", glossaries
            ):
                result = app.translate_chapter(
                    "Book", "001_第1章.txt", fake_call, populate_glossary=False
                )

            self.assertEqual(len(calls), 2)
            self.assertIn("Outside the permitted passage area.", result["translated"])

    def test_fragment_repair_falls_back_to_full_repair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            translated = root / "translated"
            glossaries = root / "glossaries"
            novel_dir = output / "Book"
            novel_dir.mkdir(parents=True)
            (novel_dir / "001_第1章.txt").write_text("第1章\n\n遁光。", encoding="utf-8")
            config = root / "translator_config.json"
            global_glossary = root / "glossary.json"
            glossary = glossaries / "Book.json"
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

            with patch.object(app, "OUTPUT_ROOT", output), patch.object(
                app, "TRANSLATED_ROOT", translated
            ), patch.object(app, "CONFIG_PATH", config), patch.object(
                app, "GLOSSARY_PATH", global_glossary
            ), patch.object(
                app, "GLOSSARY_ROOT", glossaries
            ):
                result = app.translate_chapter(
                    "Book", "001_第1章.txt", fake_call, populate_glossary=False
                )

            self.assertEqual(len(calls), 3)
            self.assertIn("escape light", result["translated"])


if __name__ == "__main__":
    unittest.main()
