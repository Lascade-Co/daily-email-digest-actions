#!/usr/bin/env python3
"""Shared SMTP delivery and local preview files, with safe public-run logging.

The workflow builds previews before its hold, then invokes this CLI on those
same files after the delivery check. No rendered content is printed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

CONFIG_PATH = Path(__file__).resolve().parents[2] / "data" / "email_config.json"


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


def send_digest(digest, edition, subject, html, test_to="", config=None):
    """Send a production or test digest; failures never disclose server text."""
    config = config if config is not None else load_config()
    digest_config = config["digests"][digest]
    recipients = ([address.strip() for address in test_to.split(",") if address.strip()]
                  if test_to else digest_config["recipients"][edition])
    if not recipients:
        raise ValueError("No recipients configured")
    user = os.environ.get("GMAIL_USER", "")
    password = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not user or not password:
        raise ValueError("GMAIL_USER / GMAIL_APP_PASSWORD not set")
    mask(user)
    mask(password)
    subject = ("[TEST] " if test_to else "") + subject
    message = MIMEMultipart("alternative")
    message["From"] = formataddr((digest_config["sender"], user))
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.attach(MIMEText(html, "html", "utf-8"))
    accepted = False
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=60) as server:
            server.starttls(context=ssl.create_default_context())
            server.login(user, password)
            refused = server.sendmail(user, recipients, message.as_string())
            accepted = True
    except Exception as exc:
        # A failed QUIT cannot undo sendmail's acceptance. Keep that delivery
        # successful so a backup run cannot resend an accepted message.
        if not accepted:
            raise RuntimeError(f"SMTP delivery failed ({type(exc).__name__})") from None
    if refused:
        # SMTP already accepted the message for everyone else. Reporting failure
        # here would cause a backup run to resend to those accepted recipients.
        print(f"sent: recipients={len(recipients) - len(refused)} refused={len(refused)}")
        return
    subject_hash = hashlib.sha256(subject.encode("utf-8")).hexdigest()[:8]
    print(f"sent: recipients={len(recipients)} subject_sha256={subject_hash}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--digest", required=True)
    parser.add_argument("--edition", choices=("pt", "ist"), required=True)
    parser.add_argument("--subject-file", required=True)
    parser.add_argument("--html-file", required=True)
    parser.add_argument("--to", default="", help="Send a [TEST] message to these recipients")
    args = parser.parse_args(argv)
    subject = Path(args.subject_file).read_text(encoding="utf-8")
    html = Path(args.html_file).read_text(encoding="utf-8")
    send_digest(args.digest, args.edition, subject, html, test_to=args.to)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit(f"SMTP send failed ({type(exc).__name__})") from None
