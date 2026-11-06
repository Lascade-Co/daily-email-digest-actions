#!/usr/bin/env python3
"""Pure data model for the container tracking credit digest. No I/O, no clock."""
from scripts.common.dates import SHORT_MONTHS, long_date


def format_money(amount):
    return f"{amount:,.2f}"


def format_num(n):
    return f"{n:,}"


def build_model(products_config, today_data, month_data, now_dt, cutoff_dt,
                display_tz=None, month_label_dt=None):
    """Build the template model from fetched per-product purchase data.

    products_config: list of {"id": str, "name": str}
    today_data: {"total_revenue": float, "total_count": int, "products": {...}}
    month_data: same shape as today_data
    """
    products = []
    for cfg in products_config:
        pid = cfg["id"]
        today = today_data.get("products", {}).get(pid, {"revenue": 0.0, "count": 0})
        month = month_data.get("products", {}).get(pid, {"revenue": 0.0, "count": 0})
        products.append({
            "id": pid,
            "name": cfg["name"],
            "today_count": today["count"],
            "today_revenue": today["revenue"],
            "month_count": month["count"],
            "month_revenue": month["revenue"],
        })

    disp_now = now_dt.astimezone(display_tz) if display_tz else now_dt
    disp_cutoff = cutoff_dt.astimezone(display_tz) if display_tz else cutoff_dt
    tz_label = f" {disp_cutoff.strftime('%Z')}" if display_tz else ""
    date_str = long_date(disp_now)
    cutoff_hour = disp_cutoff.hour % 12 or 12
    cutoff_ampm = "AM" if disp_cutoff.hour < 12 else "PM"
    cutoff_str = (f"{disp_cutoff.day} {SHORT_MONTHS[disp_cutoff.month - 1]} "
                  f"{cutoff_hour}:{disp_cutoff.minute:02d} {cutoff_ampm}{tz_label}")

    dt = month_label_dt or disp_now
    month_label = f"1–{dt.day} {SHORT_MONTHS[dt.month - 1]} {dt.year}"

    return {
        "today_revenue": today_data.get("total_revenue", 0.0),
        "today_count": today_data.get("total_count", 0),
        "month_revenue": month_data.get("total_revenue", 0.0),
        "month_count": month_data.get("total_count", 0),
        "products": products,
        "date_str": date_str,
        "cutoff_str": cutoff_str,
        "month_label": month_label,
    }
