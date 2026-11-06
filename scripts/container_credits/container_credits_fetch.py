#!/usr/bin/env python3
"""Adapty Analytics API layer for container tracking credit purchases.

Endpoint: POST https://api-admin.adapty.io/api/v1/client-api/metrics/analytics/
Uses chart_id "revenue" for dollar amounts and "non_subscriptions" for purchase counts.
Never logs API keys or response bodies.
"""


def fetch_credit_revenue(api_key, date_from, date_to, products_config, tz="UTC"):
    """Fetch non-subscription purchase revenue and counts from Adapty.

    Args:
        api_key: Adapty secret API key for MarineRadar.
        date_from: Start date (YYYY-MM-DD).
        date_to: End date (YYYY-MM-DD).
        products_config: list of {"id": str, "name": str} from container_credits.json.
        tz: IANA timezone for date grouping (default UTC).

    Returns:
        {
            "total_revenue": float (net, after store commission),
            "total_count": int,
            "products": {
                "config_id": {"revenue": float, "count": int},
                ...
            }
        }
    """
    import requests

    url = "https://api-admin.adapty.io/api/v1/client-api/metrics/analytics/"
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
        "Adapty-Tz": tz,
    }
    name_to_id = {cfg["name"]: cfg["id"] for cfg in products_config}

    products = {cfg["id"]: {"revenue": 0.0, "count": 0} for cfg in products_config}

    for chart_id, field, key in [
        ("revenue", "revenue", "revenue"),
        ("non_subscriptions", "common", "count"),
    ]:
        payload = {
            "chart_id": chart_id,
            "filters": {"date": [date_from, date_to]},
            "segmentation": "store_product_id",
            "period_unit": "day",
            "format": "json",
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            if resp.status_code != 200:
                print(f"adapty credit {chart_id}: HTTP {resp.status_code}")
                continue
            body = resp.json()
            for item in body.get("data", {}).get(field, {}).get("data", []):
                title = item.get("title", "")
                cfg_id = name_to_id.get(title)
                if cfg_id is None:
                    continue
                products[cfg_id][key] = (
                    float(item["value"]) if key == "revenue" else int(item["value"])
                )
        except Exception:
            print(f"adapty credit {chart_id}: request failed")

    total_revenue = sum(p["revenue"] for p in products.values())
    total_count = sum(p["count"] for p in products.values())

    return {
        "total_revenue": total_revenue,
        "total_count": total_count,
        "products": products,
    }


def _empty():
    return {"total_revenue": 0.0, "total_count": 0, "products": {}}
