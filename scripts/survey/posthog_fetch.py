#!/usr/bin/env python3
"""Network layer: PostHog survey responses fetcher."""
import json
import sys

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


def _is_meaningful(text):
    return text.strip().lower() not in _LOW_VALUE and len(text.strip()) > 2


def transform_to_tabs(responses, config):
    """Transform PostHog responses into {tab_name: rows} for survey_model.

    Produces four pseudo-tabs:
    - Trouble Areas: predefined choice answers only → distribution
    - Other Issues: free-text/unknown area answers → summary (grouped)
    - Detailed Feedbacks: "Area — detail" per response → summary (grouped by area)
    - Open Feedback: meaningful open-text answers → summary (grouped)
    """
    qmap = config.get("question_map", {})
    area_idx = qmap.get("area_index", 0)
    detail_indices = qmap.get("detail_indices", [])
    open_idx = qmap.get("open_index")
    known = set(KNOWN_AREAS)

    tab_names = {s["sheet_name"] for s in config["surveys"]}
    tabs = {name: [] for name in tab_names}

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

        # Collect follow-up detail
        detail_parts = []
        for di in detail_indices:
            if di in answers:
                detail_parts.append(_parse_answer(answers[di]))
        detail = "; ".join(d for d in detail_parts if d)

        open_text = _parse_answer(answers.get(open_idx, {})) if open_idx is not None else ""

        # Detailed Feedbacks: "Area — detail" for meaningful responses
        if "Detailed Feedbacks" in tabs:
            issue = f"{area} — {detail}" if detail else area
            extra = open_text if _is_meaningful(open_text) else ""
            if detail or extra:
                tabs["Detailed Feedbacks"].append([ts, issue, extra])

        # Open Feedback: meaningful open-text only
        if "Open Feedback" in tabs and _is_meaningful(open_text):
            tabs["Open Feedback"].append([ts, open_text])

    return tabs
