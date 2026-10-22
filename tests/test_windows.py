"""Boundary regressions for report-date windows; no network is used."""
import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from scripts.survey.survey_model import filter_new_responses, _parse_ts


class SurveyWindowTests(unittest.TestCase):
    def test_window_includes_start_and_excludes_end_and_0501(self):
        tz = ZoneInfo("Asia/Kolkata")
        start = datetime(2026, 10, 20, 5, tzinfo=tz)
        end = datetime(2026, 10, 21, 5, tzinfo=tz)
        rows = [
            ["2026-10-20 04:59:59", "before"],
            ["2026-10-20 05:00:00", "start"],
            ["2026-10-21 04:59:59", "inside"],
            ["2026-10-21 05:00:00", "end"],
            ["2026-10-21 05:01:00", "late"],
        ]
        selected = filter_new_responses(rows, start, tz=tz, now_utc=end)
        self.assertEqual([row[1] for row in selected], ["start", "inside"])

    def test_iso_timestamp_preserves_explicit_offset(self):
        parsed = _parse_ts("2026-10-20T23:30:00+00:00", ZoneInfo("Asia/Kolkata"))
        self.assertEqual(parsed, datetime(2026, 10, 20, 23, 30, tzinfo=timezone.utc))


class FetchWindowTests(unittest.TestCase):
    def _load(self, name):
        import importlib
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError as exc:
            self.fail(f"Offline imports must not require network SDKs: {exc.name}")

    def test_stripe_charge_and_refund_bounds_are_sent_and_enforced(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import patch
        fetch = self._load("scripts.revenue.revenue_fetch")
        start, end = 100, 200
        data = [{"id": f"item-{t}", "amount": 1000, "currency": "usd", "created": t,
                 "status": "succeeded", "metadata": {}} for t in (99, 100, 199, 200, 260)]
        calls = []
        def get(url, **kwargs):
            calls.append(kwargs["params"])
            return SimpleNamespace(status_code=200, json=lambda: {"data": data, "has_more": False})
        with patch.dict(sys.modules, {"requests": SimpleNamespace(get=get)}):
            charges = fetch.fetch_charges("secret", start, end)
            refunds = fetch.fetch_refunds("secret", start, end)
        self.assertEqual([item["created"] for item in charges], [100, 199])
        self.assertEqual([item["created"] for item in refunds], [100, 199])
        for params in calls:
            self.assertEqual(params["created[gte]"], 100)
            self.assertEqual(params["created[lt]"], 200)

    def test_appstore_review_at_end_or_0501_is_excluded(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import patch
        fetch = self._load("scripts.reviews.reviews_fetch")
        start = datetime(2026, 10, 20, 5, tzinfo=timezone.utc)
        end = datetime(2026, 10, 21, 5, tzinfo=timezone.utc)
        stamps = ("2026-10-21T05:01:00Z", "2026-10-21T05:00:00Z", "2026-10-21T04:59:59Z", "2026-10-20T05:00:00Z", "2026-10-20T04:59:59Z")
        data = [{"attributes": {"createdDate": stamp, "rating": 2, "body": "Private review", "title": "Private title", "reviewerNickname": "Private author", "territory": "USA"}} for stamp in stamps]
        with patch.object(fetch, "_asc_jwt", return_value="token"), patch.dict(sys.modules, {"requests": SimpleNamespace(get=lambda *args, **kwargs: SimpleNamespace(status_code=200, json=lambda: {"data": data, "links": {}}))}):
            result = fetch.fetch_appstore_reviews("app", start, "key", "issuer", "pem", until_dt=end)
        self.assertEqual([item["date"] for item in result], ["2026-10-21T04:59:59+00:00", "2026-10-20T05:00:00+00:00"])

    def test_playstore_review_bounds_include_start_exclude_end(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import patch
        from urllib.parse import quote
        fetch = self._load("scripts.reviews.reviews_fetch")
        start, end = datetime.fromtimestamp(100, timezone.utc), datetime.fromtimestamp(200, timezone.utc)
        data = [{"authorName": "Private author", "comments": [{"userComment": {"lastModified": {"seconds": t}, "text": "Private text", "starRating": 1}}]} for t in (99, 100, 199, 200, 260)]
        request_client = SimpleNamespace(utils=SimpleNamespace(quote=quote), get=lambda *args, **kwargs: SimpleNamespace(status_code=200, json=lambda: {"reviews": data}))
        with patch.object(fetch, "_play_access_token", return_value="token", create=True), patch.dict(sys.modules, {"requests": request_client}):
            result = fetch.fetch_playstore_reviews("app", start, {}, until_dt=end)
        self.assertEqual([item["date"] for item in result], ["1970-01-01T00:01:40+00:00", "1970-01-01T00:03:19+00:00"])

    def test_conversion_cohort_result_respects_date_to(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import patch
        fetch = self._load("scripts.conversion.conversion_fetch")
        body = {"data": [{"type": "total", "value": 20, "value_from": 20, "value_to": 4,
                           "values": [{"x": "2026-10-20", "value_from": 10, "value_to": 2, "y": 20},
                                      {"x": "2026-10-21", "value_from": 10, "value_to": 2, "y": 20}]}]}
        payloads = []
        def post(*args, **kwargs):
            payloads.append(kwargs["json"])
            return SimpleNamespace(status_code=200, json=lambda: body)
        with patch.dict(sys.modules, {"requests": SimpleNamespace(post=post)}):
            result = fetch.fetch_install_to_paid("secret", "2026-10-07", "2026-10-20", "Asia/Kolkata")
        self.assertEqual([item["date"] for item in result["cohorts"]], ["2026-10-20"])
        self.assertEqual((result["total_installs"], result["total_paid"], result["overall_rate"]), (10, 2, 20.0))
        self.assertEqual(payloads[0]["filters"]["date"], ["2026-10-07", "2026-10-20"])

    def test_fetch_failures_never_log_response_bodies(self):
        import contextlib
        import io
        import sys
        from types import SimpleNamespace
        from unittest.mock import patch
        fetch = self._load("scripts.survey.survey_fetch")
        out, err = io.StringIO(), io.StringIO()
        request_client = SimpleNamespace(get=lambda *args, **kwargs: SimpleNamespace(status_code=403, text="PRIVATE CUSTOMER BODY"))
        with patch.object(fetch, "_get_credentials", return_value=SimpleNamespace(token="secret")), patch.dict(sys.modules, {"requests": request_client}), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(fetch.FetchError):
                fetch.fetch_sheet_tab({}, "sheet", "tab")
        self.assertNotIn("PRIVATE CUSTOMER BODY", out.getvalue() + err.getvalue())


if __name__ == "__main__":
    unittest.main()
