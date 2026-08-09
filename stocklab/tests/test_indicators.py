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
    assert "vix_level" in names                      # live github_csv source
    assert all(i.source in ("fred", "github_csv") for i in inds)


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


def test_refresh_keeps_vintages(sandbox_cache, monkeypatch):
    """FRED revises history. The cache is a VINTAGE LOG (audit F13):
    revisions are appended with their own retrieved_at; series() reads the
    latest vintage (status stays current); series_asof() answers what was
    known before the revision. The old test asserted revisions must be
    DISCARDED — that enshrined statuses evaluated on stale prints forever."""
    _write_cache(sandbox_cache, "s1", ["2025-01-01", "2025-02-01"], [1.0, 2.0])

    def fake_fetch(spec):
        return pd.DataFrame({
            "date": pd.to_datetime(["2025-01-01", "2025-02-01", "2025-03-01"]),
            "value": [1.5, 2.0, 3.0],     # 2025-01 REVISED 1.0 -> 1.5
        })
    monkeypatch.setitem(ib.FETCHERS, "fred", fake_fetch)
    ind = Indicator("s1", {"source": "fred", "series_id": "X"})
    assert ind.refresh() == "fresh"

    s = ind.series()
    assert len(s) == 3
    assert s.loc[pd.Timestamp("2025-01-01")] == 1.5   # latest vintage wins for status
    assert s.loc[pd.Timestamp("2025-03-01")] == 3.0

    # the original print is retained in the log and PIT-recoverable
    # (fixture rows carry retrieved_at 2026-01-01; the revision is stamped
    # now — a cutoff between the two must see the original)
    asof = ind.series_asof("2026-02-01T00:00:00+00:00")
    assert asof.loc[pd.Timestamp("2025-01-01")] == 1.0

    # unchanged values are NOT duplicated in the cache
    raw = pd.read_csv(ind.cache_path)
    assert len(raw[raw["date"] == "2025-02-01"]) == 1


def test_malformed_threshold_rule_raises():
    """A typo in a rule must scream, not silently disable the alarm (F14)."""
    from stocklab.indicators.base import parse_rule
    with pytest.raises(ValueError):
        parse_rule("value>1.5")          # missing spaces
    with pytest.raises(ValueError):
        parse_rule("Value > 1.5")        # case
    with pytest.raises(ValueError):
        parse_rule("value > 1,5")        # locale comma
    assert parse_rule("value >= -0.5") == ("value", ">=", -0.5)


def test_registry_rules_all_parse_and_are_registered():
    from stocklab.indicators.base import parse_rule
    inds = load_registry()
    for ind in inds:
        assert ind.registered_on, f"{ind.name} missing registered_on"
        for rule in ind.thresholds.values():
            parse_rule(rule)


def test_short_history_pctile_rule_is_unknown_not_ok(sandbox_cache):
    """9 monthly points must NOT fire (or pass) a '5y percentile' rule as if
    the window meant something (F15/F16)."""
    dates = pd.date_range("2025-01-01", periods=9, freq="MS")
    _write_cache(sandbox_cache, "short", dates, list(np.linspace(4, 6, 9)))
    ind = Indicator("short", {
        "source": "fred", "series_id": "X", "transform": "level",
        "thresholds": {"triggered": "pctile > 0.95"},
    })
    st = ind.status()
    assert st.threshold_state == "UNKNOWN"


def test_flat_series_does_not_trigger_pctile(sandbox_cache):
    """A perfectly flat series had pctile 1.0 under <=-counting (F15);
    midrank puts it at 0.5."""
    dates = pd.date_range("2020-01-01", periods=260, freq="W")
    _write_cache(sandbox_cache, "flat", dates, [4.0] * 260)
    ind = Indicator("flat", {
        "source": "fred", "series_id": "X", "transform": "level",
        "thresholds": {"triggered": "pctile > 0.95"},
    })
    st = ind.status()
    assert st.threshold_state == "OK"
    assert st.pctile_5y == pytest.approx(0.5, abs=0.01)


def test_dashboard_renders_without_data(sandbox_cache):
    inds = [Indicator("ghost", {"source": "fred", "series_id": "X"})]
    md = dashboard_markdown(inds)
    assert "NO_DATA" in md and "network policy blocks" in md
