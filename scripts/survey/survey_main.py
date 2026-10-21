#!/usr/bin/env python3
"""Orchestrator for the daily survey digest. Fetch, model, render, send.

  python3 survey_main.py --report-date 2026-10-20 --config survey_marine.json \
      --recipients angel@…,cherian@… [--dry-run] [--to angel@…]

Each product gets its own config file and its own email.
Public repo — never log response text, only counts and statuses.
"""
import argparse
import base64
import json
import os
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import partial

from survey_fetch import fetch_sheet_tab, translate_text, FetchError
from survey_model import build_model
from survey_render import render


def _mask(value):
    for line in str(value).splitlines():
        if line.strip():
            print(f"::add-mask::{line}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report-date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--config", required=True, help="Path to product survey config JSON")
    ap.add_argument("--recipients", default="", help="Comma-separated production recipients")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--to", default="", help="Test mode: send [TEST] email to this address only")
    ap.add_argument("--tz", default="UTC", help="Display timezone (e.g. Asia/Kolkata, America/Los_Angeles)")
    a = ap.parse_args()

    display_tz = ZoneInfo(a.tz)

    google_sa_b64 = os.environ.get("GOOGLE_SA_KEY", "")
    gmail_user = os.environ.get("GMAIL_USER", "")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD", "")
    gemini_key = os.environ.get("GOOGLE_API_KEY", "")

    if google_sa_b64:
        _mask(google_sa_b64)
    if gmail_password:
        _mask(gmail_password)
    if gemini_key:
        _mask(gemini_key)

    if not google_sa_b64:
        sys.exit("GOOGLE_SA_KEY not set")

    try:
        sa_info = json.loads(base64.b64decode(google_sa_b64))
    except Exception as e:
        sys.exit(f"failed to decode GOOGLE_SA_KEY: {e}")

    with open(a.config) as f:
        config = json.load(f)

    product_name = config.get("product_name", "Survey")
    print(f"product: {product_name}")

    now_utc = datetime.now(timezone.utc)
    cutoff_dt = now_utc - timedelta(hours=24)

    sheet_id = config["sheet_id"]
    fetched_tabs = {}
    for survey in config["surveys"]:
        tab = survey["sheet_name"]
        print(f"fetching tab: {tab}")
        try:
            rows = fetch_sheet_tab(sa_info, sheet_id, tab)
            fetched_tabs[tab] = rows
            print(f"  rows: {len(rows)}")
        except FetchError as e:
            print(f"  failed: {e}")

    translate_fn = partial(translate_text, sa_info)
    model = build_model(config, fetched_tabs, cutoff_dt, now_utc, translate_fn, display_tz=display_tz,
                         gemini_key=gemini_key or None)
    subject, html = render(model)

    print(f"total new responses: {model['total']}")
    for sec in model["sections"]:
        print(f"  {sec['label']}: {sec['count']}")

    if a.dry_run:
        print(f"subject: {subject}")
        print(f"html length: {len(html)}")
        slug = product_name.lower().replace(" ", "-")
        fname = f"survey-{slug}-email.html"
        with open(fname, "w") as f:
            f.write(html)
        print(f"wrote {fname}")
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
    msg["From"] = f"{product_name} <{gmail_user}>"
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = f"{prefix}{subject}"
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, recipients, msg.as_string())
    print(f"sent ({product_name}) to {', '.join(recipients)}")


if __name__ == "__main__":
    main()
