Deterministic checks live here — anything that must give the same answer twice does not belong in a prompt.

## V1 pipeline (USGS earthquakes → dashboard.html)

Shape A, deterministic layer only (no model, no state, no schedule yet). Data
flows left to right; each module is pure except `usgs.fetch` and the file write.

| Module | Role |
|--------|------|
| `model.py` | Value objects (`Quake`, `Cluster`, `GdacsEvent`, `ReportItem`, `FeedHealth`, `Report`), SGT + the epoch-ms / naive-UTC / RFC-822 parsers |
| `usgs.py` | Fetch (`requests`, lazy) + parse/normalize the USGS GeoJSON feed |
| `gdacs.py` | GDACS multi-hazard adapter (V4) — **RSS-first**, JSON drop-in; handles every GDACS parsing trap |
| `reliefweb.py` | ReliefWeb curated-disaster adapter (V5) — **RSS-first**, browser-UA; GLIDE/ISO3/hazard from the description |
| `geo.py` | Offline reverse-geocode + onshore (ray-casting over vendored Natural Earth) |
| `decluster.py` | Group a mainshock + aftershocks into one sequence; flag swarms |
| `cluster.py` | Cross-feed join (V4/V5) — confidence ladder + EQ identity link, ReliefWeb GLIDE stacking (ADR-0001) |
| `severity.py` | Impact-based attention threshold (ADR-0004) + GDACS colour threshold; named constants |
| `state.py` | SQLite persistence between runs (ADR-0007) — last-published per cluster + GDACS event |
| `changes.py` | Loud-change triggers vs prior state (ADR-0006); USGS + GDACS; `feed_ok` guard |
| `render.py` | Deterministic four-section HTML + flags + heartbeat + `<!--NARRATIVE-->` slot |
| `sitrep.py` | Orchestrator / CLI (state, `--brief` for the narrator, persists on good fetch) |
| `inject.py` | Deterministically inject the model's prose into the narrative slot (escaped) |

The model narrator is **not** here — it lives in the `/sitrep` skill
(`skills/sitrep/SKILL.md`), invoked only on a loud change by
`.github/workflows/sitrep.yml`. The model writes prose to `narrative.md`;
`inject.py` places it. The model never touches the HTML, the numbers, or the
decision to run.

Run:

```
uv run python -m scripts.sitrep                        # live USGS fetch → dashboard.html
uv run python -m scripts.sitrep --gdacs                # + live GDACS (RSS) multi-hazard join
uv run python -m scripts.sitrep --fixture F            # offline USGS, from a saved payload
uv run python -m scripts.sitrep --fixture F \
    --gdacs-fixture G.xml                              # offline USGS + GDACS RSS
uv run python -m scripts.sitrep --fixture F \
    --gdacs-json-fixture G.json                        # offline USGS + GDACS JSON (drop-in)
uv run python -m scripts.sitrep --all-feeds             # live USGS + GDACS + ReliefWeb
uv run python -m scripts.sitrep --fixture F \
    --gdacs-json-fixture G.json \
    --reliefweb-fixture R.xml                          # offline all three feeds
uv run pytest                                           # tests (offline, fixtures)
```

Constants to tune (all model-free): thresholds in `severity.py`
(`MAG_SHOW_ANYWHERE`, `MAG_SHOW_ONSHORE`, `DEPTH_SHALLOW_KM`, `SIG_INCLUDE`,
`GDACS_SHOW_RANK`), declustering in `decluster.py` (`DECLUSTER_KM`,
`SWARM_DOMINANCE_M`), and the cross-feed tolerance box in `cluster.py`
(`SPACE_*_KM`, `TIME_*_MIN`, `MAG_*_M`).
