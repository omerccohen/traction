"""Phase 3 tests: indicator cache append-only semantics, transforms,
threshold evaluation, dashboard rendering — all offline (fixture data)."""
import numpy as np
import pandas as pd
import pytest

import stocklab.indicators.base as ib
from stocklab.indicators.base import Indicator, load_registry, dashboard_markdown


@pytest.fixture()
def sandbox_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(ib, "CACHE_DIR", tmp_path)
    return tmp_path


def _write_cache(tmp_path, name, dates, values):
    df = pd.DataFrame({"date": pd.to_datetime(dates), "value": values,
                       "retrieved_at": "2026-01-01T00:00:00+00:00"})
    (tmp_path / f"{name}.csv").parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(tmp_path / f"{name}.csv", index=False)


def test_registry_loads():
    inds = load_registry()
    names = [i.name for i in inds]
    assert "semis_industrial_production" in names and "hy_credit_spread" in names
    assert all(i.source == "fred" for i in inds)


def test_yoy_transform_and_trigger(sandbox_cache):
    # monthly series rising 10%/yr then contracting -> yoy < 0 triggers
    dates = pd.date_range("2020-01-01", periods=40, freq="MS")
    values = list(np.linspace(100, 130, 30)) + list(np.linspace(129, 118, 10))
    _write_cache(sandbox_cache, "semis_ip", dates, values)
    ind = Indicator("semis_ip", {
        "source": "fred", "series_id": "X", "transform": "yoy",
        "thresholds": {"elevated": "value < 0.02", "triggered": "value < 0"},
    })
    st = ind.status()
    assert st.transformed_value < 0
    assert st.threshold_state == "TRIGGERED"


def test_level_pctile_threshold(sandbox_cache):
    dates = pd.date_range("2020-01-01", periods=260, freq="W")
    values = list(np.random.default_rng(0).normal(4.0, 0.3, 255)) + [6.0, 6.2, 6.4, 6.6, 7.0]
    _write_cache(sandbox_cache, "hy", dates, values)
    ind = Indicator("hy", {
        "source": "fred", "series_id": "X", "transform": "level",
        "thresholds": {"elevated": "pctile > 0.8", "triggered": "pctile > 0.95"},
    })
    st = ind.status()
    assert st.threshold_state == "TRIGGERED" and st.pctile_5y >= 0.95


def test_no_data_state(sandbox_cache):
    ind = Indicator("ghost", {"source": "fred", "series_id": "X"})
    st = ind.status()
    assert st.threshold_state == "NO_DATA"


def test_refresh_appends_not_rewrites(sandbox_cache, monkeypatch):
    _write_cache(sandbox_cache, "s1", ["2025-01-01", "2025-02-01"], [1.0, 2.0])

    def fake_fetch(series_id):
        return pd.DataFrame({
            "date": pd.to_datetime(["2025-01-01", "2025-02-01", "2025-03-01"]),
            # revised history (1.5 vs stored 1.0) must NOT overwrite the cache
            "value": [1.5, 2.0, 3.0],
        })
    monkeypatch.setitem(ib.FETCHERS, "fred", fake_fetch)
    ind = Indicator("s1", {"source": "fred", "series_id": "X"})
    assert ind.refresh() == "fresh"
    s = ind.series()
    assert len(s) == 3
    assert s.loc[pd.Timestamp("2025-01-01")] == 1.0   # original retained
    assert s.loc[pd.Timestamp("2025-03-01")] == 3.0   # new appended


def test_dashboard_renders_without_data(sandbox_cache):
    inds = [Indicator("ghost", {"source": "fred", "series_id": "X"})]
    md = dashboard_markdown(inds)
    assert "NO_DATA" in md and "network policy blocks" in md
