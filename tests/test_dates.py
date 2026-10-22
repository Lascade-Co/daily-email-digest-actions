import unittest
from datetime import date, datetime, timezone

from scripts.common.dates import long_date, report_date_for, window_for


class ReportDateTests(unittest.TestCase):
    def test_report_date_changes_at_five_in_edition_timezone(self):
        cases = [
            ("2026-10-21T11:59:59+00:00", "America/Los_Angeles", date(2026, 10, 20)),
            ("2026-10-21T12:00:00+00:00", "America/Los_Angeles", date(2026, 10, 21)),
            ("2026-10-20T23:29:59+00:00", "Asia/Kolkata", date(2026, 10, 20)),
            ("2026-10-20T23:30:00+00:00", "Asia/Kolkata", date(2026, 10, 21)),
        ]
        for now, zone, expected in cases:
            with self.subTest(now=now, zone=zone):
                self.assertEqual(report_date_for(datetime.fromisoformat(now), zone), expected)

    def test_window_keeps_local_five_am_across_dst(self):
        cases = [
            (date(2026, 3, 8), "2026-03-07T13:00:00+00:00", "2026-03-08T12:00:00+00:00"),
            (date(2026, 11, 1), "2026-10-31T12:00:00+00:00", "2026-11-01T13:00:00+00:00"),
        ]
        for report_date, start_utc, end_utc in cases:
            with self.subTest(report_date=report_date):
                start, end = window_for(report_date, "America/Los_Angeles")
                self.assertEqual(start.astimezone(timezone.utc).isoformat(), start_utc)
                self.assertEqual(end.astimezone(timezone.utc).isoformat(), end_utc)

    def test_ist_window_is_start_inclusive_end_exclusive(self):
        start, end = window_for(date(2026, 10, 21), "Asia/Kolkata")
        self.assertEqual(start.isoformat(), "2026-10-20T05:00:00+05:30")
        self.assertEqual(end.isoformat(), "2026-10-21T05:00:00+05:30")
        items = [datetime.fromisoformat(stamp) for stamp in [
            "2026-10-20T04:59:59+05:30",
            "2026-10-20T05:00:00+05:30",
            "2026-10-21T04:59:59+05:30",
            "2026-10-21T05:00:00+05:30",
            "2026-10-21T05:01:00+05:30",
        ]]
        self.assertEqual([item.isoformat() for item in items if start <= item < end], [
            "2026-10-20T05:00:00+05:30", "2026-10-21T04:59:59+05:30",
        ])

    def test_long_date_is_locale_independent(self):
        self.assertEqual(long_date(date(2026, 10, 21)), "Wednesday, 21 October 2026")
        self.assertEqual(long_date(datetime(2025, 11, 1)), "Saturday, 1 November 2025")

    def test_naive_clock_is_rejected(self):
        with self.assertRaises(ValueError):
            report_date_for(datetime(2026, 10, 21, 5), "Asia/Kolkata")


if __name__ == "__main__":
    unittest.main()
