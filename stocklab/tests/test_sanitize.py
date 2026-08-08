"""Corporate-action sanitizer: repairs data errors, leaves real moves alone."""
import numpy as np
import pandas as pd

from stocklab.data.panel import Panel
from stocklab.data.loaders import sanitize_corporate_actions


def _panel_with(close_col: np.ndarray) -> Panel:
    dates = pd.bdate_range("2020-01-01", periods=len(close_col))
    close = pd.DataFrame({"A": close_col, "B": np.full(len(close_col), 50.0)})
    close.index = dates
    volume = pd.DataFrame(1e6, index=dates, columns=["A", "B"])
    return Panel(close=close, volume=volume)


def test_spinoff_step_backadjusted():
    c = np.full(60, 100.0)
    c[30:] = 45.0                      # -55% step: un-adjusted distribution
    p, notes = sanitize_corporate_actions(_panel_with(c))
    r = p.close["A"].pct_change().abs().max()
    assert r < 0.01, f"step not repaired (max |ret| {r:.2%})"
    assert len(notes) == 1 and "distribution" in notes[0]


def test_reversal_pair_respliced():
    c = np.full(60, 100.0)
    c[30] = 50.0                       # -50% then +100% back to 100: bad split row
    p, notes = sanitize_corporate_actions(_panel_with(c))
    r = p.close["A"].pct_change().abs().max()
    assert r < 0.05, f"reversal pair not respliced (max |ret| {r:.2%})"
    assert len(notes) == 1 and "reversal" in notes[0]


def test_genuine_rally_untouched():
    c = np.full(60, 100.0)
    c[30:] = 165.0                     # +65% and it STAYS up: real news
    p, notes = sanitize_corporate_actions(_panel_with(c))
    assert notes == []
    assert np.isclose(p.close["A"].iloc[29], 100.0)
    assert np.isclose(p.close["A"].iloc[30], 165.0)
