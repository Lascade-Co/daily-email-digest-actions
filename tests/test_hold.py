import os
import subprocess
import sys
import unittest
from datetime import date, timezone
from pathlib import Path
from unittest.mock import patch

from scripts.common import hold


class HoldTests(unittest.TestCase):
    def test_target_follows_pacific_dst(self):
        cases = [
            (date(2026, 3, 7), "2026-03-07T13:55:00+00:00"),
            (date(2026, 3, 8), "2026-03-08T12:55:00+00:00"),
            (date(2026, 10, 31), "2026-10-31T12:55:00+00:00"),
            (date(2026, 11, 1), "2026-11-01T13:55:00+00:00"),
        ]
        for report_date, expected in cases:
            with self.subTest(report_date=report_date):
                target = hold.target_for(report_date, "America/Los_Angeles")
                self.assertEqual(target.astimezone(timezone.utc).isoformat(), expected)

    def test_ist_target_is_constant_in_both_dst_seasons(self):
        for report_date in (date(2026, 3, 7), date(2026, 3, 8), date(2026, 10, 31), date(2026, 11, 1)):
            with self.subTest(report_date=report_date):
                target = hold.target_for(report_date, "Asia/Kolkata")
                self.assertEqual(target.astimezone(timezone.utc).isoformat(), f"{report_date}T00:25:00+00:00")

    def test_hold_uses_now_override_and_waits_until_target(self):
        sleeps = []
        with patch.dict(os.environ, {"NOW": "2026-03-08T12:05:00+00:00"}), patch.object(hold.time, "sleep", sleeps.append):
            hold.hold_until(date(2026, 3, 8), "America/Los_Angeles")
        self.assertEqual(sleeps, [3000.0])

    def test_late_hold_sends_without_sleeping_or_failing(self):
        sleeps = []
        with patch.dict(os.environ, {"NOW": "2026-11-01T14:01:00+00:00"}), patch.object(hold.time, "sleep", sleeps.append):
            hold.hold_until(date(2026, 11, 1), "America/Los_Angeles")
        self.assertEqual(sleeps, [])

    def test_invalid_target_is_rejected(self):
        for target in ("5:55", "24:00", "05:60", "ab:cd"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                hold.target_for(date(2026, 10, 21), "Asia/Kolkata", target)

    def test_cli_accepts_report_date_and_zone(self):
        root = Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [sys.executable, str(root / "scripts/common/hold.py"), "--report-date", "2026-10-21", "--tz", "Asia/Kolkata"],
            capture_output=True, text=True, env={**os.environ, "NOW": "2026-10-21T00:30:00+00:00"},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
