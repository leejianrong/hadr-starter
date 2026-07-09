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
CREATE TABLE IF NOT EXISTS gdacs_events (
    key          TEXT PRIMARY KEY, -- (eventtype, eventid) — ADR-0001 GDACS key
    eventtype    TEXT NOT NULL,
    eventid      INTEGER NOT NULL,
    peak_level   TEXT,             -- last-published peak alert colour
    episode_level TEXT,            -- last-published current-episode colour
    name         TEXT,
    iso3         TEXT,             -- space-joined ISO3 list
    last_seen    TEXT NOT NULL,    -- ISO-8601 UTC
    published    INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS reliefweb_disasters (
    key          TEXT PRIMARY KEY, -- GLIDE (else disaster URL) — ADR-0001 ReliefWeb key
    glide        TEXT,
    url          TEXT,
    title        TEXT,
    hazard_code  TEXT,
    iso3         TEXT,             -- space-joined ISO3 list
    last_seen    TEXT NOT NULL     -- ISO-8601 UTC
);
CREATE TABLE IF NOT EXISTS notifications (
    key         TEXT PRIMARY KEY, -- "EQ:<usgs id>" / "GDACS:<eventtype><eventid>"
    kind        TEXT,             -- EQ / TC / FL / WF … (display only)
    level       INTEGER NOT NULL, -- last-notified notify-level (see notify.notify_level)
    place       TEXT,
    notified_at TEXT NOT NULL     -- ISO-8601 UTC of the last push for this key
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


@dataclass
class GdacsStateRow:
    key: str
    eventtype: str
    eventid: int
    peak_level: str
    episode_level: str
    name: str
    iso3: tuple[str, ...]
    last_seen: datetime
    published: bool


@dataclass
class ReliefWebStateRow:
    key: str
    glide: str
    url: str
    title: str
    hazard_code: str
    iso3: tuple[str, ...]
    last_seen: datetime


@dataclass
class NotifyRow:
    """The last Telegram push we sent for one event — the idempotency marker so the
    ~hourly notify loop never re-blasts the same alert each tick (see scripts.notify).
    `level` is the notify-level last pushed; a later tick only re-sends on an
    escalation *above* it."""

    key: str
    kind: str
    level: int
    place: str
    notified_at: datetime


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

    def load_gdacs(self) -> dict[str, GdacsStateRow]:
        rows = self._conn.execute(
            "SELECT key, eventtype, eventid, peak_level, episode_level, name, iso3, "
            "last_seen, published FROM gdacs_events"
        ).fetchall()
        out: dict[str, GdacsStateRow] = {}
        for r in rows:
            out[r[0]] = GdacsStateRow(
                key=r[0],
                eventtype=r[1] or "",
                eventid=r[2],
                peak_level=r[3] or "",
                episode_level=r[4] or "",
                name=r[5] or "",
                iso3=tuple(s for s in (r[6] or "").split(" ") if s),
                last_seen=datetime.fromisoformat(r[7]),
                published=bool(r[8]),
            )
        return out

    def replace_gdacs(self, rows: list[GdacsStateRow]) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM gdacs_events")
            self._conn.executemany(
                "INSERT INTO gdacs_events (key, eventtype, eventid, peak_level, "
                "episode_level, name, iso3, last_seen, published) VALUES (?,?,?,?,?,?,?,?,?)",
                [
                    (
                        row.key,
                        row.eventtype,
                        row.eventid,
                        row.peak_level,
                        row.episode_level,
                        row.name,
                        " ".join(row.iso3),
                        _iso(row.last_seen),
                        int(row.published),
                    )
                    for row in rows
                ],
            )

    def load_reliefweb(self) -> dict[str, ReliefWebStateRow]:
        rows = self._conn.execute(
            "SELECT key, glide, url, title, hazard_code, iso3, last_seen "
            "FROM reliefweb_disasters"
        ).fetchall()
        out: dict[str, ReliefWebStateRow] = {}
        for r in rows:
            out[r[0]] = ReliefWebStateRow(
                key=r[0],
                glide=r[1] or "",
                url=r[2] or "",
                title=r[3] or "",
                hazard_code=r[4] or "",
                iso3=tuple(s for s in (r[5] or "").split(" ") if s),
                last_seen=datetime.fromisoformat(r[6]),
            )
        return out

    def replace_reliefweb(self, rows: list[ReliefWebStateRow]) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM reliefweb_disasters")
            self._conn.executemany(
                "INSERT INTO reliefweb_disasters (key, glide, url, title, hazard_code, "
                "iso3, last_seen) VALUES (?,?,?,?,?,?,?)",
                [
                    (row.key, row.glide, row.url, row.title, row.hazard_code,
                     " ".join(row.iso3), _iso(row.last_seen))
                    for row in rows
                ],
            )

    def load_notifications(self) -> dict[str, NotifyRow]:
        rows = self._conn.execute(
            "SELECT key, kind, level, place, notified_at FROM notifications"
        ).fetchall()
        out: dict[str, NotifyRow] = {}
        for r in rows:
            out[r[0]] = NotifyRow(
                key=r[0],
                kind=r[1] or "",
                level=int(r[2]),
                place=r[3] or "",
                notified_at=datetime.fromisoformat(r[4]),
            )
        return out

    def upsert_notifications(self, rows: list[NotifyRow]) -> None:
        """Insert-or-update the given markers. Unlike the feed tables this is an
        UPSERT, never a wholesale replace: a key we didn't push this tick must keep
        its prior level so it isn't re-alerted next run."""
        with self._conn:
            self._conn.executemany(
                "INSERT INTO notifications (key, kind, level, place, notified_at) "
                "VALUES (?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET "
                "kind=excluded.kind, level=excluded.level, place=excluded.place, "
                "notified_at=excluded.notified_at",
                [
                    (row.key, row.kind, int(row.level), row.place, _iso(row.notified_at))
                    for row in rows
                ],
            )

    def close(self) -> None:
        self._conn.close()


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()
