#!/usr/bin/env python3
"""Pure data model for the conversion digest. No I/O, no clock."""

from datetime import date

from scripts.common.dates import SHORT_MONTHS, long_date


def format_pct(rate):
    return f"{rate:.1f}"


def format_num(n):
    return f"{n:,}"


def format_cohort_date(iso_date):
    """'2026-10-20' → 'Oct 20'."""
    parts = iso_date.split("-")
    if len(parts) != 3:
        return iso_date
    month = int(parts[1])
    day = int(parts[2])
    return f"{SHORT_MONTHS[month - 1]} {day}"


def window_label(date_from, date_to):
    """'Oct 8 – Oct 21' for a range, 'Oct 21' for a single day."""
    if date_from == date_to:
        return format_cohort_date(date_to)
    return f"{format_cohort_date(date_from)} – {format_cohort_date(date_to)}"


def build_model(apps_config, app_data, now_dt, display_tz=None, *, date_from, date_to):
    """Build the template model from fetched per-app conversion data.

    app_data: dict mapping app name -> {
        "overall_rate": float,
        "total_installs": int,
        "total_paid": int,
        "cohorts": [{"date": str, "installs": int, "paid": int, "rate": float}, ...]
    }
    """
    window_days = (date.fromisoformat(date_to) - date.fromisoformat(date_from)).days + 1
    if window_days < 1:
        raise ValueError("date_to must not be before date_from")
    apps = []

    for app_cfg in apps_config:
        name = app_cfg["name"]
        data = app_data.get(name, {"overall_rate": 0.0, "total_installs": 0,
                                    "total_paid": 0, "cohorts": []})

        apps.append({
            "name": name,
            "overall_rate": data.get("overall_rate", 0.0),
            "total_installs": data.get("total_installs", 0),
            "installs_per_day": round(data.get("total_installs", 0) / window_days),
            "total_paid": data.get("total_paid", 0),
            "cohorts": data.get("cohorts", []),
            "has_data": data.get("total_installs", 0) > 0,
        })

    disp_now = now_dt.astimezone(display_tz) if display_tz else now_dt
    date_str = long_date(disp_now)

    return {
        "apps": apps,
        "app_names": [a["name"] for a in apps_config],
        "date_str": date_str,
        "window_days": window_days,
        "window_str": window_label(date_from, date_to),
    }
