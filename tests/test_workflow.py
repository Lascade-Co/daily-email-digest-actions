"""Workflow settings and delivery-history boundaries; no network or mail."""
import contextlib
import datetime as dt
import importlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.w = importlib.import_module("scripts.common.workflow")
        self.now = dt.datetime(2026, 10, 21, 2, tzinfo=dt.timezone.utc)

    def env(self, **kwargs):
        return {"EVENT": "workflow_dispatch", "WORKFLOW": "daily-revenue.yml",
                "INPUT_EDITION": "pt", "DRY_RUN": "true",
                "GITHUB_REF": "refs/heads/main", "GITHUB_RUN_ATTEMPT": "1",
                "RUN_CREATED_AT": "2026-10-21T00:00:00Z", **kwargs}

    def test_manual_date_uses_edition_cutoff_and_both_freezes_dates(self):
        pt = self.w.settings(self.env(), self.now)
        ist = self.w.settings(self.env(INPUT_EDITION="ist"), self.now)
        both = self.w.settings(self.env(INPUT_EDITION="both"), self.now)
        self.assertEqual(pt["report_date"], "2026-10-20")
        self.assertEqual(ist["report_date"], "2026-10-21")
        self.assertEqual(json.loads(both["editions"]), [
            {"edition": "pt", "report_date": "2026-10-20"},
            {"edition": "ist", "report_date": "2026-10-21"},
        ])
        self.assertEqual(both["report_date"], "")

    def test_schedule_is_validated_and_uses_gate_report_day(self):
        for workflow, minute in [("revenue", 45), ("reviews", 47),
                                 ("survey", 49), ("conversion", 51)]:
            settings = self.w.settings(self.env(
                EVENT="schedule", WORKFLOW=f"daily-{workflow}.yml",
                SCHEDULE=f"{minute} 3,6,9 * * *", DRY_RUN="false"), self.now)
            self.assertEqual(settings["edition"], "pt")
            self.assertEqual(settings["report_date"], "2026-10-21")
        with self.assertRaises(ValueError):
            self.w.settings(self.env(EVENT="schedule", SCHEDULE="0 14 * * *"), self.now)

    def test_dry_and_test_names_do_not_record_production_delivery(self):
        for overrides, prefix in [({}, "Dry run "),
                                  ({"DRY_RUN": "false", "TEST_TO": "fixture@example.test"}, "Test send "),
                                  ({"DRY_RUN": "false", "RECOVERY": "true"}, "Deliver ")]:
            value = self.w.settings(self.env(DIGEST="revenue", REPORT_DATE="2026-10-20", **overrides), self.now)
            self.assertEqual(value["send_step"], prefix + "revenue PT for 2026-10-20")
        with self.assertRaises(ValueError):
            self.w.settings(self.env(DRY_RUN="false"), self.now)

    def test_digest_args_build_the_requested_survey_product_without_recipients(self):
        value = self.w.settings(self.env(WORKFLOW="daily-survey.yml", DIGEST="survey_measure"), self.now)
        argv = self.w.digest_args("survey_measure", value)
        self.assertEqual(argv[:2], ["-m", "scripts.survey.survey_main"])
        self.assertIn("data/survey_measure.json", argv)
        self.assertIn("--dry-run", argv)
        self.assertEqual(argv[argv.index("--edition") + 1], "pt")
        self.assertNotIn("@", " ".join(argv))

    def test_dedupe_checks_per_digest_and_fails_closed(self):
        value = self.w.settings(self.env(DRY_RUN="false", RECOVERY="true", DIGEST="revenue",
                                         REPORT_DATE="2026-10-20"), self.now)
        with patch.object(self.w.G, "already_sent", return_value=True) as history:
            self.assertTrue(self.w.dedupe(value, "revenue"))
        self.assertEqual(history.call_args.kwargs["sent_step"], "Deliver revenue PT for ")
        self.assertEqual(history.call_args.kwargs["workflow"], "daily-revenue.yml")
        with patch.object(self.w.G, "already_sent", side_effect=self.w.G.DedupeUnavailable()):
            with self.assertRaises(self.w.G.DedupeUnavailable):
                self.w.dedupe(value, "revenue")

    def test_dry_or_test_does_not_query_history(self):
        for overrides in [{}, {"DRY_RUN": "false", "TEST_TO": "fixture@example.test"}]:
            value = self.w.settings(self.env(DIGEST="revenue", REPORT_DATE="2026-10-20", **overrides), self.now)
            with patch.object(self.w.G, "already_sent", side_effect=AssertionError("network")):
                self.assertFalse(self.w.dedupe(value, "revenue"))

    def test_settings_never_emit_test_recipient(self):
        recipient = "private-fixture@example.test"
        env = self.env(DIGEST="revenue", DRY_RUN="false", TEST_TO=recipient,
                       REPORT_DATE="2026-10-20", NOW="2026-10-21T02:00:00Z")
        output = io.StringIO()
        with patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(output):
            self.assertEqual(self.w.main(["settings"]), 0)
        self.assertNotIn(recipient, output.getvalue())

    def test_workflow_test_mode_needs_no_recipient_environment_value(self):
        value = self.w.settings(self.env(DIGEST="revenue", DRY_RUN="false", TEST_MODE="true",
                                         REPORT_DATE="2026-10-20"), self.now)
        self.assertEqual(value["mode"], "test")
        self.assertEqual(value["send_step"], "Test send revenue PT for 2026-10-20")

    def test_production_recovery_rejects_non_main_and_unknown_refs(self):
        for ref in ("refs/heads/codex/digest-emails/b", "refs/tags/main", ""):
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                self.w.settings(self.env(DRY_RUN="false", RECOVERY="true", GITHUB_REF=ref), self.now)

    def test_branch_previews_and_test_sends_remain_allowed(self):
        branch = "refs/heads/codex/digest-emails/b"
        for overrides, mode in [({"DRY_RUN": "true"}, "dry"),
                                ({"DRY_RUN": "false", "TEST_MODE": "true"}, "test")]:
            with self.subTest(mode=mode):
                value = self.w.settings(self.env(GITHUB_REF=branch, RECOVERY="true", **overrides), self.now)
                self.assertEqual(value["mode"], mode)

    def test_production_requires_a_fresh_run_attempt(self):
        for attempt in ("2", "99", "", "01"):
            with self.subTest(attempt=attempt), self.assertRaisesRegex(
                    ValueError, "production delivery requires a fresh run; re-runs are not allowed, dispatch recovery instead"):
                self.w.settings(self.env(DRY_RUN="false", RECOVERY="true",
                    GITHUB_RUN_ATTEMPT=attempt), self.now)

    def test_dry_and_test_reruns_remain_allowed(self):
        for mode in ({"DRY_RUN": "true"}, {"DRY_RUN": "false", "TEST_MODE": "true"}):
            value = self.w.settings(self.env(GITHUB_RUN_ATTEMPT="2", DIGEST="revenue",
                REPORT_DATE="2026-10-20", **mode), self.now)
            self.assertIn(value["mode"], ("dry", "test"))

    def test_rejected_rerun_cli_explains_how_to_recover(self):
        env = self.env(DRY_RUN="false", RECOVERY="true", GITHUB_RUN_ATTEMPT="2",
                       NOW="2026-10-21T02:00:00Z")
        output, errors = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(output), \
                contextlib.redirect_stderr(errors):
            self.assertEqual(self.w.main(["settings"]), 2)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(errors.getvalue().strip(),
                         "production delivery requires a fresh run; re-runs are not allowed, dispatch recovery instead")

    def test_scheduled_run_rejects_creation_older_than_36_hours(self):
        for age, allowed in ((dt.timedelta(hours=36), True),
                             (dt.timedelta(hours=36, seconds=1), False)):
            env = self.env(EVENT="schedule", SCHEDULE="45 3,6,9 * * *", DRY_RUN="false",
                           RUN_CREATED_AT=(self.now - age).isoformat())
            with self.subTest(age=age):
                if allowed:
                    self.assertEqual(self.w.settings(env, self.now)["mode"], "real")
                else:
                    with self.assertRaisesRegex(ValueError, "scheduled run is older than 36 hours"):
                        self.w.settings(env, self.now)

    def test_scheduled_creation_time_uses_own_run_api_not_repository_creation(self):
        scratch = ROOT / ".scratch"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            event = Path(directory) / "event.json"
            event.write_text(json.dumps({"schedule": "45 3,6,9 * * *",
                                        "repository": {"created_at": "2000-01-01T00:00:00Z"}}))
            env = self.env(EVENT="schedule", SCHEDULE="45 3,6,9 * * *", DRY_RUN="false",
                           RUN_CREATED_AT="", GITHUB_EVENT_PATH=str(event),
                           GITHUB_REPOSITORY="Lascade-Co/daily-email-digest-actions", GITHUB_RUN_ID="123")
            for created, allowed in (("2026-10-21T00:00:00Z", True), ("2026-10-01T00:00:00Z", False)):
                with self.subTest(created=created), patch.object(self.w.G, "gh_json",
                        return_value={"id": 123, "created_at": created}) as fetch:
                    if allowed:
                        self.w.settings(env, self.now)
                    else:
                        with self.assertRaisesRegex(ValueError, "older than 36 hours"):
                            self.w.settings(env, self.now)
                    fetch.assert_called_once_with("repos/Lascade-Co/daily-email-digest-actions/actions/runs/123")

    def test_scheduled_creation_time_accepts_own_event_metadata(self):
        scratch = ROOT / ".scratch"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            event = Path(directory) / "event.json"
            event.write_text(json.dumps({"workflow_run": {"id": 123, "created_at": "2026-10-21T00:00:00Z"}}))
            env = self.env(EVENT="schedule", SCHEDULE="45 3,6,9 * * *", DRY_RUN="false",
                           RUN_CREATED_AT="", GITHUB_EVENT_PATH=str(event), GITHUB_RUN_ID="123")
            with patch.object(self.w.G, "gh_json", side_effect=AssertionError("unexpected API call")):
                self.assertEqual(self.w.settings(env, self.now)["mode"], "real")

    def test_unavailable_or_invalid_run_creation_time_fails_closed(self):
        for timestamp in ("bad", "2026-10-21T00:00:00", ""):
            with self.subTest(timestamp=timestamp), patch.object(self.w.G, "gh_json", side_effect=OSError("private data")):
                with self.assertRaisesRegex(ValueError, "scheduled run creation time unavailable"):
                    self.w.settings(self.env(EVENT="schedule", SCHEDULE="45 3,6,9 * * *", DRY_RUN="false",
                        RUN_CREATED_AT=timestamp, GITHUB_REPOSITORY="Lascade-Co/daily-email-digest-actions",
                        GITHUB_RUN_ID="123"), self.now)

    def test_reusable_real_and_test_settings_require_frozen_report_date(self):
        for mode in ({"RECOVERY": "true"}, {"TEST_MODE": "true"}):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "REPORT_DATE is required"):
                self.w.settings(self.env(DIGEST="revenue", DRY_RUN="false", INPUT_DATE="2026-10-20", **mode), self.now)
        self.assertEqual(self.w.settings(self.env(DIGEST="revenue"), self.now)["report_date"], "2026-10-20")

    def test_explicit_dispatch_date_is_frozen_for_both_editions(self):
        value = self.w.settings(self.env(INPUT_EDITION="both", INPUT_DATE="2026-10-18"), self.now)
        self.assertEqual(json.loads(value["editions"]), [
            {"edition": "pt", "report_date": "2026-10-18"},
            {"edition": "ist", "report_date": "2026-10-18"},
        ])

    def test_matrix_legs_keep_each_edition_date_across_cutoff(self):
        for instant, expected in [
            ("2026-10-20T23:29:59+00:00", ["2026-10-20", "2026-10-20"]),
            ("2026-10-21T11:59:59+00:00", ["2026-10-20", "2026-10-21"]),
        ]:
            with self.subTest(instant=instant):
                before = dt.datetime.fromisoformat(instant)
                gate_env = self.env(WORKFLOW="daily-survey.yml", INPUT_EDITION="both",
                                    DRY_RUN="false", TEST_MODE="true")
                gate = self.w.settings(gate_env, before)
                matrix = json.loads(gate["editions"])
                self.assertEqual(matrix, [dict(edition=e, report_date=d) for e, d in zip(("pt", "ist"), expected)])
                for entry in matrix:
                    for index, digest in enumerate(("survey_marine", "survey_measure")):
                        leg = self.w.settings({**gate_env, "INPUT_EDITION": entry["edition"],
                            "REPORT_DATE": entry["report_date"], "DIGEST": digest},
                            before + dt.timedelta(minutes=index, seconds=2))
                        self.assertEqual(leg["report_date"], entry["report_date"])
                        self.assertEqual(leg["send_step"], f"Test send {digest} {entry['edition'].upper()} for {entry['report_date']}")


if __name__ == "__main__":
    unittest.main()
