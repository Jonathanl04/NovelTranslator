"""Browser regression checks against a frontend build with an entirely mocked API.

Run `npm run build` in frontend, then `python tests/frontend_regressions.py`.
Requires the project's Patchright dependency and its installed Chromium browser.
No running backend, credentials, or novel data are used.
"""

import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from patchright.sync_api import sync_playwright


class FrontendRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)
        cls.dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context()
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.chapter_count = 5000
        self.malformed = False
        self.hold_settings = False
        self.fail_settings = False
        self.held = []
        self.saves = []
        self.queues = []
        self.bulk_items = []
        self.config = {
            "has_openrouter_api_key": False, "openrouter_api_key_mask": "",
            "translation_backend": "openrouter", "glossary_backend": "openrouter",
            "translation_reasoning_effort": "none", "glossary_reasoning_effort": "none",
            "codex_fast_mode": False, "codex_translation_model": "",
            "codex_glossary_model": "", "translation_model": "", "translation_provider": "",
            "glossary_model": "", "glossary_provider": "", "glossary_strategy": "full",
            "added_models": [],
        }
        self.page.route("**/*", self.route)

    def tearDown(self):
        self.assertEqual(self.errors, [])

    def route(self, route):
        url = urlparse(route.request.url)
        if not url.path.startswith("/api/"):
            asset = self.dist / url.path.lstrip("/")
            if not asset.is_file():
                asset = self.dist / "index.html"
            mime = {".js": "text/javascript", ".css": "text/css", ".woff2": "font/woff2"}.get(asset.suffix, "text/html")
            route.fulfill(body=asset.read_bytes(), content_type=mime)
            return
        name = url.path.removeprefix("/api/")
        query = parse_qs(url.query)
        file = query.get("file", ["00001.txt"])[0]
        metadata = dict(name="Book", translated_name="Book", cover_url=None, source_url=None, updated_at=0)
        if name == "config":
            if route.request.method == "POST":
                payload = route.request.post_data_json
                self.saves.append(payload)
                if self.hold_settings:
                    self.held.append((route, payload))
                    return
                if self.fail_settings:
                    route.fulfill(status=503, json={"error": "Settings save failed"})
                    return
                self.config.update(payload)
            data = self.config
        elif name == "novels/metadata":
            data = dict(novels=["Book"], metadata={"Book": metadata})
        elif name == "novel":
            data = metadata
        elif name == "chapters":
            if self.malformed:
                route.fulfill(status=200, content_type="text/html", body="<html>Tunnel login</html>")
                return
            data = [dict(filename=f"{index:05}.txt", title=f"Chapter {index}", translated=True, source_size=100, translated_size=100) for index in range(1, self.chapter_count + 1)]
        elif name == "chapter":
            data = dict(filename=file, source=f"SOURCE {file}", translated=f"CONTENT {file}", translated_exists=True)
        elif name == "bulk-translate":
            if route.request.method == "POST":
                self.queues.append(route.request.post_data_json)
            data = dict(novel="Book", running=False, aborted=bool(self.bulk_items), items=self.bulk_items)
        elif name == "glossary":
            data = []
        elif name == "usage":
            data = dict(total={key: 0 for key in ("prompt_cache_hit_tokens", "prompt_cache_miss_tokens", "prompt_tokens", "completion_tokens", "reasoning_tokens", "total_tokens", "cost_usd")}, by_model={})
        elif name == "scrape":
            data = dict(running=False, stage="idle", result=None)
        elif name == "codex/auth":
            data = dict(available=True, signed_in=False, status="signed_out", error="")
        else:
            data = {}
        route.fulfill(json=data)

    def wait_until(self, predicate):
        for _ in range(100):
            if predicate():
                return
            self.page.wait_for_timeout(50)
        self.fail("Expected browser request did not arrive")

    def test_settings_are_serialized_and_failed_save_can_be_retried(self):
        self.page.goto("http://review.local/settings")
        self.page.locator("#openrouter-api-key").fill("unsaved-test-key")
        self.hold_settings = True
        self.page.locator("#glossary-strategy-settings").click()
        self.page.get_by_role("option", name="Recent 100 chapters").click()
        self.wait_until(lambda: len(self.held) == 1)
        self.page.locator("#translation-reasoning-settings").click()
        self.page.get_by_role("option", name="Low", exact=True).click()
        self.page.wait_for_timeout(200)
        self.assertEqual(len(self.saves), 1, "Second save must wait for the first")
        self.hold_settings = False
        self.fail_settings = True
        route, payload = self.held.pop()
        self.config.update(payload)
        route.fulfill(json=self.config)
        self.page.get_by_role("button", name="Retry saving").wait_for()
        self.assertEqual(self.saves[1]["glossary_strategy"], "rolling")
        self.assertEqual(self.saves[1]["translation_reasoning_effort"], "low")
        self.assertEqual(self.page.locator("#openrouter-api-key").input_value(), "unsaved-test-key")
        self.fail_settings = False
        self.page.get_by_role("button", name="Retry saving").click()
        self.wait_until(lambda: len(self.saves) == 3)
        self.page.get_by_text("Settings saved.", exact=True).wait_for()
        self.assertEqual(self.config["glossary_strategy"], "rolling")
        self.assertEqual(self.config["translation_reasoning_effort"], "low")
        # Routine success messages must not silently dismiss an earlier error.
        self.assertIn("Settings save failed", self.page.get_by_role("alert").inner_text())
        self.page.get_by_role("button", name="Dismiss", exact=True).click()
        self.assertEqual(self.page.get_by_role("alert").count(), 0)

    def test_html_response_shows_error_and_retry_recovers(self):
        self.malformed = True
        self.page.goto("http://review.local/translate?book=Book&chapter=00001.txt")
        alert = self.page.get_by_role("alert")
        alert.get_by_text("The server returned an unexpected response", exact=False).wait_for()
        self.assertNotIn("Tunnel login", alert.inner_text())
        self.malformed = False
        alert.get_by_role("button", name="Retry loading").click()
        self.page.get_by_text("CONTENT 00001.txt", exact=True).wait_for()
        self.assertEqual(self.page.get_by_role("alert").count(), 0)

    def test_large_list_scroll_search_and_keyboard_navigation(self):
        self.page.goto("http://review.local/translate?book=Book&chapter=00001.txt")
        self.page.get_by_text("CONTENT 00001.txt", exact=True).wait_for()
        self.assertLessEqual(self.page.locator("[data-chapter-index]").count(), 20)
        first = self.page.get_by_role("link", name="Chapter 1", exact=True)
        first.focus()
        first.press("End")
        last = self.page.get_by_role("link", name="Chapter 5000", exact=True)
        last.wait_for()
        self.assertTrue(last.evaluate("el => el === document.activeElement"))
        last.press("Enter")
        self.page.get_by_text("CONTENT 05000.txt", exact=True).wait_for()
        self.page.get_by_placeholder("Search chapters...").fill("Chapter 1234")
        match = self.page.get_by_role("link", name="Chapter 1234", exact=True)
        match.wait_for()
        self.assertEqual(self.page.locator("[data-chapter-index]").count(), 1)
        match.focus()
        match.press("Enter")
        self.page.get_by_text("CONTENT 01234.txt", exact=True).wait_for()

    def test_retry_failed_preserves_modes_and_excludes_other_chapters(self):
        self.bulk_items = [
            dict(filename=f"{index:05}.txt", title=f"Chapter {index}", status=status, mode=mode, message="Failure details remain visible" if status == "failed" else "")
            for index, status, mode in ((1, "done", "full"), (2, "failed", "only"), (3, "failed", "full"), (4, "pending", "full"))
        ]
        self.page.goto("http://review.local/translate?book=Book&chapter=00001.txt")
        self.page.get_by_role("button", name="Retry failed chapters").click()
        self.wait_until(lambda: bool(self.queues))
        items = self.queues[0]["items"]
        self.assertEqual([(item["filename"], item["mode"], item["status"]) for item in items], [("00002.txt", "only", "pending"), ("00003.txt", "full", "pending")])

    def test_connection_failure_is_recoverable(self):
        self.page.route("**/api/chapters?*", lambda route: route.abort())
        self.page.goto("http://review.local/translate?book=Book&chapter=00001.txt")
        self.page.get_by_role("alert").get_by_text("Could not connect to Novel Translator", exact=False).wait_for()
        self.page.unroute("**/api/chapters?*")
        self.page.get_by_role("button", name="Retry loading").click()
        self.page.get_by_text("CONTENT 00001.txt", exact=True).wait_for()


if __name__ == "__main__":
    unittest.main()
