# CONTEXT — shared language for the HADR Monitor

The vocabulary the PRD, the code, and the reports all use with one meaning.
Produced by the grill step (persona: Maya, OCHA sitrep veteran) from `REQS.md`,
`feeds/*.md`, and `docs/feed-blindspots.md`. Decisions with alternatives live in
`docs/adr/`; this file just fixes terms.

---

## The feeds are three object types, not three views

| Feed | One record *is* | Latency | Scope | Keyed on |
|---|---|---|---|---|
| **USGS** | a physical event (one rupture), machine-made | seconds | earthquakes only | full `ids` set (not top-level `id`) |
| **GDACS** | an automated, versioned impact alert | minutes | EQ, TC, FL, VO, DR, WF | `(eventtype, eventid)` + episode chain |
| **ReliefWeb** | a human-declared humanitarian situation | **days** | above **+ epidemics + conflict** | numeric `id` (+ GLIDE if present) |

The feeds are **not independent**: GDACS earthquakes are built from USGS/NEIC, so
feed-agreement is *not* corroboration for quakes.

## Core terms

- **Event (reader-facing):** one **resolved cross-feed cluster** — the humanitarian
  situation, not the physical rupture. A mainshock + its aftershocks + the GDACS
  episode chain + the ReliefWeb page are **one line**. See ADR-0001.
- **Cluster:** the internal resolved entity — many USGS events + one GDACS
  event-chain + one ReliefWeb disaster — carrying a **confidence score** for the
  join. Joined on **GLIDE when present** (high-precision, low-recall), else a
  **space+time+magnitude tolerance box** (~100 km, minutes, ±0.5–1.0 M).
- **The sitrep / report:** a **full standing report regenerated daily**, not a
  diff. Within it, new/changed items carry a delta flag (`NEW`, `REVISED ↑`) so
  the eye finds the change fast. The report *is* `dashboard.html`.
- **Severity:** **impact, not magnitude.** Ranked on PAGER `alert` /
  GDACS `alertscore` (green/yellow/orange/red). The colour is the **max of two
  independent ladders — fatalities OR economic loss** — so "red" ≠ "many dead."
  Both are **probabilistic ranges**, never point estimates. Magnitude is a
  descriptor only. We **consume** this judgement; we never model it (ADR-0002).
- **Attention-worthy:** clears the threshold in ADR-0004 — PAGER/GDACS ≥ orange,
  OR yellow with meaningful population exposure, OR **anything a human curated
  onto ReliefWeb** (the free, high-quality "an editor made a page" signal).
- **Window:** **last 24h rolling, ending at the 08:30 SGT publish time**,
  labelled on every report. Boundary computed in SGT (UTC+8, no DST); timestamps
  stored UTC. Governs the **sudden-onset** section only (ADR-0003).
- **Slow-onset / ongoing:** droughts, epidemics, conflict displacement — **no
  event_time, no epicentre**. `event_time` is **nullable, first-class**. Exempt
  from the window; live in the always-on ongoing section while their ReliefWeb
  status is `alert`/`current`; leave when marked `past` (ADR-0003).
- **Quiet / "nothing changed":** the **model stays asleep and no notification
  fires** — *not* "the page goes stale." The deterministic layer **always
  regenerates `dashboard.html`** at 08:30 with a fresh timestamp and feed-health.
  The **page timestamp is the heartbeat**: stamped today = healthy quiet night;
  still stamped yesterday = cron died. See ADR-0005.
- **Loud (a change worth the model):** any of **six boolean triggers** — new
  attention-worthy event, upward severity escalation, significant mag/location
  review, status automatic→reviewed on a shown event, deletion/retraction,
  slow-onset status change. Tunable constants (0.3 M, 50 km) live in `scripts/`.
  See ADR-0006.
- **Degrade loud, never silent:** a data gap or outage is **stated on the report**
  (feed-health section, per-feed "as of" time, coverage banners), never hidden.
  A silent gap reads as "quiet night" and is the cardinal sin (ADR-0007).
- **Provenance:** every figure carries its source and is **never summed across
  feeds**. "affected" ≠ "displaced" ≠ "killed" ≠ "in need." Disagreeing estimates
  (PAGER modelled vs a government count via ReliefWeb) are shown **stacked and
  attributed**, never merged, never one struck through (ADR-0008).

## Report anatomy (fixed)

**One line, left→right:** `[severity colour chip] · what & where (hazard + ISO3
place) · headline impact figure w/ source · magnitude/descriptor · age/"as of" ·
change-flag`. The eye lands first on **colour + place**. Casualty numbers never
lead (preliminary, probabilistic).

**Sections, always in this order:**
1. **Sudden-onset, last 24h** — ranked attention-worthy events.
2. **Slow-onset / ongoing** — always-on; droughts, epidemics, conflict.
3. **Feed health** — one line per feed with "as of" time and any outage. Never
   optional.
4. **Nothing-to-report** — shown only when section 1 is empty, as an explicit
   line ("No new sudden-onset events crossed threshold in the last 24h"), never a
   blank page.

## Trust rules

- **Publish preliminary-and-labelled, correct later** — a morning sitrep can't
  wait hours for `reviewed` status. Tag automatic solutions "preliminary
  (automatic)"; re-resolve and issue a correction if numbers move (ADR-0009).
- **Corrections are explicit, never silent.** A previously-published event that is
  downgraded or deleted gets a visible retraction line — the reader briefed their
  principal on it yesterday (ADR-0009).
- **The reader forgives a false positive over a miss** — tune toward inclusion at
  the margins — *provided* every false positive is loudly corrected.
- **The renderer refuses a bare casualty integer** — a number renders only wrapped
  in its source + range language + preliminary flag.

## Slice-1 vocabulary (USGS-only, first build)

- **Slice-1 threshold:** two-tier deterministic fallback (ADR-0004): Tier 1 =
  PAGER `alert` when present; Tier 2 (the `alert:null` majority) = **mww-family
  M ≥ 6.0 anywhere, OR M ≥ 5.0 with depth ≤ 70 km AND onshore/within ~100 km of a
  populated landmass**, with `sig ≥ 600` as an *additional* include. Magnitude-type
  guard: only trip the gate on `mww`/`mw`-family readings.
- **Known slice-1 blindspots (stated on the dashboard):** misses a shallow
  moderate quake under a poor dense city that PAGER hasn't scored; over-includes
  harmless deep-ocean large quakes (forgivable); and by construction covers **no**
  floods, cyclones, epidemics, or conflict. Banner: *"Coverage: earthquakes only
  (USGS). No flood/cyclone/epidemic/conflict monitoring yet."*
