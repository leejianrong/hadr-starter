# ADR-0009 — Publish preliminary-and-labelled; corrections are explicit

Status: Accepted (2026-07-08)

## Context

Everything a feed reports can change or vanish (blindspot #7): USGS `status` goes
`automatic` → `reviewed`; magnitude/location shift on review hours-to-days later;
events are deleted outright (the Dec-2025 false Reno M5.9), and in a summary feed a
deleted event simply disappears on the next poll. A morning sitrep cannot wait for
`reviewed` status — the first 24h is exactly when decisions get made — but it also
must not present an automatic solution as fact.

## Decision

- **Publish preliminary-and-labelled, correct later.** Publish the automatic
  solution, tag it **"preliminary (automatic)"**, carry its status, and re-resolve
  on later runs. If numbers move materially, issue a correction (the loud triggers
  in ADR-0006 decide "materially").
- **Corrections are explicit, never silent.** A previously-published event that is
  downgraded or deleted gets a visible **`CORRECTED`** line — the reader briefed
  their principal on it yesterday and needs to walk it back. A silent disappearance
  is the cardinal sin. (This is why persisted state must remember what we published
  — ADR-0007 — since the feed won't surface the retraction itself.)
- **The reader forgives a false positive over a miss** — tune toward inclusion at
  the margins — *provided* every false positive is loudly corrected. An
  uncorrected false positive erodes trust badly.
- **The renderer refuses a bare casualty integer** — a number renders only wrapped
  in its source, its range language, and its preliminary flag (ties to ADR-0002).

## Consequences

- The report distinguishes `preliminary (automatic)` from `reviewed`, and carries
  `NEW` / `REVISED ↑` / `CORRECTED` change-flags (breadboard U2.1 / U6).
- Requires persisted last-published state (ADR-0007) and the change-detector
  (ADR-0006) to detect the revisions and deletions this ADR promises to surface.

## Alternatives rejected

- **Wait for `reviewed` status before publishing** — defeats a *morning* sitrep;
  the decision window has passed by the time review lands.
- **Silently drop or overwrite a corrected event** — the reader already acted on
  yesterday's figure; a silent change is undetectable and untrustworthy.
