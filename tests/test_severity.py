"""Slice-1 attention threshold (ADR-0004) — tier-1 PAGER + tier-2 fallback."""
from __future__ import annotations

import pytest

from scripts.severity import passes_threshold
from tests.helpers import make_quake


# --- Tier 1: PAGER ran -> trust it (show yellow+, hide green) ---
@pytest.mark.parametrize("alert,expected", [
    ("red", True), ("orange", True), ("yellow", True), ("green", False),
])
def test_tier1_pager_colours(alert, expected):
    assert passes_threshold(make_quake(alert=alert, mag=5.5)) is expected


def test_green_pager_hidden_even_if_large():
    # PAGER rated it low-impact; we don't second-guess it with the mag proxy.
    assert passes_threshold(make_quake(alert="green", mag=6.8, sig=900)) is False


# --- Tier 2: alert None -> magnitude/depth/onshore proxy ---
def test_big_quake_anywhere_shows():
    # M6.5 deep offshore still shows (>= MAG_SHOW_ANYWHERE).
    assert passes_threshold(make_quake(alert=None, mag=6.5, depth_km=400, onshore=False)) is True


def test_shallow_onshore_moderate_shows():
    # DoD boundary: M5.9 shallow onshore.
    assert passes_threshold(make_quake(alert=None, mag=5.9, depth_km=12, onshore=True)) is True


def test_moderate_deep_offshore_hidden():
    assert passes_threshold(make_quake(alert=None, mag=5.5, depth_km=200, onshore=False)) is False


def test_below_onshore_floor_hidden():
    q = make_quake(alert=None, mag=4.9, depth_km=5, onshore=True, sig=100)
    assert passes_threshold(q) is False


def test_magnitude_type_guard():
    # An `mb 6.0` must NOT trip the magnitude gate (types aren't comparable).
    assert passes_threshold(make_quake(alert=None, mag=6.0, mag_type="mb", sig=100)) is False
    # ...but the same size as mww does.
    assert passes_threshold(make_quake(alert=None, mag=6.0, mag_type="mww", sig=100)) is True


def test_sig_is_an_additional_include():
    # Small magnitude, wrong type for the gate, but high sig -> shows.
    assert passes_threshold(make_quake(alert=None, mag=3.0, mag_type="ml", sig=650)) is True
    assert passes_threshold(make_quake(alert=None, mag=3.0, mag_type="ml", sig=599)) is False
