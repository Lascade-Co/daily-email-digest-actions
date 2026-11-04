#!/usr/bin/env python3
"""Stripe API layer for incomplete checkout outreach. Never logs emails or customer IDs."""

import requests


def _paginate(api_key, endpoint, params):
    all_items = []
    starting_after = None
    while True:
        p = dict(params, limit=100)
        if starting_after:
            p["starting_after"] = starting_after
        resp = requests.get(
            f"https://api.stripe.com/v1/{endpoint}",
            params=p,
            auth=(api_key, ""),
            timeout=30,
        )
        if resp.status_code != 200:
            print(f"stripe {endpoint}: HTTP {resp.status_code}")
            break
        body = resp.json()
        all_items.extend(body.get("data", []))
        if not body.get("has_more") or not body.get("data"):
            break
        starting_after = body["data"][-1]["id"]
    return all_items


def fetch_incomplete_customers(api_key, since_unix, until_unix):
    """Return customers created in [since, until) with no successful charges
    and no active subscriptions. Skips customers without email and internal
    @lascade.com addresses."""
    customers = _paginate(api_key, "customers", {
        "created[gte]": since_unix,
        "created[lt]": until_unix,
    })
    incomplete = []
    for cust in customers:
        email = cust.get("email")
        if not email or email.endswith("@lascade.com"):
            continue
        charges = _paginate(api_key, "charges", {
            "customer": cust["id"],
            "status": "succeeded",
            "limit": 1,
        })
        if charges:
            continue
        subs = _paginate(api_key, "subscriptions", {
            "customer": cust["id"],
            "status": "active",
            "limit": 1,
        })
        if subs:
            continue
        incomplete.append({
            "email": email,
            "created": cust["created"],
            "customer_id": cust["id"],
        })
    print(f"stripe: total={len(customers)} incomplete={len(incomplete)}")
    return incomplete
