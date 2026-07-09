---
shaping: true
---

# HADR Monitor — Slices (Shape A)

Vertical increments of the breadboard (`BREADBOARD.md`). Each slice ends in
**demo-able UI** — a `dashboard.html` a reviewer can open and check in two minutes
(cf. `.github/ISSUE_TEMPLATE/slice.md`). Affordance IDs reference `BREADBOARD.md`.

**V1 is the locked first slice** (USGS earthquakes, end-to-end). V4–V5 bring in the
multi-hazard (R4) and cross-feed (R3) machinery that single-feed slices don't need.

## Slice overview

| Slice | Goal (what exists after) | Affordances added | Demo |
|-------|--------------------------|-------------------|------|
| **V1** | USGS quakes → a real `dashboard.html`, one-shot | N1(part)·N2(USGS)·N3·N4·N6·N7(slice-1)·N10 · U1·U2·U4·U5 · D1·D3 | Run once → open page: window-labelled, coverage banner, ranked declustered quakes, USGS feed-health, nothing-to-report when empty |
| **V2** | Quiet-but-alive + change awareness | N8·N9 · U6 | Run twice on fixtures: unchanged → fresh-stamped "nothing crossed threshold"; changed → `REVISED ↑`; deleted-from-feed → `CORRECTED` (guarded) |
| **V3** | Model prose on change + the 08:30 routine | N0·N11·N12 · U7 | Loud run → narrative prose + notification; quiet run → no model, page still refreshes; workflow runs on dispatch |
| **V4** | GDACS multi-hazard + cross-feed join | N2(GDACS)·N5·N7(alertscore) · U4(GDACS) | Cyclones/floods/WF appear by alertscore; a GDACS-EQ + its USGS-EQ merge to one line (identity link, not double-counted) |
| **V5** | ReliefWeb + slow-onset + provenance | N2(ReliefWeb) · U3 · provenance stacking on U2.1 | Curated disasters in the ongoing section (window-exempt); "reached ReliefWeb" floor fires; disagreeing figures stacked+attributed, never summed; RSS-mode flags shown |

Requirement coverage by slice: V1 → R0/R0.1/R0.3, R2 (slice-1), R7 (USGS), R8;
V2 → R5, R6; V3 → R5 (model gate), R5.1; V4 → R1 (severity breadth), R3 (join),
R4 (partial); V5 → R0.2, R1 (provenance), R4 (full).

---

## V1 — USGS earthquakes → static dashboard (locked first slice)

### Goal

Running one command fetches today's USGS earthquakes and writes a real
`dashboard.html` — declustered, impact-thresholded, window-labelled, honest about
its coverage — with **no** model call, state, or scheduling yet.

### Definition of done (observable in two minutes)

- A command (e.g. `python -m scripts.sitrep`) fetches
  `…/summary/all_day.geojson` (USGS: `Accept-Encoding: gzip`, no UA needed) and
  **logs the final URL actually fetched** (CLAUDE.md #2).
- Events filtered to `type == "earthquake"`; times parsed from epoch **ms** UTC;
  tracked by the full `ids` set.
- **Declustering:** a mainshock + aftershocks collapse to one line
  ("Mainshock M7.1 + N aftershocks, largest M6.2"); a true swarm is labelled.
- **Slice-1 threshold (ADR-0004):** tier-1 PAGER when present; tier-2
  mww-family `M≥6.0`, or `M≥5.0 + depth≤70 km + onshore` (via `scripts/geo.py`
  ray-casting over the vendored Natural Earth GeoJSON), with `sig≥600` as an
  additional include; magnitude-type guard applied. Constants named in `scripts/`.
- `dashboard.html` renders the fixed anatomy: **U1** header (title, window
  "last 24h ending 08:30 SGT", SGT publish timestamp, coverage banner
  *"earthquakes only (USGS) — no flood/cyclone/epidemic/conflict monitoring yet"*),
  **U2** ranked sudden-onset lines, **U4** a USGS feed-health line with its
  "as of" time, **U5** a nothing-to-report line when nothing clears threshold.
- Severity shown as colour + range, magnitude as descriptor only; **no bare
  casualty integer** (ADR-0002).
- `pytest` covers: decluster fixture; tier-1/tier-2 boundary cases (M5.9 shallow
  onshore vs M6.5 deep offshore); magnitude-type guard; epoch-ms parse; SGT window
  boundary; onshore ray-casting on known points. Tests run **offline on fixtures**.

### Out of scope (do not let anyone add these to V1)

- Persisted state, change detection, `NEW`/`REVISED`/`CORRECTED` flags (→ V2).
- Any model call / narrative prose / notification (→ V3).
- GitHub Actions scheduling (→ V3).
- GDACS or ReliefWeb, cross-feed clustering, the slow-onset section (→ V4/V5).
- The "within ~100 km of a populated place" refinement — V1 onshore == inside a
  country polygon (`SPIKE-onshore-geocode`), stated as a limitation on the page.

---

## V2 — persisted state + change detection + heartbeat ✅ built (2026-07-08)

Adds `scripts/state.py` (SQLite, ADR-0007), `scripts/changes.py` (six loud
triggers, ADR-0006), and NEW/REVISED/CORRECTED flags + a quiet-vs-loud heartbeat
line in the renderer. **DoD met:** run twice sharing state → first run flags NEW
(loud), an unchanged second run is quiet with a fresh timestamp, and a
withdrawn/downgraded event yields an explicit CORRECTED line — with the `feed_ok`
guard so an outage never manufactures a deletion. Still no model / schedule (V3).

## V5 — ReliefWeb + slow-onset + provenance stacking ✅ built (2026-07-09)

Adds `scripts/reliefweb.py` (RSS-first adapter, API drop-in), the slow-onset/ongoing
section (U3, window-exempt), the reached-ReliefWeb severity floor, GLIDE-based
provenance stacking on sudden-onset lines (U2.1), and a ReliefWeb state/change path
(NEW-only — no retractions, since the RSS 20-item window means absence ≠ deletion).
**DoD met:** curated disasters incl. epidemics/conflict appear in the ongoing
section; the floor shows every curated disaster; a GLIDE match stacks two
*independent* sources (GDACS + ReliefWeb) on one line, attributed and **never
summed**; RSS-mode gaps (status/type/full-ISO3/date.event/pagination) flagged loud.
ISO3 is taken from the GLIDE suffix (not name-matched); figures are not scraped from
prose (API-only) — both recorded in `implementation-notes.md`. `--reliefweb` /
`--all-feeds` opt-in; workflow wiring is the follow-up. Suite: 102 tests, ruff clean.
**All slices V1–V5 built; R0–R8 satisfied.**

## V4 — GDACS multi-hazard + cross-feed join ✅ built (2026-07-09)

Adds `scripts/gdacs.py` (RSS-first adapter, JSON drop-in — every GDACS parsing
trap handled), `scripts/cluster.py` (the confidence ladder from
`SPIKE-cross-feed-confidence`, EQ identity link first), a unified `ReportItem`,
GDACS colour threshold + cross-hazard ranking, and a parallel GDACS state/change
path keyed on `(eventtype, eventid)`. **DoD met:** cyclones/floods/wildfires
appear ranked by GDACS alert colour; a GDACS-EQ and its USGS-EQ merge to ONE line
(`independent=False` — never double-counted); GDACS feed-health shown with the
100-cap warning; green GDACS noise filtered; low-confidence pairs cross-linked,
never silently merged. Ranking uses the alert **colour** not the raw `alertscore`
(the JSON/RSS scores aren't interchangeable) and GDACS hazards are windowed on
currency — both recorded in `implementation-notes.md`. GDACS is opt-in (`--gdacs`);
wiring it into `sitrep.yml` is a follow-up. Suite: 83 tests, ruff clean.

## V3 — model narrator + notification + 08:30 routine ✅ built (2026-07-08)

Wires the expensive layer, guarded by the deterministic one (ADR-0005). `sitrep.py`
now emits a `--brief` JSON with a `loud` flag and leaves a `<!--NARRATIVE-->` slot
in the page. `.github/workflows/sitrep.yml` (schedule 00:30 UTC = 08:30 SGT +
manual dispatch): (1) always regenerates `dashboard.html` + brief; (2) **only if
`loud`** invokes `anthropics/claude-code-action` running the `/sitrep` skill
(`skills/sitrep/SKILL.md`, Haiku 4.5) to write `narrative.md`; (3) `scripts/inject.py`
places the prose deterministically; (4) commits the dashboard (the "publish") and
writes a job-summary line (the notification hook). State persists across runs via a
rolling `actions/cache`. **DoD met** for the deterministic pieces (brief/loud flag,
injection, marker) — verified locally; the model call itself runs in CI with the
repo's existing `CLAUDE_CODE_OAUTH_TOKEN`.

<!-- V4–V5 expand into their own sections (Goal / DoD / Out of scope) when picked
     up. V1 is detailed now because it is the locked next build. Keep this doc in
     sync with SHAPING.md (parts) and BREADBOARD.md (affordances) — ripple both
     ways. -->
