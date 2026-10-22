"""Figure-free workflow settings and fail-closed SMTP delivery dedupe.

The two gate files can run from a SHA-pinned curl download with only the JSON
config beside them. The final dedupe command runs inside the send job's lock,
after the hold; SMTP has no provider idempotency key to fall back on.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

try:
    from . import catchup_gate as G
except ImportError:
    import catchup_gate as G


WORKFLOWS = {
    "daily-revenue.yml": (45, 11, ("revenue",)),
    "daily-reviews.yml": (47, 13, ("reviews",)),
    "daily-survey.yml": (49, 15, ("survey_marine", "survey_measure")),
    "daily-conversion.yml": (51, 17, ("conversion",)),
}


class SettingsError(ValueError):
    """A fixed, public-safe explanation for a rejected delivery."""


def load_config():
    root = Path(__file__).resolve().parents[2]
    path = root / "data/email_config.json"
    if not path.is_file():
        path = Path("email_config.json")
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def resolve_schedule(workflow, schedule):
    pt, ist, _ = WORKFLOWS[workflow]
    if schedule == f"{pt} 3,6,9 * * *":
        return "pt"
    if schedule == f"{ist} 13,16,19 * * *":
        return "ist"
    raise ValueError("unknown daily schedule")


def workflow_for(digest):
    for workflow, (_, _, digests) in WORKFLOWS.items():
        if digest in digests:
            return workflow
    raise ValueError("unknown digest")


def scheduled_run_created_at(env):
    """Read this run's creation time, never the repository's creation time."""
    try:
        timestamp = env.get("RUN_CREATED_AT") or env.get("GITHUB_RUN_CREATED_AT")
        run_id = env.get("GITHUB_RUN_ID", "")
        if not timestamp and env.get("GITHUB_EVENT_PATH"):
            with open(env["GITHUB_EVENT_PATH"], encoding="utf-8") as source:
                metadata = json.load(source).get("workflow_run") or {}
            if run_id and str(metadata.get("id")) == run_id:
                timestamp = metadata.get("created_at")
        if not timestamp:
            repo = env.get("GITHUB_REPOSITORY", "")
            if not repo or not run_id:
                raise ValueError
            metadata = G.gh_json(f"repos/{repo}/actions/runs/{run_id}")
            if str(metadata.get("id")) != run_id:
                raise ValueError
            timestamp = metadata["created_at"]
        created = dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if created.utcoffset() is None:
            raise ValueError
        return created.astimezone(dt.timezone.utc)
    except Exception:
        # GitHub errors and event payloads must never reach public logs.
        raise SettingsError("scheduled run creation time unavailable") from None


def settings(env=None, now=None):
    env = os.environ if env is None else env
    now = G.now_utc() if now is None else now
    config = load_config()
    event = env.get("EVENT", "workflow_dispatch")
    workflow = env.get("WORKFLOW", "")
    if event not in ("schedule", "workflow_dispatch") or workflow not in WORKFLOWS:
        raise ValueError("unsupported workflow or event")
    digest = env.get("DIGEST", "")
    if digest and (digest not in config["digests"] or workflow_for(digest) != workflow):
        raise ValueError("digest does not belong to workflow")
    edition = (resolve_schedule(workflow, env.get("SCHEDULE", ""))
               if event == "schedule" else env.get("INPUT_EDITION") or "both")
    if edition not in ("pt", "ist", "both") or (digest and edition == "both"):
        raise ValueError("invalid edition")
    editions = ["pt", "ist"] if edition == "both" else [edition]
    zone = config["editions"][editions[0]]["tz"]
    mode = ("dry" if env.get("DRY_RUN") == "true" else
            "test" if env.get("TEST_TO") or env.get("TEST_MODE") == "true" else "real")
    if mode == "real" and env.get("GITHUB_RUN_ATTEMPT") != "1":
        raise SettingsError("production delivery requires a fresh run; re-runs are not allowed, dispatch recovery instead")
    if mode == "real" and event == "workflow_dispatch":
        if env.get("RECOVERY") != "true":
            raise ValueError("manual production sends require recovery=true")
        # History trusts only main. A branch send would be invisible to future
        # dedupe scans even though it used the same event-independent lock.
        if env.get("GITHUB_REF") != "refs/heads/main":
            raise ValueError("production recovery must run from main")
    if event == "schedule" and now - scheduled_run_created_at(env) > dt.timedelta(hours=36):
        raise SettingsError("scheduled run is older than 36 hours; dispatch recovery instead")
    # Gate settings have no DIGEST and resolve every edition once. Reusable
    # send jobs must consume that frozen date, even when they start after 05:00.
    if digest and mode in ("real", "test") and not env.get("REPORT_DATE"):
        raise SettingsError("REPORT_DATE is required for production and test delivery")
    supplied = env.get("REPORT_DATE") or (env.get("INPUT_DATE", "") if event != "schedule" else "")
    supplied_date = None
    if supplied:
        supplied_date = dt.date.fromisoformat(supplied)
        if supplied_date.isoformat() != supplied:
            raise ValueError("report date must be YYYY-MM-DD")
    matrix = []
    for local_edition in editions:
        local_zone = config["editions"][local_edition]["tz"]
        local = now.astimezone(ZoneInfo(local_zone))
        latest_report_date = local.date() - dt.timedelta(days=local.time() < dt.time(5))
        if supplied_date:
            report_date = supplied_date
        elif event == "schedule":
            report_date = G.plan(now, tz=local_zone, target=(5, 5))[0]
        else:
            report_date = latest_report_date
        # A future report day can put an earlier recovery outside the history
        # scan's date window. Only completed cutoffs are safe for recovery.
        if mode == "real" and event == "workflow_dispatch" and report_date > latest_report_date:
            raise SettingsError("production recovery cannot target a future report day")
        matrix.append({"edition": local_edition, "report_date": report_date.isoformat()})
    date = matrix[0]["report_date"] if len(matrix) == 1 else supplied
    prefix = {"dry": "Dry run", "test": "Test send", "real": "Deliver"}[mode]
    return {
        "edition": edition,
        "editions": json.dumps(matrix, separators=(",", ":")),
        "timezone": zone,
        "report_date": date,
        "sent_step": f"Delivered {edition.upper()} for ",
        "send_step": f"{prefix} {digest} {edition.upper()} for {date}" if digest else "",
        "mode": mode,
    }


def digest_args(digest, resolved):
    entry = load_config()["digests"][digest]
    if resolved["edition"] not in ("pt", "ist") or not resolved["report_date"]:
        raise ValueError("build requires one edition and report date")
    return ["-m", entry["module"], *entry["extra_args"],
            "--edition", resolved["edition"], "--report-date", resolved["report_date"], "--dry-run"]


def dedupe(resolved, digest):
    if resolved["mode"] != "real":
        return False
    if resolved["edition"] not in ("pt", "ist"):
        raise ValueError("dedupe requires one edition")
    return G.already_sent(
        dt.date.fromisoformat(resolved["report_date"]), G.now_utc(),
        workflow=workflow_for(digest),
        sent_step=f"Deliver {digest} {resolved['edition'].upper()} for ",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("settings", "dedupe", "digest-args"))
    args = parser.parse_args(argv)
    try:
        resolved = settings()
        if args.command == "settings":
            G.emit(**resolved)
        elif args.command == "dedupe":
            G.emit(sent=str(dedupe(resolved, os.environ["DIGEST"])))
        else:
            G.emit(argv=json.dumps(digest_args(os.environ["DIGEST"], resolved)))
        return 0
    except G.DedupeUnavailable:
        print("delivery history unavailable; refusing to send", file=sys.stderr)
        return 3
    except SettingsError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (ValueError, KeyError, OSError):
        print("invalid digest workflow settings; production recovery requires recovery=true on main; "
              "branch runs require dry_run=true or to", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
