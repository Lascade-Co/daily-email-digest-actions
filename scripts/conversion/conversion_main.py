#!/usr/bin/env python3
"""Build or send install-to-paid cohorts through the day before the report."""
import argparse
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.common.dates import report_date_for, subject, window_for
from scripts.common.smtp_send import load_config, mask, send_digest, write_preview
from scripts.conversion.conversion_fetch import fetch_install_to_paid
from scripts.conversion.conversion_model import build_model
from scripts.conversion.conversion_render import render

LOOKBACK_DAYS = 14


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edition", choices=("pt", "ist"), default="pt")
    parser.add_argument("--report-date", type=date.fromisoformat)
    parser.add_argument("--apps", default=str(ROOT / "data" / "conversion_apps.json"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--to", default="", help="Send a [TEST] email to this address only")
    parser.add_argument("--lookback", type=int, default=LOOKBACK_DAYS)
    args = parser.parse_args(argv)
    if args.lookback < 1:
        parser.error("--lookback must be positive")
    config = load_config()
    tz = ZoneInfo(config["editions"][args.edition]["tz"])
    report_date = args.report_date or report_date_for(datetime.now(timezone.utc), tz)
    _, end = window_for(report_date, tz)
    date_to = (report_date - timedelta(days=1)).isoformat()
    date_from = (report_date - timedelta(days=args.lookback)).isoformat()
    with open(args.apps, encoding="utf-8") as source:
        apps = json.load(source)
    app_data = {}
    for app in apps:
        api_key = os.environ.get(app["api_key_env"], "")
        if not api_key:
            continue
        mask(api_key)
        app_data[app["name"]] = fetch_install_to_paid(api_key, date_from, date_to, tz=str(tz))
    print(f"records: apps={len(app_data)} cohorts={sum(len(data['cohorts']) for data in app_data.values())}")
    model = build_model(apps, app_data, end, display_tz=tz)
    tail, html = render(model)
    title = subject(config["digests"]["conversion"]["name"], report_date, tail)
    if args.dry_run:
        write_preview("conversion", args.edition, title, html)
    else:
        send_digest("conversion", args.edition, title, html, test_to=args.to, config=config)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit(f"Conversion digest failed ({type(exc).__name__})") from None
