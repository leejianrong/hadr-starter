---
shaping: true
---

# Spike (A4 / R2): offline reverse-geocode + onshore test

Resolves the flag on Shape A part **A4** — the "onshore / near a populated
landmass" branch of the slice-1 attention threshold (ADR-0004), and the ISO3
reverse-geocode that blindspot #10 requires ("USGS gives you only lat/lon — you
reverse-geocode to ISO3 yourself").

## Context

USGS gives only `[lon, lat, depth]`. The slice-1 tier-2 rule (ADR-0004) needs, for
an `alert:null` quake: `M ≥ 5.0 AND depth ≤ 70 km AND epicentre onshore / within
~100 km of a populated landmass`. Two capabilities are actually needed and they
are the **same mechanism**:

1. **point → ISO3** (country normalization; nullable + a list for border cases),
2. **point → onshore?** (inside any country polygon).

Constraint: CLAUDE.md is stdlib-first — "add a dependency only when it earns its
place" — and tests run **offline** on fixtures, so no network call at runtime.

## Goal

Identify a concrete, deterministic, offline mechanism (and its data asset) for
point→ISO3 and onshore, with a dependency footprint we can defend.

## Questions

| # | Question |
|---|----------|
| A4-Q1 | What offline data gives country polygons at a small file size and a licence we can vendor into the repo? |
| A4-Q2 | Can point-in-polygon be done without a C-extension dependency (stdlib-first)? |
| A4-Q3 | How do we handle the nullable + list cases (offshore = none; border = several)? |
| A4-Q4 | What's the honest, cheap approximation of "within ~100 km of a populated landmass" for slice 1? |
| A4-Q5 | Do we need a heavier library (`shapely`, `geopandas`, `reverse_geocoder`)? |

## Findings

- **A4-Q1 — Data:** **Natural Earth Admin-0 countries** (public domain, no
  attribution required) ships as GeoJSON at 1:110m / 1:50m / 1:10m. The 1:110m
  layer is small (~hundreds of KB) and carries an `ISO_A3` property per feature —
  exactly point→ISO3. Vendor the GeoJSON into the repo (it is *data*, not a code
  dependency, so it doesn't violate stdlib-first). *Verify during implementation:*
  exact file size and that `ISO_A3` is populated for the politically-loaded
  entities we care about (some are `-99` in Natural Earth — patch a small
  override table for those, per blindspot #10).
- **A4-Q2 — Point-in-polygon:** the **ray-casting** algorithm is ~20 lines of pure
  Python over the GeoJSON coordinate rings (handle `Polygon` and `MultiPolygon`,
  and holes). No `shapely`/GEOS needed. Deterministic and easily unit-tested with
  fixture coordinates. Good enough at 1:110m; bump to 1:50m only if border
  precision demands it.
- **A4-Q3 — Nullable + list:** if the point is inside **no** polygon → `ISO3 =
  None` and `onshore = False` (offshore quake — may still be tsunamigenic; keep the
  event, per blindspot #10). If inside **one** → single ISO3. Near a border, test a
  small tolerance and allow **multiple** ISO3 (country is a list, per R0/CONTEXT).
- **A4-Q4 — "within ~100 km" approximation:** for **slice 1, define onshore ==
  inside a country polygon** and treat that as the populated-landmass proxy. This
  is honest and cheap; the full "within 100 km of a *populated place*" refinement
  (great-circle distance to nearest Natural Earth `populated_places` point, or a
  coast buffer) is a **v2 refinement**, not slice-1 blocking. State this limitation
  on the dashboard (consistent with ADR-0004's "loud about the blindspot").
- **A4-Q5 — Heavier libs:** **not needed, and not worth their place.**
  `reverse_geocoder` is offline but pulls `numpy`+`scipy` (k-d tree); `shapely`
  needs the GEOS C-extension; `geopandas` is heavier still. The vendored-GeoJSON +
  ray-casting approach has **zero runtime dependency** and serves both needs.
  Cross-check (free, no data): USGS `place` ("9 km NNE of Avalon, CA") already
  names the nearest feature — a cheap sanity signal for onshore, but too
  unstructured to be primary.

## Recommendation

Build a `scripts/geo.py` with: (1) a loader for a vendored
`data/ne_110m_admin_0_countries.geojson`, (2) `iso3_for(lat, lon) -> list[str]`
via ray-casting (empty list = offshore), (3) `is_onshore(lat, lon) -> bool`. This
single module satisfies R2's onshore branch **and** the R0/blindspot-#10 ISO3
normalization, with no runtime dependency. Slice-1 "populated-landmass" = onshore;
population-distance refinement deferred to v2 and stated on the page.

**A4 flag → resolved.** Remaining smallness to verify at build time (file size,
`ISO_A3` gaps) is normal implementation detail, not an architectural unknown.

## Acceptance

Complete: we can describe the data asset, the pure-Python mechanism, the
null/list handling, the honest slice-1 approximation, and why no heavy dependency
is warranted.
