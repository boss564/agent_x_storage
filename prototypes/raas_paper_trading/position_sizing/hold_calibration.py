"""Hold-horizon calibration for Option B paper exit (B2 sample design).

Estimand: choose PAPER_HOLD_SECONDS so expected |k-step return| clears
~3× round-trip cost floor (~0.6%), with path-independent time exit.

Hard constraints (docs/PAPER_EXIT_ROUNDTRIP_SPEC.md):
- Tick SIGNAL only (exclude aggregate=True)
- Time-normalized returns (dt gaps ≠ market moves)
- E[|r|] = σ·√(2/π) — do not equate mean absolute return with σ
- Sub-window σ span for vol clustering diagnostics
- Calibration freezes measurement feasibility, not favourable f*
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Round-trip floor ≈ 20 bps; 3× → 0.60% mean absolute move target
COST_FLOOR_FRAC = 0.002
TARGET_ABS_RETURN = 3.0 * COST_FLOOR_FRAC  # 0.006
# E[|Z|] = √(2/π) for Z ~ N(0,1) ⇒ σ_k ≥ TARGET / √(2/π)
SQRT_2_OVER_PI = math.sqrt(2.0 / math.pi)
TARGET_SIGMA_K = TARGET_ABS_RETURN / SQRT_2_OVER_PI  # ≈ 0.007516

# Intervals larger than this (seconds) are treated as feed gaps, not returns
DEFAULT_GAP_DT_S = 30.0
DEFAULT_SUBWINDOWS = 5


@dataclass(frozen=True)
class TickPoint:
    ts: datetime
    price: float
    line_no: int


@dataclass
class HoldCalibrationResult:
    worm_path: str
    worm_sha256: str
    n_worm_lines: int
    n_tick_signals: int
    n_aggregate_skipped: int
    n_returns_used: int
    n_gap_excluded: int
    ts_first: Optional[str]
    ts_last: Optional[str]
    gap_dt_threshold_s: float
    dt_p50_s: Optional[float]
    dt_p95_s: Optional[float]
    dt_p99_s: Optional[float]
    dt_max_s: Optional[float]
    sigma_per_sqrt_s: Optional[float]
    target_abs_return: float
    target_sigma_k: float
    cost_floor_frac: float
    recommended_hold_seconds: Optional[float]
    sigma_subwindows: List[float]
    sigma_sub_min: Optional[float]
    sigma_sub_max: Optional[float]
    sigma_sub_median: Optional[float]
    hold_seconds_from_sub_max: Optional[float]
    hold_seconds_from_sub_min: Optional[float]
    anti_harking_note: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def freeze_table_rows(self) -> List[Tuple[str, str]]:
        """Rows for PAPER_EXIT_ROUNDTRIP_SPEC.md §7."""
        hold = self.recommended_hold_seconds
        hold_s = f"{hold:.0f}" if hold is not None else "TBD (insufficient data)"
        return [
            ("PAPER_HOLD_SECONDS", hold_s),
            ("σ_per_√s (time-norm)", f"{self.sigma_per_sqrt_s:.8f}" if self.sigma_per_sqrt_s else "TBD"),
            ("target E[|r_k|]", f"{self.target_abs_return:.4f} ({100*self.target_abs_return:.2f}%)"),
            ("target σ_k (= E[|r|]/√(2/π))", f"{self.target_sigma_k:.6f}"),
            ("σ subwindow [min, med, max]", (
                f"[{self.sigma_sub_min:.8f}, {self.sigma_sub_median:.8f}, {self.sigma_sub_max:.8f}]"
                if self.sigma_sub_min is not None
                else "TBD"
            )),
            ("n_tick_signals / n_returns / gaps_excl", f"{self.n_tick_signals} / {self.n_returns_used} / {self.n_gap_excluded}"),
            ("WORM path", self.worm_path),
            ("WORM sha256", self.worm_sha256),
            ("n_worm_lines", str(self.n_worm_lines)),
            ("ts range (UTC)", f"{self.ts_first} → {self.ts_last}"),
            ("dt p50/p95/p99/max (s)", (
                f"{self.dt_p50_s:.3f}/{self.dt_p95_s:.3f}/{self.dt_p99_s:.3f}/{self.dt_max_s:.3f}"
                if self.dt_p50_s is not None
                else "TBD"
            )),
            ("gap_dt_threshold_s", str(self.gap_dt_threshold_s)),
            ("Messdatum", datetime.now(timezone.utc).isoformat()),
            ("Anti-HARKing", self.anti_harking_note),
        ]


def _parse_ts(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_tick_signal(row: Dict[str, Any]) -> bool:
    """Tick SIGNAL only — exclude runner.py aggregate rows (aggregate=True)."""
    if row.get("action") != "SIGNAL":
        return False
    if row.get("aggregate") is True:
        return False
    if str(row.get("signal_id") or "") == "aggregate":
        return False
    return True


def load_tick_signals(path: Path) -> Tuple[List[TickPoint], int, int]:
    """Return (ticks, n_lines, n_aggregate_skipped)."""
    ticks: List[TickPoint] = []
    n_lines = 0
    n_agg = 0
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            n_lines += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("action") == "SIGNAL" and (
                row.get("aggregate") is True or str(row.get("signal_id") or "") == "aggregate"
            ):
                n_agg += 1
                continue
            if not is_tick_signal(row):
                continue
            ts = _parse_ts(row.get("ts"))
            try:
                price = float(row.get("mark_price"))
            except (TypeError, ValueError):
                continue
            if ts is None or price <= 0:
                continue
            ticks.append(TickPoint(ts=ts, price=price, line_no=line_no))
    ticks.sort(key=lambda t: t.ts)
    return ticks, n_lines, n_agg


def _percentile(sorted_vals: Sequence[float], p: float) -> float:
    if not sorted_vals:
        raise ValueError("empty")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = (len(sorted_vals) - 1) * p
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return sorted_vals[lo]
    w = idx - lo
    return sorted_vals[lo] * (1.0 - w) + sorted_vals[hi] * w


def time_normalized_returns(
    ticks: Sequence[TickPoint],
    *,
    gap_dt_s: float,
) -> Tuple[List[float], List[float], int]:
    """Build r/√dt series; exclude gaps (dt > gap_dt_s).

    Returns (normalized_returns, all_positive_dts, n_gap_excluded).
    """
    norms: List[float] = []
    dts: List[float] = []
    n_gap = 0
    for i in range(1, len(ticks)):
        dt = (ticks[i].ts - ticks[i - 1].ts).total_seconds()
        if dt <= 0:
            continue
        dts.append(dt)
        if dt > gap_dt_s:
            n_gap += 1
            continue
        log_r = math.log(ticks[i].price / ticks[i - 1].price)
        norms.append(log_r / math.sqrt(dt))
    return norms, dts, n_gap


def sample_sigma(values: Sequence[float]) -> Optional[float]:
    n = len(values)
    if n < 2:
        return None
    mean = sum(values) / n
    var = sum((x - mean) ** 2 for x in values) / (n - 1)
    return math.sqrt(var) if var > 0 else 0.0


def subwindow_sigmas(values: Sequence[float], n_windows: int) -> List[float]:
    if n_windows < 1 or len(values) < n_windows * 2:
        return []
    size = len(values) // n_windows
    out: List[float] = []
    for w in range(n_windows):
        chunk = values[w * size : (w + 1) * size]
        s = sample_sigma(chunk)
        if s is not None:
            out.append(s)
    return out


def hold_seconds_from_sigma(sigma_per_sqrt_s: float, target_sigma_k: float = TARGET_SIGMA_K) -> Optional[float]:
    if sigma_per_sqrt_s is None or sigma_per_sqrt_s <= 0:
        return None
    # σ_k = σ_√s · √k  ≥ target_sigma_k  ⇒  k ≥ (target/σ)^2
    return (target_sigma_k / sigma_per_sqrt_s) ** 2


def calibrate_hold_from_worm(
    worm_path: Path,
    *,
    gap_dt_s: float = DEFAULT_GAP_DT_S,
    n_subwindows: int = DEFAULT_SUBWINDOWS,
    target_abs_return: float = TARGET_ABS_RETURN,
    cost_floor_frac: float = COST_FLOOR_FRAC,
) -> HoldCalibrationResult:
    path = Path(worm_path)
    digest = file_sha256(path)
    ticks, n_lines, n_agg = load_tick_signals(path)
    target_sigma_k = target_abs_return / SQRT_2_OVER_PI
    anti = (
        "Calibration ensures the measurement is feasible (horizon clears cost floor), "
        "not that f* will be favourable. If f* ≤ 0 after N round-trips, that is a result — "
        "do not retune k until f* looks good (HARKing)."
    )

    if len(ticks) < 3:
        return HoldCalibrationResult(
            worm_path=str(path),
            worm_sha256=digest,
            n_worm_lines=n_lines,
            n_tick_signals=len(ticks),
            n_aggregate_skipped=n_agg,
            n_returns_used=0,
            n_gap_excluded=0,
            ts_first=ticks[0].ts.isoformat() if ticks else None,
            ts_last=ticks[-1].ts.isoformat() if ticks else None,
            gap_dt_threshold_s=gap_dt_s,
            dt_p50_s=None,
            dt_p95_s=None,
            dt_p99_s=None,
            dt_max_s=None,
            sigma_per_sqrt_s=None,
            target_abs_return=target_abs_return,
            target_sigma_k=target_sigma_k,
            cost_floor_frac=cost_floor_frac,
            recommended_hold_seconds=None,
            sigma_subwindows=[],
            sigma_sub_min=None,
            sigma_sub_max=None,
            sigma_sub_median=None,
            hold_seconds_from_sub_max=None,
            hold_seconds_from_sub_min=None,
            anti_harking_note=anti,
        )

    norms, dts, n_gap = time_normalized_returns(ticks, gap_dt_s=gap_dt_s)
    dts_sorted = sorted(dts)
    sigma = sample_sigma(norms)
    subs = subwindow_sigmas(norms, n_subwindows)
    subs_sorted = sorted(subs) if subs else []
    sub_min = subs_sorted[0] if subs_sorted else None
    sub_max = subs_sorted[-1] if subs_sorted else None
    sub_med = _percentile(subs_sorted, 0.5) if subs_sorted else None

    return HoldCalibrationResult(
        worm_path=str(path),
        worm_sha256=digest,
        n_worm_lines=n_lines,
        n_tick_signals=len(ticks),
        n_aggregate_skipped=n_agg,
        n_returns_used=len(norms),
        n_gap_excluded=n_gap,
        ts_first=ticks[0].ts.isoformat(),
        ts_last=ticks[-1].ts.isoformat(),
        gap_dt_threshold_s=gap_dt_s,
        dt_p50_s=_percentile(dts_sorted, 0.50) if dts_sorted else None,
        dt_p95_s=_percentile(dts_sorted, 0.95) if dts_sorted else None,
        dt_p99_s=_percentile(dts_sorted, 0.99) if dts_sorted else None,
        dt_max_s=dts_sorted[-1] if dts_sorted else None,
        sigma_per_sqrt_s=sigma,
        target_abs_return=target_abs_return,
        target_sigma_k=target_sigma_k,
        cost_floor_frac=cost_floor_frac,
        recommended_hold_seconds=hold_seconds_from_sigma(sigma, target_sigma_k) if sigma else None,
        sigma_subwindows=subs,
        sigma_sub_min=sub_min,
        sigma_sub_max=sub_max,
        sigma_sub_median=sub_med,
        # Conservative: use highest subwindow σ → shorter k; report both ends
        hold_seconds_from_sub_max=hold_seconds_from_sigma(sub_max, target_sigma_k) if sub_max else None,
        hold_seconds_from_sub_min=hold_seconds_from_sigma(sub_min, target_sigma_k) if sub_min else None,
        anti_harking_note=anti,
    )


def render_freeze_markdown(result: HoldCalibrationResult) -> str:
    lines = ["| Feld | Wert |", "|------|------|"]
    for key, val in result.freeze_table_rows():
        lines.append(f"| {key} | `{val}` |")
    return "\n".join(lines) + "\n"
