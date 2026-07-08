# ADR-0007 — Degrade loud; persistent state and its minimum contents

Status: Accepted (2026-07-08)

## Context

Feeds age events out while still active (GDACS is capped at 100 rolling records),
delete events silently (USGS), and go down with no uptime guarantee (GDACS). To
detect revisions and silent deletions (ADR-0006) and to never mistake an outage
for calm, the agent needs memory between runs and a loud-degradation discipline.

## Decision

**Degrade loud, never silent.** On any feed problem the report *states* it:

- A feed down at 08:30 → **publish anyway**, with that feed's line in the
  feed-health section flagged red: *"GDACS: UNREACHABLE at 08:30 SGT, last good
  data <ts>."* Never hold the report; never show a partial picture as complete.
- Sections depending on that feed carry a coverage banner ("cyclone/flood coverage
  degraded — GDACS down").
- **Never infer "event ended" from "absent from feed."** Poll and persist.
- Every feed shows its own explicit **"as of <UTC>, N hours ago"**; there is no
  single global freshness timestamp (USGS is seconds old, ReliefWeb days by
  design). Data carried forward from a failed fetch is labelled "carried forward,
  as of <yesterday>" — stale-but-labelled beats fresh-looking-but-wrong.

**Persistent state store.** A local persisted store holds, per cluster:

- the full USGS **`ids`** set (or top-level id changes double-count),
- GDACS `(eventtype, eventid)` + episode chain,
- ReliefWeb numeric `id`, and GLIDE if any,
- **last-published** severity / magnitude / status,
- **last-seen** timestamp and a **was-published** flag.

Without the `ids` set we double-count; without last-published severity we can't
detect escalation; without last-seen + was-published we can't detect a silent
deletion.

## Store: SQLite (decided 2026-07-08)

Resolved during shape detailing (docs/planning/SHAPING.md, Shape A, part A5): **SQLite** via
stdlib `sqlite3` — no dependency, queryable revision history. Chosen over a
committed JSON snapshot (git-visible diffs) because change-detection (ADR-0006)
queries prior state per cluster, which SQL serves cleanly. Revisit only if
git-visible diffs prove more valuable than queryability.

## Consequences

- Ingestion is poll-and-persist, not fetch-and-forget; re-resolution on every run.
- Feed-health is a first-class, always-present report section (ADR-0003 anatomy).
