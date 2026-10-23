#!/usr/bin/env python3
"""Network layer: fetch reviews from App Store Connect and Google Play."""
import os
import time
from datetime import datetime, timezone



def _mask(value):
    """Emit GitHub Actions mask command for a secret value."""
    if os.environ.get("GITHUB_ACTIONS", "").lower() != "true":
        return
    for line in str(value).splitlines():
        if line.strip():
            print(f"::add-mask::{line}")


def _asc_jwt(key_id, issuer_id, private_key_pem):
    """Mint an App Store Connect JWT (ES256, 20-minute expiry)."""
    import jwt
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    now = int(time.time())
    payload = {"iss": issuer_id, "iat": now, "exp": now + 1200, "aud": "appstoreconnect-v1"}
    key = load_pem_private_key(private_key_pem.encode(), password=None)
    return jwt.encode(payload, key, algorithm="ES256", headers={"kid": key_id})


PLAY_PAGE_SIZE = 100
PLAY_MAX_PAGES = 20


def fetch_appstore_reviews(apple_id, since_dt, key_id, issuer_id, private_key_pem, *, until_dt):
    """Fetch App Store reviews in [since_dt, until_dt).

    Returns (reviews, status): status is "ok" or "failed". Reviews collected before a
    failure are kept.
    """
    import requests
    reviews = []
    try:
        _mask(key_id)
        _mask(issuer_id)
        _mask(private_key_pem)
        token = _asc_jwt(key_id, issuer_id, private_key_pem)
        _mask(token)
    except Exception:
        print("ASC API auth failed")
        return reviews, "failed"

    url = (f"https://api.appstoreconnect.apple.com/v1/apps/{apple_id}"
           f"/customerReviews?sort=-createdDate&limit=200")

    while url:
        try:
            resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
            if resp.status_code != 200:
                print(f"ASC API: HTTP {resp.status_code}")
                return reviews, "failed"

            result = resp.json()
            done = False
            for review in result.get("data", []):
                attrs = review.get("attributes", {})
                created = datetime.fromisoformat(attrs["createdDate"].replace("Z", "+00:00"))
                if created < since_dt:
                    done = True
                    break
                if created >= until_dt:
                    continue
                reviews.append({
                    "store": "appstore",
                    "rating": attrs.get("rating", 0),
                    "title": attrs.get("title", ""),
                    "body": attrs.get("body", ""),
                    "author": attrs.get("reviewerNickname", "Unknown"),
                    "version": "",
                    "date": created.isoformat(),
                    "country": attrs.get("territory", ""),
                    "device": "",
                    "os_version": "",
                    "is_non_english": False,
                })

            if done:
                break
            url = (result.get("links") or {}).get("next")
        except Exception:
            print("ASC API fetch failed")
            return reviews, "failed"

    return reviews, "ok"

def _play_access_token(sa_info):
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request as AuthRequest

    creds = service_account.Credentials.from_service_account_info(
        sa_info, scopes=["https://www.googleapis.com/auth/androidpublisher"])
    creds.refresh(AuthRequest())
    _mask(creds.token)
    return creds.token


def _play_review(review, ts):
    comment = review["comments"][0].get("userComment", {})
    os_ver = comment.get("androidOsVersion", "")
    app_ver = comment.get("appVersionName", "")
    app_code = comment.get("appVersionCode", "")
    version = ""
    if app_ver:
        version = f"v{app_ver}"
        if app_code:
            version += f"+{app_code}"
    return {
        "store": "playstore",
        "rating": comment.get("starRating", 0),
        "title": "",
        "body": comment.get("text", ""),
        "author": review.get("authorName", "A Google user"),
        "version": version,
        "date": ts.isoformat(),
        "country": "",
        "device": (comment.get("deviceMetadata") or {}).get("productName", ""),
        "os_version": f"Android {os_ver}" if os_ver else "",
        "is_non_english": False,
    }


def fetch_playstore_reviews(package_name, since_dt, sa_info, *, until_dt):
    """Fetch Play Store reviews in [since_dt, until_dt), newest first, across pages.

    Returns (reviews, status): "ok", "failed" (auth, HTTP or parse error on any page) or
    "incomplete" (page cap hit before reaching since_dt). Collected reviews are kept.
    """
    import requests
    reviews = []
    try:
        token = _play_access_token(sa_info)
    except Exception:
        print("Play Store auth failed")
        return reviews, "failed"

    since_unix = int(since_dt.timestamp())
    until_unix = int(until_dt.timestamp())
    url = (f"https://androidpublisher.googleapis.com/androidpublisher/v3"
           f"/applications/{requests.utils.quote(package_name, safe='')}/reviews")
    page_token = None

    try:
        for _ in range(PLAY_MAX_PAGES):
            params = {"maxResults": PLAY_PAGE_SIZE}
            if page_token:
                params["token"] = page_token
            resp = requests.get(url, headers={"Authorization": f"Bearer {token}"},
                                params=params, timeout=30)
            if resp.status_code != 200:
                print(f"Play Store API: HTTP {resp.status_code}")
                return reviews, "failed"

            result = resp.json()
            for review in result.get("reviews", []):
                comments = review.get("comments", [])
                if not comments:
                    continue
                last_mod = comments[0].get("userComment", {}).get("lastModified") or {}
                if not last_mod.get("seconds"):
                    continue                  # undated: never let it end the scan
                seconds = int(last_mod["seconds"])
                if seconds < since_unix:
                    return reviews, "ok"      # newest first: everything after is older
                if seconds >= until_unix:
                    continue
                reviews.append(_play_review(review, datetime.fromtimestamp(seconds, tz=timezone.utc)))

            page_token = (result.get("tokenPagination") or {}).get("nextPageToken")
            if not page_token:
                return reviews, "ok"
    except Exception:
        print("Play Store fetch failed")
        return reviews, "failed"

    print("Play Store API: page cap reached")
    return reviews, "incomplete"
