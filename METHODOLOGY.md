# Methodology

This document explains the thresholds, scoring formulas, and judgment calls behind the dashboard. The goal is transparency: an IT Director should be able to defend any number this tool surfaces, and that requires knowing how it was calculated.

## Idle license detection

**Threshold: ≥30% of purchased seats unused in the last 30 days.**

The 30% figure is calibrated against industry benchmarks. Public data from Zylo, Productiv, and Tangoe shows mid-market organizations typically have 20–30% of SaaS licenses unused. Setting the flag at 30% means the tool surfaces apps that are *meaningfully* underused relative to the baseline, not apps that match the industry average.

**Why 30 days, not 7 or 90.** A 7-day window catches vacation-distorted noise. A 90-day window misses recently-onboarded seats that haven't activated yet. 30 days matches the cadence most SaaS billing reports use, which keeps the analysis aligned with the data Directors already see in their finance reviews.

**Minimum seat threshold: 10 seats.** Apps with fewer than 10 seats are excluded from idle analysis. The recoverable dollars are too small to matter at the portfolio level, and the noise (one departing employee = 100% waste flag on a 1-seat tool) creates false positives that erode trust in the dashboard.

**Recovery formula:**
```
recoverable = (seats_purchased - seats_active_30d) × (annual_cost ÷ seats_purchased)
```

This calculates recovery as if every idle seat were cut at the current per-seat list price. This is a **ceiling estimate**. Actual recovery depends on:
- Vendor flexibility on mid-term seat reductions (most won't credit you, only let you adjust at renewal)
- Volume discount tiers that may break if seat counts drop below thresholds
- Multi-year commits that lock seat counts regardless of usage

The tool does not attempt to model these. The number is intended for prioritization, not bid preparation.

## Redundancy detection

**Logic: apps grouped by category. Within each category, the highest-utilized app is the "winner." Other apps in the same category with utilization below 50% are flagged as consolidation candidates.**

**Why category-based grouping.** Functional overlap is the hard signal for redundancy. Two project management tools with 80% utilization each are probably both serving distinct workflows that don't easily merge. One project management tool at 80% and another at 30% is a clearer consolidation case — the 30% tool's users likely have an alternative they prefer.

**Why 50% utilization for the candidate threshold.** Below 50%, the cost-per-active-user starts to look bad regardless of the headline price. Above 50%, the migration cost (training, workflow disruption, integration rebuild) often exceeds the consolidation savings.

**Limitations of this logic:**
- **Categories are inherited from the input CSV.** If a user mislabels Notion as "Project Management" instead of "Documentation," it gets compared against Jira and Asana. Garbage in, garbage out.
- **The tool doesn't see workflow-level overlap.** Two CRMs might both be "active" but serve completely different customer segments. The tool would still flag the lower-utilized one as a candidate. A human review is required before acting on the recommendation.
- **The "winner" is highest utilization, not best fit.** The tool optimizes for spend efficiency, not capability. A Director might rationally keep the lower-utilized tool if it has features the winner lacks.

**Consolidation savings formula:**
```
savings = sum of annual_cost for all sunset candidates in the group
```

This assumes a clean migration with full sunset of the candidate apps. Partial migrations, dual-running periods, and per-seat add-on costs at the winner are not modeled.

## Priority action ranking (the Director's queue)

The Director's queue is the most opinionated part of the tool. It surfaces the top 5 actions by `recovery ÷ effort`.

**Effort scale (1–5 dots):**

| Effort | Description | Example |
|---|---|---|
| 1 | Single-vendor seat reduction at next renewal | Cut 18 idle Auth0 seats |
| 2 | Large seat reduction with potential vendor pushback | Cut 200+ idle seats from a Tier-1 vendor |
| 3 | Single-app sunset with one migration target | Sunset HelloSign → DocuSign |
| 4 | Multi-app sunset within a category | Sunset Mode + Tableau → Looker |
| 5 | Cross-category consolidation requiring org change | Reserved for use cases not yet auto-detected |

The effort scale is heuristic, not survey-validated. It exists to differentiate "easy win" actions from "fight worth picking" actions in the ranking, not to predict project hours.

**Deduplication rule: sunset dominates right-size on the same app.**

If New Relic shows up as both an idle-license candidate (right-size: cut seats) and a redundancy candidate (sunset: migrate to Datadog), only the sunset action appears in the queue. Right-sizing a tool you're about to kill is wasted effort.

**Why not rank by raw recovery.** A $200K consolidation that requires a 90-day cross-team migration is often a worse Q1 priority than three $30K seat reductions that close in two weeks. Raw-dollar ranking would push the consolidation to the top and obscure the easier wins. Effort-weighted ranking surfaces the wins a Director can actually execute against in a single quarter.

## Renewal queue

**Window: next 180 days.** Six months gives enough lead time for seat-reduction conversations with vendor account executives. Most enterprise SaaS contracts require 60–90 day notice for non-renewal or material change. Shorter windows would surface renewals already past the negotiation deadline.

**Sort order: descending by negotiating leverage, where leverage = idle seats × cost per seat.**

The intuition: vendors are most flexible when you can credibly threaten to walk or cut significant seat count. An app at 50% utilization with a renewal in 60 days and $40K in idle spend has more leverage than a 95%-utilized app with $80K in idle spend, because the former is a credible right-size negotiation and the latter is a "we'll renew at terms" conversation.

**Posture recommendations:**
- ≥50% idle: "Negotiate hard" — strong leverage to cut seats, switch vendors, or walk
- 25–50% idle: "Right-size" — push for seat reduction without threatening the relationship
- <25% idle: "Standard" — renew at terms, focus negotiating capital elsewhere

These thresholds are heuristic. Specific vendor relationships, contract structures, and competitive landscapes will move the actual posture in either direction.

## CSV column auto-detection

The tool normalizes column names (lowercase, strip non-alphanumerics) and matches against a list of aliases per field. This is intentionally generous — `Application`, `app_name`, `App Name`, `APP-NAME`, and `Application Name` all map to the same field.

**Failure mode: ambiguous columns.** If a CSV has two columns that both match an alias list (e.g., both `cost` and `annual_cost`), the first match wins. This can produce silently wrong numbers if a CSV has both monthly and annual cost columns. The tool does not currently warn about this. **Users with non-standard exports should sanity-check the headline number against their finance system before treating any individual recommendation as actionable.**

## What this tool intentionally treats as out of scope

These are not bugs. They are scope choices the project committed to up front. Re-introducing any of them changes the tool's buyer and weakens its primary use case.

- **Shadow IT discovery** — different problem (security posture), different buyer (CISO).
- **Identity and access governance** — different problem (who has access), different buyer (Security/IT Ops).
- **Automated remediation actions** — different product category (SaaS management platforms).
- **Consumption-based pricing models** — different analysis layer required for API/storage/MAU pricing.
- **Vendor management workflows** — contract storage, negotiation history, vendor scoring all live in procurement systems, not audit tools.
- **Per-user attribution** — the tool aggregates at the app level. Per-user activity analysis is in IGA tools.

If a user needs any of these, they need a different tool, not a bigger version of this one.
