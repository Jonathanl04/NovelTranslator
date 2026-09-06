from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from scraper.download_bookto import (
    bookto_candidate_is_viable,
    bookto_candidate_hosts,
    bookto_headless_enabled,
    bookto_real_chrome_enabled,
    collect_chapters_for_range,
    extract_book_name,
    extract_chapter_links,
    extract_chapter_text,
    extract_cover_url,
    fetch_text,
    infer_book_id,
    load_saved_bookto_host,
    migrate_saved_bookto_urls,
    resolve_bookto_index,
    save_bookto_host,
)


class BooktoDownloaderTests(unittest.TestCase):
    def test_real_chrome_can_be_enabled_for_docker(self) -> None:
        with patch.dict(
            os.environ,
            {"NOVEL_TRANSLATOR_BOOKTO_REAL_CHROME": "1"},
        ):
            self.assertTrue(bookto_real_chrome_enabled())

    def test_real_chrome_can_be_disabled(self) -> None:
        with patch.dict(
            os.environ,
            {"NOVEL_TRANSLATOR_BOOKTO_REAL_CHROME": "false"},
        ):
            self.assertFalse(bookto_real_chrome_enabled())

    def test_headless_mode_can_be_enabled(self) -> None:
        with patch.dict(
            os.environ,
            {"NOVEL_TRANSLATOR_BOOKTO_HEADLESS": "true"},
        ):
            self.assertTrue(bookto_headless_enabled())

    def test_headless_mode_can_be_disabled(self) -> None:
        with patch.dict(
            os.environ,
            {"NOVEL_TRANSLATOR_BOOKTO_HEADLESS": "0"},
        ):
            self.assertFalse(bookto_headless_enabled())

    def test_candidates_increment_from_supplied_domain(self) -> None:
        old_url = "https://bookto23.com/bbs/board.php?bo_table=novel&wr_id=27341&spage=1"

        with TemporaryDirectory() as temp_dir:
            candidates = bookto_candidate_hosts(old_url, Path(temp_dir) / "state.json")

        self.assertEqual(candidates[:3], ["bookto23.com", "bookto24.com", "bookto25.com"])

    def test_saved_domain_is_reused_for_old_links(self) -> None:
        old_url = "https://bookto23.com/bbs/board.php?bo_table=novel&wr_id=27341"

        with TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            save_bookto_host("bookto24.com", state_path)

            self.assertEqual(load_saved_bookto_host(state_path), "bookto24.com")
            self.assertEqual(bookto_candidate_hosts(old_url, state_path)[0], "bookto24.com")

    def test_resolver_increments_and_saves_working_domain(self) -> None:
        old_url = "https://bookto23.com/bbs/board.php?bo_table=novel&wr_id=27341"
        working_page = """
        <ul class="list-body">
          <li><div class="wr-num">1</div><a href="?bo_table=novel&wr_id=27342">1화</a></li>
        </ul>
        """

        with TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            with patch(
                "scraper.download_bookto.bookto_candidate_is_viable",
                side_effect=[False, True],
            ), patch(
                "scraper.download_bookto.fetch_text",
                return_value=working_page,
            ) as fetch:
                resolved_url, page = resolve_bookto_index(
                    SimpleNamespace(),
                    old_url,
                    state_path,
                    Path(temp_dir),
                )

            self.assertIn("bookto24.com", resolved_url)
            self.assertEqual(page, working_page)
            self.assertEqual(load_saved_bookto_host(state_path), "bookto24.com")
            self.assertEqual(fetch.call_count, 1)
            self.assertIn("bookto24.com", fetch.call_args.args[1])

    def test_probe_skips_domain_that_redirects_outside_bookto(self) -> None:
        response = SimpleNamespace(
            status_code=301,
            headers={"location": "https://t.me/toki_ch"},
            close=lambda: None,
        )

        with patch("scraper.download_bookto.requests.get", return_value=response):
            viable = bookto_candidate_is_viable(
                "https://bookto23.com/bbs/board.php?bo_table=novel&wr_id=27341"
            )

        self.assertFalse(viable)

    def test_probe_accepts_cloudflare_challenge_response(self) -> None:
        response = SimpleNamespace(
            status_code=403,
            headers={},
            close=lambda: None,
        )

        with patch("scraper.download_bookto.requests.get", return_value=response):
            viable = bookto_candidate_is_viable(
                "https://bookto24.com/bbs/board.php?bo_table=novel&wr_id=27341"
            )

        self.assertTrue(viable)

    def test_migrates_all_older_saved_bookto_urls(self) -> None:
        with TemporaryDirectory() as temp_dir:
            library_root = Path(temp_dir)
            old_book = library_root / "Old Book"
            current_book = library_root / "Current Book"
            other_book = library_root / "Other Book"
            old_book.mkdir()
            current_book.mkdir()
            other_book.mkdir()
            (old_book / "metadata.json").write_text(
                json.dumps(
                    {
                        "name": "Old Book",
                        "source_url": (
                            "https://bookto23.com/bbs/board.php?"
                            "bo_table=novel&wr_id=100&spage=2"
                        ),
                    }
                ),
                encoding="utf-8",
            )
            (current_book / "metadata.json").write_text(
                json.dumps(
                    {
                        "name": "Current Book",
                        "source_url": (
                            "https://bookto24.com/bbs/board.php?"
                            "bo_table=novel&wr_id=200"
                        ),
                    }
                ),
                encoding="utf-8",
            )
            (other_book / "metadata.json").write_text(
                json.dumps(
                    {
                        "name": "Other Book",
                        "source_url": "https://uukanshu.cc/book/123/",
                    }
                ),
                encoding="utf-8",
            )

            updated = migrate_saved_bookto_urls("bookto24.com", library_root)

            old_metadata = json.loads(
                (old_book / "metadata.json").read_text(encoding="utf-8")
            )
            current_metadata = json.loads(
                (current_book / "metadata.json").read_text(encoding="utf-8")
            )
            other_metadata = json.loads(
                (other_book / "metadata.json").read_text(encoding="utf-8")
            )
            self.assertEqual(updated, 1)
            self.assertEqual(
                old_metadata["source_url"],
                (
                    "https://bookto24.com/bbs/board.php?"
                    "bo_table=novel&wr_id=100&spage=2"
                ),
            )
            self.assertIn("bookto24.com", current_metadata["source_url"])
            self.assertEqual(
                other_metadata["source_url"],
                "https://uukanshu.cc/book/123/",
            )

    def test_infer_book_id_from_gnuboard_url(self) -> None:
        url = "https://bookto23.com/bbs/board.php?bo_table=novel&wr_id=27341&spage=1"

        self.assertEqual(infer_book_id(url), "27341")

    def test_infer_book_id_rejects_other_boards(self) -> None:
        with self.assertRaises(ValueError):
            infer_book_id("https://bookto23.com/bbs/board.php?bo_table=webtoon&wr_id=27341")

    def test_infer_book_id_accepts_current_numbered_domain(self) -> None:
        self.assertEqual(
            infer_book_id("https://bookto24.com/bbs/board.php?bo_table=novel&wr_id=27341"),
            "27341",
        )

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
        fetch_calls: list[dict[str, object]] = []

        def blocked_fetch(_url: str, **kwargs: object) -> SimpleNamespace:
            fetch_calls.append(kwargs)
            return SimpleNamespace(status=403, html_content="<title>Just a moment...</title>")

        session = SimpleNamespace(fetch=blocked_fetch)

        with self.assertRaisesRegex(RuntimeError, "security verification"):
            fetch_text(
                session,
                "https://bookto23.com/bbs/board.php?bo_table=novel&wr_id=27341",
                ".list-body",
            )

        self.assertEqual(len(fetch_calls), 2)
        self.assertTrue(all(call["solve_cloudflare"] is True for call in fetch_calls))

    def test_fetch_text_skips_solver_after_initial_clearance(self) -> None:
        fetch_calls: list[dict[str, object]] = []

        def successful_fetch(_url: str, **kwargs: object) -> SimpleNamespace:
            fetch_calls.append(kwargs)
            return SimpleNamespace(status=200, html_content='<div id="novel_content">text</div>')

        text = fetch_text(
            SimpleNamespace(fetch=successful_fetch),
            "https://bookto31.com/bbs/board.php?bo_table=novel&wr_id=28127",
            "#novel_content",
            retry_challenge=False,
        )

        self.assertIn("novel_content", text)
        self.assertFalse(fetch_calls[0]["solve_cloudflare"])

    def test_fetch_text_retries_challenge_once_in_persistent_session(self) -> None:
        responses = iter(
            [
                SimpleNamespace(
                    status=403,
                    html_content="<title>Just a moment...</title>",
                ),
                SimpleNamespace(status=200, html_content='<ul class="list-body"></ul>'),
            ]
        )
        session = SimpleNamespace(fetch=lambda _url, **_kwargs: next(responses))

        text = fetch_text(
            session,
            "https://bookto27.com/bbs/board.php?bo_table=novel&wr_id=27341",
            ".list-body",
        )

        self.assertIn("list-body", text)

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
