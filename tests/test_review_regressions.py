import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from novel_translator import bulk_translate, chapters, settings, translation
from novel_translator.errors import AppError
from novel_translator.translation_responses import parse_translation_response


class ReviewRegressionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.enterContext(patch.multiple(
            settings, DATA_ROOT=self.root, OUTPUT_ROOT=self.root,
            TRANSLATED_ROOT=self.root, GLOSSARY_ROOT=self.root,
            LLM_FAILURE_LOG=self.root / "failures.jsonl",
        ))
        config = {
            "openrouter_api_key": "test", "translation_backend": "openrouter",
            "translation_model": "test", "translation_provider": "test",
            "codex_translation_model": "", "translation_reasoning_effort": "none",
            "codex_fast_mode": False,
        }
        self.enterContext(patch.object(translation, "load_config", return_value=config))
        source = self.root / "Book" / "source"
        source.mkdir(parents=True)
        (source / "001.txt").write_text("Title\n" + "天" * 2000, encoding="utf-8")

    def test_short_english_translation_is_retried(self):
        call = Mock(side_effect=[
            {"translated_title": "Title", "translated_body": "The end."},
            {"translated_title": "Title", "translated_body": "The sky. " * 300},
        ])
        result = translation.translate_chapter("Book", "001.txt", call, populate_glossary=False)
        self.assertEqual(call.call_count, 2)
        self.assertIn("complete chapter translation", call.call_args.args[2][-1]["content"])
        self.assertIn(("The sky. " * 300).strip(), result["translated"])

    def test_repeated_truncation_preserves_existing_translation(self):
        target = chapters.write_translation("Book", "001.txt", "Title", "Original complete translation")
        original = target.read_bytes()
        call = Mock(return_value={"translated_title": "Title", "translated_body": "The end."})
        with self.assertRaisesRegex(AppError, "incomplete translation"):
            translation.translate_chapter("Book", "001.txt", call, populate_glossary=False)
        self.assertEqual(call.call_count, 3)
        self.assertEqual(target.read_bytes(), original)

    def test_truncated_full_repair_is_not_saved(self):
        call = Mock(side_effect=[
            {"translated_title": "Title", "translated_body": "The sky. " * 300 + "天"},
            {"replacements": []},
            {"translated_title": "Title", "translated_body": "The end."},
        ])
        with self.assertRaisesRegex(AppError, "incomplete translation"):
            translation.translate_chapter("Book", "001.txt", call, populate_glossary=False)
        self.assertFalse(chapters.translated_path("Book", "001.txt").exists())

    def test_short_source_can_have_short_translation(self):
        result = parse_translation_response(
            {"translated_title": "Title", "translated_body": "The end."}, "终。"
        )
        self.assertEqual(result["translated_body"], "The end.")

    def test_delete_rejects_active_and_aborted_worker_until_it_exits(self):
        entered, release = threading.Event(), threading.Event()

        def translate(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("Test worker timed out")
            raise AppError(bulk_translate.BULK_TRANSLATION_ABORTED_MESSAGE, 409)

        with patch.object(bulk_translate, "translate_chapter", translate):
            bulk_translate.start_bulk_translation("Book", [{"filename": "001.txt", "mode": "only"}])
            worker = bulk_translate._bulk_workers["Book"]
            try:
                self.assertTrue(entered.wait(5))
                for abort in (False, True):
                    if abort:
                        bulk_translate.abort_bulk_translation("Book")
                    with self.assertRaises(AppError) as error:
                        chapters.delete_novel("Book")
                    self.assertEqual(error.exception.status, 409)
                    self.assertTrue((self.root / "Book" / "source" / "001.txt").exists())
            finally:
                release.set()
                worker.join(5)
            self.assertFalse(worker.is_alive())
        chapters.delete_novel("Book")
        self.assertFalse((self.root / "Book").exists())
        self.assertFalse(bulk_translate.bulk_state_path("Book").exists())

    def test_delete_rejects_manual_translation_in_flight(self):
        entered, release = threading.Event(), threading.Event()
        errors = []

        def call(*args):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("Test request timed out")
            return {"translated_title": "Title", "translated_body": "The sky. " * 300}

        def translate():
            try:
                translation.translate_chapter("Book", "001.txt", call, populate_glossary=False)
            except Exception as error:
                errors.append(error)

        worker = threading.Thread(target=translate)
        worker.start()
        try:
            self.assertTrue(entered.wait(5))
            with self.assertRaises(AppError) as error:
                chapters.delete_novel("Book")
            self.assertEqual(error.exception.status, 409)
        finally:
            release.set()
            worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        chapters.delete_novel("Book")
        self.assertFalse((self.root / "Book").exists())

    def test_delete_waits_for_old_aborted_worker_after_replacement_finishes(self):
        entered, release = threading.Event(), threading.Event()
        calls = 0

        def translate(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("Test worker timed out")
                raise AppError(bulk_translate.BULK_TRANSLATION_ABORTED_MESSAGE, 409)

        with patch.object(bulk_translate, "translate_chapter", translate):
            queue = [{"filename": "001.txt", "mode": "only"}]
            bulk_translate.start_bulk_translation("Book", queue)
            old_worker = bulk_translate._bulk_workers["Book"]
            replacement = None
            try:
                self.assertTrue(entered.wait(5))
                bulk_translate.abort_bulk_translation("Book")
                bulk_translate.start_bulk_translation("Book", queue)
                replacement = bulk_translate._bulk_workers["Book"]
                replacement.join(5)
                self.assertFalse(replacement.is_alive())
                with self.assertRaises(AppError) as error:
                    chapters.delete_novel("Book")
                self.assertEqual(error.exception.status, 409)
            finally:
                release.set()
                old_worker.join(5)
                if replacement is not None:
                    replacement.join(5)
        self.assertFalse(old_worker.is_alive())
        chapters.delete_novel("Book")
        self.assertFalse((self.root / "Book").exists())
