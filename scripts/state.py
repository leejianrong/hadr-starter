"""Persistent state between runs — SQLite (ADR-0007).

Remembers what we last *published* per cluster, so the change-detector can spot
revisions and silent deletions the feed won't tell us about (ADR-0006). Stdlib
`sqlite3`, no dependency. Keyed by a stable cluster key; events are matched across
runs by their USGS `ids` set (the top-level id can change — USGS #1).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PATH = "hadr-state.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS clusters (
    key        TEXT PRIMARY KEY,   -- stable cluster key (mainshock id at first sight)
    ids        TEXT NOT NULL,      -- space-joined USGS ids set (match across runs)
    alert      TEXT,               -- last-published PAGER colour or NULL
    mag        REAL,
    depth_km   REAL,
    status     TEXT,               -- automatic / reviewed
    lat        REAL,
    lon        REAL,
    place      TEXT,
    last_seen  TEXT NOT NULL,      -- ISO-8601 UTC
    published  INTEGER NOT NULL    -- 1 if it was shown on the page
);
"""


@dataclass
class StateRow:
    key: str
    ids: frozenset[str]
    alert: str | None
    mag: float | None
    depth_km: float | None
    status: str
    lat: float | None
    lon: float | None
    place: str
    last_seen: datetime
    published: bool


class StateStore:
    """Thin SQLite wrapper: load all rows, replace with a new set."""

    def __init__(self, path: str | Path = DEFAULT_PATH):
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.executescript(_SCHEMA)

    def load(self) -> dict[str, StateRow]:
        rows = self._conn.execute(
            "SELECT key, ids, alert, mag, depth_km, status, lat, lon, place, "
            "last_seen, published FROM clusters"
        ).fetchall()
        out: dict[str, StateRow] = {}
        for r in rows:
            out[r[0]] = StateRow(
                key=r[0],
                ids=frozenset(s for s in (r[1] or "").split(" ") if s),
                alert=r[2],
                mag=r[3],
                depth_km=r[4],
                status=r[5] or "",
                lat=r[6],
                lon=r[7],
                place=r[8] or "",
                last_seen=datetime.fromisoformat(r[9]),
                published=bool(r[10]),
            )
        return out

    def replace(self, rows: list[StateRow]) -> None:
        """Overwrite the table with exactly these rows (the new source of truth)."""
        with self._conn:
            self._conn.execute("DELETE FROM clusters")
            self._conn.executemany(
                "INSERT INTO clusters (key, ids, alert, mag, depth_km, status, lat, lon, "
                "place, last_seen, published) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        row.key,
                        " ".join(sorted(row.ids)),
                        row.alert,
                        row.mag,
                        row.depth_km,
                        row.status,
                        row.lat,
                        row.lon,
                        row.place,
                        _iso(row.last_seen),
                        int(row.published),
                    )
                    for row in rows
                ],
            )

    def close(self) -> None:
        self._conn.close()


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()
