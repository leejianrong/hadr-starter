# ADR-0008 — Carry provenance, never sum feeds; RSS-first with API drop-in

Status: Accepted (2026-07-08)

## Context

The feeds report different quantities of the same reality — "affected" ≠
"displaced" ≠ "killed" ≠ "in need" — and a PAGER modelled estimate and a
government count via ReliefWeb are two measurements, not two addends. Separately,
ReliefWeb's API needs a pre-approved `appname` (Google Form, email, no SLA, since
1 Nov 2025) that may not land this week.

## Decision

**Provenance & no summing.**

- Every figure carries its source and is **never summed across feeds**.
- Disagreeing estimates are shown **stacked and attributed** under the same event:
  *"PAGER (modelled): orange, economic-driven / Govt of X via ReliefWeb: 120
  confirmed dead."* Never a merged number, never a delta, never one struck
  through. The reader holds two figures; they cannot un-see a false sum.

**RSS-first, API as a drop-in upgrade.**

- Build ReliefWeb (and GDACS) ingestion against **RSS first**; design so the API
  is a drop-in. Request the ReliefWeb `appname` **now** (external action, tracked
  in `implementation-notes.md`).
- On RSS alone we still get a curated disaster's existence, title, GLIDE (category
  tag), countries, pubDate — enough to fire the "reached ReliefWeb" floor.
- **Visibly missing on RSS**, and flagged on the report: `status`
  (alert/current/past), `type`, structured `iso3`, `date.event`, and pagination
  (RSS shows only the latest ~20 unpaginated — a burst can be silently dropped).
  The report must say *"ReliefWeb: RSS mode, no API — status and full backfill
  unavailable"* so the gap is loud (ADR-0007), not silent.

## Consequences

- Ingestion layer is source-agnostic behind a small adapter; API swaps in per feed.
- Slice 1 (USGS-only) is unaffected by ReliefWeb approval timing — deliberate
  de-risking (ADR-0004).

## Alternatives rejected

- **Block on API approval** — no SLA; would stall the week. RSS-first unblocks.
- **Merge/deduplicate casualty figures into one number** — fabricates precision
  and destroys attribution.
