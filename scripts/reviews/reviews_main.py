#!/usr/bin/env python3
"""Build or send app reviews for an edition-local report date."""
import argparse
import base64
from datetime import date, datetime, timezone
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
from scripts.reviews.reviews_fetch import fetch_appstore_reviews, fetch_playstore_reviews
from scripts.reviews.reviews_model import build_model
from scripts.reviews.reviews_render import render


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edition", choices=("pt", "ist"), default="pt")
    parser.add_argument("--report-date", type=date.fromisoformat)
    parser.add_argument("--apps", default=str(ROOT / "data" / "reviews_apps.json"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--to", default="", help="Send a [TEST] email to this address only")
    args = parser.parse_args(argv)
    config = load_config()
    tz = ZoneInfo(config["editions"][args.edition]["tz"])
    report_date = args.report_date or report_date_for(datetime.now(timezone.utc), tz)
    start, end = window_for(report_date, tz)

    key_id = os.environ.get("ASC_KEY_ID", "")
    issuer_id = os.environ.get("ASC_ISSUER_ID", "")
    private_key = os.environ.get("ASC_PRIVATE_KEY", "")
    google_sa = os.environ.get("GOOGLE_SA_KEY", "")
    gemini_key = os.environ.get("GOOGLE_API_KEY", "")
    for secret in (key_id, issuer_id, private_key, google_sa, gemini_key):
        if secret:
            mask(secret)
    sa_info = None
    if google_sa:
        try:
            sa_info = json.loads(base64.b64decode(google_sa))
        except Exception:
            raise ValueError("Invalid GOOGLE_SA_KEY") from None
    with open(args.apps, encoding="utf-8") as source:
        apps = json.load(source)
    app_reviews = {}
    for app in apps:
        appstore, playstore = [], []
        status = {"appstore": "failed", "playstore": "n/a"}   # missing credentials = failed
        if key_id and issuer_id and private_key:
            appstore, status["appstore"] = fetch_appstore_reviews(
                app["apple_id"], start, key_id, issuer_id, private_key, until_dt=end)
        if app.get("play_package"):
            status["playstore"] = "failed"
            if sa_info:
                playstore, status["playstore"] = fetch_playstore_reviews(
                    app["play_package"], start, sa_info, until_dt=end)
        app_reviews[app["name"]] = {"appstore": appstore, "playstore": playstore, "status": status}
        print(f"reviews app={app['name']} appstore={len(appstore)}:{status['appstore']} "
              f"playstore={len(playstore)}:{status['playstore']}")
    model = build_model(apps, app_reviews, start, end, display_tz=tz, gemini_key=gemini_key or None)
    print(f"records: reviews={model['grand_total']} fetched={model['total_fetched']}")
    tail, html = render(model)
    title = subject(config["digests"]["reviews"]["name"], report_date, tail)
    if args.dry_run:
        write_preview("reviews", args.edition, title, html)
    else:
        send_digest("reviews", args.edition, title, html, test_to=args.to, config=config)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit(f"Reviews digest failed ({type(exc).__name__})") from None
