#!/usr/bin/env python3
"""Adapty Analytics Export API layer for the conversion digest.

Endpoint docs: https://adapty.io/docs/api-export-analytics/operations/retrieveConversionData
Never logs API keys or response bodies.
"""


def fetch_install_to_paid(api_key, date_from, date_to, tz="UTC"):
    """Fetch Install → Paid cohort conversion rates from Adapty.

    Calls POST https://api-admin.adapty.io/api/v1/client-api/metrics/conversion/
    with segmentation by day. The "Total" row in the response contains a
    per-install-date breakdown with installs, paid count, and conversion rate.

    Args:
        api_key: Adapty secret API key for the app.
        date_from: Start date (YYYY-MM-DD).
        date_to: End date (YYYY-MM-DD).
        tz: IANA timezone for date grouping (default UTC).

    Returns:
        {
            "overall_rate": float,
            "total_installs": int,
            "total_paid": int,
            "cohorts": [{"date": str, "installs": int, "paid": int, "rate": float}, ...]
        }
        Cohorts are sorted newest-first.
    """
    import requests

    url = "https://api-admin.adapty.io/api/v1/client-api/metrics/conversion/"
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
        "Adapty-Tz": tz,
    }
    # from_period is intentionally omitted — null means "install"
    payload = {
        "filters": {
            "date": [date_from, date_to],
        },
        "to_period": "1",
        "period_unit": "day",
        "date_type": "profile_install_date",
        "segmentation": "day",
        "format": "json",
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code != 200:
            print(f"adapty conversion: HTTP {resp.status_code}")
            return _empty()

        body = resp.json()

        total_row = None
        for item in body.get("data", []):
            if item.get("type") == "total":
                total_row = item
                break

        if not total_row:
            return _empty()

        cohorts = []
        outside_window = False
        for v in total_row.get("values", []):
            date_str = str(v.get("x", ""))[:10]
            if not date_from <= date_str <= date_to:
                outside_window = True
                continue
            installs = int(v.get("value_from", 0))
            paid = int(v.get("value_to", 0))
            rate = float(v.get("y", 0.0))
            if installs > 0:
                cohorts.append({
                    "date": date_str,
                    "installs": installs,
                    "paid": paid,
                    "rate": rate,
                })

        cohorts.sort(key=lambda c: c["date"], reverse=True)

        # If the API includes an out-of-range cohort, its aggregate must not
        # smuggle that cohort back into the digest after row filtering.
        total_installs = int(total_row.get("value_from", 0))
        total_paid = int(total_row.get("value_to", 0))
        overall_rate = float(total_row.get("value", 0))
        if outside_window:
            total_installs = sum(cohort["installs"] for cohort in cohorts)
            total_paid = sum(cohort["paid"] for cohort in cohorts)
            overall_rate = total_paid / total_installs * 100 if total_installs else 0.0

        return {
            "overall_rate": overall_rate,
            "total_installs": total_installs,
            "total_paid": total_paid,
            "cohorts": cohorts,
        }
    except Exception:
        print("adapty conversion: request failed")
        return _empty()


def _empty():
    return {"overall_rate": 0.0, "total_installs": 0, "total_paid": 0, "cohorts": []}
