from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scraper.download_bookto import (
    collect_chapters_for_range,
    extract_book_name,
    extract_chapter_links,
    extract_chapter_text,
    extract_cover_url,
    fetch_text,
    infer_book_id,
)


class BooktoDownloaderTests(unittest.TestCase):
    def test_infer_book_id_from_gnuboard_url(self) -> None:
        url = "https://bookto23.com/bbs/board.php?bo_table=novel&wr_id=27341&spage=1"

        self.assertEqual(infer_book_id(url), "27341")

    def test_infer_book_id_rejects_other_boards(self) -> None:
        with self.assertRaises(ValueError):
            infer_book_id("https://bookto23.com/bbs/board.php?bo_table=webtoon&wr_id=27341")

    def test_extract_book_details(self) -> None:
        html = """
        <html>
          <body>
            <div class="page-title"><span class="page-desc">회귀한 천재 헌터</span></div>
            <div class="view-img"><img src="/data/file/novel/cover.jpg"></div>
          </body>
        </html>
        """

        self.assertEqual(extract_book_name(html), "회귀한 천재 헌터")
        self.assertEqual(
            extract_cover_url(html, "https://bookto23.com/bbs/board.php?bo_table=novel&wr_id=27341"),
            "https://bookto23.com/data/file/novel/cover.jpg",
        )

    def test_extract_chapter_links_uses_wr_num_and_sorts(self) -> None:
        html = """
        <ul class="list-body">
          <li>
            <div class="wr-num">2</div>
            <div><a href="/bbs/board.php?bo_table=novel&amp;wr_id=27343">두 번째 이야기</a></div>
          </li>
          <li>
            <div class="wr-num">1</div>
            <div><a href="/bbs/board.php?bo_table=novel&amp;wr_id=27342">첫 번째 이야기</a></div>
          </li>
        </ul>
        """

        links = extract_chapter_links(html, "https://bookto23.com")

        self.assertEqual([item[0] for item in links], [1, 2])
        self.assertEqual(links[0][1], "첫 번째 이야기")
        self.assertEqual(
            links[0][2],
            "https://bookto23.com/bbs/board.php?bo_table=novel&wr_id=27342",
        )

    def test_collect_chapters_finds_chapter_one_on_last_spage(self) -> None:
        page_one = """
        <ul class="list-body">
          <li><div class="wr-num">6</div><a href="?bo_table=novel&wr_id=106&spage=1">6화</a></li>
          <li><div class="wr-num">5</div><a href="?bo_table=novel&wr_id=105&spage=1">5화</a></li>
        </ul>
        <a href="./board.php?bo_table=novel&wr_id=100&spage=3">3</a>
        """
        page_three = """
        <ul class="list-body">
          <li><div class="wr-num">2</div><a href="?bo_table=novel&wr_id=102&spage=3">2화</a></li>
          <li><div class="wr-num">1</div><a href="?bo_table=novel&wr_id=101&spage=3">1화</a></li>
        </ul>
        """
        source_url = "https://bookto23.com/bbs/board.php?bo_table=novel&wr_id=100&spage=1"

        with patch("scraper.download_bookto.fetch_text", return_value=page_three) as fetch:
            chapters = collect_chapters_for_range(SimpleNamespace(), source_url, page_one, 1, 1)

        self.assertEqual([item[0] for item in chapters], [1, 2, 5, 6])
        self.assertIn("spage=3", fetch.call_args.args[1])

    def test_extract_chapter_text_removes_duplicate_title_and_scripts(self) -> None:
        html = """
        <html>
          <body>
            <h1>첫 번째 이야기</h1>
            <div id="novel_content">
              <script>advertise()</script>
              첫 번째 이야기
              <p>첫 문단입니다.</p>
              <p>둘째 문단입니다.</p>
            </div>
          </body>
        </html>
        """

        title, content = extract_chapter_text(html, "첫 번째 이야기")

        self.assertEqual(title, "첫 번째 이야기")
        self.assertEqual(content, "첫 문단입니다.\n둘째 문단입니다.")

    def test_fetch_text_rejects_cloudflare_challenge(self) -> None:
        def blocked_fetch(_url: str, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(status=403, html_content="<title>Just a moment...</title>")

        session = SimpleNamespace(fetch=blocked_fetch)

        with self.assertRaisesRegex(RuntimeError, "security verification"):
            fetch_text(
                session,
                "https://bookto23.com/bbs/board.php?bo_table=novel&wr_id=27341",
                ".list-body",
            )

    def test_extract_chapter_text_uses_current_bookto_viewer(self) -> None:
        html = """
        <html>
          <body>
            <h1>시한부 천재가 살아남는 법 - 754화</h1>
            <div class="view-content book-text-viewer">
              <p>첫 문단입니다.</p>
              <p>둘째 문단입니다.</p>
            </div>
          </body>
        </html>
        """

        title, content = extract_chapter_text(
            html,
            "시한부 천재가 살아남는 법 - 754화",
        )

        self.assertEqual(title, "시한부 천재가 살아남는 법 - 754화")
        self.assertEqual(content, "첫 문단입니다.\n둘째 문단입니다.")


if __name__ == "__main__":
    unittest.main()
