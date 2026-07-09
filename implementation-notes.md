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

### 2026-07-08 — CI + linting (adopted from DEVELOPER-WORKFLOWS)

Adopted the fast-gate / CI-merge-gate practices from `docs/DEVELOPER-WORKFLOWS.md`,
scaled to a Python-only, offline-test project (skipped the web-app machinery:
testcontainers, Playwright, service containers, Fly deploy). Added `ruff`
(E/F/I, line-length 100), `.github/workflows/ci.yml` (ruff + pytest on PR/push to
main, `uv --frozen`, cached), and a tracked `scripts/git-hooks/pre-push` mirroring
CI. CLAUDE.md gained a Development workflow section. (PR #4, merged.)

### 2026-07-08 — V2 built: state + change detection + heartbeat

`docs/planning/SLICES.md` V2, all deterministic (still no model/schedule):

- `state.py` — SQLite store (stdlib `sqlite3`, ADR-0007): last-published
  severity/mag/depth/status/location per cluster, keyed stably, matched across
  runs by USGS `ids` intersection (top-level id can change).
- `changes.py` — the six loud triggers (ADR-0006): NEW, escalation (± when was
  orange+), magnitude/location review (≥0.3 M / ≥50 km / depth reclass),
  automatic→reviewed, withdrawal/retraction — with the **`feed_ok` guard** so an
  outage never manufactures a deletion.
- `render.py` — NEW/REVISED/CORRECTED flags, a corrections block, and a
  quiet-vs-loud **heartbeat** line; the page still regenerates every run (ADR-0005).
- `sitrep.py` — loads state before, persists after (only on a good fetch).

Verified end-to-end on a captured live payload: run 1 → 2× NEW (LOUD); run 2 (same
feed) → quiet, "no changes since last run"; run 3 (feed emptied) → 2× CORRECTED.
Suite now 46 tests. State DB (`*.sqlite3`) is gitignored.

### 2026-07-08 — V3 built: model narrator + 08:30 routine

The two-layer design goes live (ADR-0005), still deterministic where it must be:

- `sitrep.py --brief` writes a JSON brief with a `loud` flag + the changed
  clusters/retractions; `render.py` leaves a `<!--NARRATIVE-->` slot.
- `skills/sitrep/SKILL.md` — the `/sitrep` skill (the course's required skill):
  reads the brief, writes 2–4 sentences of attributed, preliminary-labelled prose
  to `narrative.md`, invents no numbers. Model note: **Haiku 4.5**.
- `scripts/inject.py` — deterministically injects the prose into the slot
  (escaped), keeping the model out of the HTML/number path (ADR-0002).
- `.github/workflows/sitrep.yml` (renamed from `.disabled`): schedule
  **00:30 UTC = 08:30 SGT** + dispatch. Deterministic step always regenerates the
  page + brief; the model step (`anthropics/claude-code-action`, same
  `CLAUDE_CODE_OAUTH_TOKEN` as `claude.yml`) runs **only if `loud`**; inject; commit
  `dashboard.html` (the publish) + a job-summary line. State persists across runs
  via a rolling `actions/cache`.

Deterministic pieces verified locally end-to-end (brief/loud flag → inject →
quiet). The `claude-code-action` call runs in CI. Suite now 53 tests; ruff clean.

**Notification** is currently the dashboard commit + the Actions job summary; a
push/Slack channel is a future hook (needs a secret). **State across CI runs** uses
`actions/cache`; if it's evicted, that day re-marks events NEW (acceptable).

### 2026-07-09 — V4 built: GDACS multi-hazard + cross-feed join

The multi-hazard (R4) and cross-feed (R3) machinery lands. New deterministic
modules, all offline-tested against trimmed **real** GDACS samples captured
2026-07-08 (`tests/fixtures/gdacs_rss_sample.xml`, `gdacs_eventlist_sample.json`):

- `scripts/gdacs.py` — GDACS adapter, **RSS-first with the JSON list as a drop-in**
  (ADR-0008). Handles every GDACS trap in `docs/feed-blindspots.md`: string
  booleans (`"true"`/`"false"`), naive-UTC vs RFC-822 dates (two parsers in
  `model.py`), `affectedcountries[]` as the ISO3 list (not the comma `country`
  string), per-hazard heterogeneous severity units (M/km/h/ha), and the
  JSON-vs-RSS `alertscore` non-interchangeability (see Deviations).
- `scripts/cluster.py` — the confidence ladder from `SPIKE-cross-feed-confidence`.
  **EQ identity link checked first** (`source == "NEIC"` + embedded `sourceid` in
  the USGS `ids` set → `certain`); then GLIDE/tolerance box (tight→`high`,
  loose→`medium`, partial→`low`). `join()` merges per A3-Q5: certain/high merge
  silently, medium merges + "likely the same event", **low cross-links and never
  merges**. Every EQ merge is `independent=False` — a GDACS-EQ is *built from*
  USGS/NEIC, so it is one reading arriving twice, never corroboration and never
  double-counted (ADR-0002, blindspot #2).
- `model.py` grows `GdacsEvent` + a unified `ReportItem` (one resolved cross-feed
  cluster — ADR-0001); `severity.py` grows the GDACS threshold (peak colour ≥
  orange) and a cross-hazard `item_sort_key`; `state.py`/`changes.py` grow a
  parallel GDACS state table + change detector keyed on `(eventtype, eventid)`.
- `sitrep.py` gains `--gdacs` / `--gdacs-fixture` / `--gdacs-json-fixture`; the
  renderer shows GDACS hazard lines, provenance, confidence/cross-link notes, and
  a GDACS feed-health line with the 100-record rolling-cap warning.

**DoD verified** (offline + a live two-run demo): cyclones/floods/wildfires appear
ranked by GDACS alert colour; a GDACS-EQ and its USGS-EQ resolve to one line;
green GDACS noise is filtered; low-confidence pairs are cross-linked, not merged;
GDACS state persists so a second run is quiet. Suite now 83 tests; ruff clean.

### 2026-07-09 — V4 follow-ups

Closed the three follow-ups flagged above:

1. **`--gdacs` wired into `sitrep.yml`** — the 08:30 routine now runs the GDACS
   multi-hazard join live. GDACS change-detection state lives in the same
   `hadr-state.sqlite3`, so the existing rolling `actions/cache` persists it with
   no extra cache key.
2. **ReliefWeb appname** — turned into a concrete, ready-to-submit owner action
   (appname, purpose text, contact, secret name) under Open questions. Still an
   external form; not automatable.
3. **Merged-EQ country label** — a merged earthquake whose USGS point reverse-
   geocodes offshore (our onshore test uses coarse 110m polygons) now borrows the
   merged GDACS record's ISO3, shown attributed as "(country via GDACS)" instead of
   a bare "(offshore)". Rendering-only; numbers untouched. Suite now 84 tests.

## Open questions

- **ReliefWeb API `appname` — OWNER ACTION (external, no-SLA).** The API has
  required a pre-approved `appname` since 1 Nov 2025 (unapproved → 403; missing →
  400; v1 → 410). Approval is a form + email confirmation with no published SLA,
  so it must be requested by a human now to unblock the V5→API upgrade later; V5
  itself ships on RSS and does **not** block on this.
  - Request at: https://apidoc.reliefweb.int/parameters#appname
  - Proposed appname: **`hadr-monitor-sitrep`** (lowercase, stable — it's the
    rate-limit identity; keep it constant once approved).
  - Purpose to state on the form: *"Daily humanitarian situation report —
    read-only, ~1 call/day at 08:30 SGT against `/v2/disasters?preset=latest`,
    well under the 1000 calls/day quota."*
  - Contact: the repo owner's email (`leejianrong2@gmail.com`).
  - When approved: store it as the `RELIEFWEB_APPNAME` Actions secret and switch
    the adapter from RSS to the API path (the V5 adapter is built as a drop-in).
  - **Status: not yet requested** (blocked on human form submission).
- ~~GDACS `--gdacs` opt-in / not in the workflow~~ — **done (2026-07-09):**
  `sitrep.yml` step 1 now runs `--gdacs`; GDACS state shares `hadr-state.sqlite3`,
  so the existing rolling `actions/cache` persists it with no extra key.

## Deviations

<!-- Anything built that departs from the PRD or CLAUDE.md is recorded here,
     with the reason. An undocumented deviation is a bug. -->

### 2026-07-09 — V4 (GDACS)

- **Ranking is on the GDACS alert *colour*, not the raw numeric `alertscore`.**
  The SLICES/DoD wording says "ranked by GDACS alertscore". We confirmed with live
  data that the same event's raw `alertscore` differs between the JSON and RSS
  feeds (EQ1550772: JSON peak score 1.0 vs RSS 0.0) — the "roughly swapped
  conventions" blindspot. The `alertlevel` **colour** (Green/Orange/Red, which the
  score buckets into) IS stable across both feeds, so it is the canonical severity
  axis; the raw score is tagged with its `score_format` and only ever used as an
  intra-format tiebreaker, never compared across feeds. This *is* ranking by
  alertscore, just via its stable bucket rather than the unstable integer.
- **GDACS sudden-onset hazards are windowed on currency (`iscurrent`), not onset
  time.** The 24h-ending-08:30 window (ADR-0003) is defined on event onset. GDACS
  cyclones/floods/wildfires run for days; a Red cyclone that began a week ago is
  still the top of today's report while `iscurrent` holds. Windowing those out on
  onset age would be the "infer 'ended' from age" error (ADR-0007 / GDACS
  rolling-cap blindspot). Non-current GDACS alerts fall back to the 24h onset
  window so stale records don't linger. Earthquakes (instantaneous) keep the strict
  onset window unchanged.
- **GDACS is opt-in on the CLI (`--gdacs`)**, so V1–V3 default behaviour and the
  existing `sitrep.yml` are byte-unchanged until the workflow is updated. `Report`
  gained an `items` list (the unified render surface); `build_report` kept its
  positional signature (GDACS args are keyword-only with safe defaults) so the V1–V3
  call sites and tests are untouched.
