# QUESTIONS — grilling log

Scratch file for the grill step. Questions posed to the stakeholder (persona:
**Maya**, OCHA sitrep veteran), grouped by theme. All answered 2026-07-08 and
folded into `CONTEXT.md` and `docs/adr/*.md`.

Legend: ☐ open · ☑ answered · ⚑ was a contradiction, now resolved

---

## 1. Terms & the core object

- ☑ Q1.1 "An event" = **resolved cross-feed cluster**, not a rupture or a raw
  alert. → CONTEXT "Core terms", ADR-0001.
- ☑ Q1.2 The sitrep is a **full standing report regenerated daily**, with a
  delta flag (NEW/REVISED) on changed items. → CONTEXT, ADR-0005.
- ☑ Q1.3 "Quiet" = no new attention-worthy event AND no decision-changing
  revision (not new-events-only). Threshold enumerated in ADR-0006.
- ☑ Q1.4 Floor: **anything curated onto ReliefWeb always shows**, plus every
  active slow-onset crisis stays visible. → ADR-0004, ADR-0003.

## 2. The report itself

- ☑ Q2.1 Line order: colour · what/where · impact+source · magnitude · as-of ·
  change-flag. Eye lands on colour+place. → CONTEXT "Report anatomy".
- ☑ Q2.2 Four fixed sections: sudden-onset / slow-onset / feed-health /
  nothing-to-report. → CONTEXT, ADR-0003, ADR-0007.
- ☑ Q2.3 Ranges shown as ranges; renderer refuses a bare casualty integer.
  → ADR-0002, CONTEXT "Trust rules".
- ☑ Q2.4 Disagreeing figures shown **stacked and attributed**, never merged.
  → ADR-0008.
- ☑ Q2.5 ⚑ No-news report **still published** (silence = failure); reconciled
  with "stay quiet" via ADR-0005 (see FU1 below).

## 3. Severity & filtering

- ☑ Q3.1 "Meaningful exposure" anchored at **~1,000 exposed to MMI VI+**;
  slice-1 fallback proxy since PAGER is null <M5.5. → ADR-0004 (see FU2).
- ☑ Q3.2 "Reached ReliefWeb" **overrides** the 24h window → ongoing section.
  → ADR-0003, ADR-0004.
- ☑ Q3.3 Show mainshock headline + count + largest aftershock; name true swarms.
  → CONTEXT (declustering), PRD.

## 4. Change, revision, and trust

- ☑ Q4.1 Downgrade/deletion → **explicit correction**, never a silent drop.
  → ADR-0006 row 5, ADR-0009.
- ☑ Q4.2 **Publish preliminary-and-labelled, correct later.** → CONTEXT, ADR-0006 row 4.
- ☑ Q4.3 Reader **forgives a false positive over a miss** (given loud
  corrections). → ADR-0004 consequences.

## 5. Failure & degradation

- ☑ Q5.1 Feed down → publish anyway, feed-health red, coverage banner. → ADR-0007.
- ☑ Q5.2 RSS-only keeps the "reached ReliefWeb" floor; missing status/type/iso3/
  date.event/pagination flagged loud. → ADR-0008.
- ☑ Q5.3 Per-feed "as of" time; carried-forward data labelled. → ADR-0007.

## 6. State & cadence

- ☑ Q6.1 Local persisted store; minimum = ids set + GDACS key/episode + RW id +
  GLIDE + last-published severity/mag/status + last-seen + was-published.
  Store = **SQLite** (decided during shaping). → ADR-0007.
- ☑ Q6.2 Slow-onset (null event_time) **exempt** from window; ongoing section.
  → ADR-0003.

## 7. Scope pressure

- ☑ Q7.1 Irreducible core = **USGS EQ end-to-end with declustering, impact
  severity, loud feed-health, persisted state catching revisions/deletions.**
  → ADR-0004, README slice.
- ☑ Q7.2 Refuse: **recomputing severity ourselves** (ADR-0002) and **real-time
  sub-daily alerting**. → REQS out-of-scope, ADR-0002.

---

## Follow-ups (round 2)

- ☑ ⚑ FU1 — "stay quiet" vs "always publish" reconciled: deterministic layer
  **always regenerates the page** (timestamp = heartbeat); "quiet" = model asleep,
  no ping. Open owner-decision: a daily all-clear ping (recommended yes).
  → ADR-0005.
- ☑ FU2 — Honest USGS-only slice-1 threshold: PAGER tier-1 + a
  magnitude/depth/onshore tier-2 fallback + `sig≥600` supplement; states loudly
  what it misses. → ADR-0004.
- ☑ FU3 — Six deterministic "loud" triggers with tunable constants in `scripts/`.
  → ADR-0006.

## Still-open owner-decisions (surfaced, not blocking the PRD)

- **Daily all-clear ping** on quiet mornings, yes/no (ADR-0005). Recommend yes.
- Final numeric constants for the thresholds (ADR-0004) and loud triggers
  (ADR-0006) — defaults recommended, owner tunes in `scripts/`.
- Request the ReliefWeb **appname** now (external action, ADR-0008).

*(Resolved during shaping: state store = **SQLite**, ADR-0007.)*
