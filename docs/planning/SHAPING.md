---
shaping: true
---

# HADR Monitor — Shaping

Working document for requirements (R), shapes (S), and the fit check. Frame lives
in `FRAME.md`; decisions in `docs/adr/`. Ground truth for R and shapes.

## Requirements (R)

Proposed starting set derived from `docs/PRD.md` + `CONTEXT.md` + ADRs. Statuses
are negotiable — this is a starting point, not a fixed list. (🟡 = new this pass.)

| ID | Requirement | Status |
|----|-------------|--------|
| 🟡 **R0** | **Publish a skimmable morning situation report to `dashboard.html` at 08:30 SGT, ranked by human impact.** | Core goal |
| 🟡 R0.1 | Windowed **sudden-onset** section = last 24h rolling ending 08:30 SGT, window labelled on the page | Must-have |
| 🟡 R0.2 | Always-on **slow-onset / ongoing** section — `event_time` nullable, window-exempt (drought/epidemic/conflict) | Must-have |
| 🟡 R0.3 | Fixed four-section anatomy: sudden-onset · slow-onset · feed-health · nothing-to-report (never a blank page) | Must-have |
| 🟡 **R1** | **Honest impact figures:** severity consumed from PAGER/GDACS (never modelled), magnitude is descriptor only, numbers shown as ranges not points, provenance carried, **never summed across feeds** | Must-have |
| 🟡 **R2** | **Deterministic attention threshold** — orange+ / exposed-yellow / reached-ReliefWeb — including an honest USGS-only slice-1 fallback (mag+depth+onshore, sig≥600) | Must-have |
| 🟡 **R3** | **Cross-feed clustering (N:1:1) with a confidence score**, plus aftershock **declustering** into one line ("mainshock + N aftershocks, largest M6.2") | Must-have |
| 🟡 **R4** | **Multi-hazard coverage** — floods, cyclones, epidemics, conflict via GDACS + ReliefWeb, not earthquake-only (the load-bearing caseload) | Must-have |
| 🟡 **R5** | **Quiet-but-alive** — deterministic layer regenerates the page every morning (timestamp = heartbeat); the expensive model wakes only on a loud change | Must-have |
| 🟡 R5.1 | Daily lightweight **all-clear ping** on quiet mornings (deterministic, no model) so absence-of-ping means failure | Undecided |
| 🟡 **R6** | **Deterministic change detection** — six loud triggers (new/escalation/review/reviewed/deletion/slow-onset) — over **persisted state** that catches revisions and silent deletions | Must-have |
| 🟡 **R7** | **Degrade loud** — feed-health section, per-feed "as of", coverage banners, explicit corrections; never infer "event ended" from "absent from feed" | Must-have |
| 🟡 **R8** | **Engineering constraints** — deterministic logic in `scripts/` never calls a model; Python 3.12 stdlib-first; runs unattended on schedule; tested via pytest fixtures (offline) | Must-have |

**Notes:**
- R4 is deliberately listed as Must-have even though **slice 1 (USGS-only) does
  not satisfy it** — that gap is real and the fit check should show it, rather
  than hide it behind the scoping decision.
- R5.1 (all-clear ping) is the one genuinely Undecided item — an owner call
  recorded in ADR-0005.
- Chunking: R0 is chunked (R0.1–R0.3) to keep the top level at 9 items.

---

## Shapes (S)

Three mutually-exclusive architectures. They share the deterministic decision core
(ingest → normalize → decluster/cluster → severity/threshold → state/change-detect);
they differ on **where the model sits** and **polling cadence**. `⚠️` = mechanism
described but not yet concretely known (a spike resolves it).

### A: Deterministic render, model narrates only

Single once-a-day run. Every *decision and the HTML itself* is Python in `scripts/`.
The model writes prose only, injected into a fully-templated page. Quiet mornings
are byte-stable (pure template), so the timestamp heartbeat and git-diffs are clean.

| Part | Mechanism | Flag |
|------|-----------|:----:|
| **A1** | Per-feed ingestion adapters — polite headers per feed (USGS `If-Modified-Since`/gzip/no-UA; GDACS default-UA server-side; ReliefWeb browser-UA, RSS-first); log the final URL fetched | |
| **A2** | Normalizer → common model: nullable `event_time`, ISO3 country **list**, UTC attached (USGS epoch-ms, GDACS naive-UTC, RSS RFC-822), provenance per field | |
| **A3** | Declusterer + cross-feed cluster resolver — space/time/mag declustering to one sequence; cluster keyed per ADR-0001 with a **confidence ladder** (`certain`/`high`/`medium`/`low`; EQ identity link first) → `SPIKE-cross-feed-confidence.md` | |
| **A4** | Severity + threshold engine — PAGER/GDACS lookup; orange+/exposed-yellow/reached-ReliefWeb; slice-1 mag+depth+onshore & `sig≥600` fallback; onshore via vendored Natural Earth GeoJSON + pure-Python ray-casting → `SPIKE-onshore-geocode.md`; constants in `scripts/` | |
| **A5** | State store (**SQLite**) + change-detector — persist ADR-0007 minimum; six loud triggers with the `feed_fetch_succeeded` guard | |
| **A6** | Deterministic HTML renderer — Python templates, four fixed sections, **always runs**, stamps SGT publish + per-feed "as of"; byte-stable on quiet mornings | |
| **A7** | Model narrator — headless `claude -p` running `/sitrep` skill, **prose only** for loud changes, injected into A6 output; skipped when quiet | |
| **A8** | Orchestration — GitHub Actions cron 08:30 SGT; deterministic steps always run; model+notify step guarded on the change-detector exit | |

### B: Model assembles the report from a deterministic bundle

Decisions stay deterministic and emit a JSON **sitrep bundle**; the model then
builds the *entire* `dashboard.html` (layout, prose, within-section ordering) from
the bundle on a loud change. Richer presentation — but the model is now in the
number-rendering path.

| Part | Mechanism | Flag |
|------|-----------|:----:|
| **B1** | Per-feed ingestion adapters — as A1 | |
| **B2** | Normalizer — as A2 | |
| **B3** | Declusterer + cross-feed cluster resolver — as A3 | ⚠️ |
| **B4** | Severity + threshold engine → emits a structured **sitrep bundle** (JSON: clusters, severities, changes, feed-health) | ⚠️ |
| **B5** | State store + change-detector — as A5 | |
| **B6** | Model report-assembler — `claude -p` builds the **full** `dashboard.html` from the bundle on loud change | |
| **B7** | Output validator + quiet fallback renderer — schema/number-integrity check on the model's HTML (no bare casualty integer, ranges intact, provenance present); deterministic fallback when model absent/invalid | ⚠️ |
| **B8** | Orchestration — as A8 | |

### C: Continuous collector + daily reporter (two processes)

Decouple polling from reporting: a frequent collector persists everything and
detects change continuously; a separate daily reporter renders at 08:30. Best
silent-deletion / rolling-feed-ageout robustness — at the cost of always-on infra.

| Part | Mechanism | Flag |
|------|-----------|:----:|
| **C1** | Collector process — frequent poll (~15–60 min), persist raw + normalized continuously | ⚠️ |
| **C2** | Normalizer — as A2 | |
| **C3** | Continuous declusterer + cluster resolver — clusters updated every collection | ⚠️ |
| **C4** | Severity + threshold engine — as A4 | ⚠️ |
| **C5** | State store + continuous change-log — every transition recorded as it happens | |
| **C6** | Daily reporter — at 08:30 reads state only (no fetching), selects window + sections | |
| **C7** | Deterministic renderer + model narrator — as A6 + A7 | |
| **C8** | Orchestration — **two** schedules (frequent collector + daily reporter) | ⚠️ |

---

## Fit Check v1 (all shapes, pre-spike)

| Req | Requirement | Status | A | B | C |
|-----|-------------|--------|:-:|:-:|:-:|
| R0 | Publish a skimmable morning sitrep to `dashboard.html` at 08:30 SGT, ranked by human impact | Core goal | ✅ | ✅ | ✅ |
| R0.1 | Sudden-onset section = last 24h rolling ending 08:30 SGT, window labelled | Must-have | ✅ | ✅ | ✅ |
| R0.2 | Always-on slow-onset/ongoing section — `event_time` nullable, window-exempt | Must-have | ✅ | ✅ | ✅ |
| R0.3 | Fixed four-section anatomy; never a blank page | Must-have | ✅ | ✅ | ✅ |
| R1 | Honest impact figures — consumed not modelled, ranges not points, provenance carried, never summed | Must-have | ✅ | ❌ | ✅ |
| R2 | Deterministic attention threshold incl. honest USGS-only slice-1 fallback | Must-have | ❌ | ❌ | ❌ |
| R3 | Cross-feed clustering (N:1:1) with confidence + aftershock declustering | Must-have | ❌ | ❌ | ❌ |
| R4 | Multi-hazard coverage — floods/cyclones/epidemics/conflict via GDACS+ReliefWeb | Must-have | ✅ | ✅ | ✅ |
| R5 | Quiet-but-alive — page regenerates every morning (heartbeat); model only on loud change | Must-have | ✅ | ✅ | ✅ |
| R5.1 | Daily all-clear ping on quiet mornings | Undecided | ✅ | ✅ | ✅ |
| R6 | Deterministic change detection (six triggers) over persisted state catching revisions/deletions | Must-have | ✅ | ✅ | ✅ |
| R7 | Degrade loud — feed-health, per-feed as-of, coverage banners, explicit corrections | Must-have | ✅ | ✅ | ✅ |
| R8 | Engineering — determinism in `scripts/`, Python 3.12 stdlib-first, unattended schedule, pytest fixtures | Must-have | ✅ | ✅ | ❌ |

**Notes:**

- **B fails R1** — putting the model in the HTML-rendering path (B6) means it can
  restate a range as a point, drop a provenance tag, or fabricate a figure.
  Guaranteeing honest numbers then depends on the flagged validator **B7 ⚠️**, so
  the claim of knowledge fails. This is exactly why ADR-0002/0008 keep numbers
  deterministic.
- **C fails R8** — the continuous collector (C1) needs reliable sub-hourly
  scheduling / an always-on host, which the starter's GitHub Actions cron does not
  provide (C8 ⚠️, ~5-min-granularity, not guaranteed on-time, per-minute cost).
  C's real advantage — catching an event that appears *and* disappears within a
  day — is **not a current requirement**, so its extra cost buys nothing R asks
  for. (If an always-on host existed, revisit.)
- **R2 fails for all three** — the threshold *logic* is known, but the
  "onshore / within ~100 km of a populated landmass" test needs an offline dataset
  + point-in-polygon that isn't yet concrete (**A4/B4/C4 ⚠️**). Not a
  discriminator — a **spike** resolves it regardless of shape.
- **R3 fails for all three** — aftershock *declustering* is known, but the
  **cross-feed confidence score** calibration (GLIDE-then-tolerance-box → a number)
  isn't concrete (**A3/B3/C3 ⚠️**). Also a **spike**, not a discriminator. (Slice 1
  is single-feed, so this doesn't block the first build.)
- **R4 passes for all** at the *architecture* level (every shape has GDACS +
  ReliefWeb adapters). Slice 1 being earthquake-only is a **slicing** matter, not a
  shape failure — it surfaces in the slice plan, not here.

**Reading:** Only **A** has no shape-unique failure. B and C each fail one
Must-have on their differentiating mechanism. R2 and R3 are shared spike-items that
any selected shape must resolve.

---

## Selected shape: A — Deterministic render, model narrates only

Picked 2026-07-08. Rationale: no shape-unique fit failure; the model never touches
numbers (satisfies R1 by construction); the quiet page is byte-stable so the
heartbeat (R5) and git-diffs are clean; fits the starter's GitHub Actions cron
(R8) with no always-on host. The two shared unknowns were resolved by spikes:

- **R2 / A4** → `SPIKE-onshore-geocode.md`: vendored Natural Earth Admin-0 GeoJSON
  + pure-Python ray-casting gives point→ISO3 and onshore with **zero runtime
  dependency**; slice-1 "populated-landmass" == onshore, population-distance
  refinement deferred to v2 and stated on the page.
- **R3 / A3** → `SPIKE-cross-feed-confidence.md`: a deterministic confidence
  **ladder** (`certain`/`high`/`medium`/`low`) with the earthquake **identity
  link** (GDACS-EQ ⊂ USGS/NEIC) checked first; per-level report behaviour
  (merge / "likely same" / "possibly related", never a silent low-confidence
  merge).

## Fit Check v2 (R × A, post-spike)

| Req | Requirement | Status | A |
|-----|-------------|--------|:-:|
| R0 | Publish a skimmable morning sitrep to `dashboard.html` at 08:30 SGT, ranked by human impact | Core goal | ✅ |
| R0.1 | Sudden-onset section = last 24h rolling ending 08:30 SGT, window labelled | Must-have | ✅ |
| R0.2 | Always-on slow-onset/ongoing section — `event_time` nullable, window-exempt | Must-have | ✅ |
| R0.3 | Fixed four-section anatomy; never a blank page | Must-have | ✅ |
| R1 | Honest impact figures — consumed not modelled, ranges not points, provenance carried, never summed | Must-have | ✅ |
| R2 | Deterministic attention threshold incl. honest USGS-only slice-1 fallback | Must-have | 🟡 ✅ |
| R3 | Cross-feed clustering (N:1:1) with confidence + aftershock declustering | Must-have | 🟡 ✅ |
| R4 | Multi-hazard coverage — floods/cyclones/epidemics/conflict via GDACS+ReliefWeb | Must-have | ✅ |
| R5 | Quiet-but-alive — page regenerates every morning (heartbeat); model only on loud change | Must-have | ✅ |
| R5.1 | Daily all-clear ping on quiet mornings | Undecided | ✅ |
| R6 | Deterministic change detection (six triggers) over persisted state catching revisions/deletions | Must-have | ✅ |
| R7 | Degrade loud — feed-health, per-feed as-of, coverage banners, explicit corrections | Must-have | ✅ |
| R8 | Engineering — determinism in `scripts/`, Python 3.12 stdlib-first, unattended schedule, pytest fixtures | Must-have | ✅ |

🟡 R2 and R3 moved ❌→✅ for A after the spikes. **Shape A now passes every
requirement with no remaining ⚠️.**

## Detail A (C7 — no flags remaining)

All eight parts of Shape A have concrete mechanisms; the two former ⚠️ are
resolved above. Decisions locked while detailing (rippled to ADRs):

- **State store = SQLite** (A5) — resolves the open owner-decision in ADR-0007
  (stdlib `sqlite3`, queryable revision history, no dependency).
- **Geo data asset = vendored `data/ne_110m_admin_0_countries.geojson`** (A4) —
  data, not a code dependency; serves ISO3 normalization and the onshore test.
- **Cross-feed join = confidence ladder** (A3) — see spike; lands with feed #2.

Remaining owner-decision (non-blocking, not a flag): **R5.1 daily all-clear ping**
(ADR-0005, recommend yes).

The concrete affordance breakdown (UI/Non-UI affordance tables + wiring) is
**Step D — breadboarding**, whose `/breadboarding` skill is not installed in this
environment (see next-steps note in chat).
