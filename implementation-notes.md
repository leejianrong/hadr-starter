# Implementation notes

Kept by the agent, reviewed by you. One entry per working block.

## Decisions

### 2026-07-08 — Report window, severity threshold, first slice

Resolved the three open decisions from `docs/feed-blindspots.md` (the fourth,
requesting the ReliefWeb appname, is an external action — see Open questions).

- **Report window: last 24h rolling, ending at the 08:30 SGT publish time.**
  Chosen over the SGT/UTC calendar-day options because a rolling 24h window has
  no blind gap (a calendar-day report published at 08:30 omits 00:00–08:30) and
  a single, easily-labelled lookback. Event timestamps stay UTC internally;
  the window boundary is computed in SGT (UTC+8, no DST). Slow-onset events
  (drought/epidemic/famine — blindspot #6) do not fit a 24h window and are
  handled as a separate always-on section, not filtered by the window.
  *Per blindspot #9, the window must be labelled on every report.*
- **Attention threshold: PAGER/GDACS ≥ orange, OR yellow with meaningful
  population exposure, OR anything already curated onto ReliefWeb.** The
  "reached ReliefWeb" signal is free and high-quality — editors don't create a
  page for a harmless quake (blindspot #2). Thresholds are deterministic code
  in `scripts/` (CLAUDE.md #1); a model never decides an alert level.
- **First vertical slice: USGS earthquakes, end-to-end.** Single feed with the
  least integration friction (no User-Agent/appname wall, verified live), one
  hazard, one JSON shape — exercises the whole pipeline (ingest → decluster →
  severity → `dashboard.html`) before taking on GDACS/ReliefWeb parsing traps.

### 2026-07-08 — Product planning (grill + PRD)

Ran Steps A–B of the build-plan-product process, grilling a stakeholder persona
(Maya, OCHA sitrep veteran) instead of a live person. Outputs:
`docs/planning/REQS.md` (idea capture), `docs/planning/QUESTIONS.md` (grill log), `docs/planning/CONTEXT.md` (shared
vocabulary), `docs/adr/0001`–`0008` (decision records), `docs/PRD.md`. Notable
resolutions beyond the three decisions above: "quiet" = model asleep + no ping
while the page always regenerates (ADR-0005); the honest USGS-only slice-1
threshold falls back to a magnitude/depth/onshore proxy since PAGER is null below
~M5.5 (ADR-0004); loud-change detection = six deterministic boolean triggers
(ADR-0006). Three owner-decisions remain open and non-blocking — see `docs/planning/QUESTIONS.md`.

### 2026-07-08 — Shaping: Shape A selected

Ran build-plan-product Step C (shaping): `docs/planning/FRAME.md`, `docs/planning/SHAPING.md` (R0–R8, three
shapes, fit check). **Selected Shape A** — "deterministic render, model narrates
only": all decisions and the HTML are Python in `scripts/`; the model writes prose
only, injected into a fully-templated, byte-stable page. Shapes B (model assembles
the page — fails R1, model in the number path) and C (continuous collector — fails
R8, needs an always-on host GitHub Actions cron doesn't give) were rejected.

Two flagged unknowns resolved by spikes:

- `docs/planning/SPIKE-onshore-geocode.md` (R2/A4): point→ISO3 + onshore via a vendored Natural
  Earth Admin-0 GeoJSON + pure-Python ray-casting — **zero runtime dependency**.
  Slice-1 "populated-landmass" == onshore; population-distance refinement is v2.
- `docs/planning/SPIKE-cross-feed-confidence.md` (R3/A3): a deterministic confidence ladder with
  the earthquake identity link (GDACS-EQ ⊂ USGS/NEIC) first; lands with feed #2.

Decision locked while detailing: **state store = SQLite** (stdlib `sqlite3`) —
closes the open question in ADR-0007. Remaining non-blocking owner-decision: the
daily all-clear ping (ADR-0005, recommend yes).

### 2026-07-08 — Breadboard + slices (Step D)

`docs/planning/BREADBOARD.md` (UI/non-UI affordances + wiring) and `docs/planning/SLICES.md` (5 vertical
slices, each demo-able). **V1 = the locked first build**: USGS earthquakes →
one-shot `dashboard.html` (fetch → decluster → slice-1 threshold w/ geo onshore →
four-section render), no state/model/schedule yet — detailed in `docs/planning/SLICES.md` in the
`slice.md` issue-template shape. V2 adds state + change detection + heartbeat; V3
the model narrator + 08:30 routine; V4 GDACS multi-hazard + cross-feed join; V5
ReliefWeb + slow-onset + provenance stacking.

### 2026-07-08 — Reconcile pass (Step E)

Consistency sweep over the planning doc-set. Fixed: (1) **ADR-0009 was cited 3×
but had no file** — created `docs/adr/0009-preliminary-labelled-corrections-explicit.md`
(publish preliminary-and-labelled; corrections explicit — from grill Q4.1/Q4.2) and
indexed it; (2) **stale "SQLite vs JSON open decision"** in `docs/PRD.md` (×2) and
`docs/planning/QUESTIONS.md` (×2) updated to reflect SQLite decided during shaping; (3) added
PRD §9 (solution shape + build order) pointing to SHAPING/BREADBOARD/SLICES.
Verified: all `ADR-00NN` and `SPIKE-*.md` references resolve; no `3.11` remnants.

### 2026-07-08 — Tooling: uv + pyproject; V1 built and verified

- **Tooling: adopted `uv` + `pyproject.toml`/`uv.lock`** (Python 3.12+). CLAUDE.md
  and README updated; test command is now `uv run pytest`. Reason: the system
  `pip` for 3.12 is broken (distutils removed) — see
  `docs/solutions/2026-07-08-python-312-uv-env.md`. Deps: `requests` (HTTP),
  `pytest` (dev). Consistent with PRD §5 / CLAUDE.md; not a deviation.
- **V1 slice built and verified** (`docs/planning/SLICES.md`). `scripts/`:
  `model`, `usgs`, `geo`, `decluster`, `severity`, `render`, `sitrep`; vendored
  `data/ne_110m_admin_0_countries.geojson` (slimmed, 254 KB). 31 pytest tests
  pass (offline fixtures). `uv run python -m scripts.sitrep` fetches the live
  feed, logs the final URL (CLAUDE.md #2), and writes a four-section
  `dashboard.html` — verified end-to-end: live run showed a Costa Rica M5.3 and a
  declustered China M5.1 swarm (both reverse-geocoded, both tier-2/"NO PAGER"),
  and the quiet fixture path renders "nothing-to-report", not a blank page. Render
  is byte-deterministic for a fixed input+publish-time (needed for the V2
  heartbeat / git-diffs).

## Open questions

- ReliefWeb API `appname` approval is a manual, no-SLA process (Google Form +
  email since 1 Nov 2025). Request it now so the API path is unblocked later;
  build against RSS meanwhile (blindspot ReliefWeb notes). *Not yet requested.*

## Deviations

<!-- Anything built that departs from the PRD or CLAUDE.md is recorded here,
     with the reason. An undocumented deviation is a bug. -->
