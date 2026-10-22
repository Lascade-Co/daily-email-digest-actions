# Daily email digests

Five daily emails share one rendering shell and Gmail SMTP transport: MarineRadar web revenue, app reviews, MarineRadar surveys, Smart Ruler surveys, and Install → Paid conversion. The two survey products share one pipeline and workflow.

Each digest has **PT** (`America/Los_Angeles`, DST-aware) and **IST** (`Asia/Kolkata`) editions. Existing recipient lists and sender display names live in `data/email_config.json`; the former `pst` recipient key is now `pt`.

## Delivery and report dates

Scheduled runs gate until **05:05 local**, build the email, hold the completed files until **05:55 local**, then check delivery history and send. A late build sends immediately with the original report date. The holding job has a 75-minute timeout; the two earlier gate jobs each have a 350-minute timeout.

The report window is **[05:00 on D−1, 05:00 on D)** in the edition's timezone. Stripe month-to-date totals also stop at that upper bound. Conversion retains its 14-day cohort view, ending on **D−1** because the API takes calendar dates. Subjects use the report day, for example `MarineRadar web revenue · Wed, Oct 21 — $412.00 (3 purchases)`.

| Workflow | PT cron (UTC) | IST cron (UTC) |
|---|---|---|
| `daily-revenue.yml` | `45 3,6,9 * * *` | `11 13,16,19 * * *` |
| `daily-reviews.yml` | `47 3,6,9 * * *` | `13 13,16,19 * * *` |
| `daily-survey.yml` | `49 3,6,9 * * *` | `15 13,16,19 * * *` |
| `daily-conversion.yml` | `51 3,6,9 * * *` | `17 13,16,19 * * *` |

The four callers use `./.github/workflows/_digest.yml` from the same commit. Each digest and edition has an event-independent send-job lock, shared by schedules and manual recovery. Inside that lock, delivery history is checked **after the hold**, using successful dated `Deliver <digest> <PT|IST> for <D>` steps from this repository's `main` runs. History lookup failure stops SMTP delivery. A verified previous delivery skips SMTP and retains a successful dated step.

The `Delivered <PT|IST> for <D>` aggregate marker appears only after every digest in the edition succeeds. A partial survey run preserves its successful per-digest marker so a later cron sends only the missing product. Test sends and dry runs never create delivery markers. Gmail SMTP has no provider idempotency key: an ambiguous transport failure can still require investigation before recovery.

## TravelAnimator digest trigger

`ta-digest-trigger.yml` sends no email itself. The private `Lascade-Co/TA-daily-issues-digest` repository's crons start
hours late, and sleeping there would use the organisation's shared private Actions minutes, so this public workflow
does the waiting. PT runs at `53 3,6,9 * * *` and IST at `19 13,16,19 * * *` UTC. Two gates sleep until 05:05 local.
`scripts/ta_trigger/trigger.py` then dispatches TA's issues and crash workflows with `phase=build` and
`end=<D> 05:00`, holds until 05:55, and dispatches `phase=send build_run=<build run>` for every kind that built. Each kind
is independent and gets one retry. Builds must finish by 05:50 and sends by 06:10 local. A child still running at its
deadline is cancelled. Only a fully delivered edition gets the dated `Delivered TA <PT|IST> for <D>` step the gates
dedupe on.

Manual inputs: `mode=dry` (TA dry runs, the default), `mode=test` with `to` (real build→send chain to that address
only, no markers) and `mode=recovery` (production now, `main` only; TA's markers make an already-delivered day a no-op).
Manual runs skip the sleeps and the hold.

It needs the fine-grained token `TA_DIGEST_DISPATCH_TOKEN` (resource owner Lascade-Co, only TA-daily-issues-digest,
Actions: read and write) as a secret of the `ta-dispatch` environment, whose deployment branches are limited to `main`.
When it expires, the deliver step fails and TA's own late fallback crons still deliver.

## Manual runs and encrypted previews

Each caller accepts:

- `edition`: `pt`, `ist`, or `both` (default).
- `dry_run`: build encrypted previews without SMTP delivery.
- `report_date`: optional `YYYY-MM-DD`; blank means the newest 05:00 cutoff in each edition's timezone.
- `to`: send a `[TEST]` email only to the supplied address.
- `recovery`: production delivery, only when no successful dated send exists. A manual production run requires `recovery=true` and must be dispatched from `main`, which is the branch trusted by delivery history. Branch dry runs and test sends remain available.

Manual runs skip gate sleeps and the delivery hold. For previews from a review branch:

```bash
gh workflow run daily-revenue.yml -R Lascade-Co/daily-email-digest-actions -r <branch> -f dry_run=true -f edition=both
```

Use the reviews, survey, and conversion workflow filenames for the other digests. Each matrix leg uploads `preview-<digest>-<edition>`, containing **only `preview.tar.gz.enc`**. This is a tar.gz of `out/`, encrypted with `openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:PREVIEW_KEY`. The archive contains `<digest>-<edition>.html` and `<digest>-<edition>.subject.txt`. Plaintext previews are never uploaded, and normal sends create no artifacts.

To decrypt a downloaded artifact with a separately provided key file:

```bash
openssl enc -d -aes-256-cbc -pbkdf2 -in preview.tar.gz.enc -pass file:/path/to/keyfile | tar xz
```

Rendered content and recipients stay out of public Actions logs. Logs contain counts and an eight-character SHA-256 subject fingerprint. Test recipient inputs are read from the event file at send time so Actions does not print them in environment headers.

## Secrets

| Secret | Purpose |
|---|---|
| `GMAIL_USER`, `GMAIL_APP_PASSWORD` | Gmail SMTP |
| `STRIPE_API_KEY` | MarineRadar web revenue |
| `ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_PRIVATE_KEY` | App Store Connect reviews |
| `GOOGLE_SA_KEY` | Base64-encoded Google service account JSON for Play reviews and Sheets surveys |
| `GOOGLE_API_KEY` | Survey text processing |
| `ADAPTY_KEY_MARINERADAR`, `ADAPTY_KEY_SMARTRULER`, `ADAPTY_KEY_GEOANIMATOR` | Conversion cohorts |
| `PREVIEW_KEY` | Required encryption key for dry-run artifacts |

No Telegram integration is used. Failed workflows remain visible in GitHub Actions.

## Shared shell and local verification

`scripts/common/email_shell.py` is a copy of `product-intelligence/Style Template/email_shell.py`. Edit the canonical file, then re-copy its exact bytes after the two provenance header lines. Do not edit the copy or its CSS independently. Renderers compose digest-specific content around the shell helpers.

Tests use `unittest`, synthetic fixtures, and mocked transports without network requests. Install `requirements-dev.txt` for the YAML workflow checks, then run:

```bash
python3 -m unittest discover -s tests -q
python3 -m py_compile scripts/common/*.py scripts/*/*.py
actionlint .github/workflows/*.yml
python3 tests/render_fixtures.py .scratch/render-fixtures
```

Run the product-intelligence email validator on all five generated HTML files. Before landing, compare SHA-256 of the canonical shell with the copy after removing its first two lines. Local `out/`, fixture scratch files, and encrypted archives are ignored by Git.

The coordinator handles branch dispatches, real-data previews, approval, merge, and submodule updates. At cutover, possible one-day duplicates are accepted; inspect the first PT and IST deliveries for dated green steps, 05:55–05:58 inbox arrival, sender names, subjects, and Gmail iOS dark mode. This lane does not push or change `main`.
