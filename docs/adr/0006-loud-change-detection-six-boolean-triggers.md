# ADR-0006 — Loud-change detection = six deterministic boolean triggers

Status: Accepted (2026-07-08)

## Context

Per ADR-0005 the model wakes only on a "loud" change. "Loud" must be decidable by
deterministic code (CLAUDE.md #1) comparing the current poll against persisted
last-published state (ADR-0007) — no model in the decision.

## Decision

An event is **loud** if **any** row fires. All are boolean comparisons against
persisted state; none needs a model.

1. **New attention-worthy event** — `cluster_key ∉ state AND passes_threshold`
   (ADR-0004).
2. **Severity escalation (upward)** — `new_alert_rank > last_published_rank`
   (green<yellow<orange<red). A within-colour wobble is quiet. **Downward** is
   also loud **if the cluster was previously shown at orange+** (the reader needs
   the walk-back — see row 5).
3. **Magnitude/location review** on a *shown* event — `|Δmag| ≥ 0.3` (mww-family)
   OR epicentre moved `≥ 50 km` OR depth reclassified across the ≤70 km ↔ >70 km
   boundary. Below those thresholds is noise ⇒ quiet.
4. **Status automatic→reviewed** on a *shown* event —
   `last_status == "automatic" AND new_status == "reviewed"`.
5. **Deletion / retraction** — `cluster_key ∈ state AND was_published AND
   absent_from_current_feed AND feed_fetch_succeeded`. The **`feed_fetch_succeeded`
   guard is critical** — never fire a retraction off a failed fetch, or an outage
   manufactures false deletions. (This is the Dec-2025 Reno M5.9 false-solution
   case, which vanishes silently on next poll.)
6. **Slow-onset status change** — ReliefWeb `status` transition `alert→current`,
   `current→past`, a new disaster appearing at `alert`/`current`, or a tracked
   disaster dropping off (same fetch-succeeded guard). In RSS-only mode `status`
   is unavailable ⇒ proxy on GLIDE appearance/disappearance and flag "status
   unavailable (RSS mode)."

## Consequences

- The tunable constants (`0.3` M, `50` km, and whether downward escalation wakes
  the model) are **named constants in `scripts/`** — one-line, model-free tuning.
- Everything else is a hard boolean, not a judgement call.

## Alternatives rejected

- **Let the model decide "is this worth reporting"** — non-deterministic, costs a
  call on every quiet morning, violates CLAUDE.md #1.
