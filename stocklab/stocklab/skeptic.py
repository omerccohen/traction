"""Automated skeptic: red-flag analysis of experiment results.

Encodes the field's known self-deception modes as executable checks
(see docs/RESEARCH_LITERATURE.md, SKEPTIC CHECKLIST). The skeptic runs after
every experiment; its output ships with the results. A result without its
skeptic report is not a result.

Severity levels:
  FATAL — the number is almost certainly an artifact; do not use.
  WARN  — plausible but fragile; needs the listed follow-up.
  NOTE  — context the reader must have to interpret the number honestly.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Flag:
    severity: str   # FATAL | WARN | NOTE
    check: str
    message: str

    def format(self) -> str:
        return f"[{self.severity}] {self.check}: {self.message}"


@dataclass
class SkepticReport:
    model: str
    flags: list = field(default_factory=list)

    def add(self, severity: str, check: str, message: str) -> None:
        self.flags.append(Flag(severity, check, message))

    @property
    def fatal(self) -> bool:
        return any(f.severity == "FATAL" for f in self.flags)

    def format(self) -> str:
        if not self.flags:
            return f"skeptic({self.model}): no flags raised"
        lines = [f"skeptic({self.model}):"]
        order = {"FATAL": 0, "WARN": 1, "NOTE": 2}
        for f in sorted(self.flags, key=lambda f: order[f.severity]):
            lines.append("  " + f.format())
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "fatal": self.fatal,
            "flags": [f.__dict__ for f in self.flags],
        }


# Tripwire thresholds from the literature (docs/RESEARCH_LITERATURE.md §6):
IC_SUSPECT = 0.10          # sustained daily rank IC above this = leakage until proven otherwise
IC_IMPLAUSIBLE = 0.20
SHARPE_SUSPECT = 2.5       # net, daily cross-sectional equity strategy
SHARPE_IMPLAUSIBLE = 4.0


def review_signal(
    model: str,
    sig: dict,
    bt: dict | None = None,
    dataset_biases: list[str] | None = None,
    baseline_ic: float | None = None,
    n_trials: int | None = None,
    dsr: float | None = None,
    first_half_ic: float | None = None,
    second_half_ic: float | None = None,
) -> SkepticReport:
    """sig: SignalReport.to_dict(); bt: BacktestResult.to_dict() (optional)."""
    r = SkepticReport(model=model)
    ic = sig.get("ic_mean", np.nan)
    t = sig.get("ic_tstat_nw", np.nan)

    # --- leakage tripwires ---------------------------------------------------
    if np.isfinite(ic):
        if abs(ic) >= IC_IMPLAUSIBLE:
            r.add("FATAL", "too-good IC", f"mean rank IC {ic:.3f} — this magnitude does not "
                  "exist in honest daily equity signals; audit for leakage before anything else.")
        elif abs(ic) >= IC_SUSPECT:
            r.add("WARN", "high IC", f"mean rank IC {ic:.3f} exceeds the 0.10 plausibility line "
                  "(good published signals: 0.02-0.06); run the leakage checklist.")

    # --- significance --------------------------------------------------------
    if np.isfinite(t):
        needed = 3.0 if (n_trials or 1) > 10 else 2.0
        if abs(t) < needed:
            r.add("WARN", "significance", f"NW t-stat {t:.2f} < {needed:.0f} required given "
                  f"{n_trials or 1} trials — consistent with noise (Harvey-Liu-Zhu).")

    # --- monotonicity --------------------------------------------------------
    mono = sig.get("monotonicity", np.nan)
    if np.isfinite(mono) and mono < 0.6 and np.isfinite(ic) and ic > 0:
        r.add("WARN", "quantile monotonicity", f"decile monotonicity {mono:.2f} — returns are "
              "not smooth across ranks; edge may be a tail artifact.")

    # --- vs baseline ---------------------------------------------------------
    if baseline_ic is not None and np.isfinite(ic):
        if ic <= baseline_ic + 1e-4:
            r.add("NOTE", "baseline", f"does not beat momentum baseline IC ({baseline_ic:.4f}); "
                  "per design rules this model is not admitted to the ensemble.")

    # --- decay ---------------------------------------------------------------
    if first_half_ic is not None and second_half_ic is not None and np.isfinite(first_half_ic):
        if first_half_ic > 0 and second_half_ic < 0.5 * first_half_ic:
            r.add("WARN", "decay", f"second-half OOS IC ({second_half_ic:.4f}) is less than half "
                  f"of first-half ({first_half_ic:.4f}) — edge is decaying (Fischer-Krauss pattern).")

    # --- backtest-level ------------------------------------------------------
    if bt:
        s_net = bt.get("stats_net", {})
        sharpe = s_net.get("sharpe", np.nan)
        if np.isfinite(sharpe):
            if sharpe >= SHARPE_IMPLAUSIBLE:
                r.add("FATAL", "too-good Sharpe", f"net Sharpe {sharpe:.2f} — not a real number "
                      "for a daily equity strategy; audit for leakage/cost errors.")
            elif sharpe >= SHARPE_SUSPECT:
                r.add("WARN", "high Sharpe", f"net Sharpe {sharpe:.2f} above the 2.5 plausibility "
                      "line; deflate and stress costs before believing it.")
        be = bt.get("breakeven_cost_bps", np.nan)
        if np.isfinite(be) and be < 25.0:
            r.add("WARN", "cost fragility", f"break-even cost {be:.0f} bps/side — the edge dies "
                  "within realistic retail cost ranges (10-25 bps).")
        legs = bt.get("leg_stats", {})
        lr = legs.get("long", {}).get("ann_return", np.nan)
        sr = legs.get("short", {}).get("ann_return", np.nan)
        if np.isfinite(lr) and np.isfinite(sr):
            total = abs(lr) + abs(sr)
            if total > 0 and abs(sr) / total > 0.7:
                r.add("WARN", "short-leg dependence", f"{abs(sr)/total:.0%} of gross alpha comes "
                      "from the short leg — hard to implement (borrow costs/availability), and on "
                      "survivor-biased data the short leg is precisely where the bias helps most.")
        if dsr is not None and np.isfinite(dsr) and dsr < 0.95:
            r.add("WARN", "deflated Sharpe", f"DSR probability {dsr:.2f} < 0.95 given "
                  f"{n_trials} trials — the Sharpe is not distinguishable from the best of "
                  "that many noise strategies.")

    # --- dataset context (always attached) -----------------------------------
    for b in dataset_biases or []:
        r.add("NOTE", "dataset", b)

    return r
