"""SQLite state store roundtrip (ADR-0007)."""
from __future__ import annotations

from datetime import datetime, timezone

from scripts.state import StateRow, StateStore

NOW = datetime(2026, 7, 8, tzinfo=timezone.utc)


def _row(**kw):
    defaults = dict(key="k1", ids=frozenset({"a", "b"}), alert="orange", mag=6.1,
                    depth_km=10.0, status="reviewed", lat=1.0, lon=2.0, place="here",
                    last_seen=NOW, published=True)
    defaults.update(kw)
    return StateRow(**defaults)


def test_roundtrip(tmp_path):
    p = tmp_path / "s.sqlite3"
    store = StateStore(p)
    store.replace([_row()])
    store.close()

    loaded = StateStore(p).load()
    assert "k1" in loaded
    r = loaded["k1"]
    assert r.ids == frozenset({"a", "b"})
    assert r.alert == "orange"
    assert r.mag == 6.1
    assert r.published is True
    assert r.last_seen == NOW


def test_replace_overwrites(tmp_path):
    p = tmp_path / "s.sqlite3"
    store = StateStore(p)
    store.replace([_row(key="old")])
    store.replace([_row(key="new")])
    loaded = store.load()
    assert set(loaded) == {"new"}


def test_empty_load(tmp_path):
    assert StateStore(tmp_path / "s.sqlite3").load() == {}
