#!/usr/bin/env python3
"""Build or send either survey digest for an edition-local report date."""
import argparse
import base64
from datetime import date, datetime, timezone
from functools import partial
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
from scripts.survey.survey_fetch import fetch_sheet_tab, translate_text, FetchError
from scripts.survey.survey_model import build_model
from scripts.survey.survey_render import render
from scripts.survey.posthog_fetch import fetch_responses, transform_to_tabs
from scripts.survey.posthog_fetch import FetchError as PostHogFetchError


def _fetch_sheets(config, start, end, tz):
    """Fetch survey data from Google Sheets."""
    google_sa = os.environ.get("GOOGLE_SA_KEY", "")
    gemini_key = os.environ.get("GOOGLE_API_KEY", "")
    if not google_sa:
        raise ValueError("GOOGLE_SA_KEY not set")
    mask(google_sa)
    if gemini_key:
        mask(gemini_key)
    try:
        sa_info = json.loads(base64.b64decode(google_sa))
    except Exception:
        raise ValueError("Invalid GOOGLE_SA_KEY") from None
    fetched_tabs = {}
    failures = 0
    for survey in config["surveys"]:
        tab = survey["sheet_name"]
        try:
            fetched_tabs[tab] = fetch_sheet_tab(sa_info, config["sheet_id"], tab)
        except FetchError:
            failures += 1
    print(f"records: rows={sum(len(rows) for rows in fetched_tabs.values())} failed_tabs={failures}")
    translate_fn = partial(translate_text, sa_info)
    return fetched_tabs, translate_fn, gemini_key or None


def _fetch_posthog(config, start, end):
    """Fetch survey data from PostHog API."""
    api_key_env = config["posthog_api_key_env"]
    api_key = os.environ.get(api_key_env, "")
    gemini_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        raise ValueError(f"{api_key_env} not set")
    mask(api_key)
    if gemini_key:
        mask(gemini_key)
    responses = fetch_responses(
        api_key, config["posthog_project_id"], config["posthog_survey_id"], start, end)
    print(f"records: posthog_responses={len(responses)}")
    fetched_tabs = transform_to_tabs(responses, config)
    print(f"records: rows={sum(len(rows) for rows in fetched_tabs.values())}")
    return fetched_tabs, None, gemini_key or None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--digest", choices=("survey_marine", "survey_measure", "survey_geo"), required=True)
    parser.add_argument("--edition", choices=("pt", "ist"), default="pt")
    parser.add_argument("--report-date", type=date.fromisoformat)
    parser.add_argument("--config", help="Product survey config JSON")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--to", default="", help="Send a [TEST] email to this address only")
    args = parser.parse_args(argv)
    email_config = load_config()
    tz = ZoneInfo(email_config["editions"][args.edition]["tz"])
    report_date = args.report_date or report_date_for(datetime.now(timezone.utc), tz)
    start, end = window_for(report_date, tz)
    config_path = args.config or ROOT / "data" / f"{args.digest}.json"
    with open(config_path, encoding="utf-8") as source:
        config = json.load(source)
    if config.get("source") == "posthog":
        fetched_tabs, translate_fn, gemini_key = _fetch_posthog(config, start, end)
    else:
        fetched_tabs, translate_fn, gemini_key = _fetch_sheets(config, start, end, tz)
    model = build_model(config, fetched_tabs, start, end, translate_fn,
                        display_tz=tz, gemini_key=gemini_key)
    print(f"records: responses={model['total']}")
    tail, html = render(model)
    title = subject(email_config["digests"][args.digest]["name"], report_date, tail)
    if args.dry_run:
        write_preview(args.digest, args.edition, title, html)
    else:
        send_digest(args.digest, args.edition, title, html, test_to=args.to, config=email_config)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit(f"Survey digest failed ({type(exc).__name__})") from None
