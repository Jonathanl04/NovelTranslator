from __future__ import annotations

import unittest

from scraper.download_uukanshu import extract_chapter_links, parse_chapter_number


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


if __name__ == "__main__":
    unittest.main()
