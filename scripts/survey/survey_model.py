#!/usr/bin/env python3
"""Pure data layer: filter, detect language, build the email model. No I/O."""
from collections import Counter
from datetime import datetime, timedelta, timezone

try:
    from langdetect import detect as _detect
except ImportError:
    _detect = None

_TIMESTAMP_FMTS = [
    "%m/%d/%Y %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
]


_IST = timezone(timedelta(hours=5, minutes=30))

_TZ_MAP = {
    "Asia/Kolkata": _IST,
    "UTC": timezone.utc,
}


_SHEETS_EPOCH = datetime(1899, 12, 30)

_FUTURE_SLACK = timedelta(hours=2)


def _parse_ts(raw, tz=None, now_utc=None):
    """Parse a Google Sheets timestamp into a tz-aware datetime.

    Handles serial date numbers (from dateTimeRenderOption=SERIAL_NUMBER)
    as well as formatted date strings.  *tz* is the timezone the sheet
    timestamps are in (default: UTC).

    When *now_utc* is provided, any candidate that falls in the future
    (beyond a small slack) is rejected and the next format is tried.
    This guards against dd/mm ↔ mm/dd misparses that produce future dates.
    """
    raw = str(raw).strip()
    if tz is None:
        tz = timezone.utc
    ceiling = (now_utc + _FUTURE_SLACK) if now_utc else None

    def _accept(dt):
        if ceiling and dt > ceiling:
            return None
        return dt

    # Serial date number (days since 1899-12-30)
    try:
        serial = float(raw)
        if 1 < serial < 200000:
            dt = _SHEETS_EPOCH + timedelta(days=serial)
            result = _accept(dt.replace(tzinfo=tz))
            if result:
                return result
    except (ValueError, OverflowError):
        pass
    for fmt in _TIMESTAMP_FMTS:
        try:
            dt = datetime.strptime(raw, fmt).replace(tzinfo=tz)
            result = _accept(dt)
            if result:
                return result
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(raw).replace(tzinfo=tz)
        return _accept(dt)
    except Exception:
        pass
    return None


def filter_new_responses(rows, cutoff_dt, tz=None, now_utc=None):
    """Return rows whose timestamp (col 0) is after *cutoff_dt*."""
    out = []
    for row in rows:
        if not row:
            continue
        ts = _parse_ts(row[0], tz, now_utc=now_utc)
        if ts and ts > cutoff_dt:
            out.append(row)
    return out


def detect_and_translate(text, translate_fn):
    """Return (display_text, was_translated). Uses langdetect if available."""
    if not text or len(text) < 20:
        return text, False
    if _detect is None:
        return text, False
    try:
        lang = _detect(text)
    except Exception:
        return text, False
    if lang == "en":
        return text, False
    translated = translate_fn(text)
    if translated and translated != text:
        return translated, True
    return text, False


def _cell_value(row, col_index):
    """Safely get a cell value from a row."""
    if col_index < len(row):
        return str(row[col_index]).strip()
    return ""


import re
import json
import logging
import urllib.request
import urllib.error

log = logging.getLogger(__name__)

_OTHER_RE = re.compile(r"^other\b", re.IGNORECASE)
_LOW_VALUE = {"", "—", "-", "n/a", "na", "none", "no", "nothing", "nil", ".", "ok", "good"}
_MAX_SUMMARY_GROUPS = 8

_GROUP_PROMPT = """\
You are a survey response analyst. Given a list of user responses (already translated to English), \
group similar responses into themed summary points.

Rules:
- Each group has a short summary (max 12 words) describing the common theme
- Include specific examples (ship names, feature names) in parentheses when relevant
- Discard low-value responses like "ok", "good", "nothing", single characters
- Maximum {max_groups} groups; roll remaining into an "Other responses" group
- Return ONLY valid JSON, no markdown fences

Responses:
{responses}

Return JSON array: [{{"summary": "...", "count": N}}, ...]
Count = number of original responses in that group. Total counts must equal {total}."""


def _llm_group(texts, gemini_key):
    """Group responses using Gemini Flash."""
    prompt = _GROUP_PROMPT.format(
        responses="\n".join(f"- {t}" for t in texts),
        total=len(texts),
        max_groups=_MAX_SUMMARY_GROUPS,
    )
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 1024,
            "responseMimeType": "application/json",
        },
    }).encode()
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-3.5-flash-lite:generateContent?key=" + gemini_key
    )
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        raw = data["candidates"][0]["content"]["parts"][0]["text"]
        groups = json.loads(raw)
        return [{"text": g["summary"], "count": g["count"]} for g in groups]
    except Exception as e:
        log.warning("Gemini grouping failed, falling back to simple: %s", e)
        return None


def _simple_group(texts):
    """Fallback: exact-match grouping via Counter."""
    counted = Counter(texts)
    results = [{"text": t, "count": c} for t, c in counted.most_common()]
    if len(results) > _MAX_SUMMARY_GROUPS:
        kept = results[:_MAX_SUMMARY_GROUPS]
        rest = sum(g["count"] for g in results[_MAX_SUMMARY_GROUPS:])
        kept.append({"text": f"{rest} other responses", "count": rest})
        results = kept
    return results


def _fuzzy_group(texts, gemini_key=None):
    if not texts:
        return []
    if len(texts) == 1:
        return [{"text": texts[0], "count": 1}]
    if gemini_key:
        result = _llm_group(texts, gemini_key)
        if result:
            return result
    return _simple_group(texts)


def _split_multi(val, color_map=None):
    """Split a multi-choice response into individual options.

    Google Forms stores checkbox answers as 'Option A, Option B'.
    If a color_map is provided and the whole value matches a key, return it as-is.
    Normalise 'Other: free text' → 'Other'.
    """
    if not val:
        return []
    if color_map and val in color_map:
        return [val]
    parts = [p.strip() for p in val.split(",")]
    out = []
    for p in parts:
        if not p:
            continue
        if _OTHER_RE.match(p):
            out.append("Other")
        elif color_map:
            matched = False
            for key in color_map:
                if p.lower() == key.lower():
                    out.append(key)
                    matched = True
                    break
            if not matched:
                out.append(p)
        else:
            out.append(p)
    return out


def _is_meaningful(text):
    """Return True if a free-text response carries signal."""
    return text.strip().lower() not in _LOW_VALUE and len(text.strip()) > 2


def build_model(config, fetched_tabs, cutoff_dt, now_dt, translate_fn=None, display_tz=None, gemini_key=None):
    """Build the template model from config + raw sheet data.

    Supports two status patterns:
    - Global: config has "has_pro_free": true + "status_col" (Smart Ruler)
    - Per-survey: survey has "has_status": true + "status_col" (Marine Radar Map Survey)
    """
    sections = []
    total = 0
    free_count = 0
    pro_count = 0

    sheet_tz = _TZ_MAP.get(config.get("timezone", "UTC"), timezone.utc)
    global_status = config.get("has_pro_free", False)
    global_status_col = config.get("status_col", 2)

    for survey in config["surveys"]:
        rows = fetched_tabs.get(survey["sheet_name"], [])
        filtered = filter_new_responses(rows, cutoff_dt, sheet_tz, now_utc=now_dt)
        if not filtered:
            continue

        render_mode = survey.get("render", "table")
        has_status = survey.get("has_status", global_status)
        status_col = survey.get("status_col", global_status_col)
        status_values = survey.get("status_values", {"pro": "Pro", "free": "Free"})
        count = len(filtered)
        total += count

        if has_status:
            for row in filtered:
                status_raw = _cell_value(row, status_col).lower()
                if status_raw in ("pro", "premium"):
                    pro_count += 1
                else:
                    free_count += 1

        if render_mode == "distribution":
            distributions = []
            for col_def in survey["columns"]:
                color_map = col_def.get("color_map", {})
                counter = Counter()
                for row in filtered:
                    val = _cell_value(row, col_def["col"])
                    for part in _split_multi(val, color_map):
                        counter[part] += 1
                total_picks = sum(counter.values())
                options = []
                for val, cnt in counter.most_common():
                    pct = cnt / total_picks * 100 if total_picks else 0
                    options.append({
                        "value": val,
                        "count": cnt,
                        "pct": round(pct, 1),
                        "color": color_map.get(val, "#555"),
                    })
                distributions.append({
                    "header": col_def["header"],
                    "total": total_picks,
                    "options": options,
                })
            sections.append({
                "label": survey["label"],
                "subtitle": survey["subtitle"],
                "render": "distribution",
                "count": count,
                "distributions": distributions,
                "has_status": False,
            })

        elif render_mode == "summary":
            summaries = []
            for col_def in survey["columns"]:
                color_map = col_def.get("color_map", {})
                is_score = col_def.get("is_score", False)

                if color_map:
                    counter = Counter()
                    for row in filtered:
                        val = _cell_value(row, col_def["col"])
                        for part in _split_multi(val, color_map):
                            counter[part] += 1
                    total_picks = sum(counter.values())
                    options = []
                    for val, cnt in counter.most_common():
                        pct = cnt / total_picks * 100 if total_picks else 0
                        options.append({
                            "value": val,
                            "count": cnt,
                            "pct": round(pct, 1),
                            "color": color_map.get(val, "#555"),
                        })
                    summaries.append({
                        "header": col_def["header"],
                        "type": "distribution",
                        "total": total_picks,
                        "options": options,
                    })
                elif is_score:
                    scores = []
                    for row in filtered:
                        v = _cell_value(row, col_def["col"])
                        try:
                            scores.append(int(v))
                        except ValueError:
                            pass
                    avg = sum(scores) / len(scores) if scores else 0
                    summaries.append({
                        "header": col_def["header"],
                        "type": "score",
                        "avg": round(avg, 1),
                        "total": len(scores),
                        "breakdown": dict(Counter(scores)),
                    })
                else:
                    translated = []
                    for row in filtered:
                        v = _cell_value(row, col_def["col"])
                        if not _is_meaningful(v):
                            continue
                        if translate_fn:
                            tv, _ = detect_and_translate(v, translate_fn)
                        else:
                            tv = v
                        tv = tv.strip()
                        if tv:
                            translated.append(tv)
                    grouped = _fuzzy_group(translated, gemini_key=gemini_key)
                    summaries.append({
                        "header": col_def["header"],
                        "type": "grouped",
                        "total": len(translated),
                        "groups": grouped,
                    })
            sections.append({
                "label": survey["label"],
                "subtitle": survey["subtitle"],
                "render": "summary",
                "count": count,
                "summaries": summaries,
                "has_status": has_status,
            })

        else:
            rendered_rows = []
            for row in filtered:
                status_label = None
                status_color = None
                if has_status:
                    status_raw = _cell_value(row, status_col).lower()
                    is_pro = status_raw in ("pro", "premium")
                    status_label = status_values.get(status_raw, "Pro" if is_pro else "Free")
                    status_color = "#5a5aad" if is_pro else "#888"

                cells = []
                for col_def in survey["columns"]:
                    val = _cell_value(row, col_def["col"])
                    was_translated = False
                    if translate_fn and val:
                        val, was_translated = detect_and_translate(val, translate_fn)

                    color = "#222"
                    bold = False
                    empty_text = col_def.get("empty_text")
                    empty_color = col_def.get("empty_color", "#aaa")
                    color_map = col_def.get("color_map", {})
                    bold_list = col_def.get("bold", [])
                    bold_all = col_def.get("bold_all", False)
                    is_score = col_def.get("is_score", False)

                    if not val and empty_text:
                        val = empty_text
                        color = empty_color
                    elif not val:
                        val = "—"
                        color = "#aaa"

                    if is_score and val:
                        try:
                            score = int(val)
                            val = f"{score}/5"
                            if score >= 4:
                                color = "#2a8c4a"
                            elif score == 3:
                                color = "#c9922a"
                            else:
                                color = "#c0392b"
                            bold = True
                        except ValueError:
                            pass

                    if val in color_map:
                        color = color_map[val]
                    if bold_all:
                        bold = True
                    elif isinstance(bold_list, list) and val in bold_list:
                        bold = True

                    cells.append({
                        "value": val,
                        "color": color,
                        "bold": bold,
                        "translated": was_translated,
                    })

                rendered_rows.append({
                    "cells": cells,
                    "status_label": status_label,
                    "status_color": status_color,
                })

            sections.append({
                "label": survey["label"],
                "subtitle": survey["subtitle"],
                "render": "table",
                "columns": [c["header"] for c in survey["columns"]],
                "rows": rendered_rows,
                "count": len(rendered_rows),
                "has_status": has_status,
            })

    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    months = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    short_months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    disp_now = now_dt.astimezone(display_tz) if display_tz else now_dt
    disp_cutoff = cutoff_dt.astimezone(display_tz) if display_tz else cutoff_dt
    tz_label = f" {disp_cutoff.strftime('%Z')}" if display_tz else ""

    date_str = f"{weekdays[disp_now.weekday()]}, {disp_now.day} {months[disp_now.month - 1]} {disp_now.year}"

    cutoff_h = disp_cutoff.hour % 12 or 12
    cutoff_ampm = "AM" if disp_cutoff.hour < 12 else "PM"
    cutoff_str = f"{disp_cutoff.day} {short_months[disp_cutoff.month - 1]} {cutoff_h}:{disp_cutoff.minute:02d} {cutoff_ampm}{tz_label}"

    return {
        "product_name": config.get("product_name", "Survey"),
        "email_title": config.get("email_title", "Survey Responses"),
        "sections": sections,
        "total": total,
        "free_count": free_count,
        "pro_count": pro_count,
        "date_str": date_str,
        "cutoff_str": cutoff_str,
        "sheet_url": config.get("sheet_url", ""),
    }
