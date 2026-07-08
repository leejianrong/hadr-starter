# PRD — HADR Monitor

Status: Draft (2026-07-08). Product-requirements document produced from `docs/planning/REQS.md`,
`docs/planning/CONTEXT.md`, and `docs/adr/*.md` (the grill step). Decisions here link to the ADR
that records their context and alternatives. Renders to `prd.html` (course
artefact) when this stabilises.

---

## 1. Problem

A decision-maker starting their day in Singapore needs a trustworthy, skimmable
picture of the world's active disasters — *what happened, where, how bad, who is
affected* — in about 30 seconds, without reading three raw feeds or drowning in
aftershock noise. The three available feeds (GDACS, USGS, ReliefWeb) are not
three views of one thing; they are **three object types** at different atomicity
and latency (ADR-0001), reporting **impact figures that must never be summed**
(ADR-0008), and **magnitude is not severity** (ADR-0002). Raw, they mislead. The
product's value is **judgement and trust**, not data relay.

## 2. Users and their jobs

**Primary user — the morning decision-maker** (humanitarian analyst / duty
officer). Jobs to be done:

- *"When I open my screen at 08:30, show me what deserves my attention in the last
  day, ranked by human impact, so I can decide where to look."*
- *"Never let me mistake a quiet night for a dead pipeline, or a preliminary
  number for a fact, or a data outage for calm."*
- *"When something I briefed yesterday changes or turns out false, tell me so I can
  walk it back."*

**Secondary user — the operator/maintainer** (us): *"Tell me, on the page itself,
what the monitor can and cannot currently see, so its blindspots are never
silent."*

### User stories

1. As the reader, I open `dashboard.html` at 08:30 SGT and see the last-24h
   attention-worthy events, ranked by impact severity, each on one line
   (colour · what/where · impact+source · magnitude · as-of · change-flag).
   *(ADR-0001, ADR-0004, CONTEXT report anatomy)*
2. As the reader, on a no-news morning I still see a fresh page stamped 08:30
   today saying "nothing crossed threshold," so I know the pipeline is alive.
   *(ADR-0005)*
3. As the reader, I see every active slow-onset crisis (drought/epidemic/conflict)
   in an always-on section, even though it didn't "happen" in the last 24h.
   *(ADR-0003)*
4. As the reader, I see an aftershock sequence as **one** line ("mainshock M7.1 +
   43 aftershocks, largest M6.2"), never dozens. *(CONTEXT declustering)*
5. As the reader, when a feed is down I see it flagged red in feed-health with its
   last-good time and a coverage banner — never a silent gap. *(ADR-0007)*
6. As the reader, when an event I saw yesterday is downgraded or deleted, I see an
   explicit correction line. *(ADR-0006 row 5)*
7. As the reader, casualty figures always come wrapped in source + range +
   preliminary flag; disagreeing estimates are stacked and attributed, never
   merged. *(ADR-0002, ADR-0008)*
8. As the operator, the dashboard states current coverage limits (e.g. "earthquakes
   only") so blindspots are visible. *(ADR-0004)*

## 3. Solution

A scheduled, unattended agent with a strict **two-layer** design (ADR-0005):

- **Deterministic layer (`scripts/`, never calls a model)** — runs every morning
  at 08:30 SGT: fetch each feed politely and resiliently → normalize to the common
  model (nullable `event_time`, ISO3 country list, UTC timestamps, provenance per
  field) → decluster earthquakes → resolve cross-feed clusters with a confidence
  score → apply the deterministic attention threshold → detect loud changes vs
  persisted state → **regenerate `dashboard.html` unconditionally**, stamping the
  publish time and per-feed "as of" times.
- **Model layer (expensive, guarded)** — wakes **only** when the change-detector
  reports a loud change (ADR-0006), writes the narrative prose for what changed,
  and only then sends a notification. On a quiet morning it never runs.

The page timestamp is the heartbeat; "quiet" means the model sleeps, not the page
goes stale.

### Report structure (fixed — CONTEXT "Report anatomy")

1. **Sudden-onset, last 24h** — ranked attention-worthy events.
2. **Slow-onset / ongoing** — always-on; window-independent.
3. **Feed health** — one line per feed, "as of" time, any outage. Never optional.
4. **Nothing-to-report** — explicit line when section 1 is empty; never a blank page.

## 4. Scope

### First vertical slice (build now) — USGS earthquakes, end-to-end

Least integration friction (no UA/appname wall), one hazard, one JSON shape;
exercises the whole pipeline. Delivers stories 1, 2, 4, 5, 6, 7, 8 for earthquakes
only, with the **honest slice-1 threshold** (ADR-0004): PAGER tier-1 when present,
else the magnitude/depth/onshore tier-2 proxy + `sig≥600`. The dashboard states
loudly: *"Coverage: earthquakes only (USGS). No flood/cyclone/epidemic/conflict
monitoring yet."*

**Definition of done (slice 1):** at 08:30 the agent fetches `all_day.geojson`,
declusters, applies the threshold, persists state, detects changes vs the prior
run, and writes a `dashboard.html` with the four sections — including a correct
feed-health line and a correct "nothing-to-report" line on a quiet run — with the
model invoked only on a loud change.

### Roadmap (later slices, not now)

GDACS multi-hazard (RSS-first) → ReliefWeb (RSS-first, API on approval) →
cross-feed cluster resolution across all three → the 08:30 scheduled routine and
notification.

## 5. Implementation decisions

- **Language/tooling:** Python 3.12+, standard-library-first; `requests` for HTTP,
  `pytest` for tests. (CLAUDE.md)
- **Determinism in `scripts/`, never a model** — severity thresholds, declustering,
  ISO3 normalization, dedup, change-detection. A model may draft prose; it never
  decides an alert level or a merge. (CLAUDE.md #1; ADR-0002/0004/0006)
- **Severity:** consume PAGER `alert` / GDACS `alertscore`; colour is max of
  fatalities-OR-economic ladders; ranges never point estimates. (ADR-0002)
- **Cluster** is the unit; keyed per ADR-0001; joined GLIDE-then-tolerance-box.
- **Window:** last 24h ending 08:30 SGT, labelled; slow-onset exempt. (ADR-0003)
- **Persistent state** holding the minimum in ADR-0007, stored in **SQLite**
  (stdlib `sqlite3`) — decided during shaping (Shape A, `docs/planning/SHAPING.md`).
- **Degrade loud:** per-feed "as of", coverage banners, corrections, never infer
  "ended" from "absent". (ADR-0007)
- **Log the final URL actually fetched**, not the one requested. (CLAUDE.md #2)
- **Feed traps honoured** (feed-blindspots): USGS times are ms; track full `ids`
  set; `alert:null` ≠ minor; GDACS booleans are strings; UTC-without-designator;
  100-record cap; ReliefWeb UA + appname wall, RSS-first. (ADR-0008)

## 6. Testing decisions

`pytest` from repo root (CLAUDE.md). The deterministic layer is the testable core;
tests use **fixture feed payloads** (saved real responses), not live fetches, so
they are deterministic and offline. Priority cases:

- **Declustering:** a mainshock + N aftershocks fixture collapses to one line.
- **Threshold (slice-1):** tier-1 PAGER cases; tier-2 boundary cases (M5.9 shallow
  onshore vs M6.5 deep offshore); magnitude-type guard (`mb 6.0` does not trip).
- **Change-detector:** each of the six loud triggers fires on its fixture and a
  sub-threshold wobble stays quiet; the **`feed_fetch_succeeded` guard** — a failed
  fetch never manufactures a deletion (ADR-0006 row 5).
- **Quiet vs loud rendering:** a no-change run still writes a fresh-stamped page
  with a "nothing-to-report" line and no model call (ADR-0005).
- **Degrade-loud:** a simulated feed outage produces a red feed-health line and a
  coverage banner, and the report still publishes (ADR-0007).
- **Provenance:** the renderer refuses a bare casualty integer; two disagreeing
  figures render stacked and attributed, never summed (ADR-0002, ADR-0008).
- **Time handling:** epoch-ms parse; SGT window boundary; nullable `event_time`.

## 7. Out of scope (deliberate — REQS + ADR-0002)

- Recomputing severity ourselves (exposure/fatality modelling or forecasting).
- Real-time / sub-daily alerting — this is a once-a-day morning sitrep.
- Feeds beyond the three named (no social, no news scraping).
- Interactive UI beyond a static `dashboard.html` (no server, auth, drill-down).
- Historical archive / backfill analytics.

## 8. Open owner-decisions (surfaced, non-blocking)

- **Daily all-clear ping** on quiet mornings, yes/no (ADR-0005). Recommend yes.
- Final numeric constants for thresholds (ADR-0004) and loud triggers (ADR-0006);
  defaults recommended, owner tunes in `scripts/`.
- Request the ReliefWeb **appname** now so the API path is unblocked (ADR-0008).

*(Resolved during shaping: state store = **SQLite**, ADR-0007.)*

## 9. Solution shape and build order

The architecture and slice plan were selected in `docs/planning/SHAPING.md` (Shape A —
deterministic render, model narrates only) and detailed in `docs/planning/BREADBOARD.md` /
`docs/planning/SLICES.md`. Build order: **V1** USGS earthquakes → one-shot `dashboard.html`
(the locked first slice) → V2 state + change detection → V3 model narrator + 08:30
routine → V4 GDACS multi-hazard → V5 ReliefWeb + slow-onset + provenance.
