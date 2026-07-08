---
shaping: true
---

# Spike (A3 / R3): cross-feed cluster confidence score

Resolves the flag on Shape A part **A3** — turning the "GLIDE-then-tolerance-box"
join (ADR-0001) into a concrete, deterministic **confidence** the report can act
on. Does **not** block slice 1 (single-feed = declustering only); needed before
GDACS/ReliefWeb join.

## Context

The resolved entity is a cross-feed cluster (ADR-0001): many USGS events + one
GDACS chain + one ReliefWeb disaster. We must decide *how sure* we are that two
records are the same event, deterministically (CLAUDE.md #1), and what the report
does at each confidence level. A fuzzy weighted sum is hard to defend and tune; we
want a rule ladder with named constants in `scripts/`.

## Goal

Describe a deterministic function `confidence(record_a, record_b) -> level` and the
report behaviour per level, plus the key domain shortcut for earthquakes.

## Questions

| # | Question |
|---|----------|
| A3-Q1 | What inputs are available to join on, per feed pair? |
| A3-Q2 | Is the earthquake case actually probabilistic, or definitional? |
| A3-Q3 | What tolerance dimensions and thresholds define a match when GLIDE is absent? |
| A3-Q4 | Should confidence be a float or a labelled ladder? |
| A3-Q5 | What does the report do at each level (esp. low confidence)? |

## Findings

- **A3-Q1 — Join inputs:** GLIDE (USGS: none; GDACS: ~2%; ReliefWeb: in a category
  tag) — high-precision, low-recall. Else: lat/lon, event time (UTC), magnitude
  (USGS/GDACS), country/ISO3, and — critically — GDACS EQ carries `source` and the
  embedded USGS id.
- **A3-Q2 — Earthquakes are definitional, not probabilistic.** GDACS EQ alerts are
  *built from* USGS/NEIC (blindspot #2, ADR-0002). So a GDACS-EQ↔USGS join is an
  identity link — match on GDACS `source == "NEIC"` + the embedded USGS id — **not**
  a fuzzy space/time guess, and it must **not** count as independent corroboration.
  The tolerance box is really for ReliefWeb (human page, days later) and for
  non-EQ hazards.
- **A3-Q3 — Tolerance box (when GLIDE absent, non-identity):** three dimensions
  with two tiers of named constants:
  - space: tight ≤ 50 km, loose ≤ 100 km;
  - time: tight ≤ 2 min, loose ≤ 60 min (ReliefWeb: same GLIDE-day, since it's
    days-latent);
  - magnitude: tight ≤ 0.3 M, loose ≤ 1.0 M (mww-family only — types aren't
    comparable). ISO3 must not *disqualify* (offshore = no country; border spans).
- **A3-Q4 — Ladder, not a float.** A deterministic **rule ladder** yields a label
  (and a coarse bucket for storage):
  - **`certain`** — exact GLIDE match, OR the EQ identity link (A3-Q2).
  - **`high`** — all three dims within *tight* tolerance.
  - **`medium`** — all three within *loose* tolerance.
  - **`low`** — only 1–2 dims match, or ISO3+date only.
  A ladder is defensible, testable, and tunable (constants in `scripts/`); a
  weighted float invites bikeshedding and hides the reason for a merge.
- **A3-Q5 — Report behaviour per level:**
  - `certain`/`high` → **merge** into one cluster line silently.
  - `medium` → merge but label *"likely the same event"* and show the confidence.
  - `low` → **do not merge**; keep separate and **cross-link** *"possibly
    related"*. Never silently merge a low-confidence pair — a wrong merge hides an
    event, which the reader forgives least (ADR-0004 / Maya's miss-vs-false-positive
    rule).

## Recommendation

Implement `scripts/cluster.py::confidence(a, b) -> {"certain","high","medium","low"}`
as the rule ladder above, with the EQ identity link checked first and GLIDE second,
constants named at module top. Renderer maps level → merge/label/cross-link per
A3-Q5. Slice 1 uses only the declustering half of A3 (single feed); this join
logic lands with the second feed.

**A3 flag → resolved.**

## Acceptance

Complete: we can describe the deterministic confidence ladder, the earthquake
identity shortcut, the tolerance constants, and the per-level report behaviour.
