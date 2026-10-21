#!/usr/bin/env python3
"""Orchestrator for the daily conversion digest. Fetch, model, render, send.

  python3 conversion_main.py --report-date 2026-10-20 --apps conversion_apps.json \
      --recipients angel@…,cherian@… [--dry-run] [--to angel@…]

Fetches Install → Paid cohort conversion rates from the Adapty Analytics
Export API for each configured app. The conversion rate for an install-date
cohort grows over time as more users from that date make their first
subscription purchase.

Public repo — never log API keys or response bodies, only counts and statuses.
"""
import argparse
import json
import os
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from conversion_fetch import fetch_install_to_paid
from conversion_model import build_model
from conversion_render import render

LOOKBACK_DAYS = 14


def _mask(value):
    for line in str(value).splitlines():
        if line.strip():
            print(f"::add-mask::{line}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report-date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--apps", required=True, help="Path to conversion_apps.json")
    ap.add_argument("--recipients", default="", help="Comma-separated production recipients")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--to", default="", help="Test mode: send [TEST] email to this address only")
    ap.add_argument("--tz", default="UTC", help="Display timezone (e.g. Asia/Kolkata, America/Los_Angeles)")
    ap.add_argument("--sender", default="Lascade", help="Sender display name")
    ap.add_argument("--lookback", type=int, default=LOOKBACK_DAYS,
                    help=f"Number of days of cohort data to fetch (default {LOOKBACK_DAYS})")
    a = ap.parse_args()

    display_tz = ZoneInfo(a.tz)

    gmail_user = os.environ.get("GMAIL_USER", "")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD", "")
    if gmail_password:
        _mask(gmail_password)

    with open(a.apps) as f:
        apps_config = json.load(f)

    report_date = datetime.strptime(a.report_date, "%Y-%m-%d").date()
    now_utc = datetime.now(timezone.utc)
    date_to = report_date.isoformat()
    date_from = (report_date - timedelta(days=a.lookback - 1)).isoformat()

    print(f"cohort window: {date_from} to {date_to}")

    app_data = {}
    for app in apps_config:
        name = app["name"]
        api_key = os.environ.get(app["api_key_env"], "")
        if not api_key:
            print(f"  {name}: skipped (no API key in {app['api_key_env']})")
            continue
        _mask(api_key)
        print(f"fetching {name}...")
        data = fetch_install_to_paid(api_key, date_from, date_to)
        print(f"  {name}: overall {data['overall_rate']:.1f}%, {len(data['cohorts'])} cohort days")
        app_data[name] = data

    model = build_model(apps_config, app_data, now_utc, display_tz=display_tz)
    subject, html = render(model)

    if a.dry_run:
        print(f"subject: {subject}")
        print(f"html length: {len(html)}")
        with open("conversion-email.html", "w") as f:
            f.write(html)
        print("wrote conversion-email.html")
        return

    if not gmail_user or not gmail_password:
        sys.exit("GMAIL_USER / GMAIL_APP_PASSWORD not set")

    if a.to:
        recipients = [a.to]
        prefix = "[TEST] "
    elif a.recipients:
        recipients = [r.strip() for r in a.recipients.split(",") if r.strip()]
        prefix = ""
    else:
        sys.exit("Either --to or --recipients must be provided")

    msg = MIMEMultipart("alternative")
    msg["From"] = f"{a.sender} <{gmail_user}>"
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = f"{prefix}{subject}"
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, recipients, msg.as_string())
    print(f"sent to {', '.join(recipients)}")


if __name__ == "__main__":
    main()
