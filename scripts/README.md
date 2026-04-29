# Data source scripts

The audit dashboard expects a CSV with seven fields: app name, category, annual cost, seats purchased, active seats (30d), renewal date, and owner. The scripts in this folder bridge the gap between that format and the data sources most IT orgs actually have.

These are starter scripts, not production ETL. They're intentionally short and readable so a competent IT engineer can adapt them in an afternoon. Each one solves a specific data-collection problem the audit tool would otherwise leave to the user.

## Which script to use

Pick the path that matches your org's stack:

| If your org uses... | Use this script | Why |
|---|---|---|
| Okta as the IdP, with most SaaS behind SSO | `okta-join.py` | Most common mid-market setup. Okta sign-in logs give you accurate active-seat data without buying a SaaS management platform. |
| Google Workspace as the IdP, OAuth-heavy | `gworkspace-join.py` | The right answer for Google-first shops. Pulls login activity from the Admin SDK Reports API. |
| Zylo (or Productiv / BetterCloud / Torii) | `zylo-normalize.py` | If you already have a SaaS management platform, it gathers everything. This script just renames columns to the audit format. |
| None of the above (small org, manual inventory) | None | Build the CSV manually. The audit tool's column auto-detection will accept most reasonable header names. |

## How they fit together

All three scripts produce the same output format — a CSV the audit dashboard can ingest directly. The dashboard doesn't know or care which data source you used.

```
                        ┌────────────────────┐
   Okta API ────────────► okta-join.py       │
                        │                    │
   Google Workspace ────► gworkspace-join.py ├──► audit-ready.csv ──► dashboard
   Admin SDK            │                    │
                        │                    │
   Zylo CSV export ─────► zylo-normalize.py  │
                        └────────────────────┘
```

This separation matters. The dashboard is the "last mile" — it turns clean data into a prioritized action list. Gathering the data is its own problem with its own tools. Mixing the two would have made both harder.

## Running on a schedule

For a real deployment, the typical pattern is:

1. Schedule the appropriate join script via cron (weekly is usually enough)
2. Output `audit-ready.csv` to a shared drive (Google Drive, S3, internal share)
3. The IT Director uploads it to the dashboard when they want to review

Direct integration between the script and the dashboard isn't needed — the dashboard's "Upload your CSV" button is the right interaction model for a tool that gets used periodically rather than continuously.

## What these scripts deliberately don't do

Same scope discipline as the audit tool itself.

- **No shadow IT discovery.** If an app isn't behind SSO, it's invisible to these scripts. That's by design — discovering unsanctioned SaaS is a different problem with mature dedicated tools (Nudge Security, Push Security, BetterCloud).
- **No data warehousing.** The scripts produce a CSV. They don't build a database, maintain history, or track trends over time. If you need that, you've outgrown this tool.
- **No vendor API integrations.** Each SaaS vendor has its own admin API for usage data. Building 50 vendor-specific connectors is what Zylo charges $30K+/year for. That's not in scope here.
- **No production hardening.** These scripts have basic error handling, but they're not bulletproof. Add retries, alerting, and credential rotation before running them unattended in a real environment.

## Authentication setup

Each script reads credentials from environment variables. See the docstring at the top of each file for the specifics. A few high-level notes:

**Okta:** Create an API token in the Okta admin console (Security → API → Tokens). The token's permissions should be limited to read-only access to the System Log. Rotate it on the org's normal credential rotation schedule.

**Google Workspace:** Requires a service account with domain-wide delegation. The service account needs the `admin.reports.audit.readonly` scope. Setting this up takes ~20 minutes the first time and is documented in Google's [Admin SDK guide](https://developers.google.com/workspace/guides/create-credentials).

**Zylo:** No auth needed — the script reads a CSV file you've already exported from Zylo's UI.

## A note on accuracy

Active-seat counts from these scripts will be *close to* but not *identical to* what a paid SaaS management platform reports. SMPs use vendor-specific APIs that catch things SSO logs miss (admin actions, API-only users, mobile-only sessions). For a Director-level audit, "close enough to make a defensible recommendation" is what matters. If you need audit-grade precision for compliance reporting, that's the use case where buying Zylo or Productiv is genuinely worth the money.
