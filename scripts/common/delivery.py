#!/usr/bin/env python3
"""Shared Resend delivery with frozen-envelope idempotency and local preview
files, with safe public-run logging.

The workflow builds previews before its hold, then invokes this CLI on those
same files after the delivery check. No rendered content is printed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time

import requests

CONFIG_PATH = Path(__file__).resolve().parents[2] / "data" / "email_config.json"
SEND_URL = "https://api.resend.com/emails"


class DeliveryError(Exception):
    """A fixed, public-safe explanation for a rejected delivery."""


def _valid_key(value):
    return isinstance(value, str) and len(value) > 0 and not re.search(r"[\r\n\x00]", value)


def mask(value):
    """Mask secrets in Actions without exposing them in local stdout."""
    if os.environ.get("GITHUB_ACTIONS", "").lower() != "true":
        return
    for line in str(value).splitlines():
        if line.strip():
            print(f"::add-mask::{line.replace('%', '%25').replace(chr(13), '%0D')}")


def load_config(path=None):
    with open(path or CONFIG_PATH, encoding="utf-8") as source:
        return json.load(source)


def write_preview(digest, edition, subject, html, out_dir="out"):
    """Write only the HTML and subject needed for an encrypted preview."""
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{digest}-{edition}"
    html_path = directory / f"{stem}.html"
    subject_path = directory / f"{stem}.subject.txt"
    html_path.write_text(html, encoding="utf-8")
    subject_path.write_text(subject, encoding="utf-8")
    subject_hash = hashlib.sha256(subject.encode("utf-8")).hexdigest()[:8]
    print(f"preview: html_bytes={len(html.encode('utf-8'))} subject_sha256={subject_hash}")
    return html_path, subject_path


def idempotency_key(digest, edition, report_date="", test_to="", run_id=""):
    if not _valid_key(digest) or not _valid_key(edition):
        raise DeliveryError("Invalid idempotency key settings")
    suffix = f"{digest}/{edition}"
    if not test_to:
        if not _valid_key(report_date):
            raise DeliveryError("Invalid idempotency key settings")
        return f"{suffix}/{report_date}"
    test_run_id = run_id or str(int(time.time()))
    if not _valid_key(test_run_id):
        raise DeliveryError("Test delivery requires a run id")
    return f"{suffix}/test/{test_run_id}"


def freeze_envelope(path, key, payload):
    """Create once with private permissions. An existing envelope is never replaced."""
    if not _valid_key(key):
        raise DeliveryError("Invalid idempotency key settings")
    if not isinstance(payload, dict) or "scheduled_at" in payload:
        raise DeliveryError("Invalid email payload")
    try:
        body = json.dumps(payload)
        parsed = json.loads(body)
        if not isinstance(parsed, dict) or "scheduled_at" in parsed:
            raise DeliveryError("Invalid email payload")
    except (TypeError, ValueError):
        raise DeliveryError("Invalid email payload")
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, json.dumps({"key": key, "body": body}).encode("utf-8"))
        finally:
            os.close(fd)
    except FileExistsError:
        raise DeliveryError("Frozen envelope already exists")
    except OSError:
        raise DeliveryError("Unable to write frozen envelope")
    return str(path)


def _read_envelope(path):
    try:
        with open(path, encoding="utf-8") as f:
            envelope = json.load(f)
        if not _valid_key(envelope.get("key", "")) or not isinstance(envelope.get("body"), str):
            raise DeliveryError("Invalid frozen envelope")
        parsed = json.loads(envelope["body"])
        if not isinstance(parsed, dict) or "scheduled_at" in parsed:
            raise DeliveryError("Invalid frozen envelope")
        return envelope
    except DeliveryError:
        raise
    except Exception:
        raise DeliveryError("Invalid frozen envelope")


def send_frozen(path, api_key, max_attempts=4, session=None, sleep_fn=None):
    """Read once, then submit the same payload bytes and key at most max_attempts
    times. A 200 is acceptance; changed payload conflicts fail closed."""
    if not isinstance(api_key, str) or not api_key.strip():
        raise DeliveryError("Resend API key is missing")
    if not isinstance(max_attempts, int) or max_attempts < 1 or max_attempts > 10:
        raise DeliveryError("Invalid delivery attempt limit")
    if sleep_fn is None:
        sleep_fn = time.sleep
    envelope = _read_envelope(path)
    key = envelope["key"]
    body = envelope["body"]
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Idempotency-Key": key,
    }
    http = session or requests

    for attempt in range(1, max_attempts + 1):
        status = 0
        response = None
        try:
            response = http.post(SEND_URL, headers=headers, data=body, timeout=60)
            code = response.status_code
            if isinstance(code, int) and 100 <= code <= 599:
                status = code
        except Exception:
            pass

        if status == 200:
            return {"accepted": True, "status": 200, "attempts": attempt}

        category = "transport" if status == 0 else "HTTP error"
        retryable = status == 0 or status == 429 or 500 <= status <= 599

        if status == 409:
            name = None
            try:
                name = response.json().get("name")
            except Exception:
                pass
            if name == "concurrent_idempotent_requests":
                category = "concurrent_idempotent_requests"
                retryable = True
            elif name == "invalid_idempotent_request":
                category = "invalid_idempotent_request"
                retryable = False
            else:
                category = "idempotency conflict"
                retryable = False

        if not retryable or attempt == max_attempts:
            hint = ""
            if response is not None and status in (400, 401, 403, 404, 422):
                try:
                    hint = f" — {response.json().get('message', '')}"
                except Exception:
                    pass
            raise DeliveryError(f"Resend delivery failed: HTTP {status} ({category}){hint}")

        sleep_fn(min(1 * 2 ** (attempt - 1), 15))


def send_digest(digest, edition, subject, html, test_to="", config=None, report_date=""):
    """Send a production or test digest via Resend; failures never disclose
    upstream text."""
    config = config if config is not None else load_config()
    digest_config = config["digests"][digest]
    recipients = ([addr.strip() for addr in test_to.split(",") if addr.strip()]
                  if test_to else digest_config["recipients"][edition])
    if not recipients:
        raise DeliveryError("No recipients configured")
    api_key = os.environ.get("RESEND_API_KEY", "")
    mail_from = os.environ.get("MAIL_FROM", "")
    if not api_key or not mail_from:
        raise DeliveryError("RESEND_API_KEY / MAIL_FROM not set")
    mask(api_key)
    mask(mail_from)
    subject = ("[TEST] " if test_to else "") + subject
    sender_name = digest_config.get("sender", "")
    from_field = f"{sender_name} <{mail_from}>" if sender_name else mail_from

    key = idempotency_key(digest, edition, report_date=report_date,
                          test_to=test_to,
                          run_id=os.environ.get("GITHUB_RUN_ID", ""))
    payload = {"from": from_field, "to": recipients, "subject": subject, "html": html}
    out_dir = Path("out")
    out_dir.mkdir(parents=True, exist_ok=True)
    frozen_path = out_dir / f"frozen-{digest}-{edition}.json"
    freeze_envelope(str(frozen_path), key, payload)
    send_frozen(str(frozen_path), api_key)
    subject_hash = hashlib.sha256(subject.encode("utf-8")).hexdigest()[:8]
    print(f"sent: recipients={len(recipients)} subject_sha256={subject_hash}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--digest", required=True)
    parser.add_argument("--edition", choices=("pt", "ist"), required=True)
    parser.add_argument("--subject-file", required=True)
    parser.add_argument("--html-file", required=True)
    parser.add_argument("--report-date", default="")
    parser.add_argument("--to", default="", help="Send a [TEST] message to these recipients")
    args = parser.parse_args(argv)
    subject = Path(args.subject_file).read_text(encoding="utf-8")
    html = Path(args.html_file).read_text(encoding="utf-8")
    send_digest(args.digest, args.edition, subject, html,
                test_to=args.to, report_date=args.report_date)


if __name__ == "__main__":
    try:
        main()
    except DeliveryError as exc:
        raise SystemExit(str(exc)) from None
    except Exception as exc:
        raise SystemExit(f"Delivery failed ({type(exc).__name__})") from None
