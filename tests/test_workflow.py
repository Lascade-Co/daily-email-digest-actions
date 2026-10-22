"""Workflow settings and delivery-history boundaries; no network or mail."""
import contextlib
import datetime as dt
import importlib
import io
import json
import os
from pathlib import Path
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
                "GITHUB_REF": "refs/heads/main", **kwargs}

    def test_manual_date_uses_edition_cutoff_and_both_defers_date(self):
        pt = self.w.settings(self.env(), self.now)
        ist = self.w.settings(self.env(INPUT_EDITION="ist"), self.now)
        both = self.w.settings(self.env(INPUT_EDITION="both"), self.now)
        self.assertEqual(pt["report_date"], "2026-10-20")
        self.assertEqual(ist["report_date"], "2026-10-21")
        self.assertEqual(json.loads(both["editions"]), ["pt", "ist"])
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
            value = self.w.settings(self.env(DIGEST="revenue", **overrides), self.now)
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
        value = self.w.settings(self.env(DRY_RUN="false", RECOVERY="true", DIGEST="revenue"), self.now)
        with patch.object(self.w.G, "already_sent", return_value=True) as history:
            self.assertTrue(self.w.dedupe(value, "revenue"))
        self.assertEqual(history.call_args.kwargs["sent_step"], "Deliver revenue PT for ")
        self.assertEqual(history.call_args.kwargs["workflow"], "daily-revenue.yml")
        with patch.object(self.w.G, "already_sent", side_effect=self.w.G.DedupeUnavailable()):
            with self.assertRaises(self.w.G.DedupeUnavailable):
                self.w.dedupe(value, "revenue")

    def test_dry_or_test_does_not_query_history(self):
        for overrides in [{}, {"DRY_RUN": "false", "TEST_TO": "fixture@example.test"}]:
            value = self.w.settings(self.env(DIGEST="revenue", **overrides), self.now)
            with patch.object(self.w.G, "already_sent", side_effect=AssertionError("network")):
                self.assertFalse(self.w.dedupe(value, "revenue"))

    def test_settings_never_emit_test_recipient(self):
        recipient = "private-fixture@example.test"
        env = self.env(DIGEST="revenue", DRY_RUN="false", TEST_TO=recipient, NOW="2026-10-21T02:00:00Z")
        output = io.StringIO()
        with patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(output):
            self.assertEqual(self.w.main(["settings"]), 0)
        self.assertNotIn(recipient, output.getvalue())

    def test_workflow_test_mode_needs_no_recipient_environment_value(self):
        value = self.w.settings(self.env(DIGEST="revenue", DRY_RUN="false", TEST_MODE="true"), self.now)
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


if __name__ == "__main__":
    unittest.main()
