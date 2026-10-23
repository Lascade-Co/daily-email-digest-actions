#!/usr/bin/env python3
"""Network layer: PostHog survey responses fetcher."""
import json
import sys

import requests


class FetchError(Exception):
    pass


_API_BASE = "https://us.posthog.com/api"


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


def transform_to_tabs(responses, config):
    """Transform PostHog responses into {tab_name: rows} for survey_model.

    Each row starts with an ISO timestamp (col 0) followed by field values
    at the column indices the survey config expects.
    """
    qmap = config.get("question_map", {})
    area_idx = qmap.get("area_index", 0)
    detail_indices = qmap.get("detail_indices", [])
    open_idx = qmap.get("open_index")

    tab_names = {s["sheet_name"] for s in config["surveys"]}
    tabs = {name: [] for name in tab_names}

    for resp in responses:
        ts = resp["submitted_at"]
        answers = {a["question_index"]: a for a in resp.get("answers", [])}
        extra = resp.get("extra", {})

        area = _parse_answer(answers.get(area_idx, {}))
        if not area:
            continue

        detail_parts = []
        for di in detail_indices:
            if di in answers:
                detail_parts.append(_parse_answer(answers[di]))
        detail = "; ".join(d for d in detail_parts if d)
        open_text = _parse_answer(answers.get(open_idx, {})) if open_idx is not None else ""
        country = extra.get("geoip_country_name", "")
        device = extra.get("device_type", "")

        if "Trouble Areas" in tabs:
            tabs["Trouble Areas"].append([ts, area])
        if "Responses" in tabs:
            tabs["Responses"].append([ts, area, detail, open_text, country, device])
        if "Open Feedback" in tabs and open_text:
            tabs["Open Feedback"].append([ts, open_text])

    return tabs
