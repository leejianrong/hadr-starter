# HADR feeds: blindspot pass

A survey of the *unknown unknowns* in building a HADR monitor on GDACS, USGS, and
ReliefWeb — the things you don't know to ask about. The "Open questions" already
in `feeds/*.md` cover the known unknowns; this covers the rest.

Grounded in live fetches of all three feeds on **2026-07-07**. Where a claim was
confirmed by fetching, it's marked; otherwise it's from official docs.

---

## The reframe that reorders everything

The three feeds look like "three views of the same disasters at different quality."
They are not. They are **three different object types**, and almost every hard
problem below descends from this:

| Feed | What one record *is* | Latency | Scope |
|---|---|---|---|
| **USGS** | a *physical event* (one earthquake rupture), machine-generated | seconds | earthquakes only |
| **GDACS** | an *automated impact alert*, versioned over the event's life | minutes | EQ, cyclone, flood, volcano, drought, wildfire |
| **ReliefWeb** | a *human-declared humanitarian situation* (a coordination object) | **days** | everything above **+ epidemics + conflict** |

"Deduplicating" across them is not fuzzy-matching rows in one table. It's entity
resolution across three ontologies with different atomicity. Hold that picture and
the rest follows.

---

## Blindspots at the problem level

### 1. Severity is impact, not magnitude — and this is the whole product
A M7 in the deep ocean can be harmless; a M6 shallow under a poor, dense city is
catastrophic. The real severity signals already exist, computed by people who model
population exposure × building vulnerability × coping capacity:

- **USGS PAGER** (`alert`: green/yellow/orange/red) and **GDACS `alertscore`** (0–3
  → Green/Orange/Red) are your severity axis. Rank on these, with magnitude as a
  *descriptor only*.
- **The alert color is the max of two independent ladders — fatalities OR economic
  loss.** A quake in a rich country can go orange/red on *dollars* with near-zero
  deaths; a poor-country quake goes red on *deaths* with low dollars. Don't collapse
  "red" to "many dead."
  - Fatalities: yellow ≥1, orange ≥100, red ≥1000.
  - Economic loss: yellow ≥$1M, orange ≥$100M, red ≥$1B.
- Both are *probabilistic ranges*, not point estimates. Never publish "≈240 deaths";
  publish the color and the range.

### 2. Your feeds are NOT independent
GDACS's earthquake alerts are *built from USGS/NEIC ShakeMaps* (note `source: NEIC`
in the GDACS sample — that's literally USGS). So a GDACS quake and a USGS quake
"agreeing" is *one source counted twice*, not corroboration. Same for GDACS
`alertscore` vs PAGER. Don't treat feed-agreement as confidence for earthquakes.

### 3. Dedup is N:1:1, not 1:1
One ReliefWeb "disaster" ("Venezuela: Earthquakes - Jun 2026", one GLIDE) covers a
mainshock **plus its whole aftershock sequence** — dozens of USGS `id`s and a
multi-episode GDACS chain. Model the resolved entity as a **cluster** (many USGS
events + one GDACS event-chain + one ReliefWeb disaster) with a confidence score.

Join strategy: **GLIDE when present** (high-precision, *low-recall* — see #4), else a
**space + time + magnitude tolerance box** (~100 km, few minutes, ~±0.5–1.0 M). ISO3
alone is both too coarse (border quakes) and too fine (offshore = no country).

### 4. GLIDE is the intended cross-feed key but it's mostly absent
Format `EQ-2026-000093-VEN` = hazard + year + 6-digit seq + ISO3. But: USGS emits
**none**; GDACS had it on **2/100** live records; it's assigned *weekly* only for
EM-DAT-qualifying events (EM-DAT's own 2025 audit found ~74% of historical events
were *missing* GLIDEs). Trust it when present; treat its absence as meaning nothing.
Never use GLIDE as a primary key or a "this is significant" filter.

### 5. Earthquakes are the *small* story
USGS is earthquake-only, but in 2024 weather events (cyclones ~54%, floods ~42%)
drove 99.5% of *disaster* displacement, and conflict displaced ~73M more. An
earthquake-centric monitor misses most humanitarian caseload. The load-bearing
hazards (floods, cyclones, epidemics, conflict) come from GDACS and ReliefWeb.

### 6. Slow-onset disasters break your schema
Droughts, epidemics, and famines have **no event time, no epicenter, no alert
instant** — they "start" by declaration. A pipeline that assumes every disaster has
a timestamp will silently mishandle the largest crises. Make `event_time` nullable
and distinguish sudden- vs slow-onset as a first-class case.

### 7. Everything you report will change or vanish
USGS `status` goes `automatic` → `reviewed`; magnitude/location shift ±0.5 M and tens
of km on review, hours to days later. Events get **deleted outright** (the Dec-2025
false Reno M5.9) — and in the summary feed a deleted event simply *disappears on
next poll*, it doesn't linger as `status:deleted`. Reporting an automatic solution as
fact is a domain error. Store status, prefer reviewed, label preliminary numbers as
preliminary, and re-resolve rather than caching-and-forgetting.

### 8. Aftershock swarms will flood your sitrep
One mainshock spawns dozens–hundreds of aftershocks; swarms have no mainshock at all.
Reporting each USGS event as its own line is how the report becomes noise. You need
**declustering**: group by space-time-magnitude into one sequence → "mainshock M7.1 +
N aftershocks, largest M6.2."

### 9. "Today's disasters at 08:30 Singapore" is ambiguous
Three clocks: event time (UTC), *local* time at the disaster (the humanitarian-
relevant one — a 3am quake kills more, and PAGER uses it), and your SGT publish time.
"Today" could mean last-24h-rolling, the UTC calendar day, or the SGT calendar day —
each yields different report contents. Pick one, document it (CLAUDE.md deviations
policy applies), and label the window on the report. Slow-onset events don't fit a
daily window at all.

### 10. Country/geocoding is a minefield
Normalize everything to **ISO3** — never string-match names ("Venezuela (Bolivarian
Republic of)", "Congo, Dem. Rep. of the"). Country must be **nullable** (offshore
quakes — some of which cause tsunamis) **and a list** (cyclones/floods span borders).
Expect politically-loaded entities (occupied Palestinian territory, Taiwan, Kosovo).
USGS gives you only lat/lon — you reverse-geocode to ISO3 yourself.

---

## Per-feed operational traps (the afternoon-eaters)

### ReliefWeb
- **The RSS feed 403s your default `requests` User-Agent** (AWS WAF). You *must* set
  a browser-like UA — the RSS analog of the API's appname wall. *(verified live)*
- Three distinct error codes: **missing appname → 400**, **unapproved appname → 403**,
  **v1 → 410**. Handle separately. *(verified live)*
- The appname must be **pre-approved** (Google Form, email confirmation, no published
  SLA, no sandbox) since 1 Nov 2025. You cannot call the API at all until approved —
  plan lead time, build against RSS meanwhile.
- Documented hard quota (on the apidoc *index*, easy to miss): **1000 calls/day,
  1000 rows/call.**
- Naive call returns **10 near-empty records** — default `limit=10`, default
  `profile=minimal`. You must paginate and request `profile=full` or explicit
  `fields[include][]`.
- Status value is **`current`, not "ongoing"** (the UI lies); values
  `alert`/`current`/`past`. (There's also a deprecated boolean `current` field — a
  different thing; don't use it.)
- In RSS, **GLIDE and countries are only in `<category>` tags and double-escaped HTML**
  in `<description>` — no dedicated `<glide>`/`<country>` element, and `type` isn't in
  RSS at all (infer from GLIDE prefix). RSS shows only the latest **20** items,
  unpaginated — a burst can be missed; only the API backfills. *(verified live)*
- Code collisions: Severe Local Storm = `ST`, Land Slide *and* Mud Slide both = `LS`,
  Technological = `AC`.
- RSS `<item>` fields: `title`, `link`, `guid` (= disaster URL), `pubDate` (RFC-822),
  `source`, `description`, `category` (one per related country + one holding the GLIDE
  string matching `^[A-Z]{2}-\d{4}-\d{6}-[A-Z]{3}$`).

### USGS
- **The preferred top-level `id` can CHANGE** when a regional network takes over from
  NEIC. Track events by the full **`ids`** set (comma-delimited *with leading/trailing
  commas* — strip empties), not the top-level `id`, or you'll double-count.
- **Most sizeable events have `alert: null`** — PAGER only runs above ~M5.5. Null alert
  does *not* mean minor. Don't use `alert` presence as an importance filter.
- `sig` is **not** capped at 1000 (that myth is everywhere) — verified 2611. The
  `significant_*` feeds are defined by `sig ≥ 600`, not by alert.
- `tz` is **deprecated, always null** — compute local time yourself. Times are epoch
  **milliseconds** UTC (13 digits).
- **No User-Agent needed** (unlike ReliefWeb) — CDN-fronted static files, CORS open.
  Use `If-Modified-Since` for 304s (there's **no ETag**), send `Accept-Encoding: gzip`,
  and don't poll faster than 60s (that's the regen cadence). *(verified live)*
- Filter `type == "earthquake"` — the feed also carries `quarry blast`, `explosion`,
  `sonic boom`, `ice quake`, etc. (values contain spaces).
- `tsunami: 1` means "in a tsunami-eligible region," **not** "a tsunami occurred" — it
  was `0` even on the M7.5 red events. Don't treat it as a tsunami signal either way.
- Magnitude types (`ml`, `md`, `mb`, `mww`) are **not comparable** — an `mb 4.8` ≠
  `mww 4.8`. Sub-M2.5 events are essentially US-only (network density).
- `coordinates` = `[lon, lat, depth]`, depth in km, **can be negative** (above sea
  level) or fixed at round defaults (0/10/33) when unconstrained.
- `types` field lists attached products (origin, shakemap, dyfi, losspager…) — a cheap
  way to know what downstream detail exists without fetching `detail`.

### GDACS
- **`istemporary`/`iscurrent` are strings** `"true"`/`"false"`, not JSON booleans —
  `x == True` silently fails; test `== "true"`.
- JSON dates have **no timezone designator** (`"2026-07-07T07:16:26"`) but *are* UTC —
  `datetime.fromisoformat` gives a naive value libs then treat as local. Attach UTC
  yourself. RSS uses a *different* format (RFC-822 GMT) — two parsers.
- `alertlevel`/`alertscore` = **peak** for the whole event; `episodealertlevel`/
  `episodealertscore` = **current episode** (can be above *or* below peak). Two icons:
  `iconoverall` (peak) vs `icon` (current) — pick deliberately.
- **`alertscore` means different things in JSON vs RSS** (roughly swapped conventions)
  — don't treat the two feeds' score fields as interchangeable.
- `episodeid` semantics **differ by hazard**: small sequential counter for TC/FL/WF/VO,
  but a huge global ID for EQ. And `getepisodedata?episodeid=N` appears to **ignore the
  episode** and return the current summary — per-episode track data lives in the
  `getgeometry` endpoint.
- Feed is **hard-capped at 100 records, rolling** — an event ages out while still
  active. **Don't infer "event ended" from "absent from feed"**; poll and persist.
  (RSS carries a wider window — ~227 items live — paginate the API via
  `pagenumber`/`pagesize`.)
- **No CORS** → browser-side fetch is blocked, proxy server-side. No key, no observed
  rate limit, default UA fine.
- Live feed is **wildfire-dominated** (78/100 were WF, mostly Green noise). Parse
  `affectedcountries` (array of `{iso2, iso3, countryname}`), not the comma-joined
  `country` string. `glide`/`sourceid`/`eventname` are routinely empty — use `.get()`.
- `severitydata` is per-hazard and unit-heterogeneous (EQ=magnitude, TC=wind km/h,
  WF=burned ha; FL/VO often `severity: 0`). Don't compare `severity` across types.
- Hazard `eventtype` codes: EQ, TC, FL, VO, DR, WF (+ TS). Per-type source: EQ=NEIC,
  TC=JTWC, FL=GLOFAS, WF=GWIS, VO=TOULOUSE.

---

## What this means for how to prompt the agent

The payoff — where these findings turn into sharper instructions:

1. **Decide and state the report window explicitly:** "last 24h ending 08:30 SGT" vs
   "the SGT calendar day." A decision only you can make; everything downstream depends
   on it.
2. **State the attention threshold, not "filter noise":** e.g. *PAGER/GDACS ≥ orange,
   OR yellow with meaningful population exposure, OR anything a human already curated
   onto ReliefWeb.* That last one — *reached ReliefWeb* — is a free, high-quality
   severity signal (editors don't make a page for a harmless quake).
3. **Model the resolved entity as a cluster with a confidence score**, not a 1:1 table.
   Key GDACS on `(eventtype, eventid)`, USGS on the full `ids` set, ReliefWeb on numeric
   `id`; join on GLIDE-then-tolerance-box.
4. **Push determinism into `scripts/`** (CLAUDE.md #1): severity thresholds, declustering,
   ISO3 normalization, and dedup must be deterministic code — a model may draft the
   *prose*, never decide an alert level or a merge.
5. **Carry provenance and never sum across feeds:** "affected" ≠ "displaced" ≠ "killed"
   ≠ "in need"; a USGS-PAGER estimate and a ReliefWeb government figure are two estimates
   of one reality — present both attributed, don't add.
6. **Build against RSS first for both ReliefWeb and GDACS** (ReliefWeb appname approval
   may not land this week); design ingestion so the API is a drop-in upgrade — but note
   RSS loses `status`, `type`, `iso3`, `date.event`, and pagination.

---

## Open decisions to resolve before building

- [x] Report window definition (#1 above) and its timezone label. → **last 24h
      ending 08:30 SGT**, rolling; slow-onset events handled separately.
      (2026-07-08, see `implementation-notes.md`)
- [x] Attention/severity threshold (#2). → **PAGER/GDACS ≥ orange, OR yellow with
      meaningful population exposure, OR anything curated onto ReliefWeb.**
      (2026-07-08)
- [x] Which vertical slice to build first (PRD, Day 2). → **USGS earthquakes,
      end-to-end.** (2026-07-08)
- [ ] Request the ReliefWeb appname now (email approval, no SLA) so the API path is
      unblocked later. **Still outstanding — external action.**

## Sources

Verified by live fetch on 2026-07-07 plus:

- USGS PAGER background / FAQ; GeoJSON Summary Format; ComCat event terms; magnitude types.
- GDACS API quickstart v2; GDACS EQ alert model; Monty/STAC GDACS mapping.
- ReliefWeb API docs (`reliefweb.int/help/api`, `apidoc.reliefweb.int`).
- GLIDE (glidenumber.net); EM-DAT GLIDE update 2025; IDMC GRID 2025 (displacement figures).
