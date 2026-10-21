#!/usr/bin/env python3
"""Pure data model for the conversion digest. No I/O, no clock."""

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]
SHORT_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


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


def build_model(apps_config, app_data, now_dt, display_tz=None):
    """Build the template model from fetched per-app conversion data.

    app_data: dict mapping app name -> {
        "overall_rate": float,
        "total_installs": int,
        "total_paid": int,
        "cohorts": [{"date": str, "installs": int, "paid": int, "rate": float}, ...]
    }
    """
    apps = []

    for app_cfg in apps_config:
        name = app_cfg["name"]
        data = app_data.get(name, {"overall_rate": 0.0, "total_installs": 0,
                                    "total_paid": 0, "cohorts": []})

        apps.append({
            "name": name,
            "overall_rate": data.get("overall_rate", 0.0),
            "total_installs": data.get("total_installs", 0),
            "total_paid": data.get("total_paid", 0),
            "cohorts": data.get("cohorts", []),
            "has_data": data.get("total_installs", 0) > 0,
        })

    disp_now = now_dt.astimezone(display_tz) if display_tz else now_dt
    date_str = f"{DAYS[disp_now.weekday()]}, {disp_now.day} {MONTHS[disp_now.month - 1]} {disp_now.year}"

    return {
        "apps": apps,
        "app_names": [a["name"] for a in apps_config],
        "date_str": date_str,
    }
