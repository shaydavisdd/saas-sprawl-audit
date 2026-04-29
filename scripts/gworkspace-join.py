#!/usr/bin/env python3
"""
gworkspace-join.py — Build an audit-ready CSV from Google Workspace login audit
logs + finance export.

USE WHEN:
  Your org uses Google Workspace as the identity provider (or Google Workspace
  + a separate IdP) and most SaaS apps are accessed via "Sign in with Google".

WHAT IT DOES:
  1. Fetches login audit events from the Google Admin SDK Reports API
  2. Counts unique users per OAuth client / app over the last 30 days
  3. Joins with a finance CSV that has app name, annual cost, seats purchased,
     renewal date, owner, and category
  4. Writes audit-ready output to stdout or a file

LIMITATIONS:
  - Only catches apps logged in via Google OAuth. Apps using direct user/pass
    or a different IdP are invisible. (Same scope boundary as the audit tool.)
  - OAuth client names sometimes differ from the marketing app name
    (e.g. 'Slack' vs 'slack-prod-v2'). Mismatches are logged so you can fix
    them in your finance CSV.
  - Requires a service account with domain-wide delegation and the
    'https://www.googleapis.com/auth/admin.reports.audit.readonly' scope.

USAGE:
  Set up a service account, download credentials.json, then:
  export GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
  export GWORKSPACE_ADMIN_EMAIL=admin@yourcompany.com
  python gworkspace-join.py --finance finance-export.csv > audit-ready.csv

REQUIREMENTS:
  pip install google-api-python-client google-auth
"""
import argparse
import csv
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from google.oauth2 import service_account
from googleapiclient.discovery import build

LOOKBACK_DAYS = 30
SCOPES = ["https://www.googleapis.com/auth/admin.reports.audit.readonly"]


def get_admin_service():
    """Authenticate with a service account and impersonate a workspace admin."""
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    admin_email = os.environ.get("GWORKSPACE_ADMIN_EMAIL")
    if not creds_path or not admin_email:
        sys.exit("ERROR: set GOOGLE_APPLICATION_CREDENTIALS and GWORKSPACE_ADMIN_EMAIL env vars")

    creds = service_account.Credentials.from_service_account_file(
        creds_path, scopes=SCOPES, subject=admin_email
    )
    return build("admin", "reports_v1", credentials=creds, cache_discovery=False)


def fetch_login_events(service, since: datetime):
    """Fetch login audit events from Google Admin SDK Reports API. Paginates."""
    page_token = None
    while True:
        resp = service.activities().list(
            userKey="all",
            applicationName="login",
            startTime=since.isoformat(),
            maxResults=1000,
            pageToken=page_token,
        ).execute()
        for activity in resp.get("items", []):
            yield activity
        page_token = resp.get("nextPageToken")
        if not page_token:
            break


def count_active_users_per_app(events):
    """Returns {app_name: count_of_unique_users} from login activity events."""
    by_app = defaultdict(set)
    for activity in events:
        actor_email = (activity.get("actor") or {}).get("email")
        if not actor_email:
            continue
        for event in activity.get("events", []):
            # SSO logins to third-party apps include the app name in event params
            if event.get("name") not in ("login_success", "logout"):
                continue
            params = {p["name"]: p.get("value") for p in event.get("parameters", [])}
            app = params.get("oauth_application_name") or params.get("application_name")
            if app:
                by_app[app].add(actor_email)
    return {app: len(users) for app, users in by_app.items()}


def merge_with_finance(active_counts: dict, finance_csv_path: str):
    """Join active-user counts onto the finance CSV."""
    with open(finance_csv_path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames

    app_col = next(
        (c for c in fieldnames if c.lower().strip() in
         ("app_name", "app", "application", "tool", "vendor", "product", "name")),
        None,
    )
    if not app_col:
        sys.exit("ERROR: finance CSV has no recognizable app-name column")

    google_by_lower = {k.lower(): (k, v) for k, v in active_counts.items()}
    matched, unmatched_finance, unmatched_google = 0, [], set(active_counts.keys())

    for row in rows:
        finance_app = (row[app_col] or "").strip()
        match = google_by_lower.get(finance_app.lower())
        if match:
            google_name, count = match
            row["seats_active_30d"] = count
            unmatched_google.discard(google_name)
            matched += 1
        else:
            row["seats_active_30d"] = 0
            unmatched_finance.append(finance_app)

    print(f"[gworkspace-join] matched {matched}/{len(rows)} apps from finance CSV", file=sys.stderr)
    if unmatched_finance:
        print(f"[gworkspace-join] no Google logins found for: {', '.join(unmatched_finance[:10])}"
              f"{'...' if len(unmatched_finance) > 10 else ''}", file=sys.stderr)
        print("[gworkspace-join]   → not using Google OAuth, or app-name mismatch", file=sys.stderr)
    if unmatched_google:
        print(f"[gworkspace-join] Google OAuth apps with no finance row: "
              f"{', '.join(list(unmatched_google)[:10])}"
              f"{'...' if len(unmatched_google) > 10 else ''}", file=sys.stderr)
        print("[gworkspace-join]   → free apps, or shadow IT — review separately", file=sys.stderr)

    return rows, fieldnames + ["seats_active_30d"]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--finance", required=True, help="Path to finance CSV with app inventory")
    parser.add_argument("--output", default="-", help="Output CSV path (default: stdout)")
    args = parser.parse_args()

    since = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    print(f"[gworkspace-join] fetching Google Workspace logins since {since.date()}", file=sys.stderr)

    service = get_admin_service()
    events = list(fetch_login_events(service, since))
    print(f"[gworkspace-join] retrieved {len(events)} login activity records", file=sys.stderr)

    active_counts = count_active_users_per_app(events)
    print(f"[gworkspace-join] {len(active_counts)} unique apps with login activity", file=sys.stderr)

    rows, fieldnames = merge_with_finance(active_counts, args.finance)

    out = sys.stdout if args.output == "-" else open(args.output, "w", newline="")
    writer = csv.DictWriter(out, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    if out is not sys.stdout:
        out.close()
        print(f"[gworkspace-join] wrote {len(rows)} rows to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
