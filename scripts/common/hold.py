#!/usr/bin/env python3
"""Hold a built digest until its edition-local delivery time.

Lateness never fails delivery: if a queued gate or slow build finishes after
05:55, send immediately with the original report date. The locked dedupe step
must run after this hold and immediately before the SMTP delivery.

NOW may contain an ISO timestamp to override the UTC clock for tests.
"""
from __future__ import annotations

import argparse
import os
import time
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo


def now_utc() -> datetime:
    value = os.environ.get("NOW")
    if not value:
        return datetime.now(timezone.utc)
    now = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def target_for(report_date: date | str, tz: str | ZoneInfo, target: str = "05:55") -> datetime:
    day = date.fromisoformat(report_date) if isinstance(report_date, str) else report_date
    zone = ZoneInfo(tz) if isinstance(tz, str) else tz
    if (len(target) != 5 or target[2] != ":" or not target[:2].isascii()
            or not target[3:].isascii() or not target[:2].isdigit() or not target[3:].isdigit()):
        raise ValueError("target must be HH:MM in 24-hour time")
    hour, minute = map(int, target.split(":"))
    if hour > 23 or minute > 59:
        raise ValueError("target must be HH:MM in 24-hour time")
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone)


def hold_until(report_date: date | str, tz: str | ZoneInfo, target: str = "05:55") -> None:
    release = target_for(report_date, tz, target).astimezone(timezone.utc)
    wait = max(0.0, (release - now_utc()).total_seconds())
    print(f"hold_seconds={wait:.0f}")
    if wait:
        time.sleep(wait)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-date", required=True, type=date.fromisoformat)
    parser.add_argument("--tz", required=True)
    parser.add_argument("--target", default="05:55")
    args = parser.parse_args(argv)
    hold_until(args.report_date, args.tz, args.target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
