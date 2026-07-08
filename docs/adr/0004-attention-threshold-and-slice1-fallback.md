# ADR-0004 — Attention threshold, and the honest USGS-only slice-1 fallback

Status: Accepted (2026-07-08)

## Context

"Filter noise" is not an instruction a machine can execute. We need a stated
threshold. But the locked first slice is USGS-only, and PAGER `alert` is **null
below ~M5.5** with **no exposure count** in the feed — so the impact ladder
barely bites on slice 1. The threshold must be honest about that.

## Decision

**General threshold (all feeds):** an item is attention-worthy if **any** holds —

1. PAGER/GDACS severity **≥ orange**;
2. **yellow with meaningful population exposure** — recommended concrete anchor:
   **≥ ~1,000 people exposed to MMI VI (strong) shaking or worse**, OR a
   non-trivial upper tail on the fatality/economic range;
3. **anything a human curated onto ReliefWeb** (window-independent — see below).

Branch 3 is the free, high-quality signal that catches floods, epidemics, and
conflict the numeric ladders miss; a curated ReliefWeb disaster **overrides the
24h window** and appears in the ongoing section even if curated days ago.

**Slice-1 fallback (USGS-only), fully deterministic:**

- **Tier 1 (when present):** rank by PAGER `alert`; show orange/red always, yellow
  shown. (A small minority of records.)
- **Tier 2 (the `alert:null` majority):** show when **mww/mw-family M ≥ 6.0
  anywhere**, OR **M ≥ 5.0 with depth ≤ 70 km AND epicentre onshore / within
  ~100 km of a populated landmass**. Use **`sig ≥ 600`** (significant-feed
  membership) as an *additional* include, not the primary gate.
- **Magnitude-type guard:** only `mww`/`mw`-family readings trip the gate
  (`mb 6.0` ≠ `mww 6.0`).

All thresholds are **named constants in `scripts/`**; a model never decides an
alert level (CLAUDE.md #1). The recommended numbers are defaults; the owner sets
finals with a one-line, model-free change.

## Consequences — stated loudly on the dashboard

Slice 1 **will miss** a shallow moderate quake under a poor dense city that PAGER
hasn't scored (the exact case exposure modelling exists for, which USGS can't give
us), and **over-includes** harmless deep-ocean large quakes (the forgivable error
— the reader forgives a false positive over a miss). By construction it covers
**no** floods, cyclones, epidemics, or conflict. The dashboard carries the banner:
*"Coverage: earthquakes only (USGS). No flood/cyclone/epidemic/conflict monitoring
yet."* Silence about a blindspot is itself a blindspot.

## Alternatives rejected

- **`sig` as the primary gate** — opaque (folds in felt reports); supplements, not replaces.
- **Magnitude-only threshold** — reintroduces the magnitude≠severity error (ADR-0002).
