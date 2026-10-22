#!/usr/bin/env python3
"""Stripe API layer for the revenue digest. Never logs amounts or charge IDs."""


def fetch_charges(api_key, since_unix, until_unix):
    """Return succeeded charges in [since_unix, until_unix)."""
    import requests
    all_charges = []
    starting_after = None
    while True:
        params = {"limit": 100, "created[gte]": since_unix, "created[lt]": until_unix}
        if starting_after:
            params["starting_after"] = starting_after
        resp = requests.get(
            "https://api.stripe.com/v1/charges",
            params=params,
            auth=(api_key, ""),
            timeout=30,
        )
        if resp.status_code != 200:
            print(f"stripe charges: HTTP {resp.status_code}")
            break
        body = resp.json()
        for c in body.get("data", []):
            if c.get("status") == "succeeded" and since_unix <= c["created"] < until_unix:
                all_charges.append({
                    "amount_cents": c["amount"],
                    "currency": c.get("currency", "usd"),
                    "created": c["created"],
                    "metadata": c.get("metadata", {}),
                })
        if not body.get("has_more") or not body.get("data"):
            break
        starting_after = body["data"][-1]["id"]
    return all_charges


def fetch_refunds(api_key, since_unix, until_unix):
    """Return refunds in [since_unix, until_unix)."""
    import requests
    all_refunds = []
    starting_after = None
    while True:
        params = {"limit": 100, "created[gte]": since_unix, "created[lt]": until_unix}
        if starting_after:
            params["starting_after"] = starting_after
        resp = requests.get(
            "https://api.stripe.com/v1/refunds",
            params=params,
            auth=(api_key, ""),
            timeout=30,
        )
        if resp.status_code != 200:
            print(f"stripe refunds: HTTP {resp.status_code}")
            break
        body = resp.json()
        for r in body.get("data", []):
            if not since_unix <= r["created"] < until_unix:
                continue
            all_refunds.append({
                "amount_cents": r["amount"],
                "currency": r.get("currency", "usd"),
                "created": r["created"],
            })
        if not body.get("has_more") or not body.get("data"):
            break
        starting_after = body["data"][-1]["id"]
    return all_refunds
