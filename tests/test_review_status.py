"""Review fetch status: Play paging, failures that must never read as "No new reviews"."""
import base64
import contextlib
from datetime import datetime, timezone
import io
import json
import os
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import quote

from scripts.reviews import reviews_fetch, reviews_main

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
START = datetime.fromtimestamp(1000, timezone.utc)
END = datetime.fromtimestamp(2000, timezone.utc)
SA = base64.b64encode(b'{"type":"service_account","client_email":"fixture@example.test"}').decode()
ASC = {"ASC_KEY_ID": "fixture-key", "ASC_ISSUER_ID": "fixture-issuer", "ASC_PRIVATE_KEY": "fixture-pem"}
IN_WINDOW = int(datetime(2026, 10, 20, 20, tzinfo=timezone.utc).timestamp())   # 13:00 PDT on Oct 20


def play_review(seconds, text="Fixture text", stars=2):
    return {"authorName": "Fixture author",
            "comments": [{"userComment": {"lastModified": {"seconds": seconds}, "text": text, "starRating": stars}}]}


def response(status=200, body=None):
    return SimpleNamespace(status_code=status, json=lambda: body or {})


def fake_requests(get):
    return SimpleNamespace(utils=SimpleNamespace(quote=quote), get=get)


class PlayPagingTests(unittest.TestCase):
    def _fetch(self, pages):
        """pages: list of (status, body); one request consumes one page."""
        calls = []

        def get(url, headers, params=None, timeout=None):
            calls.append(dict(params or {}))
            status, body = pages[len(calls) - 1]
            return response(status, body)

        with patch.object(reviews_fetch, "_play_access_token", return_value="token"), \
                patch.dict(sys.modules, {"requests": fake_requests(get)}), \
                contextlib.redirect_stdout(io.StringIO()):
            reviews, status = reviews_fetch.fetch_playstore_reviews("pkg", START, {}, until_dt=END)
        return [r["date"] for r in reviews], status, calls

    def test_two_pages_then_stops_at_since(self):
        pages = [(200, {"reviews": [play_review(1900), play_review(1800)], "tokenPagination": {"nextPageToken": "p2"}}),
                 (200, {"reviews": [play_review(1500), play_review(900), play_review(800)],
                        "tokenPagination": {"nextPageToken": "p3"}})]
        dates, status, calls = self._fetch(pages)
        self.assertEqual(status, "ok")
        self.assertEqual(len(dates), 3)
        self.assertEqual(len(calls), 2)                      # never asks for p3
        self.assertEqual(calls[0]["maxResults"], 100)
        self.assertEqual(calls[1]["token"], "p2")

    def test_page_newer_than_until_keeps_paging(self):
        pages = [(200, {"reviews": [play_review(2600), play_review(2000)], "tokenPagination": {"nextPageToken": "p2"}}),
                 (200, {"reviews": [play_review(1999), play_review(1000)]})]
        dates, status, calls = self._fetch(pages)
        self.assertEqual(status, "ok")
        self.assertEqual(len(dates), 2)
        self.assertEqual(len(calls), 2)

    def test_failure_on_later_page_keeps_earlier_reviews(self):
        pages = [(200, {"reviews": [play_review(1900)], "tokenPagination": {"nextPageToken": "p2"}}),
                 (500, {})]
        dates, status, _ = self._fetch(pages)
        self.assertEqual(status, "failed")
        self.assertEqual(len(dates), 1)

    def test_page_cap_with_more_pages_is_incomplete(self):
        page = (200, {"reviews": [play_review(1900)], "tokenPagination": {"nextPageToken": "more"}})
        dates, status, calls = self._fetch([page] * reviews_fetch.PLAY_MAX_PAGES)
        self.assertEqual(status, "incomplete")
        self.assertEqual(len(calls), reviews_fetch.PLAY_MAX_PAGES)
        self.assertEqual(len(dates), reviews_fetch.PLAY_MAX_PAGES)

    def test_undated_review_does_not_end_the_scan(self):
        undated = {"authorName": "x", "comments": [{"userComment": {"text": "no date", "starRating": 1}}]}
        dates, status, _ = self._fetch([(200, {"reviews": [undated, play_review(1500)]})])
        self.assertEqual(status, "ok")
        self.assertEqual(len(dates), 1)

    def test_auth_failure_is_failed(self):
        with patch.object(reviews_fetch, "_play_access_token", side_effect=RuntimeError("no access")), \
                patch.dict(sys.modules, {"requests": fake_requests(None)}), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(reviews_fetch.fetch_playstore_reviews("pkg", START, {}, until_dt=END), ([], "failed"))


class AppStoreStatusTests(unittest.TestCase):
    def test_jwt_failure_is_failed(self):
        with patch.object(reviews_fetch, "_asc_jwt", side_effect=ValueError("bad pem")), \
                patch.dict(sys.modules, {"requests": fake_requests(None)}), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(reviews_fetch.fetch_appstore_reviews("app", START, "k", "i", "pem", until_dt=END),
                             ([], "failed"))

    def test_http_error_is_failed(self):
        with patch.object(reviews_fetch, "_asc_jwt", return_value="token"), \
                patch.dict(sys.modules, {"requests": fake_requests(lambda *a, **k: response(401))}), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(reviews_fetch.fetch_appstore_reviews("app", START, "k", "i", "pem", until_dt=END),
                             ([], "failed"))


class MainStatusTests(unittest.TestCase):
    """Real main -> model -> render path; only HTTP, tokens and preview writing are replaced."""

    def _run(self, environment, get):
        captured = {}

        def capture(digest, edition, subject, html):
            captured.update(subject=subject, html=html)

        output = io.StringIO()
        env = {"GOOGLE_API_KEY": "", "GITHUB_ACTIONS": "false", **environment}
        with patch.dict(os.environ, env, clear=False), \
                patch.object(reviews_fetch, "_asc_jwt", return_value="token"), \
                patch.object(reviews_fetch, "_play_access_token", return_value="token"), \
                patch.dict(sys.modules, {"requests": fake_requests(get)}), \
                patch.object(reviews_main, "write_preview", side_effect=capture), \
                patch.object(reviews_main, "send_digest", side_effect=AssertionError("dry run must not send")), \
                contextlib.redirect_stdout(output):
            for name in set(ASC) | {"GOOGLE_SA_KEY"}:
                if name not in environment:
                    os.environ.pop(name, None)
            reviews_main.main(["--edition", "pt", "--report-date", "2026-10-21", "--dry-run"])
        return captured["subject"], captured["html"], output.getvalue()

    @staticmethod
    def _ta_section(html):
        return html[html.rindex(">TravelAnimator<"):]

    def test_travelanimator_play_403_on_page_two_keeps_review_and_warns(self):
        def get(url, headers, params=None, timeout=None):
            if "appstoreconnect" in url:
                return response(200, {"data": [], "links": {}})
            if "com.travelanimator.routemap" in url:
                if (params or {}).get("token"):
                    return response(403)
                return response(200, {"reviews": [play_review(IN_WINDOW, text="Map turns grey")],
                                      "tokenPagination": {"nextPageToken": "p2"}})
            return response(200, {"reviews": []})

        subject, html, log = self._run({**ASC, "GOOGLE_SA_KEY": SA}, get)
        section = self._ta_section(html)
        self.assertIn("Map turns grey", section)
        self.assertIn("Couldn't fetch Play Store reviews today", section.replace("&#x27;", "'"))
        self.assertTrue(subject.endswith("(partial)"))
        self.assertIn("reviews app=TravelAnimator appstore=0:ok playstore=1:failed", log)
        self.assertNotIn("Map turns grey", log)

    def test_travelanimator_play_403_on_first_page_never_reads_as_no_reviews(self):
        def get(url, headers, params=None, timeout=None):
            if "appstoreconnect" in url:
                return response(200, {"data": [], "links": {}})
            if "com.travelanimator.routemap" in url:
                return response(403)
            return response(200, {"reviews": []})

        subject, html, _ = self._run({**ASC, "GOOGLE_SA_KEY": SA}, get)
        section = self._ta_section(html).replace("&#x27;", "'")
        self.assertIn("Couldn't fetch Play Store reviews today", section)
        self.assertNotIn("No new reviews", section)
        self.assertEqual(html.count("No new reviews"), 3)        # the other three apps are clean
        self.assertTrue(subject.endswith("(partial)"))

    def test_play_page_cap_renders_incomplete_warning(self):
        def get(url, headers, params=None, timeout=None):
            if "appstoreconnect" in url:
                return response(200, {"data": [], "links": {}})
            if "com.travelanimator.routemap" in url:
                return response(200, {"reviews": [play_review(IN_WINDOW)], "tokenPagination": {"nextPageToken": "more"}})
            return response(200, {"reviews": []})

        subject, html, log = self._run({**ASC, "GOOGLE_SA_KEY": SA}, get)
        self.assertIn("Play Store reviews may be incomplete today", self._ta_section(html))
        self.assertIn("apps (partial)", html)                    # preheader carries the marker
        self.assertTrue(subject.endswith("(partial)"))
        self.assertIn(f"playstore={reviews_fetch.PLAY_MAX_PAGES}:incomplete", log)

    def test_missing_asc_credentials_never_read_as_no_reviews(self):
        get = lambda url, headers, params=None, timeout=None: response(200, {"reviews": []})
        subject, html, _ = self._run({"GOOGLE_SA_KEY": SA}, get)
        self.assertNotIn("No new reviews", html)
        self.assertEqual(html.replace("&#x27;", "'").count("Couldn't fetch App Store reviews today"), 4)
        self.assertTrue(subject.endswith("(partial)"))

    def test_empty_service_account_never_reads_as_no_reviews(self):
        get = lambda url, headers, params=None, timeout=None: response(200, {"data": [], "links": {}})
        subject, html, _ = self._run({**ASC, "GOOGLE_SA_KEY": base64.b64encode(b"{}").decode()}, get)
        self.assertNotIn("No new reviews", html)
        self.assertEqual(html.replace("&#x27;", "'").count("Couldn't fetch Play Store reviews today"), 4)
        self.assertTrue(subject.endswith("(partial)"))

    def test_clean_run_is_not_partial(self):
        def get(url, headers, params=None, timeout=None):
            return response(200, {"data": [], "links": {}} if "appstoreconnect" in url else {"reviews": []})

        subject, html, _ = self._run({**ASC, "GOOGLE_SA_KEY": SA}, get)
        self.assertFalse(subject.endswith("(partial)"))
        self.assertNotIn("Partial data", html)
        self.assertEqual(html.count("No new reviews"), 4)


class AppListTests(unittest.TestCase):
    def test_travelanimator_is_listed_with_both_store_ids(self):
        with open(os.path.join(ROOT, "data", "reviews_apps.json"), encoding="utf-8") as source:
            apps = {app["name"]: app for app in json.load(source)}
        self.assertEqual(apps["TravelAnimator"]["apple_id"], "6462844561")
        self.assertEqual(apps["TravelAnimator"]["play_package"], "com.travelanimator.routemap")


if __name__ == "__main__":
    unittest.main()
