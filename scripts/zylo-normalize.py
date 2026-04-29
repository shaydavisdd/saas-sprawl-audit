#!/usr/bin/env python3
"""
zylo-normalize.py — Convert a Zylo CSV export to audit-ready format.

USE WHEN:
  Your org has Zylo (or a similar SaaS management platform with a comparable
  export format). Zylo already gathers everything the audit needs — this
  script just renames columns and reformats dates to match the audit tool.

WHAT IT DOES:
  1. Reads a Zylo application export CSV
  2. Maps Zylo's column names to the audit tool's expected columns
  3. Normalizes dates to ISO format (YYYY-MM-DD)
  4. Writes audit-ready output to stdout or a file

NOTES:
  - The audit tool's CSV auto-detection actually handles most of Zylo's
    column variants directly. This script exists as an explicit, version-stable
    bridge — useful if Zylo changes their export format and the audit tool's
    aliases haven't been updated yet.
  - Productiv, BetterCloud, and Torii exports follow similar patterns.
    Adapt the COLUMN_MAP below for those tools.

USAGE:
  python zylo-normalize.py --input zylo-export.csv > audit-ready.csv

REQUIREMENTS:
  Python 3.8+ (standard library only)
"""
import argparse
import csv
import sys
from datetime import datetime

# Map: audit tool column name -> list of Zylo column names to try (in priority order)
COLUMN_MAP = {
    "app_name":          ["Application Name", "Application", "App", "Vendor"],
    "category":          ["Category", "Function", "Tag"],
    "annual_cost":       ["Annual Spend", "Annual Cost", "Total Annual Cost", "Spend (USD)"],
    "seats_purchased":   ["Licenses", "Total Licenses", "License Count", "Provisioned Seats"],
    "seats_active_30d":  ["Active Users (30d)", "MAU", "Monthly Active Users", "Active Users"],
    "renewal_date":      ["Renewal Date", "Contract End Date", "Next Renewal", "Expiration"],
    "owner":             ["Business Owner", "Owner", "Department", "Cost Center"],
}

OUTPUT_COLUMNS = list(COLUMN_MAP.keys())


def find_source_column(target_field: str, headers: list) -> str:
    """Find the first matching Zylo column for an audit field. Case-insensitive."""
    headers_lower = {h.lower().strip(): h for h in headers}
    for candidate in COLUMN_MAP[target_field]:
        if candidate.lower() in headers_lower:
            return headers_lower[candidate.lower()]
    return None


def normalize_date(value: str) -> str:
    """Convert various date formats to ISO YYYY-MM-DD. Returns empty string on failure."""
    if not value or not value.strip():
        return ""
    value = value.strip()
    formats = ["%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%d/%m/%Y", "%B %d, %Y", "%b %d %Y"]
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return value  # leave as-is if no format matched; audit tool will skip invalid dates


def normalize_cost(value: str) -> str:
    """Strip currency symbols, commas, spaces. Leaves the cleaned numeric string."""
    if not value:
        return "0"
    cleaned = str(value).replace("$", "").replace(",", "").replace(" ", "").strip()
    return cleaned or "0"


def normalize(input_path: str, output_path: str):
    with open(input_path, newline="") as f:
        reader = csv.DictReader(f)
        zylo_headers = reader.fieldnames
        zylo_rows = list(reader)

    # Resolve the Zylo column for each audit field
    column_resolution = {}
    missing = []
    for audit_field in OUTPUT_COLUMNS:
        source = find_source_column(audit_field, zylo_headers)
        column_resolution[audit_field] = source
        if not source:
            missing.append(audit_field)

    if missing:
        print(f"[zylo-normalize] WARNING: no source column found for: {', '.join(missing)}",
              file=sys.stderr)
        print("[zylo-normalize]   → these fields will be empty in the output", file=sys.stderr)
        print("[zylo-normalize]   → check your Zylo export options or extend COLUMN_MAP",
              file=sys.stderr)

    out = sys.stdout if output_path == "-" else open(output_path, "w", newline="")
    writer = csv.DictWriter(out, fieldnames=OUTPUT_COLUMNS)
    writer.writeheader()

    written = 0
    for row in zylo_rows:
        out_row = {}
        for audit_field, zylo_col in column_resolution.items():
            raw = row.get(zylo_col, "") if zylo_col else ""
            if audit_field == "renewal_date":
                out_row[audit_field] = normalize_date(raw)
            elif audit_field == "annual_cost":
                out_row[audit_field] = normalize_cost(raw)
            else:
                out_row[audit_field] = (raw or "").strip()

        # Skip rows with no app name or zero cost — they aren't useful in the audit
        if out_row["app_name"] and out_row["annual_cost"] not in ("0", ""):
            writer.writerow(out_row)
            written += 1

    if out is not sys.stdout:
        out.close()
    print(f"[zylo-normalize] wrote {written}/{len(zylo_rows)} rows to "
          f"{'stdout' if output_path == '-' else output_path}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", required=True, help="Path to Zylo CSV export")
    parser.add_argument("--output", default="-", help="Output CSV path (default: stdout)")
    args = parser.parse_args()
    normalize(args.input, args.output)


if __name__ == "__main__":
    main()
