# Daily Email Digest Actions

Automated daily email digests via GitHub Actions — reviews, revenue, and survey responses.

## Digests

| Digest | Schedule | Description |
|--------|----------|-------------|
| **Reviews** | 6:30 PM IST | App Store + Play Store reviews for MarineRadar, Smart Ruler, GeoAnimator |
| **Revenue** | 6:30 PM IST | Stripe revenue summary for MarineRadar Web |
| **Survey** | 6:30 PM IST | Google Sheets survey responses (Marine Radar + Smart Ruler, separate emails) |

## Structure

```
.github/workflows/
  daily-reviews.yml       # Reviews digest workflow
  daily-revenue.yml       # Revenue digest workflow
  daily-survey.yml        # Survey digest workflow

scripts/
  catchup/catchup_gate.py # Timing gate (ensures once-daily delivery)
  reviews/                # Reviews: fetch, model, render, main
  revenue/                # Revenue: fetch, model, render, main
  survey/                 # Survey: fetch, model, render, main

data/
  reviews_apps.json       # App IDs and package names
  survey_marine.json      # Marine Radar sheet config (9 tabs)
  survey_measure.json     # Smart Ruler sheet config (3 tabs)
```

## Required Secrets

| Secret | Description |
|--------|-------------|
| `ASC_KEY_ID` | App Store Connect API key ID |
| `ASC_ISSUER_ID` | App Store Connect issuer ID |
| `ASC_PRIVATE_KEY` | App Store Connect private key (.p8 contents) |
| `GOOGLE_SA_KEY` | Google service account key JSON (base64-encoded) |
| `STRIPE_API_KEY` | Stripe secret key (for revenue digest) |
| `GMAIL_USER` | Gmail address for sending |
| `GMAIL_APP_PASSWORD` | Gmail app password |

## Recipients

All digests send to: `angelrose@lascade.com`, `cherian@lascade.com`

## Manual Trigger

Each workflow supports `workflow_dispatch` with:
- **dry_run** — build the email without sending
- **to** — send a `[TEST]` email to a single address
