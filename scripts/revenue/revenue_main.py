#!/usr/bin/env python3
"""Build or send the revenue digest for an edition-local report date."""
import argparse
from datetime import date, datetime, timezone
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.common.dates import report_date_for, subject, window_for
from scripts.common.smtp_send import load_config, mask, send_digest, write_preview
from scripts.revenue.revenue_fetch import fetch_charges, fetch_refunds
from scripts.revenue.revenue_model import build_model
from scripts.revenue.revenue_render import render


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edition", choices=("pt", "ist"), default="pt")
    parser.add_argument("--report-date", type=date.fromisoformat)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--to", default="", help="Send a [TEST] email to this address only")
    args = parser.parse_args(argv)
    config = load_config()
    tz = ZoneInfo(config["editions"][args.edition]["tz"])
    report_date = args.report_date or report_date_for(datetime.now(timezone.utc), tz)
    start, end = window_for(report_date, tz)
    month_start = end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    since, until = int(start.timestamp()), int(end.timestamp())
    month_since = int(month_start.timestamp())

    stripe_key = os.environ.get("STRIPE_API_KEY", "")
    if not stripe_key:
        raise ValueError("STRIPE_API_KEY not set")
    mask(stripe_key)
    today_charges = fetch_charges(stripe_key, since, until)
    today_refunds = fetch_refunds(stripe_key, since, until)
    month_charges = fetch_charges(stripe_key, month_since, until)
    month_refunds = fetch_refunds(stripe_key, month_since, until)
    print(f"records: daily_charges={len(today_charges)} daily_refunds={len(today_refunds)} "
          f"month_charges={len(month_charges)} month_refunds={len(month_refunds)}")
    model = build_model(today_charges, today_refunds, month_charges, month_refunds,
                        end, start, display_tz=tz)
    tail, html = render(model)
    title = subject(config["digests"]["revenue"]["name"], report_date, tail)
    if args.dry_run:
        write_preview("revenue", args.edition, title, html)
    else:
        send_digest("revenue", args.edition, title, html, test_to=args.to, config=config)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit(f"Revenue digest failed ({type(exc).__name__})") from None
