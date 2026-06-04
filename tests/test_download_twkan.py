from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from scraper.download_twkan import (
    extract_book_name,
    extract_chapter_links,
    extract_chapter_text,
    extract_cover_url,
    fetch_text,
    remove_existing_chapter_files,
)


class TwkanDownloaderTests(unittest.TestCase):
    def test_extract_chapter_links_uses_data_num_attribute(self) -> None:
        chapter_list_html = """
        <ul>
          <li data-num="1"><a href="https://twkan.com/txt/92274/51846139">第1章 黑石營地 </a></li>
          <li data-num="2"><a href="https://twkan.com/txt/92274/51846140">第2章 鐵棘種子 </a></li>
          <li data-num="8"><a href="https://twkan.com/txt/92274/51846151">第8張 租住木屋 </a></li>
        </ul>
        """

        links = extract_chapter_links(chapter_list_html, "92274")

        self.assertEqual([item[0] for item in links], [1, 2, 8])
        self.assertEqual(
            [item[2] for item in links],
            [
                "https://twkan.com/txt/92274/51846139",
                "https://twkan.com/txt/92274/51846140",
                "https://twkan.com/txt/92274/51846151",
            ],
        )

    def test_extract_chapter_links_deduplicates(self) -> None:
        chapter_list_html = """
        <ul>
          <li data-num="1"><a href="https://twkan.com/txt/92274/51846139">第1章 黑石營地</a></li>
          <li data-num="1"><a href="https://twkan.com/txt/92274/51846139">第1章 黑石營地</a></li>
        </ul>
        """

        links = extract_chapter_links(chapter_list_html, "92274")

        self.assertEqual(len(links), 1)

    def test_extract_book_name_from_og_meta(self) -> None:
        html = """
        <html><head>
          <meta property="og:novel:book_name" content="巫師：我在兩界當泰坦">
        </head></html>
        """

        self.assertEqual(extract_book_name(html), "巫師：我在兩界當泰坦")

    def test_extract_book_name_falls_back_to_h1(self) -> None:
        html = """
        <html><body>
          <div class="booknav2"><h1><a href="#">我的小說</a></h1></div>
        </body></html>
        """

        self.assertEqual(extract_book_name(html), "我的小說")

    def test_extract_cover_url_from_og_image(self) -> None:
        html = """
        <html><head>
          <meta property="og:image" content="https://twkan.com/files/article/image/92/92274/92274s.jpg">
        </head></html>
        """

        self.assertEqual(
            extract_cover_url(html),
            "https://twkan.com/files/article/image/92/92274/92274s.jpg",
        )

    def test_extract_chapter_text_removes_duplicate_title(self) -> None:
        html = """
        <html><body>
          <h1>第1章 黑石營地</h1>
          <div id="txtcontent0">
            第1章 黑石營地
            正文第一段。
            正文第二段。
          </div>
        </body></html>
        """

        title, content = extract_chapter_text(html, "第1章 黑石營地")

        self.assertEqual(title, "第1章 黑石營地")
        self.assertNotIn("第1章 黑石營地", content)
        self.assertIn("正文第一段。", content)

    def test_extract_chapter_text_raises_on_missing_content(self) -> None:
        html = "<html><body><h1>第1章</h1></body></html>"

        with self.assertRaises(RuntimeError):
            extract_chapter_text(html, "第1章")

    def test_fetch_text_returns_content_on_success(self) -> None:
        ok_response = SimpleNamespace(status_code=200, text="<html><body>正文</body></html>")
        with patch("scraper.download_twkan.cf_requests.get", return_value=ok_response):
            result = fetch_text("https://twkan.com/txt/92274/51846139")

        self.assertEqual(result, "<html><body>正文</body></html>")

    def test_fetch_text_raises_after_retries_exhausted(self) -> None:
        blocked_response = SimpleNamespace(status_code=403, text="blocked")
        with patch("scraper.download_twkan.cf_requests.get", return_value=blocked_response):
            with patch("scraper.download_twkan.time.sleep"):
                with self.assertRaises(RuntimeError):
                    fetch_text("https://twkan.com/txt/92274/51846139")

    def test_fetch_text_retries_on_cloudflare_challenge(self) -> None:
        challenge = SimpleNamespace(status_code=200, text="<html><title>Just a moment...</title></html>")
        ok_response = SimpleNamespace(status_code=200, text="<html><body>正文</body></html>")
        responses = iter([challenge, ok_response])
        with patch("scraper.download_twkan.cf_requests.get", side_effect=lambda *a, **k: next(responses)):
            with patch("scraper.download_twkan.time.sleep"):
                result = fetch_text("https://twkan.com/txt/92274/51846139")

        self.assertEqual(result, "<html><body>正文</body></html>")

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
