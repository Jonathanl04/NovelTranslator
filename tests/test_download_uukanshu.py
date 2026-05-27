from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from scraper.download_uukanshu import (
    extract_chapter_links,
    extract_cover_url,
    parse_chapter_number,
    remove_existing_chapter_files,
)


class UukanshuDownloaderTests(unittest.TestCase):
    def test_parse_chapter_number_handles_chinese_numerals(self) -> None:
        self.assertEqual(parse_chapter_number("第一章 章名"), 1)
        self.assertEqual(parse_chapter_number("第十二章 章名"), 12)
        self.assertEqual(parse_chapter_number("第一百二十三章 章名"), 123)
        self.assertEqual(parse_chapter_number("第129章 章名"), 129)

    def test_extract_chapter_links_handles_mixed_numerals(self) -> None:
        index_text = """
        <div class="content">
          <a href="/book/26855/1.html">第一章 起點</a>
          <a href="/book/26855/2.html">第二章 續章</a>
          <a href="/book/26855/12.html">第十二章 轉折</a>
          <a href="/book/26855/129.html">第129章 進入新篇</a>
        </div>
        """

        links = extract_chapter_links(index_text, "26855")

        self.assertEqual([item[0] for item in links], [1, 2, 12, 129])
        self.assertEqual(
            [item[2] for item in links],
            [
                "https://uukanshu.cc/book/26855/1.html",
                "https://uukanshu.cc/book/26855/2.html",
                "https://uukanshu.cc/book/26855/12.html",
                "https://uukanshu.cc/book/26855/129.html",
            ],
        )

    def test_extract_chapter_links_handles_markdown_links(self) -> None:
        index_text = """
        Markdown Content:
        [第一章 起點](/book/26855/1.html)
        [第十二章 轉折](/book/26855/12.html)
        [第129章 進入新篇](/book/26855/129.html)
        """

        links = extract_chapter_links(index_text, "26855")

        self.assertEqual([item[0] for item in links], [1, 12, 129])

    def test_extract_cover_url_handles_html_thumbnail(self) -> None:
        index_text = """
        <div>
          <img class="thumbnail" src="https://image.uukanshu.cc/25/25771/25771s.jpg" title="老祖，時代變了" />
        </div>
        """

        self.assertEqual(
            extract_cover_url(index_text, "https://uukanshu.cc/book/25771/"),
            "https://image.uukanshu.cc/25/25771/25771s.jpg",
        )

    def test_remove_existing_chapter_files_keeps_other_files(self) -> None:
        with TemporaryDirectory() as directory:
            output_dir = Path(directory)
            (output_dir / "001_old.txt").write_text("old", encoding="utf-8")
            (output_dir / "002_keep.txt").write_text("keep", encoding="utf-8")
            (output_dir / "notes.txt").write_text("notes", encoding="utf-8")

            remove_existing_chapter_files(output_dir, 1)

            self.assertFalse((output_dir / "001_old.txt").exists())
            self.assertTrue((output_dir / "002_keep.txt").exists())
            self.assertTrue((output_dir / "notes.txt").exists())


if __name__ == "__main__":
    unittest.main()
