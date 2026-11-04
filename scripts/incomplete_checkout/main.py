#!/usr/bin/env python3
"""Send personal outreach emails to customers who started checkout but
did not complete payment in the last 24 hours.

Unlike other digests this sends one email per customer, not one email to
a fixed recipient list. Resend idempotency keys prevent duplicate sends
on re-runs.
"""
import argparse
import hashlib
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[2]
import sys
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from scripts.common.delivery import load_config, mask
from scripts.incomplete_checkout.fetch import fetch_incomplete_customers
from scripts.incomplete_checkout.render import render

IST = ZoneInfo("Asia/Kolkata")
SEND_URL = "https://api.resend.com/emails"


def _send_one(*, resend_key, from_field, reply_to, to, subject, text,
              idempotency_key, dry_run=False):
    """Send a single plain-text email via Resend with idempotency."""
    if dry_run:
        return {"accepted": True, "dry_run": True}
    payload = {
        "from": from_field,
        "to": [to],
        "reply_to": reply_to,
        "subject": subject,
        "text": text,
    }
    resp = requests.post(
        SEND_URL,
        headers={
            "Authorization": f"Bearer {resend_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
        },
        data=json.dumps(payload),
        timeout=60,
    )
    if resp.status_code == 200:
        return {"accepted": True}
    return {"accepted": False, "status": resp.status_code}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-date", type=date.fromisoformat,
                        help="YYYY-MM-DD; defaults to today IST")
    parser.add_argument("--since", type=date.fromisoformat,
                        help="Override window start to midnight IST on this date (for backfills)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Render and log without sending")
    parser.add_argument("--to", default="",
                        help="Send a [TEST] email to this address only")
    args = parser.parse_args(argv)

    stripe_key = os.environ.get("STRIPE_API_KEY", "")
    if not stripe_key:
        raise ValueError("STRIPE_API_KEY not set")
    mask(stripe_key)

    resend_key = os.environ.get("RESEND_API_KEY", "")
    mail_from = os.environ.get("MAIL_FROM", "")
    if not args.dry_run and (not resend_key or not mail_from):
        raise ValueError("RESEND_API_KEY / MAIL_FROM not set")
    mask(resend_key)
    mask(mail_from)

    report_date = args.report_date or datetime.now(IST).date()
    cutoff = datetime.combine(report_date, datetime.min.time().replace(hour=10),
                              tzinfo=IST)
    if args.since:
        window_start_dt = datetime.combine(args.since, datetime.min.time(), tzinfo=IST)
    else:
        window_start_dt = cutoff - timedelta(hours=24)
    window_start = int(window_start_dt.timestamp())
    window_end = int(cutoff.timestamp())

    print(f"window: {window_start_dt} to {cutoff}")
    customers = fetch_incomplete_customers(stripe_key, window_start, window_end)

    if not customers:
        print("no incomplete customers found")
        return

    subject, body_text = render()
    from_field = "Angel Rose <connect@marineradar.com>"
    reply_to = "connect@marineradar.com"
    date_tag = report_date.isoformat()

    if args.to:
        subject = f"[TEST] {subject}"

    sent = 0
    failed = 0
    for cust in customers:
        recipient = args.to if args.to else cust["email"]
        idem_key = hashlib.sha256(
            f"incomplete_checkout/{recipient}/{date_tag}".encode()
        ).hexdigest()[:32]
        result = _send_one(
            resend_key=resend_key,
            from_field=from_field,
            reply_to=reply_to,
            to=recipient,
            subject=subject,
            text=body_text,
            idempotency_key=idem_key,
            dry_run=args.dry_run,
        )
        if result.get("accepted"):
            sent += 1
        else:
            failed += 1
        if args.to:
            print(f"test: sent to {args.to}")
            break

    subject_hash = hashlib.sha256(subject.encode()).hexdigest()[:8]
    print(f"done: sent={sent} failed={failed} subject_sha256={subject_hash}")

    if args.dry_run:
        out_dir = Path("out")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "incomplete_checkout-ist.txt").write_text(body_text, encoding="utf-8")
        (out_dir / "incomplete_checkout-ist.subject.txt").write_text(subject, encoding="utf-8")
        print(f"preview: text_bytes={len(body_text.encode('utf-8'))}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit(
            f"Incomplete checkout outreach failed ({type(exc).__name__})"
        ) from None
