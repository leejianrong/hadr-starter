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

### 2026-07-09 — V5 built: ReliefWeb + slow-onset + provenance stacking

The final planned slice — the curated humanitarian layer that adds epidemics and
conflict (the hazards USGS/GDACS structurally cannot see) and completes R0.2 / R1 /
R4. All offline-tested against a trimmed **real** ReliefWeb RSS sample captured
2026-07-08 (`tests/fixtures/reliefweb_disasters_rss_sample.xml`).

- `scripts/reliefweb.py` — RSS-first adapter (API is a drop-in once the appname
  lands). Handles the ReliefWeb RSS traps: browser-like UA (the WAF wall), GLIDE +
  countries parsed out of the double-escaped HTML in `<description>`, **ISO3 taken
  from the GLIDE suffix** (a clean code) rather than string-matching country names
  (blindspot #10), hazard type inferred from the GLIDE prefix (no `type` in RSS),
  and the ~20-item unpaginated window surfaced on feed-health. Casualty figures are
  deliberately **not** scraped from the prose (numbers are consumed, never modelled
  — ADR-0002); real figure-stacking lands with the API.
- `scripts/cluster.py::attach_reliefweb` — GLIDE-stacks a disaster onto a matching
  sudden-onset line (its GDACS GLIDE) as **provenance stacking** (U2.1); everything
  else becomes a window-exempt ongoing item. Unlike the EQ↔NEIC link, GDACS and
  ReliefWeb are independent orgs, so a GLIDE match **does** corroborate
  (`independent=True`) — but figures are shown attributed, never summed (ADR-0008).
- `model.py` grows `ReliefWebDisaster` + the GLIDE parser/hazard map + `Report.ongoing`
  + `ReportItem.reliefweb`; `state.py`/`changes.py` grow a ReliefWeb state table +
  change detector (**NEW only, no retractions** — RSS's 20-item window means
  disappearance ≠ deletion); `render.py` grows the slow-onset section (U3), the
  REACHED-RELIEFWEB lines, and the stacked-attribution line; `sitrep.py` gains
  `--reliefweb` / `--reliefweb-fixture` / `--all-feeds`.

**DoD verified** (offline + a live three-feed run): curated disasters (incl.
epidemics) appear in the window-exempt ongoing section; the reached-ReliefWeb floor
shows every disaster; a GLIDE match stacks two independent sources on one line,
attributed and never summed; RSS-mode gaps (status/type/full-ISO3/date.event/
pagination) are flagged loud on the page. Suite now 102 tests; ruff clean.
**Every planned slice (V1–V5) is now built; the R0–R8 matrix is satisfied.**

### 2026-07-09 — V6: livelier dashboard (7-day history, scan summary, activity chart, restyle, 15:00 run)

A presentation + context slice (no new feed). Driven by the report reading too sparse
on quiet mornings.

- **Past-7-days section.** USGS now fetches `all_week.geojson`; the pipeline declusters
  the whole week and splits clusters by mainshock time: last-24h → the sudden-onset
  brief (`report.items`), 24h–7d → a new context section (`report.recent`). GDACS
  splits the same way (current/last-24h vs closed-with-onset-in-week). `report.clusters`
  stays the 24h set so the model brief and V1–V5 call sites are unchanged.
- **Union change-detection (a correctness fix).** Change detection + retractions now
  run over the full 7-day kept set, not just the 24h slice. Previously a significant
  event would age out of the 24h window each day and be reported as a CORRECTED
  withdrawal — a spurious retraction. Now an event ageing from the brief into the
  context section is still "seen", so only a real withdrawal or below-threshold drop
  retracts (still `feed_ok`-guarded).
- **Scanned-vs-shown summary + activity chart.** A `ScanSummary` carries per-feed
  scanned counts and shown counts (today / week / ongoing); the renderer shows an
  honest "Scanned N, cleared the bar M" line and a deterministic inline-SVG stacked
  bar chart of significant events per SGT day over 7 days, coloured by severity. No
  JS, no external deps — it stays byte-stable.
- **Duty Desk restyle.** `render.py`'s template now uses the same ink / mono /
  alert-triad language as the landing page, so the two read as one product. Committed
  to a single dark theme deliberately (an ops desk). All text strings the tests assert
  were preserved.
- **Second daily run.** `sitrep.yml` gains a 15:00 SGT (07:00 UTC) schedule. The
  window label is derived from run time, so the afternoon run reads "last 24h ending
  15:00 SGT" with no code change; the model still wakes only on a loud change.

DoD verified with a live all-feeds run (6 sudden + 4 past-week + 20 ongoing; scan line
and chart populated). Suite now 108 tests; ruff clean.

**CI push fix (bundled, since it touches the same workflow).** The first real
scheduled run that produced a diff failed at the publish `git push` with "Password
authentication is not supported." Root cause (from the run logs): the token was fine
(`permissions: contents: write` did grant write), but `anthropics/claude-code-action@v1`
removes the auth header `actions/checkout` persisted and rewrites `origin` with its own
non-GitHub token, so the later bare `git push` inherited a broken credential. Fix: push
with an explicit `https://x-access-token:${{ secrets.GITHUB_TOKEN }}@github.com/…` URL,
which is immune to what the action leaves behind. No repo setting change needed; the
YAML `permissions:` block is now load-bearing (repo default is read-only).

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

### 2026-07-09 — V5 (ReliefWeb)

- **ReliefWeb ISO3 comes from the GLIDE suffix, not the country name.** RSS gives
  country *names* (with political variants — "Venezuela (Bolivarian Republic of)")
  in a tag, and the GLIDE (e.g. `EQ-2026-000093-VEN`) whose last field is a clean
  ISO3. We take ISO3 from the GLIDE and keep the names as display-only, never
  matched (blindspot #10). Cost: a multi-country disaster on RSS shows only the
  GLIDE's primary country until the API provides the full list — flagged on the page.
- **No ReliefWeb retractions.** The other feeds guard retractions on `feed_ok`; for
  ReliefWeb we suppress them entirely, because the RSS feed only carries the latest
  ~20 items, so a disaster leaving the feed has aged out of the window, not ended.
  Emitting a "cleared" line there would be the exact "infer ended from absent" error
  (ADR-0007), amplified. Change detection is therefore NEW-only on RSS.
- **ReliefWeb figures are not scraped from prose.** ADR-0008's stacked-and-attributed
  figures ("Govt of X: 120 confirmed dead") require the API's structured fields. On
  RSS we stack the *attributed existence + GLIDE*, not numbers regex'd out of the
  narrative — regexing a casualty count out of prose would be modelling a figure
  (ADR-0002). Full figure-stacking is deferred to the API upgrade, flagged on the page.
- ~~`--reliefweb` opt-in / not in `sitrep.yml`~~ — **done (2026-07-09):** the 08:30
  workflow step now runs `--all-feeds` (USGS + GDACS + ReliefWeb). Verified with a
  live three-feed run producing a full page (6 sudden + 20 ongoing, all feeds ok);
  the `brief.json` `loud` flag the workflow branches on reads correctly. All three
  feeds' state shares `hadr-state.sqlite3` (already cached); each degrades loud
  independently; ReliefWeb's RSS path needs no secret.

### 2026-07-09 — Telegram alerts, Phase 1 (deterministic)

The "(c)" agentic/Telegram feature, built as a **second scheduled workflow**
(`alerts.yml`, ~hourly) on the fast feeds only. Phase 1 is fully deterministic —
**no model is in the alert loop** — matching Shape A (ADR-0002/0005). A later
Phase 2 may let a cheap model (Claude Haiku via `claude-code-action`, the same
provider as the daily narrator) *refine the wording* of an already-composed
message; it will never gain a vote on severity, merges, or whether to fire.

- **The loop reuses the daily pipeline, not a new one.** `scripts/notify.py`
  calls `sitrep.build_report` with USGS + GDACS (ReliefWeb off — it's days-latent,
  so it stays on the daily page, never the alert loop) and reads `report.items`.
  It passes *empty* priors on purpose: the notify loop derives its trigger from its
  OWN "last notified" markers (below), not the daily page's change flags, so the
  page-oriented change detection inside `build_report` is irrelevant here.
- **Chattiness gate (`notify.notify_level`).** The user chose "new event OR
  escalation reaching orange/red." Only orange/red impact reaches a phone;
  sub-orange stays on the daily page (anti-cry-wolf). **Deviation worth flagging:**
  a major earthquake PAGER hasn't scored yet (`alert=None`, so rank 0) would be
  silenced by a pure colour gate — an obvious failure. So an unscored mww-family
  quake at M≥`NOTIFY_MAG_UNSCORED` (6.0) is treated as orange-equivalent *priority*
  (never a severity claim — the message says "not yet scored for impact"). Both
  thresholds are named, tunable constants (CLAUDE.md #1).
- **Idempotency = a `notifications` table (its own Actions cache).** Keyed per
  event (`EQ:<usgs id>` / `GDACS:<type><id>`), storing the last-notified level. A
  tick re-sends only on an *escalation above* that level; a de-escalation or a
  repeat never re-fires. Persisted only *after* a confirmed send — a push that
  errored is not recorded, so it isn't lost. Separate DB from `hadr-state.sqlite3`
  so the two cadences never race on one file.
  - **Caveat (USGS #1):** the USGS top-level id can change between runs; a re-keyed
    quake could, worst case, alert once more. Bounded and rare within an hourly loop
    — accepted for Phase 1 rather than reintroducing the full ids-set match here.
- **Transport = one HTTPS POST (`scripts/telegram.py`), no bot framework / webhook /
  host** (matches the "no always-on host" scope). HTML parse mode; all dynamic text
  `html.escape`d. `requests` imported lazily so the gate + formatter stay
  offline-testable with no token and no network.
- **Config is env-only:** `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (a channel/group),
  optional `NOTIFY_DASHBOARD_URL`. The workflow falls back to `--dry-run` when the
  secrets are absent (forks) so the scheduled job stays green instead of failing.
- **Not yet verified live** (no bot token configured in this repo yet): exercised
  end-to-end via `--dry-run` over the saved fixtures (a real GDACS orange TC
  produced a correct, escaped message) and unit-tested for the gate, idempotency
  (first-sight / same-level / escalation / de-escalation / below-threshold), and
  formatting. Live send pending the `@BotFather` token + channel id — see README.
- **Degrade loud, never crash-loop.** A feed fetch failure degrades to empty items
  (no false alert); a Telegram send failure is logged, leaves the idempotency
  markers *unsaved* (so the event re-fires next tick), and exits 0 — a red X every
  hour on a transient outage would be worse than a retry (mirrors sitrep's loaders).
- **Integrated onto V6 (2026-07-09).** Branched pre-V6; merged `origin/main` (V6
  livelier dashboard + CI push fix). No manual conflicts. Confirmed the semantic
  change that matters here: V6 widened the USGS window to 7 days but `report.items`
  is still the **24h sudden-onset** subset (7-day history is the separate
  `report.recent`), so the alert loop reads exactly the right set — verified by the
  `--dry-run` fixture test exercising the post-V6 `build_report`. Gate green
  (`ruff` + 123 pytest).

### 2026-07-09 — Telegram alerts, Phase 2 (Claude Haiku wording refinement)

Layered the model onto Phase 1 without giving it any say over the trigger or the
numbers (Shape A / ADR-0002/0005). **Substrate: `claude-code-action` with Claude
Haiku** (`claude-haiku-4-5-20251001`) reusing the existing `CLAUDE_CODE_OAUTH_TOKEN`
— same provider and pattern as the daily narrator, **no new secret** (the earlier
GPT-4o idea was dropped once we confirmed the daily narrator already runs Claude).

- **emit → refine → send**, three deterministic-bookended workflow steps mirroring
  the daily narrator's pipeline→model→inject shape:
  1. `notify --emit-dir` runs the pipeline + the deterministic gate and writes
     `brief.json` (honest facts), `message.txt` (the deterministic message — the
     **source of truth and fallback**), and `markers.json`; sets `has_alert`.
     Sends nothing, persists nothing.
  2. `claude-code-action` (Haiku), guarded by `skills/telegram-alert/SKILL.md`,
     rewrites **only the wording** into `message.refined.txt`. `continue-on-error`:
     a missing token (forks) or an API blip just leaves the refined file absent.
  3. `notify --send-dir` sends the refined text **iff it is safe**, else the
     deterministic default; persists markers only after a confirmed send.
- **The refiner can rephrase but not invent (`_refined_is_safe`).** Every numeric
  value in the refined text must already appear in the deterministic message
  (compared by value, so `M6.5`↔`magnitude 6.5` and `08`↔`8` are fine). A novel
  figure — or empty output — is rejected and the default is sent. This makes
  ADR-0002's "consume numbers, never model them" hold *deterministically* even
  though a model touched the string.
- **Decision/send split** is what keeps the model honest: it never runs the gate,
  never sees prior state, and its output passes through a numeric check before a
  byte reaches Telegram. The whole feature still degrades to the Phase-1
  deterministic message if the model is absent or misbehaves.
- The single-process `notify` (no `--emit-dir`/`--send-dir`) path is unchanged — it
  stays the deterministic Phase-1 behaviour for local runs and `--dry-run`.
- Verified end-to-end offline: emit over fixtures → hand-written "refined" message
  (safe and unsafe variants) → send `--dry-run` picks refined-when-safe, falls back
  on an invented figure. Gate green (`ruff` + 127 pytest). Live refinement pending
  the same `CLAUDE_CODE_OAUTH_TOKEN` the daily job uses (already set in this repo).
