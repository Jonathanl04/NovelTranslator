import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from novel_translator import settings
from novel_translator.bulk_translate import (
    flush_pending_glossary_updates,
    load_bulk_state,
    save_bulk_state,
)
from novel_translator.glossary_strategy import (
    entries_in_chapter_order,
    finish_rolling_glossary_chapter,
    prepare_rolling_glossary_prompt,
    rolling_glossary_snapshot,
)


def entry(source: str, english: str) -> dict[str, str]:
    return {
        "source_term": source,
        "english_term": english,
        "category": "term",
        "gender_or_pronoun": "",
    }


class GlossaryStrategyTests(unittest.TestCase):
    def test_chapter_matches_use_occurrence_order_not_glossary_order(self) -> None:
        glossary = [
            entry("后出现", "later"),
            entry("先出现", "first"),
            entry("先", "first-short"),
        ]

        matches = entries_in_chapter_order(glossary, "先出现，然后后出现。")

        self.assertEqual(
            [item["source_term"] for item in matches],
            ["先出现", "先", "后出现"],
        )

    def test_snapshot_scans_only_the_requested_lookback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "Book" / "source"
            source.mkdir(parents=True)
            (source / "1_one.txt").write_text("第一章\n旧词", encoding="utf-8")
            (source / "2_two.txt").write_text("第二章\n近期词", encoding="utf-8")
            (source / "3_three.txt").write_text("第三章\n当前词", encoding="utf-8")
            with patch.object(settings, "OUTPUT_ROOT", root), patch.object(
                settings, "TRANSLATED_ROOT", root
            ):
                snapshot = rolling_glossary_snapshot(
                    "Book",
                    "3_three.txt",
                    [entry("旧词", "old"), entry("近期词", "recent")],
                    window=1,
                )

        self.assertEqual([item["source_term"] for item in snapshot], ["近期词"])

    def test_prepare_appends_reactivated_entries_in_chapter_order(self) -> None:
        state = {
            "epoch_start_filename": "200.txt",
            "processed": 10,
            "snapshot": [entry("固定", "fixed")],
            "additions": [entry("已有新增", "existing addition")],
        }
        glossary = [
            entry("后出现", "later"),
            entry("固定", "fixed"),
            entry("先出现", "first"),
        ]

        next_state, prompt = prepare_rolling_glossary_prompt(
            "Book", "210.txt", "先出现，然后后出现。", glossary, state
        )

        self.assertEqual(
            [item["source_term"] for item in prompt],
            ["固定", "已有新增", "先出现", "后出现"],
        )
        self.assertEqual(next_state["processed"], 10)

    def test_finish_appends_new_entries_and_advances_epoch(self) -> None:
        state = {
            "epoch_start_filename": "200.txt",
            "processed": 10,
            "snapshot": [entry("固定", "fixed")],
            "additions": [entry("回归", "returned")],
        }
        before = [entry("固定", "fixed"), entry("回归", "returned")]
        after = [*before, entry("后新增", "later new"), entry("先新增", "first new")]

        next_state = finish_rolling_glossary_chapter(
            state, "先新增，然后后新增。", before, after
        )

        self.assertIsNotNone(next_state)
        self.assertEqual(next_state["processed"], 11)
        self.assertEqual(
            [item["source_term"] for item in next_state["additions"]],
            ["回归", "先新增", "后新增"],
        )

    def test_prepare_rebuilds_snapshot_after_fifty_chapters(self) -> None:
        state = {
            "epoch_start_filename": "200.txt",
            "processed": 50,
            "snapshot": [entry("旧固定", "old fixed")],
            "additions": [],
        }
        with patch(
            "novel_translator.glossary_strategy.rolling_glossary_snapshot",
            return_value=[entry("新固定", "new fixed")],
        ):
            next_state, prompt = prepare_rolling_glossary_prompt(
                "Book",
                "250.txt",
                "当前词",
                [entry("新固定", "new fixed"), entry("当前词", "current")],
                state,
            )

        self.assertEqual(next_state["epoch_start_filename"], "250.txt")
        self.assertEqual(next_state["processed"], 0)
        self.assertEqual(
            [item["source_term"] for item in prompt], ["新固定", "当前词"]
        )

    def test_bulk_state_persists_frozen_glossary_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            settings, "DATA_ROOT", Path(tmp)
        ):
            save_bulk_state(
                "Book",
                {
                    "running": True,
                    "items": [
                        {
                            "filename": "200.txt",
                            "title": "Chapter 200",
                            "status": "pending",
                            "mode": "full",
                        }
                    ],
                    "rolling_glossary": {
                        "epoch_start_filename": "200.txt",
                        "processed": 3,
                        "snapshot": [entry("固定", "fixed")],
                        "additions": [entry("新增", "new")],
                    },
                },
            )
            loaded = load_bulk_state("Book")

        self.assertEqual(loaded["rolling_glossary"]["processed"], 3)
        self.assertEqual(
            loaded["rolling_glossary"]["additions"][0]["source_term"], "新增"
        )

    def test_flush_pending_updates_fills_blank_fields_and_clears_bank(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            settings, "GLOSSARY_ROOT", Path(tmp)
        ):
            glossary = Path(tmp) / "Book" / "glossary" / "glossary.json"
            glossary.parent.mkdir(parents=True)
            glossary.write_text(
                json.dumps(
                    [
                        {
                            "source_term": "徐邢",
                            "english_term": "Xu Xing",
                            "category": "",
                            "gender_or_pronoun": "",
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            pending = [
                {
                    "source_term": "徐邢",
                    "english_term": "Different Name",
                    "category": "character",
                    "gender_or_pronoun": "male",
                }
            ]

            flush_pending_glossary_updates("Book", pending)

            saved = json.loads(glossary.read_text(encoding="utf-8"))

        self.assertEqual(pending, [])
        self.assertEqual(saved[0]["english_term"], "Xu Xing")
        self.assertEqual(saved[0]["category"], "character")
        self.assertEqual(saved[0]["gender_or_pronoun"], "male")


if __name__ == "__main__":
    unittest.main()
