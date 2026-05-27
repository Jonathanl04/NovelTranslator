from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scraper.download_69shuba import (
    extract_book_name,
    extract_chapter_links,
    extract_chapter_text,
    extract_cover_url,
    parse_chapter_number,
    remove_existing_chapter_files,
)


class ShubaDownloaderTests(unittest.TestCase):
    def test_parse_chapter_number_handles_69shuba_prefixes(self) -> None:
        self.assertEqual(parse_chapter_number("第1章 合成魔方"), 1)
        self.assertEqual(parse_chapter_number("10.第10章 这就是巫师吗"), 10)
        self.assertEqual(parse_chapter_number("第十二章 巫师传承"), 12)
        self.assertIsNone(parse_chapter_number("后记"))

    def test_extract_chapter_links_handles_markdown_links(self) -> None:
        index_text = """
        Markdown Content:
        [第1章 合成魔方](https://www.69shuba.com/txt/77582/38804612)
        [10.第10章 这就是巫师吗](https://www.69shuba.com/txt/77582/38804621)
        [后记](https://www.69shuba.com/txt/77582/39634519)
        """

        links = extract_chapter_links(index_text, "77582")

        self.assertEqual([item[0] for item in links], [1, 10])
        self.assertEqual(
            [item[2] for item in links],
            [
                "https://www.69shuba.com/txt/77582/38804612",
                "https://www.69shuba.com/txt/77582/38804621",
            ],
        )

    def test_extract_chapter_links_handles_html_links(self) -> None:
        index_text = """
        <ul>
          <li><a href="/txt/77582/38804612">第1章 合成魔方</a></li>
          <li><a href="/txt/77582/38804621">10.第10章 这就是巫师吗</a></li>
          <li><a href="/txt/77582/39634519">后记</a></li>
        </ul>
        """

        links = extract_chapter_links(index_text, "77582")

        self.assertEqual([item[0] for item in links], [1, 10])

    def test_extract_book_name_from_mirror_title(self) -> None:
        index_text = "Title: 合成系巫师最新章节列表,合成系巫师无弹窗广告-69书吧\n\nMarkdown Content:\n"

        self.assertEqual(extract_book_name(index_text), "合成系巫师")

    def test_extract_chapter_text_removes_mirror_metadata_and_duplicate_title(self) -> None:
        page_text = """
        Title: 合成系巫师-第1章 合成魔方-69书吧

        Markdown Content:
        2024-09-01 作者： 失眠不如写书

        第1章 合成魔方

        正文第一段。
        """

        title, content = extract_chapter_text(page_text, "第1章 合成魔方")

        self.assertEqual(title, "第1章 合成魔方")
        self.assertEqual(content, "正文第一段。")

    def test_extract_cover_url_handles_book_image(self) -> None:
        page_text = """
        <div>
          <img alt="合成系巫师" src="https://cdn.cdnshu.com/files/article/image/77/77582/77582s.jpg" title="合成系巫师" />
        </div>
        """

        self.assertEqual(
            extract_cover_url(page_text, "https://www.69shuba.com/book/77582.htm"),
            "https://cdn.cdnshu.com/files/article/image/77/77582/77582s.jpg",
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
