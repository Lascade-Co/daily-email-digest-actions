"""Conversion totals always say which install window they cover, plus installs per day."""
import contextlib
from datetime import datetime, timezone
import io
import os
import unittest
from unittest.mock import patch

from scripts.conversion import conversion_main
from scripts.conversion.conversion_model import build_model
from scripts.conversion.conversion_render import render

NOW = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
APPS = [{"name": "MarineRadar"}]


def data(total=1000, paid=32, cohorts=None):
    return {"MarineRadar": {
        "overall_rate": paid / total * 100, "total_installs": total, "total_paid": paid,
        "cohorts": cohorts if cohorts is not None else [
            {"date": "2026-10-20", "installs": total, "paid": paid, "rate": paid / total * 100}],
    }}


class WindowModelTests(unittest.TestCase):
    def test_default_fourteen_day_window(self):
        model = build_model(APPS, data(), NOW, date_from="2026-10-07", date_to="2026-10-20")
        self.assertEqual(model["window_days"], 14)
        self.assertEqual(model["window_str"], "Oct 7 – Oct 20")
        self.assertEqual(model["apps"][0]["installs_per_day"], 71)

    def test_single_day_window(self):
        model = build_model(APPS, data(), NOW, date_from="2026-10-20", date_to="2026-10-20")
        self.assertEqual(model["window_days"], 1)
        self.assertEqual(model["window_str"], "Oct 20")
        self.assertEqual(model["apps"][0]["installs_per_day"], 1000)

    def test_sparse_cohorts_divide_by_calendar_days(self):
        sparse = [{"date": "2026-10-20", "installs": 600, "paid": 6, "rate": 1.0},
                  {"date": "2026-10-10", "installs": 400, "paid": 4, "rate": 1.0}]
        model = build_model(APPS, data(cohorts=sparse), NOW, date_from="2026-10-07", date_to="2026-10-20")
        self.assertEqual(model["apps"][0]["installs_per_day"], 71)      # 1000 / 14, not 1000 / 2

    def test_reversed_window_is_rejected(self):
        with self.assertRaises(ValueError):
            build_model(APPS, data(), NOW, date_from="2026-10-21", date_to="2026-10-20")


class WindowRenderTests(unittest.TestCase):
    def _html(self, date_from, date_to, **kwargs):
        return render(build_model(APPS, data(**kwargs), NOW, date_from=date_from, date_to=date_to))

    def test_fourteen_day_labels_everywhere(self):
        tail, html = self._html("2026-10-07", "2026-10-20")
        self.assertIn("Installs Oct 7 – Oct 20 (14 days): 1,000 installs, about 71 a day. 32 paid to date.", html)
        self.assertIn("Install → paid by app · installs Oct 7 – Oct 20 (14 days), payments to date", html)
        self.assertIn("(32 paid / 1,000 installs, Oct 7 – Oct 20)", html)          # preheader
        self.assertIn("Totals cover installs Oct 7 – Oct 20 and payments made since", html)
        self.assertIn("Install → paid, latest cohorts (up to 7)", html)
        self.assertNotIn("14-day rate", html)
        self.assertNotIn("Cohort days", html)
        self.assertEqual(tail, "MarineRadar 3.2%")

    def test_single_day_has_no_per_day_phrase(self):
        _, html = self._html("2026-10-20", "2026-10-20")
        self.assertIn("Installs Oct 20 (1 day): 1,000 installs. 32 paid to date.", html)
        self.assertNotIn("a day.", html)

    def test_thirty_day_window(self):
        _, html = self._html("2026-09-21", "2026-10-20")
        self.assertIn("Installs Sep 21 – Oct 20 (30 days): 1,000 installs, about 33 a day.", html)
        self.assertIn("installs Sep 21 – Oct 20 (30 days), payments to date", html)


class MainPropagationTests(unittest.TestCase):
    def test_lookback_thirty_reaches_the_rendered_email(self):
        captured = {}

        def fetch(api_key, date_from, date_to, tz):
            return data()["MarineRadar"]

        def preview(digest, edition, subject, html):
            captured["html"] = html

        env = {"ADAPTY_KEY_MARINERADAR": "key", "ADAPTY_KEY_SMARTRULER": "", "ADAPTY_KEY_GEOANIMATOR": "",
               "GITHUB_ACTIONS": "false"}
        with patch.dict(os.environ, env), \
                patch.object(conversion_main, "fetch_install_to_paid", side_effect=fetch), \
                patch.object(conversion_main, "write_preview", side_effect=preview), \
                patch.object(conversion_main, "send_digest", side_effect=AssertionError("dry run must not send")), \
                contextlib.redirect_stdout(io.StringIO()):
            conversion_main.main(["--edition", "pt", "--report-date", "2026-10-21", "--lookback", "30", "--dry-run"])
        self.assertIn("Installs Sep 21 – Oct 20 (30 days)", captured["html"])
        self.assertIn("about 33 a day", captured["html"])


if __name__ == "__main__":
    unittest.main()
