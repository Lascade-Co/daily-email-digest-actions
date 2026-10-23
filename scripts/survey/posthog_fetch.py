#!/usr/bin/env python3
"""Network layer: PostHog survey responses fetcher."""
import json
import sys
from collections import defaultdict

import requests


class FetchError(Exception):
    pass


_API_BASE = "https://us.posthog.com/api"

_LOW_VALUE = {"", "—", "-", "n/a", "na", "none", "no", "nothing", "nil", ".", "ok", "good"}

KNOWN_AREAS = [
    "Selecting or positioning locations",
    "Highlighting or styling regions",
    "Adding text / labels",
    "Adding images",
    "Adding markers",
    "Timeline editing",
    "Exporting video",
    "Camera movement / transitions",
]


def fetch_responses(api_key, project_id, survey_id, start_dt, end_dt):
    """Return responses submitted in [start_dt, end_dt), newest first."""
    from datetime import datetime
    results = []
    url = f"{_API_BASE}/projects/{project_id}/surveys/{survey_id}/responses/"
    headers = {"Authorization": f"Bearer {api_key}"}
    while url:
        try:
            resp = requests.get(url, headers=headers, params={"limit": 200}, timeout=30)
        except requests.RequestException:
            print("posthog: network error", file=sys.stderr)
            raise FetchError("posthog-network")
        if resp.status_code != 200:
            print(f"posthog: HTTP {resp.status_code}", file=sys.stderr)
            raise FetchError(f"posthog-{resp.status_code}")
        data = resp.json()
        for r in data.get("results", []):
            submitted = datetime.fromisoformat(r["submitted_at"].replace("Z", "+00:00"))
            if submitted < start_dt:
                return results
            if submitted < end_dt:
                results.append(r)
        url = data.get("next")
    return results


def _parse_answer(answer):
    """Extract answer text, joining multiple-choice arrays."""
    val = answer.get("answer", "")
    if not val:
        return ""
    if answer.get("question_type") == "multiple_choice":
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return ", ".join(str(v) for v in parsed)
        except (json.JSONDecodeError, TypeError):
            pass
    return str(val).strip()


def _parse_answer_list(answer):
    """Extract answer as a list of individual choices."""
    val = answer.get("answer", "")
    if not val:
        return []
    if answer.get("question_type") == "multiple_choice":
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return [str(v).strip() for v in parsed if str(v).strip()]
        except (json.JSONDecodeError, TypeError):
            pass
    text = str(val).strip()
    return [text] if text else []


def _is_meaningful(text):
    return text.strip().lower() not in _LOW_VALUE and len(text.strip()) > 2


def transform_to_tabs(responses, config):
    """Transform PostHog responses into {tab_name: rows} for survey_model.

    Produces pseudo-tabs based on config['surveys'] (static sections) plus
    dynamic per-area detail tabs when area_detail_map is configured.

    Returns (tabs, detail_sections) where detail_sections is a list of
    survey config entries to inject into config['surveys'].
    """
    qmap = config.get("question_map", {})
    area_idx = qmap.get("area_index", 0)
    open_idx = qmap.get("open_index")
    area_detail_map = qmap.get("area_detail_map", {})
    known = set(KNOWN_AREAS)

    tab_names = {s["sheet_name"] for s in config["surveys"]}
    tabs = {name: [] for name in tab_names}

    # Per-area detail collection: area -> list of individual choice strings
    area_details = defaultdict(list)

    for resp in responses:
        ts = resp["submitted_at"]
        answers = {a["question_index"]: a for a in resp.get("answers", [])}

        area = _parse_answer(answers.get(area_idx, {}))
        if not area:
            continue

        is_known = area in known

        # Trouble Areas: only predefined choices
        if "Trouble Areas" in tabs and is_known:
            tabs["Trouble Areas"].append([ts, area])

        # Other Issues: free-text area answers
        if "Other Issues" in tabs and not is_known:
            tabs["Other Issues"].append([ts, area])

        # Per-area detail: find which follow-up question this area maps to
        if area in area_detail_map:
            detail_qi = area_detail_map[area]
            if detail_qi in answers:
                choices = _parse_answer_list(answers[detail_qi])
                for choice in choices:
                    area_details[area].append((ts, choice))

        open_text = _parse_answer(answers.get(open_idx, {})) if open_idx is not None else ""

        # Open Feedback: meaningful open-text only
        if "Open Feedback" in tabs and _is_meaningful(open_text):
            tabs["Open Feedback"].append([ts, open_text])

    # Build per-area detail tabs and config entries
    detail_sections = []
    for area in KNOWN_AREAS:
        entries = area_details.get(area, [])
        if not entries:
            continue
        tab_name = f"Detail: {area}"
        tabs[tab_name] = [[e[0], e[1]] for e in entries]
        detail_sections.append({
            "sheet_name": tab_name,
            "label": area,
            "subtitle": f"{len(entries)} response{'s' if len(entries) != 1 else ''}",
            "render": "distribution",
            "columns": [{"col": 1, "header": "Issue"}],
        })

    return tabs, detail_sections
