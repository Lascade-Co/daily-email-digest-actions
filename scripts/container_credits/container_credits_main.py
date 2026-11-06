#!/usr/bin/env python3
"""Build or send the container tracking credit purchase digest for an edition-local report date."""
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
from scripts.common.delivery import load_config, mask, send_digest, write_preview
from scripts.container_credits.container_credits_fetch import fetch_credit_revenue
from scripts.container_credits.container_credits_model import build_model
from scripts.container_credits.container_credits_render import render


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edition", choices=("pt", "ist"), default="pt")
    parser.add_argument("--report-date", type=date.fromisoformat)
    parser.add_argument("--products", default=str(ROOT / "data" / "container_credits.json"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--to", default="", help="Send a [TEST] email to this address only")
    args = parser.parse_args(argv)
    config = load_config()
    tz = ZoneInfo(config["editions"][args.edition]["tz"])
    report_date = args.report_date or report_date_for(datetime.now(timezone.utc), tz)
    start, end = window_for(report_date, tz)

    with open(args.products, encoding="utf-8") as source:
        products_config = json.load(source)
    product_ids = [p["id"] for p in products_config]

    api_key = os.environ.get("ADAPTY_KEY_MARINERADAR", "")
    if not api_key:
        raise ValueError("ADAPTY_KEY_MARINERADAR not set")
    mask(api_key)

    today_date = (report_date - timedelta(days=1)).isoformat()
    month_first = end.astimezone(tz).replace(day=1).strftime("%Y-%m-%d")

    today_data = fetch_credit_revenue(api_key, today_date, today_date, product_ids, tz=str(tz))
    month_data = fetch_credit_revenue(api_key, month_first, today_date, product_ids, tz=str(tz))
    print(f"records: today_count={today_data['total_count']} month_count={month_data['total_count']}")

    model = build_model(products_config, today_data, month_data, end, start, display_tz=tz)
    tail, html = render(model)
    title = subject(config["digests"]["container_credits"]["name"], report_date, tail)
    if args.dry_run:
        write_preview("container_credits", args.edition, title, html)
    else:
        send_digest("container_credits", args.edition, title, html, test_to=args.to, config=config)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit(f"Container credits digest failed ({type(exc).__name__})") from None
