#!/usr/bin/env python3
"""
okta-join.py — Build an audit-ready CSV from Okta SSO logs + finance export.

USE WHEN:
  Your org uses Okta as the identity provider and you can export SaaS spend
  data from your finance/procurement system (or maintain it manually).

WHAT IT DOES:
  1. Fetches Okta sign-in events for the last 30 days via the Okta System Log API
  2. Counts unique users per app (the "active seats" the audit tool needs)
  3. Joins with a finance CSV that has app name, annual cost, seats purchased,
     renewal date, owner, and category
  4. Writes audit-ready output to stdout or a file

LIMITATIONS:
  - Apps not behind Okta SSO are invisible. This is by design — same scope
    boundary as the audit tool itself. Shadow IT discovery is a different problem.
  - The Okta app name has to match the finance CSV app name. Mismatches are
    logged to stderr so you can fix them in your finance CSV.
  - Free-tier Okta API rate limits (600 requests/min) are fine for orgs under
    ~5,000 employees. Larger orgs need to paginate more carefully.

USAGE:
  export OKTA_DOMAIN="your-org.okta.com"
  export OKTA_API_TOKEN="00xxx..."
  python okta-join.py --finance finance-export.csv > audit-ready.csv

REQUIREMENTS:
  pip install requests
"""
import argparse
import csv
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests

OKTA_DOMAIN = os.environ.get("OKTA_DOMAIN")
OKTA_API_TOKEN = os.environ.get("OKTA_API_TOKEN")
LOOKBACK_DAYS = 30


def fetch_signin_events(since: datetime):
    """Fetch Okta sign-in events since the given datetime. Paginates."""
    if not OKTA_DOMAIN or not OKTA_API_TOKEN:
        sys.exit("ERROR: set OKTA_DOMAIN and OKTA_API_TOKEN env vars")

    url = f"https://{OKTA_DOMAIN}/api/v1/logs"
    headers = {"Authorization": f"SSWS {OKTA_API_TOKEN}", "Accept": "application/json"}
    params = {
        "since": since.isoformat(),
        "filter": 'eventType eq "user.authentication.sso"',
        "limit": 1000,
    }

    while url:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        for event in resp.json():
            yield event
        # Okta paginates via Link headers
        next_link = None
        for link in resp.headers.get("Link", "").split(","):
            if 'rel="next"' in link:
                next_link = link.split(";")[0].strip("<> ")
        url = next_link
        params = None  # subsequent requests use the full URL with embedded params


def count_active_users_per_app(events):
    """Returns {app_name: set_of_user_ids} from sign-in events."""
    by_app = defaultdict(set)
    for e in events:
        # Okta SSO event: target[0] is the app, actor is the user
        targets = e.get("target") or []
        app = next((t.get("displayName") for t in targets if t.get("type") == "AppInstance"), None)
        user_id = (e.get("actor") or {}).get("id")
        if app and user_id:
            by_app[app].add(user_id)
    return {app: len(users) for app, users in by_app.items()}


def merge_with_finance(active_counts: dict, finance_csv_path: str):
    """Join active-user counts onto the finance CSV. Logs unmatched apps to stderr."""
    with open(finance_csv_path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames

    # Auto-detect the app name column in the finance CSV
    app_col = next(
        (c for c in fieldnames if c.lower().strip() in
         ("app_name", "app", "application", "tool", "vendor", "product", "name")),
        None,
    )
    if not app_col:
        sys.exit("ERROR: finance CSV has no recognizable app-name column")

    # Build a case-insensitive lookup so 'slack' matches 'Slack'
    okta_by_lower = {k.lower(): (k, v) for k, v in active_counts.items()}
    matched, unmatched_finance, unmatched_okta = 0, [], set(active_counts.keys())

    for row in rows:
        finance_app = (row[app_col] or "").strip()
        match = okta_by_lower.get(finance_app.lower())
        if match:
            okta_name, count = match
            row["seats_active_30d"] = count
            unmatched_okta.discard(okta_name)
            matched += 1
        else:
            row["seats_active_30d"] = 0
            unmatched_finance.append(finance_app)

    # Diagnostics — important for the user to see
    print(f"[okta-join] matched {matched}/{len(rows)} apps from finance CSV", file=sys.stderr)
    if unmatched_finance:
        print(f"[okta-join] no Okta sign-ins found for: {', '.join(unmatched_finance[:10])}"
              f"{'...' if len(unmatched_finance) > 10 else ''}", file=sys.stderr)
        print("[okta-join]   → likely not behind SSO, or app-name mismatch in finance CSV",
              file=sys.stderr)
    if unmatched_okta:
        print(f"[okta-join] Okta apps with no finance row: {', '.join(list(unmatched_okta)[:10])}"
              f"{'...' if len(unmatched_okta) > 10 else ''}", file=sys.stderr)
        print("[okta-join]   → free apps, or apps missing from your finance inventory",
              file=sys.stderr)

    return rows, fieldnames + ["seats_active_30d"]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--finance", required=True, help="Path to finance CSV with app inventory")
    parser.add_argument("--output", default="-", help="Output CSV path (default: stdout)")
    args = parser.parse_args()

    since = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    print(f"[okta-join] fetching Okta sign-ins since {since.date()}", file=sys.stderr)

    events = list(fetch_signin_events(since))
    print(f"[okta-join] retrieved {len(events)} sign-in events", file=sys.stderr)

    active_counts = count_active_users_per_app(events)
    print(f"[okta-join] {len(active_counts)} unique apps with sign-in activity", file=sys.stderr)

    rows, fieldnames = merge_with_finance(active_counts, args.finance)

    out = sys.stdout if args.output == "-" else open(args.output, "w", newline="")
    writer = csv.DictWriter(out, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    if out is not sys.stdout:
        out.close()
        print(f"[okta-join] wrote {len(rows)} rows to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
