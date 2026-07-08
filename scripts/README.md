Deterministic checks live here — anything that must give the same answer twice does not belong in a prompt.

## V1 pipeline (USGS earthquakes → dashboard.html)

Shape A, deterministic layer only (no model, no state, no schedule yet). Data
flows left to right; each module is pure except `usgs.fetch` and the file write.

| Module | Role |
|--------|------|
| `model.py` | Value objects (`Quake`, `Cluster`, `FeedHealth`, `Report`), SGT, `from_ms` |
| `usgs.py` | Fetch (`requests`, lazy) + parse/normalize the GeoJSON feed |
| `geo.py` | Offline reverse-geocode + onshore (ray-casting over vendored Natural Earth) |
| `decluster.py` | Group a mainshock + aftershocks into one sequence; flag swarms |
| `severity.py` | Impact-based attention threshold (ADR-0004), named constants |
| `state.py` | SQLite persistence between runs (ADR-0007) — last-published per cluster |
| `changes.py` | Six loud-change triggers vs prior state (ADR-0006); `feed_ok` guard |
| `render.py` | Deterministic four-section HTML + NEW/REVISED/CORRECTED flags + heartbeat |
| `sitrep.py` | Orchestrator / CLI entrypoint (loads state, persists on good fetch) |

Run:

```
uv run python -m scripts.sitrep                 # live USGS fetch → dashboard.html
uv run python -m scripts.sitrep --fixture F     # offline, from a saved payload
uv run pytest                                    # tests (offline, fixtures)
```

Constants to tune (all model-free): thresholds in `severity.py`
(`MAG_SHOW_ANYWHERE`, `MAG_SHOW_ONSHORE`, `DEPTH_SHALLOW_KM`, `SIG_INCLUDE`) and
declustering in `decluster.py` (`DECLUSTER_KM`, `SWARM_DOMINANCE_M`).
