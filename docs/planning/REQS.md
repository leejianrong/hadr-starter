# REQS — HADR Monitor

Raw requirements capture. The seed for `/grill-with-docs` → `/to-prd` → `/shaping`.
Intentionally leaves open questions open; those are for the grilling step to resolve.

Grounded in: `README.md`, `feeds/{usgs,gdacs,reliefweb}.md`, `docs/feed-blindspots.md`,
and the three decisions recorded in `implementation-notes.md` (2026-07-08).

---

## The idea

A monitoring agent for humanitarian assistance and disaster response (HADR). It
watches live disaster feeds, filters out the noise, assesses what remains — what
happened, where, how bad, who is affected — and publishes a morning situation
report to `dashboard.html` at **08:30 Singapore time**. It runs on a schedule,
unattended, and **stays quiet when nothing has changed**.

## Who it's for and why

A human decision-maker starting their day in Singapore who needs a trustworthy,
skimmable picture of the world's active disasters — without reading three raw
feeds or drowning in aftershock noise. The product's value is *judgement*
(severity, deduplication, "does this deserve attention"), not raw data relay.

## The feeds — three different object types, not three views of one thing

This reframe (from `docs/feed-blindspots.md`) drives most of the hard problems.

- **USGS** — a *physical event* (one earthquake rupture), machine-generated,
  latency in seconds, earthquakes only. GeoJSON, regenerates every ~60s.
- **GDACS** — an *automated impact alert*, versioned over the event's life,
  latency in minutes, multi-hazard (EQ, cyclone, flood, volcano, drought,
  wildfire).
- **ReliefWeb** — a *human-declared humanitarian situation* (a coordination
  object), latency in **days**, everything above **+ epidemics + conflict**.

Consequence: cross-feed dedup is entity resolution across three ontologies with
different atomicity — **N:1:1** (many USGS events + one GDACS event-chain + one
ReliefWeb disaster), not row-matching. The feeds are also **not independent**:
GDACS earthquakes are built from USGS/NEIC, so feed-agreement is *not*
corroboration for quakes.

## What the product must do (intent, not yet spec)

1. **Ingest** the three feeds politely and resiliently (respect each feed's
   rate/UA/auth rules; never infer "event ended" from "absent from feed").
2. **Normalize** into a common internal model: nullable `event_time` (slow-onset
   crises have none), ISO3 country as a nullable *list*, UTC timestamps attached
   explicitly, provenance carried per field.
3. **Decluster** earthquakes — group a mainshock + its aftershock sequence into
   one line ("mainshock M7.1 + N aftershocks, largest M6.2"), so a swarm doesn't
   flood the report.
4. **Resolve** cross-feed clusters with a confidence score — GLIDE when present
   (high-precision, low-recall), else a space+time+magnitude tolerance box.
5. **Assess severity by impact, not magnitude** — rank on PAGER `alert` /
   GDACS `alertscore` (both probabilistic ranges, both a max of independent
   fatalities-OR-economic ladders). Magnitude is a descriptor only.
6. **Filter to what earns attention** (see decisions below).
7. **Publish** a situation report to `dashboard.html`, labelled with its window,
   attributing every figure to its source, never summing across feeds
   ("affected" ≠ "displaced" ≠ "killed" ≠ "in need").
8. **Run unattended on a schedule** at 08:30 SGT, and **stay silent when nothing
   changed** — a deterministic change-detector decides whether to wake the model.

## Decisions already locked (2026-07-08)

- **Report window:** last 24h rolling, ending at the 08:30 SGT publish time.
  Timestamps stay UTC internally; the boundary is computed in SGT (UTC+8, no
  DST). The window is **labelled on every report**. Slow-onset events don't fit
  a 24h window → handled in a separate always-on section, not filtered by it.
- **Attention threshold:** PAGER/GDACS **≥ orange**, OR **yellow with meaningful
  population exposure**, OR **anything already curated onto ReliefWeb** (an
  editor making a page is itself a high-quality severity signal). Thresholds are
  deterministic code in `scripts/`; a model never decides an alert level.
- **First vertical slice:** **USGS earthquakes, end-to-end** — least
  integration friction (no UA/appname wall), one hazard, one JSON shape;
  exercises the whole pipeline (ingest → decluster → severity → dashboard)
  before taking on GDACS/ReliefWeb parsing traps.

## Hard constraints (from CLAUDE.md and the feeds)

- **Python 3.12+**, standard-library-first; `requests` for HTTP, `pytest` for
  tests. A dependency must earn its place.
- **Deterministic logic lives in `scripts/` and never calls a model.** Severity
  thresholds, declustering, ISO3 normalization, dedup — all deterministic.
- **Log the final URL actually fetched**, not the one requested.
- **One learning per file in `docs/solutions/`** when something costs >10 min.
- **Any deviation from PRD or CLAUDE.md is recorded in `implementation-notes.md`
  with its reason.** An undocumented deviation is a bug.
- Feed-specific traps that ingestion must respect (see `feed-blindspots.md` for
  the full list): ReliefWeb 403s a default UA and needs a pre-approved appname;
  USGS times are epoch **ms**, track events by the full `ids` set not top-level
  `id`, most sizeable events have `alert: null`; GDACS booleans are the strings
  `"true"`/`"false"`, dates are UTC-without-designator, feed is capped at 100
  rolling records.

## Out of scope (deliberately, so nobody "helpfully" adds them)

- Real-time / sub-daily alerting — this is a once-a-day morning sitrep.
- Predictive modelling of severity — we *consume* PAGER/GDACS/editor judgement,
  we don't recompute exposure or forecast.
- Feeds beyond the three named (no Twitter/social, no news scraping).
- Interactive UI beyond a static `dashboard.html` — no server, no auth, no
  clicks-to-drill-down for the first pass.
- Historical archive / backfill analytics — the product is about "today."

## End state (from README, the Day-1→3 arc)

By Wednesday afternoon the repo contains an agent that watches the feeds,
assesses what remains, publishes to `dashboard.html` at 08:30 SGT on a schedule,
unattended, staying quiet when nothing changed. Expected artefacts:
`prd.html` · `system-view.html` · `implementation-notes.md` · `dashboard.html` ·
`goal.md` · at least one skill.

## Open questions (leave for grilling — do not resolve here)

- What exactly does "meaningful population exposure" mean numerically for the
  yellow-with-exposure branch of the threshold?
- How is "nothing changed" defined for the change-detector — new events only, or
  also revisions (status automatic→reviewed, magnitude shifts, deletions)?
- What does the 08:30 report say on a morning a feed is **down**? (GDACS
  publishes no uptime guarantee.)
- Confidence-score model for cross-feed clusters: what thresholds promote a
  match, and what does the report show for a *low-confidence* cluster?
- Where does state live between runs (so we can re-resolve revised events and
  not re-report yesterday's)? What's the persistence story?
- ReliefWeb appname approval may not land this week — RSS-first is the fallback,
  but RSS loses `status`, `type`, `iso3`, `date.event`, and pagination. How much
  of the product degrades gracefully without the API?
