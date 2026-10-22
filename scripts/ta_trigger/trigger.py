"""On-time trigger for the private Lascade-Co/TA-daily-issues-digest emails.

GitHub starts that repository's crons hours late, and it is private, so a job
sleeping there until 05:55 would burn the organisation's shared Actions
minutes. This public workflow sleeps for free in the gate jobs, then:

  05:05 local  dispatch phase=build of the issues and crash workflows
  05:55 local  dispatch phase=send build_run=<that build> for each built kind

Each kind is independent: a failed or slow build never blocks the other
kind's send. TA's delivery markers and Resend idempotency keys make a repeated
send of the same day a no-op. Public logs carry only kind and outcome, never
run ids, URLs, subjects or recipients.

  settings  resolve editions, report dates and step names (GITHUB_OUTPUT)
  deliver   run one edition's build -> hold -> send chain
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

from scripts.common import catchup_gate as G
from scripts.common import hold as H

REPO = "Lascade-Co/TA-daily-issues-digest"
KINDS = {"issues": "daily-digest.yml", "crash": "crash-digest.yml"}
ZONES = {"pt": "America/Los_Angeles", "ist": "Asia/Kolkata"}
SCHEDULES = {"53 3,6,9 * * *": "pt", "19 13,16,19 * * *": "ist"}
STEP = {"scheduled": "Delivered", "recovery": "Delivered", "test": "Test", "dry": "Dry run"}
POLL_SECONDS = 15
MANUAL_BUILD = dt.timedelta(minutes=30)
MANUAL_SEND = dt.timedelta(minutes=15)


class TriggerError(ValueError):
    """A fixed, public-safe reason."""


def now_utc():
    return G.now_utc()


def latest_cutoff_day(now, zone):
    local = now.astimezone(ZoneInfo(zone))
    return local.date() - dt.timedelta(days=local.time() < dt.time(5))


def settings(env, now):
    event = env.get("EVENT", "")
    if event == "schedule":
        edition = SCHEDULES.get(env.get("SCHEDULE", ""))
        if not edition:
            raise TriggerError("unknown schedule")
        mode, editions = "scheduled", [edition]
    elif event == "workflow_dispatch":
        mode = env.get("MODE", "dry")
        choice = env.get("INPUT_EDITION") or "both"
        if mode not in ("dry", "test", "recovery") or choice not in ("pt", "ist", "both"):
            raise TriggerError("invalid mode or edition")
        if (mode == "test") != bool(env.get("TEST_TO", "").strip()):
            raise TriggerError("mode=test requires to; other modes must leave to empty")
        if mode == "recovery" and env.get("GITHUB_REF") != "refs/heads/main":
            raise TriggerError("recovery must run from main")
        editions = ["pt", "ist"] if choice == "both" else [choice]
    else:
        raise TriggerError("unsupported event")
    if mode in ("scheduled", "recovery") and env.get("GITHUB_RUN_ATTEMPT", "1") != "1":
        raise TriggerError("production re-runs are not allowed; dispatch mode=recovery instead")
    matrix = []
    for edition in editions:
        zone = ZONES[edition]
        day = (G.plan(now, tz=zone, target=(5, 5))[0] if mode == "scheduled"
               else latest_cutoff_day(now, zone))
        matrix.append({"edition": edition, "zone": zone, "report_date": day.isoformat(),
                       "step": f"{STEP[mode]} TA {edition.upper()} for {day.isoformat()}"})
    return {
        "mode": mode,
        "matrix": json.dumps(matrix, separators=(",", ":")),
        "zone": matrix[0]["zone"],
        "report_date": matrix[0]["report_date"],
        "sent_step": f"Delivered TA {editions[0].upper()} for ",
    }


def gh(args, payload=None):
    out = subprocess.run(["gh", "api", *args], input=None if payload is None else json.dumps(payload),
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out) if out.strip() else {}


class TA:
    """The few TA repository calls the chain needs; replaced by a fake in tests."""

    def __init__(self, call=gh):
        self.call = call

    def dispatch(self, workflow, inputs):
        result = self.call(["-X", "POST", f"repos/{REPO}/actions/workflows/{workflow}/dispatches", "--input", "-"],
                           {"ref": "main", "inputs": inputs, "return_run_details": True})
        return int(result["workflow_run_id"])

    def run(self, run_id):
        return self.call([f"repos/{REPO}/actions/runs/{run_id}"])

    def cancel(self, run_id):
        self.call(["-X", "POST", f"repos/{REPO}/actions/runs/{run_id}/cancel"])


class Chain:
    def __init__(self, ta, edition, report_date, zone, mode, to="", clock=now_utc, sleep=time.sleep, hold=None):
        self.ta, self.edition, self.day, self.zone, self.mode, self.to = ta, edition, report_date, zone, mode, to
        self.clock, self.sleep = clock, sleep
        self.hold = hold or (lambda: H.hold_until(report_date, zone, "05:55"))
        self.end = f"{report_date} 05:00"

    def local(self, hhmm):
        hour, minute = map(int, hhmm.split(":"))
        day = dt.date.fromisoformat(self.day)
        return dt.datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZoneInfo(self.zone))

    def deadline(self, phase, started):
        if self.mode == "scheduled":
            return self.local("05:50" if phase == "build" else "06:10")
        return started + (MANUAL_SEND if phase == "send" else MANUAL_BUILD)

    def inputs(self, phase, build_run=None):
        base = {"edition": self.edition, "end": self.end}
        if phase == "dry":
            return {**base, "dry": "true"}
        base["phase"] = phase
        if build_run is not None:
            base["build_run"] = str(build_run)
        if self.to:
            base["to"] = self.to
        return base

    def start(self, kind, phase, build_run=None):
        """Dispatch one child; None when the dispatch itself failed."""
        try:
            return self.ta.dispatch(KINDS[kind], self.inputs(phase, build_run))
        except Exception:
            print(f"{kind}: {phase} dispatch failed")
            return None

    def status(self, run_id):
        try:
            run = self.ta.run(run_id)
        except Exception:
            return None   # transient API error; poll again
        return (run.get("conclusion") or "unknown") if run.get("status") == "completed" else None

    def run_all(self, phase, build_runs=None):
        """Run one phase for every kind at once; each kind gets one re-dispatch and its own deadline.

        Returns {kind: (run_id or None, outcome)}. A kind past its deadline is cancelled
        without waiting for, or holding up, the other kind.
        """
        kinds = list(build_runs) if build_runs is not None else list(KINDS)
        extra = (lambda kind: build_runs[kind]) if build_runs is not None else (lambda kind: None)
        state = {}
        for kind in kinds:
            started = self.clock()
            state[kind] = {"run": self.start(kind, phase, extra(kind)), "attempt": 1,
                           "deadline": self.deadline(phase, started)}
        done = {}
        while True:
            for kind in [k for k in kinds if k not in done]:
                s = state[kind]
                outcome = self.status(s["run"]) if s["run"] is not None else "dispatch failed"
                if outcome == "success":
                    done[kind] = (s["run"], "success")
                    continue
                if outcome is None and self.clock() < s["deadline"]:
                    continue
                if outcome is None:
                    try:
                        self.ta.cancel(s["run"])
                    except Exception:
                        pass
                    print(f"{kind}: {phase} timeout")
                    done[kind] = (None, "timeout")
                    continue
                print(f"{kind}: {phase} attempt {s['attempt']} {outcome}")
                if s["attempt"] == 1 and self.clock() < s["deadline"]:
                    s["run"], s["attempt"] = self.start(kind, phase, extra(kind)), 2
                else:
                    done[kind] = (None, outcome)
            if len(done) == len(kinds):
                return done
            self.sleep(POLL_SECONDS)

    def deliver(self):
        if self.mode == "dry":
            return {kind: "dry run ok" if run else f"dry run {outcome}"
                    for kind, (run, outcome) in self.run_all("dry").items()}
        result = {}
        built = {}
        # A day TA already delivered builds nothing; its send run then finds the marker and skips.
        for kind, (run, outcome) in self.run_all("build").items():
            if run:
                built[kind] = run
            else:
                result[kind] = f"build {outcome}"
        if built:
            if self.mode == "scheduled":
                self.hold()
            for kind, (run, outcome) in self.run_all("send", built).items():
                result[kind] = "delivered" if run else f"send {outcome}"
        return {kind: result[kind] for kind in KINDS}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("settings", "deliver"))
    args = parser.parse_args(argv)
    env = os.environ
    try:
        if args.command == "settings":
            G.emit(**settings(env, now_utc()))
            return 0
        # A job-only re-run skips settings, so repeat its production re-run guard here.
        if env["MODE"] in ("scheduled", "recovery") and env.get("GITHUB_RUN_ATTEMPT", "1") != "1":
            raise TriggerError("production re-runs are not allowed; dispatch mode=recovery instead")
        chain = Chain(TA(), env["EDITION"], env["REPORT_DATE"], env["ZONE"], env["MODE"], env.get("TEST_TO", ""))
        result = chain.deliver()
    except TriggerError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    for kind, outcome in result.items():
        print(f"{kind}: {outcome}")
    good = {"delivered", "dry run ok"}
    return 0 if all(outcome in good for outcome in result.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
