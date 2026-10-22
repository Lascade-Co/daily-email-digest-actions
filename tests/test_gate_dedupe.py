import contextlib
import io
import os
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from scripts.common import catchup_gate as gate


REPO = "Lascade-Co/daily-email-digest-actions"
REPORT_DATE = date(2026, 10, 21)
PREFIX = "Deliver survey_marine IST for "


def history_fetch(jobs, *, event="schedule", branch="main", repository=REPO, attempts=1):
    """Return a complete API-shaped history without making network requests."""
    def fetch(path):
        if "/actions/workflows/" in path:
            return {"total_count": 1, "workflow_runs": [{
                "id": 123, "event": event, "head_branch": branch,
                "head_repository": {"full_name": repository}, "run_attempt": attempts,
                "status": "completed", "conclusion": "failure",
            }]}
        if "/attempts/1/jobs?" in path:
            return {"total_count": len(jobs), "jobs": jobs}
        if "/attempts/2/jobs?" in path:
            return {"total_count": 0, "jobs": []}
        raise AssertionError(f"Unexpected GitHub API path: {path}")
    return fetch


def job(step_name, conclusion="success", name="email (survey_marine)", job_conclusion="success"):
    return {"id": 456, "name": name, "status": "completed", "conclusion": job_conclusion,
            "steps": [{"name": step_name, "status": "completed", "conclusion": conclusion}]}


class GateDedupeTests(unittest.TestCase):
    def accepted(self, fetch):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": REPO}):
            return gate.already_sent(REPORT_DATE, datetime(2026, 10, 21, tzinfo=timezone.utc),
                                     fetch=fetch, workflow="daily-survey.yml", sent_step=PREFIX)

    def test_matrix_and_reusable_job_names_match_dated_step(self):
        for name in ("email (survey_marine)", "send / email (survey_marine)"):
            with self.subTest(name=name):
                self.assertTrue(self.accepted(history_fetch([job(f"{PREFIX}{REPORT_DATE}", name=name)])))

    def test_successful_delivery_is_kept_when_another_step_failed(self):
        self.assertTrue(self.accepted(history_fetch([
            job(f"{PREFIX}{REPORT_DATE}", job_conclusion="failure"),
        ])))

    def test_prior_attempt_delivery_is_not_hidden_by_rerun(self):
        self.assertTrue(self.accepted(history_fetch([job(f"{PREFIX}{REPORT_DATE}")], attempts=2)))

    def test_test_dry_failed_and_other_day_steps_never_mark_sent(self):
        for step_name, result in [
            ("Test send survey_marine IST for 2026-10-21", "success"),
            ("Dry run survey_marine IST for 2026-10-21", "success"),
            ("Deliver survey_marine IST for 2026-10-20", "success"),
            ("Deliver survey_marine IST for 2026-10-21", "failure"),
            ("Deliver survey_measure IST for 2026-10-21", "success"),
        ]:
            with self.subTest(step_name=step_name, result=result):
                self.assertFalse(self.accepted(history_fetch([job(step_name, conclusion=result)])))

    def test_untrusted_runs_never_mark_sent(self):
        for kwargs in ({"event": "pull_request"}, {"branch": "preview"}, {"repository": "fork/example"}):
            with self.subTest(kwargs=kwargs):
                self.assertFalse(self.accepted(history_fetch([job(f"{PREFIX}{REPORT_DATE}")], **kwargs)))

    def test_unavailable_history_fails_closed(self):
        def unavailable(path):
            raise OSError("API unavailable")
        with self.assertRaises(gate.DedupeUnavailable):
            self.accepted(unavailable)

    def test_incomplete_history_fails_closed(self):
        def incomplete(path):
            return {"total_count": 2, "workflow_runs": []}
        with self.assertRaises(gate.DedupeUnavailable):
            self.accepted(incomplete)


class GateScheduleTests(unittest.TestCase):
    def test_first_gate_keeps_the_date_frozen_by_settings(self):
        now = datetime(2026, 10, 21, 23, tzinfo=timezone.utc)
        argv = ["catchup_gate.py", "--phase", "1", "--event", "schedule",
                "--report-date", "2026-10-21", "--tz", "America/Los_Angeles", "--target", "05:05"]
        with patch.object(gate.sys, "argv", argv), patch.object(gate, "now_utc", return_value=now), \
                patch.object(gate, "already_sent", return_value=False), \
                patch.object(gate.time, "sleep") as sleep, patch.object(gate, "emit") as emit, \
                contextlib.redirect_stdout(io.StringIO()):
            gate.main()
        self.assertEqual(emit.call_args.kwargs["report_date"], date(2026, 10, 21))
        self.assertEqual(emit.call_args.kwargs["proceed"], "true")
        sleep.assert_called_once_with(0)

    def test_all_b_crons_fit_gate_cap_and_target_intended_day(self):
        # PT's UTC cron day is the target local date; IST's is the day before.
        report_days = (date(2026, 3, 7), date(2026, 3, 8), date(2026, 10, 31), date(2026, 11, 1))
        for report_day in report_days:
            for zone, minutes, hours, day_offset in (
                ("America/Los_Angeles", (45, 47, 49, 51), (3, 6, 9), 0),
                ("Asia/Kolkata", (11, 13, 15, 17), (13, 16, 19), -1),
            ):
                cron_day = report_day + timedelta(days=day_offset)
                for minute in minutes:
                    for hour in hours:
                        now = datetime(cron_day.year, cron_day.month, cron_day.day, hour, minute, tzinfo=timezone.utc)
                        with self.subTest(zone=zone, now=now):
                            actual_date, wait, proceed = gate.plan(now, zone, "05:05")
                            self.assertEqual(actual_date, report_day)
                            self.assertTrue(proceed)
                            self.assertGreater(wait, 0)
                            self.assertLessEqual(wait, gate.MAX_WAIT)
                            release = (now + timedelta(seconds=wait)).astimezone(ZoneInfo(zone))
                            self.assertEqual(release.isoformat()[:16], f"{report_day}T05:05")

    def test_second_gate_recomputes_remaining_wait_after_queue_delay(self):
        now = datetime(2026, 3, 8, 11, 35, tzinfo=timezone.utc)
        self.assertEqual(gate.phase2_wait(date(2026, 3, 8), now, "America/Los_Angeles", "05:05"), 1800)


if __name__ == "__main__":
    unittest.main()
