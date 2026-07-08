---
shaping: true
---

# HADR Monitor — Breadboard (Shape A)

Concrete affordances and wiring for the selected shape (`SHAPING.md` → Shape A).
Tables are the source of truth; the Mermaid diagram renders them. This is the
whole-product breadboard; `SLICES.md` cuts it into demo-able increments.

Because the only human surface is a **static** `dashboard.html`, UI affordances
have no click-wiring — their "wire" is the data field each renders *from*. All
behaviour lives in the non-UI pipeline.

## Places

- **`dashboard.html`** — the read-only morning page (the only UI surface).
- **GitHub Actions runner** — the scheduled entrypoint (08:30 SGT).
- **`scripts/` pipeline** — the deterministic decision core + the guarded model step.
- **Repo data** — vendored geo data, the SQLite state file, the HTML output.

## UI Affordances (Place: `dashboard.html`)

| ID | Affordance | Renders from |
|----|------------|--------------|
| **U1** | Header: title · window label ("last 24h ending 08:30 SGT") · SGT publish timestamp · coverage banner ("earthquakes only (USGS)…") | N10 ← report meta |
| **U2** | Sudden-onset section (ranked list of event lines) | N10 ← thresholded clusters |
| **U2.1** | Event line: severity chip · what/where (hazard + ISO3 place) · impact figure + source · magnitude descriptor · as-of/age · change-flag (`NEW`/`REVISED ↑`/`CORRECTED`) | N10 ← one cluster record |
| **U3** | Slow-onset / ongoing section (window-exempt crises) | N10 ← ongoing clusters |
| **U4** | Feed-health section: per feed — name · as-of · status (green/red) · outage/degradation note | N10 ← feed-health records |
| **U5** | Nothing-to-report line (only when U2 is empty) | N10 ← empty threshold result |
| **U6** | Correction/retraction line (inline in U2) | N10 ← change-detector deletions/downgrades |
| **U7** | Narrative prose block (loud mornings only) | N11 (model), injected via N10 |

## Non-UI Affordances

| ID | Affordance | Place | Wires out |
|----|------------|-------|-----------|
| **N0** | Cron trigger 08:30 SGT (`sitrep.yml`) | GH Actions | → N1 |
| **N1** | Orchestrator entrypoint | scripts/ | → N2, then N3–N10 |
| **N2** | Ingestion adapters (USGS / GDACS / ReliefWeb) — polite per-feed headers, **log the final URL fetched**, `feed_fetch_succeeded` flag | scripts/ | → N3; → N4 (feed-health) |
| **N3** | Normalizer → common model (nullable `event_time`, ISO3 **list**, UTC attached, provenance per field) | scripts/ | → N4 |
| **N4** | Declusterer (space/time/mag → one sequence) | scripts/ | → N5 |
| **N5** | Cluster resolver — confidence ladder, **EQ identity link first** (`SPIKE-cross-feed-confidence`) | scripts/ | → N7; uses N6 |
| **N6** | Geo module — `iso3_for` / `is_onshore` via ray-casting over D1 (`SPIKE-onshore-geocode`) | scripts/ | used by N3, N5, N7 |
| **N7** | Severity + threshold engine — PAGER/GDACS lookup + slice-1 mag/depth/onshore/`sig≥600`; named constants | scripts/ | → N8 |
| **N8** | State store (SQLite / `sqlite3`) read+write — ADR-0007 minimum | scripts/ | ↔ D2; → N9 |
| **N9** | Change-detector — six loud triggers, `feed_fetch_succeeded` guard | scripts/ | → N10; gates N11, N12 |
| **N10** | Deterministic renderer → writes `dashboard.html` (**always runs**, stamps publish + per-feed as-of) | scripts/ | → D3 → U1–U6 |
| **N11** | Model narrator — `claude -p` running `/sitrep`, prose only, **loud only** | scripts/ | → U7 via N10 |
| **N12** | Notifier — loud only (+ optional daily all-clear ping, R5.1) | scripts/ | → external |

| ID | Data affordance | Place |
|----|-----------------|-------|
| **D1** | Vendored `data/ne_110m_admin_0_countries.geojson` | repo data |
| **D2** | SQLite state file | repo data |
| **D3** | `dashboard.html` output | repo data |

## Wiring

```mermaid
flowchart TD
  subgraph GHA[GitHub Actions runner]
    N0[N0 cron 08:30 SGT]
  end
  subgraph SCRIPTS[scripts/ pipeline]
    N1[N1 orchestrator]
    N2[N2 ingestion adapters]
    N3[N3 normalizer]
    N4[N4 declusterer]
    N5[N5 cluster resolver]
    N6[N6 geo module]
    N7[N7 severity + threshold]
    N8[N8 state store I/O]
    N9[N9 change-detector]
    N10[N10 deterministic renderer]
    N11[N11 model narrator - loud only]
    N12[N12 notifier - loud only]
  end
  subgraph DATA[Repo data]
    D1[(D1 NE geojson)]
    D2[(D2 SQLite state)]
    D3[/D3 dashboard.html/]
  end
  subgraph PAGE[dashboard.html]
    U1[U1 header]
    U2[U2 sudden-onset]
    U3[U3 slow-onset]
    U4[U4 feed-health]
    U5[U5 nothing-to-report]
    U6[U6 corrections]
    U7[U7 narrative prose]
  end

  N0 --> N1 --> N2 --> N3 --> N4 --> N5 --> N7 --> N8 --> N9 --> N10 --> D3
  N6 -. used by .-> N3 & N5 & N7
  D1 --> N6
  N8 <--> D2
  N2 -. feed-health .-> N4
  N9 -- loud --> N11 --> N10
  N9 -- loud --> N12
  D3 --> U1 & U2 & U3 & U4 & U5 & U6
  N11 --> U7
```
