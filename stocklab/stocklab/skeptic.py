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


# Tripwire thresholds from the literature (docs/RESEARCH_LITERATURE.md §6),
# calibrated at a 1-DAY label horizon. Cross-sectional IC scales roughly with
# sqrt(horizon), so k-day-label ICs are compared against sqrt(k)-scaled lines
# (unscaled lines cried leakage on honest 5d signals — review finding F4).
IC_SUSPECT_1D = 0.10       # sustained 1d rank IC above this = leakage until proven otherwise
IC_IMPLAUSIBLE_1D = 0.20
SHARPE_SUSPECT = 2.5       # net, annualized, daily cross-sectional equity strategy
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
    horizon: int = 5,
) -> SkepticReport:
    """sig: SignalReport.to_dict(); bt: BacktestResult.to_dict() (optional)."""
    r = SkepticReport(model=model)
    ic = sig.get("ic_mean", np.nan)
    t = sig.get("ic_tstat_nw", np.nan)

    # Every check below is gated on isfinite, so an evaluation that produced
    # NO usable numbers (empty ic series, failed backtest) raised zero flags —
    # and "no flags raised" read as a clean bill of health. Missing evidence
    # is its own finding.
    if not (np.isfinite(ic) or np.isfinite(t)):
        r.add("FATAL", "no evidence",
              "core metrics (ic_mean, ic_tstat_nw) are missing or non-finite — "
              "this signal has NOT been evaluated; a clean-looking report here "
              "would mean 'nothing was checked', not 'nothing was found'.")

    # --- leakage tripwires ---------------------------------------------------
    # Prefer the 1-day-horizon IC (directly comparable to the literature's
    # reference ranges) when the tear sheet computed it; otherwise scale the
    # 1d thresholds by sqrt(horizon).
    ic_1d = (sig.get("ic_by_horizon") or {}).get(1)
    if ic_1d is not None and np.isfinite(ic_1d):
        if abs(ic_1d) >= IC_IMPLAUSIBLE_1D:
            r.add("FATAL", "too-good IC", f"1d-horizon rank IC {ic_1d:.3f} — this magnitude does "
                  "not exist in honest daily equity signals; audit for leakage before anything else.")
        elif abs(ic_1d) >= IC_SUSPECT_1D:
            r.add("WARN", "high IC", f"1d-horizon rank IC {ic_1d:.3f} exceeds the 0.10 "
                  "plausibility line (good published 1d signals: 0.02-0.06); run the leakage checklist.")
    if np.isfinite(ic):
        scale = np.sqrt(max(horizon, 1))
        if abs(ic) >= IC_IMPLAUSIBLE_1D * scale:
            r.add("FATAL", "too-good IC", f"mean rank IC {ic:.3f} at {horizon}d horizon exceeds "
                  f"{IC_IMPLAUSIBLE_1D * scale:.2f} — audit for leakage before anything else.")
        elif abs(ic) >= IC_SUSPECT_1D * scale:
            r.add("WARN", "high IC", f"mean rank IC {ic:.3f} at {horizon}d horizon exceeds the "
                  f"{IC_SUSPECT_1D * scale:.2f} plausibility line; run the leakage checklist.")

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
        # short leg CONTRIBUTES only when its return is positive (it made
        # money shorting); |abs| attribution mislabeled money-losing short
        # legs as the alpha source — review finding F12
        if np.isfinite(lr) and np.isfinite(sr) and sr > 0:
            total = max(lr, 0.0) + sr
            if total > 0 and sr / total > 0.7:
                r.add("WARN", "short-leg dependence", f"{sr/total:.0%} of positive gross alpha "
                      "comes from the short leg — hard to implement (borrow costs/availability), "
                      "and on survivor-biased data the short leg is where the bias helps most.")
        fe = bt.get("forced_exit_days", 0)
        if fe > 0:
            r.add("NOTE", "forced exits", f"{fe} held-name days had missing prices (forced "
                  "liquidation at last close; delisting returns not modeled).")
        if dsr is not None and np.isfinite(dsr) and dsr < 0.95:
            r.add("WARN", "deflated Sharpe", f"DSR probability {dsr:.2f} < 0.95 given "
                  f"{n_trials} trials — the Sharpe is not distinguishable from the best of "
                  "that many noise strategies.")

    # --- dataset context (always attached) -----------------------------------
    for b in dataset_biases or []:
        r.add("NOTE", "dataset", b)

    return r
