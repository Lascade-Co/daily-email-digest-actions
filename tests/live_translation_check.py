#!/usr/bin/env python3
"""Check real translation services without loading settings or sending email.

Requires only GOOGLE_API_KEY and base64-encoded GOOGLE_SA_KEY. Output is fixed
case labels and PASS/FAIL. Inputs and service responses are never printed.
"""
import base64
from contextlib import contextmanager, nullcontext, redirect_stderr, redirect_stdout
from datetime import timedelta
from functools import partial
import io
import json
import logging
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.reviews import reviews_model
from scripts.survey.survey_fetch import translate_text
from scripts.survey.survey_model import detect_and_translate
from translation_cases import CHINESE_CASE, LIVE_CASES, MOMENT, review_inputs


@contextmanager
def _quiet_services():
    """Even an unexpected library error must not expose request or response data."""
    disabled = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            yield
    finally:
        logging.disable(disabled)


def _translated(source, result):
    # These fixed inputs have English equivalents without non-Latin letters.
    return (isinstance(result, str) and bool(result.strip())
            and source.strip().casefold() not in result.strip().casefold()
            and all(not char.isalpha() or char.isascii() for char in result))


def review_passed(case, review):
    if review.get("translate_failed"):
        return False
    lang = str(review.get("language", "")).lower().split("-")[0]
    if lang != case["language"]:
        return False
    for field in ("title", "body"):
        result = review.get("translated_" + field)
        original = case[field]
        if case["language"] == "en" or not original:
            if result != original:
                return False
        elif not _translated(original, result):
            return False
    return True


def run_checks(gemini_key, sa_info):
    passed = True
    cloud = partial(translate_text, sa_info)
    for mode in ("gemini", "cloud"):
        # The first pass must prove Gemini works; fallback cannot hide its failure.
        forced_failure = (patch.object(reviews_model.urllib.request, "urlopen",
                                       side_effect=TimeoutError("Forced translation failure"))
                          if mode == "cloud" else nullcontext())
        with _quiet_services(), forced_failure:
            try:
                model = reviews_model.build_model(
                    [{"name": "Fixture app"}],
                    {"Fixture app": {"appstore": review_inputs(LIVE_CASES), "playstore": []}},
                    MOMENT - timedelta(days=1), MOMENT, gemini_key=gemini_key,
                    translate_fn=cloud if mode == "cloud" else None,
                )
                reviews = model["apps"][0]["appstore_reviews"]
            except Exception:
                reviews = []
        for index, case in enumerate(LIVE_CASES):
            ok = index < len(reviews) and review_passed(case, reviews[index])
            passed = passed and ok
            print(f"reviews {mode} case={index + 1}: {'PASS' if ok else 'FAIL'}")

        with _quiet_services():
            try:
                text, translated, lang, failed = detect_and_translate(CHINESE_CASE["body"], cloud)
                ok = (not failed and translated and str(lang).lower().split("-")[0] == "zh"
                      and _translated(CHINESE_CASE["body"], text))
            except Exception:
                ok = False
        passed = passed and ok
        print(f"survey case=1: {'PASS' if ok else 'FAIL'}")
    return 0 if passed else 1


def main():
    try:
        key = os.environ["GOOGLE_API_KEY"]
        sa_info = json.loads(base64.b64decode(os.environ["GOOGLE_SA_KEY"]))
        if not key or not isinstance(sa_info, dict):
            raise ValueError("Invalid translation setup")
    except Exception:
        print("translation setup: FAIL")
        return 1
    try:
        return run_checks(key, sa_info)
    except Exception:
        print("translation check: FAIL")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
