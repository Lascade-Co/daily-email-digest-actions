import unittest
from datetime import date

from scripts.common.dates import subject


class SubjectTests(unittest.TestCase):
    def test_human_date_and_existing_metric_tail(self):
        self.assertEqual(
            subject("MarineRadar web revenue", date(2026, 10, 21), "$412 (3 purchases)"),
            "MarineRadar web revenue · Wed, Oct 21 — $412 (3 purchases)",
        )

    def test_single_digit_day_has_no_padding(self):
        self.assertEqual(
            subject("Install → Paid", date(2025, 11, 1), "3 paid"),
            "Install → Paid · Sat, Nov 1 — 3 paid",
        )


if __name__ == "__main__":
    unittest.main()
