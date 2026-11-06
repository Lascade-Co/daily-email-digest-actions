#!/usr/bin/env python3
"""Adapty Analytics API layer for container tracking credit purchases.

Endpoint: POST https://api-admin.adapty.io/api/v1/client-api/metrics/revenue/
Never logs API keys or response bodies.
"""


def fetch_credit_revenue(api_key, date_from, date_to, product_ids=None, tz="UTC"):
    """Fetch non-subscription purchase revenue segmented by product from Adapty.

    Args:
        api_key: Adapty secret API key for MarineRadar.
        date_from: Start date (YYYY-MM-DD).
        date_to: End date (YYYY-MM-DD).
        product_ids: Optional set/list of Adapty product IDs to keep;
                     None keeps all products.
        tz: IANA timezone for date grouping (default UTC).

    Returns:
        {
            "total_revenue": float (net, after store commission),
            "total_count": int,
            "products": {
                "product_id": {"revenue": float, "count": int},
                ...
            }
        }
    """
    import requests

    url = "https://api-admin.adapty.io/api/v1/client-api/metrics/revenue/"
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
        "Adapty-Tz": tz,
    }
    payload = {
        "filters": {
            "date": [date_from, date_to],
        },
        "segmentation": "product_id",
        "period_unit": "day",
        "format": "json",
    }
    keep = set(product_ids) if product_ids else None

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code != 200:
            print(f"adapty credit revenue: HTTP {resp.status_code}")
            return _empty()

        body = resp.json()
        products = {}

        for item in body.get("data", []):
            item_type = item.get("type", "")
            if item_type == "total":
                continue
            if keep and item_type not in keep:
                continue
            revenue = float(item.get("value", 0.0))
            count = int(item.get("value_from", 0))
            if revenue > 0 or count > 0:
                products[item_type] = {"revenue": revenue, "count": count}

        total_revenue = sum(p["revenue"] for p in products.values())
        total_count = sum(p["count"] for p in products.values())

        return {
            "total_revenue": total_revenue,
            "total_count": total_count,
            "products": products,
        }
    except Exception:
        print("adapty credit revenue: request failed")
        return _empty()


def _empty():
    return {"total_revenue": 0.0, "total_count": 0, "products": {}}
