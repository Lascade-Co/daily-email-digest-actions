import contextlib
import io
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from scripts.common import catchup_gate as gate
from scripts.ta_trigger import trigger as T


def utc(text):
    return datetime.fromisoformat(text).astimezone(timezone.utc)


class Clock:
    def __init__(self, start):
        self.now = start

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += timedelta(seconds=seconds)


class FakeTA:
    """Each dispatch takes `durations[(kind, phase)]` (a list, one per attempt) and ends with `outcomes`."""

    def __init__(self, clock, outcomes=None, durations=None, fail_dispatch=()):
        self.clock, self.outcomes, self.durations = clock, outcomes or {}, durations or {}
        self.fail_dispatch = set(fail_dispatch)
        self.runs, self.dispatched, self.cancelled, self.attempts = {}, [], [], {}

    def dispatch(self, workflow, inputs):
        kind = next(k for k, w in T.KINDS.items() if w == workflow)
        phase = inputs.get("phase", "dry")
        attempt = self.attempts.get((kind, phase), 0)
        self.attempts[(kind, phase)] = attempt + 1
        if (kind, phase, attempt) in self.fail_dispatch:
            raise RuntimeError("api down")
        run_id = 1000 + len(self.dispatched)
        self.dispatched.append((kind, phase, inputs))
        minutes = self.durations.get((kind, phase), [1, 1])[attempt]
        outcome = self.outcomes.get((kind, phase), ["success", "success"])[attempt]
        self.runs[run_id] = (self.clock() + timedelta(minutes=minutes), outcome)
        return run_id

    def run(self, run_id):
        done_at, outcome = self.runs[run_id]
        if run_id in self.cancelled:
            return {"status": "completed", "conclusion": "cancelled"}
        if self.clock() >= done_at:
            return {"status": "completed", "conclusion": outcome}
        return {"status": "in_progress"}

    def cancel(self, run_id):
        self.cancelled.append(run_id)


def chain(ta, clock, mode="scheduled", edition="pt", day="2026-10-23", to=""):
    holds = []

    def hold():   # like hold.hold_until: advance to 05:55 local
        holds.append(clock())
        clock.now = max(clock.now, c.local("05:55").astimezone(timezone.utc))

    c = T.Chain(ta, edition, day, T.ZONES[edition], mode, to, clock=clock, sleep=clock.sleep, hold=hold)
    return c, holds


def quiet(fn):
    with contextlib.redirect_stdout(io.StringIO()) as out:
        result = fn()
    return result, out.getvalue()


class SettingsTests(unittest.TestCase):
    def test_schedules_select_edition_and_upcoming_report_day(self):
        cases = [
            ("53 3,6,9 * * *", "2026-10-23T03:53:00+00:00", "pt", "2026-10-23"),   # 20:53 PDT the evening before
            ("53 3,6,9 * * *", "2026-11-01T09:53:00+00:00", "pt", "2026-11-01"),   # DST end night
            ("53 3,6,9 * * *", "2026-03-08T03:53:00+00:00", "pt", "2026-03-08"),   # DST start night
            ("19 13,16,19 * * *", "2026-10-22T13:19:00+00:00", "ist", "2026-10-23"),
            ("19 13,16,19 * * *", "2026-10-22T19:19:00+00:00", "ist", "2026-10-23"),
        ]
        for schedule, now, edition, day in cases:
            with self.subTest(schedule=schedule, now=now):
                out = T.settings({"EVENT": "schedule", "SCHEDULE": schedule}, utc(now))
                matrix = json.loads(out["matrix"])
                self.assertEqual([m["edition"] for m in matrix], [edition])
                self.assertEqual(matrix[0]["report_date"], day)
                self.assertEqual(matrix[0]["step"], f"Delivered TA {edition.upper()} for {day}")
                self.assertEqual(out["sent_step"], f"Delivered TA {edition.upper()} for ")
                # The gates can reach 05:05 from every scheduled start.
                _, wait, ok = gate.plan(utc(now), tz=T.ZONES[edition], target=(5, 5))
                self.assertTrue(ok and wait > 0)

    def test_manual_runs_use_latest_completed_cutoff(self):
        env = {"EVENT": "workflow_dispatch", "MODE": "dry", "INPUT_EDITION": "both"}
        out = T.settings(env, utc("2026-10-22T20:00:00-07:00"))     # 20:00 PDT = 08:30 IST on the 23rd
        days = {m["edition"]: m["report_date"] for m in json.loads(out["matrix"])}
        self.assertEqual(days, {"pt": "2026-10-22", "ist": "2026-10-23"})
        out = T.settings(env, utc("2026-10-22T04:30:00-07:00"))     # before the PT cutoff
        self.assertEqual(json.loads(out["matrix"])[0]["report_date"], "2026-10-21")

    def test_step_names_keep_dry_and_test_out_of_delivery_history(self):
        now = utc("2026-10-22T10:00:00-07:00")
        names = {}
        for mode, to in (("dry", ""), ("test", "t@example.com"), ("recovery", "")):
            env = {"EVENT": "workflow_dispatch", "MODE": mode, "INPUT_EDITION": "pt", "TEST_TO": to,
                   "GITHUB_REF": "refs/heads/main"}
            names[mode] = json.loads(T.settings(env, now)["matrix"])[0]["step"]
        self.assertEqual(names["recovery"], "Delivered TA PT for 2026-10-22")
        for mode in ("dry", "test"):
            self.assertFalse(names[mode].startswith("Delivered TA PT for "), names[mode])

    def test_invalid_manual_combinations_are_rejected(self):
        bad = [
            {"MODE": "test"},                                            # no recipient
            {"MODE": "dry", "TEST_TO": "t@example.com"},                 # recipient outside test
            {"MODE": "recovery", "GITHUB_REF": "refs/heads/feature"},    # production off main
            {"MODE": "recovery", "GITHUB_REF": "refs/heads/main", "GITHUB_RUN_ATTEMPT": "2"},
            {"MODE": "send"},
            {"MODE": "test", "TEST_TO": "a@example.com,\nb@example.com"},
        ]
        for extra in bad:
            with self.subTest(extra=extra), self.assertRaises(T.TriggerError):
                T.settings({"EVENT": "workflow_dispatch", "INPUT_EDITION": "pt", **extra}, utc("2026-10-22T10:00:00-07:00"))
        with self.assertRaises(T.TriggerError):
            T.settings({"EVENT": "schedule", "SCHEDULE": "53 3,6,9 * * *", "GITHUB_RUN_ATTEMPT": "2"},
                       utc("2026-10-23T03:53:00+00:00"))
        with self.assertRaises(T.TriggerError):
            T.settings({"EVENT": "schedule", "SCHEDULE": "0 0 * * *"}, utc("2026-10-23T03:53:00+00:00"))


class ChainTests(unittest.TestCase):
    def scheduled_clock(self):
        return Clock(utc("2026-10-23T05:05:00-07:00"))

    def test_scheduled_chain_builds_holds_then_sends_both_with_matching_inputs(self):
        clock = self.scheduled_clock()
        ta = FakeTA(clock)
        c, holds = chain(ta, clock)
        result, out = quiet(c.deliver)
        self.assertEqual(result, {"issues": "delivered", "crash": "delivered"})
        self.assertEqual(len(holds), 1)
        phases = [(k, p) for k, p, _ in ta.dispatched]
        self.assertEqual(phases, [("issues", "build"), ("crash", "build"), ("issues", "send"), ("crash", "send")])
        builds = {k: i for k, p, i in ta.dispatched if p == "build"}
        for kind, phase, inputs in ta.dispatched:
            self.assertEqual(inputs["end"], "2026-10-23 05:00")
            self.assertEqual(inputs["edition"], "pt")
            self.assertNotIn("to", inputs)
            self.assertNotIn("dry", inputs)
        sends = [i for _, p, i in ta.dispatched if p == "send"]
        self.assertEqual([s["build_run"] for s in sends], ["1000", "1001"])
        self.assertNotIn("1000", out)

    def test_timed_out_build_does_not_block_the_healthy_kind(self):
        clock = self.scheduled_clock()
        ta = FakeTA(clock, durations={("issues", "build"): [120, 1]})
        c, holds = chain(ta, clock)
        result, _ = quiet(c.deliver)
        self.assertEqual(result, {"issues": "build timeout", "crash": "delivered"})
        self.assertEqual(ta.cancelled, [1000])
        self.assertEqual([k for k, p, _ in ta.dispatched if p == "send"], ["crash"])
        self.assertEqual(len(holds), 1)

    def test_failed_build_is_redispatched_once(self):
        clock = self.scheduled_clock()
        ta = FakeTA(clock, outcomes={("crash", "build"): ["failure", "success"]})
        c, _ = chain(ta, clock)
        result, _ = quiet(c.deliver)
        self.assertEqual(result, {"issues": "delivered", "crash": "delivered"})
        crash_send = next(i for k, p, i in ta.dispatched if (k, p) == ("crash", "send"))
        self.assertEqual(crash_send["build_run"], "1002")   # the retry's build, not the failed one

    def test_two_failed_sends_report_failure(self):
        clock = self.scheduled_clock()
        ta = FakeTA(clock, outcomes={("issues", "send"): ["failure", "failure"]})
        c, _ = chain(ta, clock)
        result, _ = quiet(c.deliver)
        self.assertEqual(result["issues"], "send failure")
        self.assertEqual(result["crash"], "delivered")
        self.assertEqual(sum(1 for k, p, _ in ta.dispatched if (k, p) == ("issues", "send")), 2)

    def test_dispatch_api_failure_is_retried(self):
        clock = self.scheduled_clock()
        ta = FakeTA(clock, fail_dispatch={("issues", "build", 0)})
        c, _ = chain(ta, clock)
        result, _ = quiet(c.deliver)
        self.assertEqual(result["issues"], "delivered")

    def test_manual_send_budget_starts_at_send_dispatch(self):
        clock = Clock(utc("2026-10-22T11:00:00-07:00"))
        ta = FakeTA(clock, durations={("issues", "build"): [20, 1], ("issues", "send"): [10, 1]})
        c, holds = chain(ta, clock, mode="test", day="2026-10-22", to="t@example.com")
        result, _ = quiet(c.deliver)
        self.assertEqual(result, {"issues": "delivered", "crash": "delivered"})
        self.assertEqual(holds, [])                                 # manual runs never hold
        for _, _, inputs in ta.dispatched:
            self.assertEqual(inputs["to"], "t@example.com")

    def test_dry_mode_runs_phase_all_dry_only(self):
        clock = Clock(utc("2026-10-22T11:00:00-07:00"))
        ta = FakeTA(clock)
        c, holds = chain(ta, clock, mode="dry", day="2026-10-22")
        result, _ = quiet(c.deliver)
        self.assertEqual(result, {"issues": "dry run ok", "crash": "dry run ok"})
        self.assertEqual([i for _, _, i in ta.dispatched],
                         [{"edition": "pt", "end": "2026-10-22 05:00", "dry": "true"}] * 2)
        self.assertEqual(holds, [])

    def test_slow_send_does_not_block_the_other_send(self):
        clock = self.scheduled_clock()
        ta = FakeTA(clock, durations={("issues", "send"): [60, 1]})
        c, _ = chain(ta, clock)
        result, _ = quiet(c.deliver)
        self.assertEqual(result, {"issues": "send timeout", "crash": "delivered"})
        crash_send = next(r for r, (k, p, _) in zip(sorted(ta.runs), ta.dispatched) if (k, p) == ("crash", "send"))
        self.assertNotIn(crash_send, ta.cancelled)

    def test_early_crash_failure_is_retried_while_issues_is_still_building(self):
        clock = self.scheduled_clock()
        ta = FakeTA(clock, outcomes={("crash", "build"): ["failure", "success"]},
                    durations={("issues", "build"): [40, 1], ("crash", "build"): [1, 1]})
        c, _ = chain(ta, clock)
        result, _ = quiet(c.deliver)
        self.assertEqual(result, {"issues": "delivered", "crash": "delivered"})
        order = [(k, p) for k, p, _ in ta.dispatched]
        self.assertLess(order.index(("crash", "build"), 2), 3)   # crash retried before any send

    def test_dry_builds_get_the_build_budget(self):
        clock = Clock(utc("2026-10-22T11:00:00-07:00"))
        ta = FakeTA(clock, durations={("issues", "dry"): [20, 1]})
        c, _ = chain(ta, clock, mode="dry", day="2026-10-22")
        result, _ = quiet(c.deliver)
        self.assertEqual(result["issues"], "dry run ok")

    def test_job_only_rerun_of_production_deliver_is_refused(self):
        import os
        from unittest.mock import patch
        env = {"EDITION": "pt", "REPORT_DATE": "2026-10-22", "ZONE": T.ZONES["pt"], "MODE": "recovery",
               "GITHUB_RUN_ATTEMPT": "2"}
        with patch.dict(os.environ, env), patch.object(T, "TA", side_effect=AssertionError("dispatched")), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(T.main(["deliver"]), 2)

    def test_ist_scheduled_deadlines_use_ist(self):
        clock = Clock(utc("2026-10-23T05:05:00+05:30"))
        c, _ = chain(FakeTA(clock), clock, edition="ist")
        self.assertEqual(c.deadline("build", clock()), utc("2026-10-23T05:50:00+05:30"))
        self.assertEqual(c.deadline("send", clock()), utc("2026-10-23T06:10:00+05:30"))


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / ".github/workflows/ta-digest-trigger.yml"
        self.wf = yaml.load(path.read_text(), Loader=yaml.BaseLoader)

    def test_token_is_bound_only_to_the_dated_deliver_step(self):
        jobs = self.wf["jobs"]
        users = [(name, step.get("name")) for name, job in jobs.items() for step in job.get("steps", [])
                 if "TA_DIGEST_DISPATCH_TOKEN" in json.dumps(step)]
        self.assertEqual(users, [("deliver", "${{ matrix.step }}")])
        self.assertEqual(jobs["deliver"]["environment"], "ta-dispatch")
        self.assertNotIn("pull_request", self.wf["on"])
        self.assertNotIn("pull_request_target", self.wf["on"])

    def test_mask_steps_read_the_event_file_not_env(self):
        for job in ("gate", "deliver"):
            first = self.wf["jobs"][job]["steps"][0]
            self.assertEqual(first["name"], "Mask test recipient")
            self.assertNotIn("env", first)
            self.assertIn("GITHUB_EVENT_PATH", first["run"])
            import os, subprocess, tempfile
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as event:
                json.dump({"inputs": {"to": "a@example.com,\nb@example.com; c%d@example.com"}}, event)
            out = subprocess.run(["bash", "-c", first["run"]], capture_output=True, text=True,
                                 env={**os.environ, "GITHUB_EVENT_PATH": event.name}).stdout.splitlines()
            os.unlink(event.name)
            self.assertTrue(all(line.startswith("::add-mask::") for line in out), out)
            self.assertTrue({"::add-mask::a@example.com", "::add-mask::b@example.com",
                             "::add-mask::c%25d@example.com"} <= set(out), out)

    def test_gates_target_0505_and_dedupe_on_the_production_prefix(self):
        for job in ("gate", "gate2"):
            run = next(s["run"] for s in self.wf["jobs"][job]["steps"] if s.get("id") == "timing")
            self.assertIn("--target 05:05", run)
            self.assertIn("--workflow ta-digest-trigger.yml", run)
            self.assertIn('--sent-step "$SENT_STEP"', run)

    def test_schedules_if_present_match_settings(self):
        crons = {entry["cron"] for entry in self.wf["on"].get("schedule", [])}
        self.assertTrue(crons <= set(T.SCHEDULES), crons)
