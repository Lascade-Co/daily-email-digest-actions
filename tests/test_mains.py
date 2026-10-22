"""Offline end-to-end builds use the requested edition/date and safe logs."""
import base64
import contextlib
from datetime import datetime, timezone
import importlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class MainBuildTests(unittest.TestCase):
    def _load(self, name):
        try:
            return importlib.import_module(f"scripts.{name}.{name}_main")
        except ModuleNotFoundError as exc:
            self.fail(f"Main must be importable without network SDKs: {exc.name}")

    def _read_preview(self, digest, edition):
        directory = Path("out")
        self.assertEqual(sorted(p.name for p in directory.iterdir()),
                         [f"{digest}-{edition}.html", f"{digest}-{edition}.subject.txt"])
        html = (directory / f"{digest}-{edition}.html").read_text()
        subject = (directory / f"{digest}-{edition}.subject.txt").read_text()
        self.assertIn("Wednesday, 21 October 2026", html)
        self.assertIn(" · Wed, Oct 21 — ", subject)
        return subject, html

    def test_revenue_uses_report_window_and_same_month_upper_bound(self):
        main = self._load("revenue")
        calls = []
        def fetch(key, start, end):
            calls.append((start, end))
            return [{"amount_cents": 41200, "currency": "usd", "created": start, "metadata": {}}]
        output = io.StringIO()
        with tempfile.TemporaryDirectory(dir=ROOT) as directory, contextlib.chdir(directory), patch.dict(os.environ, {"STRIPE_API_KEY": "secret", "GITHUB_ACTIONS": "false"}), patch.object(main, "fetch_charges", side_effect=fetch), patch.object(main, "fetch_refunds", return_value=[]), patch.object(main, "send_digest", side_effect=AssertionError("dry run must not send")), contextlib.redirect_stdout(output):
            main.main(["--edition", "ist", "--report-date", "2026-10-21", "--dry-run"])
            subject, _ = self._read_preview("revenue", "ist")
        self.assertTrue(subject.startswith("MarineRadar web revenue · Wed, Oct 21 — $412.00"))
        self.assertEqual(calls, [(1792452600, 1792539000), (1790793000, 1792539000)])
        self.assertNotIn(subject, output.getvalue())
        self.assertNotIn("$412", output.getvalue())

    def test_reviews_use_pt_report_window(self):
        main = self._load("reviews")
        calls = []
        def fetch(app, start, *credentials, until_dt):
            calls.append((start.isoformat(), until_dt.isoformat()))
            return []
        with tempfile.TemporaryDirectory(dir=ROOT) as directory, contextlib.chdir(directory), patch.dict(os.environ, {"ASC_KEY_ID": "key", "ASC_ISSUER_ID": "issuer", "ASC_PRIVATE_KEY": "pem", "GOOGLE_SA_KEY": "", "GITHUB_ACTIONS": "false"}), patch.object(main, "fetch_appstore_reviews", side_effect=fetch), patch.object(main, "send_digest", side_effect=AssertionError("dry run must not send")), contextlib.redirect_stdout(io.StringIO()):
            main.main(["--edition", "pt", "--report-date", "2026-10-21", "--dry-run"])
            subject, _ = self._read_preview("reviews", "pt")
        self.assertTrue(subject.startswith("App reviews · Wed, Oct 21"))
        self.assertTrue(calls)
        self.assertEqual(set(calls), {("2026-10-20T05:00:00-07:00", "2026-10-21T05:00:00-07:00")})

    def test_both_survey_products_write_digest_specific_filenames(self):
        main = self._load("survey")
        for digest, head in (("survey_marine", "MarineRadar surveys"), ("survey_measure", "Smart Ruler surveys")):
            with self.subTest(digest=digest), tempfile.TemporaryDirectory(dir=ROOT) as directory, contextlib.chdir(directory), patch.dict(os.environ, {"GOOGLE_SA_KEY": base64.b64encode(b"{}").decode(), "GOOGLE_API_KEY": "", "GITHUB_ACTIONS": "false"}), patch.object(main, "fetch_sheet_tab", return_value=[]), patch.object(main, "send_digest", side_effect=AssertionError("dry run must not send")), contextlib.redirect_stdout(io.StringIO()):
                main.main(["--digest", digest, "--edition", "ist", "--report-date", "2026-10-21", "--dry-run"])
                subject, _ = self._read_preview(digest, "ist")
                self.assertTrue(subject.startswith(head + " · Wed, Oct 21"))

    def test_conversion_requests_previous_day_as_upper_bound(self):
        main = self._load("conversion")
        calls = []
        def fetch(api_key, date_from, date_to, tz):
            calls.append((date_from, date_to, tz))
            return {"overall_rate": 10.0, "total_installs": 10, "total_paid": 1,
                    "cohorts": [{"date": "2026-10-20", "installs": 10, "paid": 1, "rate": 10.0}]}
        with tempfile.TemporaryDirectory(dir=ROOT) as directory, contextlib.chdir(directory), patch.dict(os.environ, {"ADAPTY_KEY_MARINERADAR": "key", "ADAPTY_KEY_SMARTRULER": "key", "ADAPTY_KEY_GEOANIMATOR": "key", "GITHUB_ACTIONS": "false"}), patch.object(main, "fetch_install_to_paid", side_effect=fetch), patch.object(main, "send_digest", side_effect=AssertionError("dry run must not send")), contextlib.redirect_stdout(io.StringIO()):
            main.main(["--edition", "ist", "--report-date", "2026-10-21", "--dry-run"])
            subject, _ = self._read_preview("conversion", "ist")
        self.assertTrue(subject.startswith("Install → Paid · Wed, Oct 21"))
        self.assertTrue(calls)
        self.assertEqual(set(calls), {("2026-10-07", "2026-10-20", "Asia/Kolkata")})


if __name__ == "__main__":
    unittest.main()
