#!/usr/bin/env python3
"""Pure data model for the revenue digest. No I/O, no clock."""
from collections import defaultdict
from scripts.common.dates import SHORT_MONTHS, long_date


def format_money(amount):
    """Format a dollar amount with commas and two decimals: 1234.5 → '1,234.50'."""
    return f"{amount:,.2f}"


def _sum_cents(items):
    return sum(c["amount_cents"] for c in items)


def build_model(today_charges, today_refunds, month_charges, month_refunds, now_dt, cutoff_dt, display_tz=None):
    """Build the template model dict from raw charge/refund lists.

    All monetary values are in dollars (float). Counts are ints.
    """
    today_total = _sum_cents(today_charges) / 100
    today_refund_total = _sum_cents(today_refunds) / 100

    month_total = _sum_cents(month_charges) / 100
    month_refund_total = _sum_cents(month_refunds) / 100

    # Group today's charges by dollar amount (credit pack)
    by_pack = defaultdict(lambda: {"count": 0, "total": 0.0})
    for c in today_charges:
        amt = c["amount_cents"] / 100
        key = f"{amt:.2f}"
        by_pack[key]["count"] += 1
        by_pack[key]["total"] += amt
    packs = [
        {"amount": key, "count": v["count"], "total": v["total"]}
        for key, v in sorted(by_pack.items(), key=lambda kv: float(kv[0]))
    ]

    disp_now = now_dt.astimezone(display_tz) if display_tz else now_dt
    disp_cutoff = cutoff_dt.astimezone(display_tz) if display_tz else cutoff_dt
    tz_label = f" {disp_cutoff.strftime('%Z')}" if display_tz else ""

    date_str = long_date(disp_now)
    cutoff_hour = disp_cutoff.hour % 12 or 12
    cutoff_ampm = "AM" if disp_cutoff.hour < 12 else "PM"
    cutoff_str = f"{disp_cutoff.day} {SHORT_MONTHS[disp_cutoff.month - 1]} {cutoff_hour}:{disp_cutoff.minute:02d} {cutoff_ampm}{tz_label}"

    month_label = f"1–{disp_now.day} {SHORT_MONTHS[disp_now.month - 1]} {disp_now.year}"

    # Purchase Source Breakdown — commented out until metadata property is configured
    # TODO: Uncomment when purchase_source metadata key is set in Stripe
    # source_meta_key = "purchase_source"
    # by_source = defaultdict(lambda: {"count": 0, "total": 0.0})
    # for c in today_charges:
    #     src = c["metadata"].get(source_meta_key, "Unknown")
    #     by_source[src]["count"] += 1
    #     by_source[src]["total"] += c["amount_cents"] / 100
    # sources = [
    #     {"source": k, "count": v["count"], "total": v["total"]}
    #     for k, v in sorted(by_source.items(), key=lambda kv: -kv[1]["total"])
    # ]

    return {
        "today_total": today_total,
        "today_refund_total": today_refund_total,
        "today_count": len(today_charges),
        "today_refund_count": len(today_refunds),
        "packs": packs,
        "month_total": month_total,
        "month_refund_total": month_refund_total,
        "month_net": month_total - month_refund_total,
        "month_count": len(month_charges),
        "month_refund_count": len(month_refunds),
        "month_label": month_label,
        "date_str": date_str,
        "cutoff_str": cutoff_str,
        # "sources": sources,  # TODO: uncomment with Purchase Source Breakdown
    }
