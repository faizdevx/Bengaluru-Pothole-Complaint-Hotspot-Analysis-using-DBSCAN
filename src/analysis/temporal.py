"""Monthly spatial analysis on fixed spatial units (wards, and DBSCAN clusters
as footprints): normalisation, persistence, recent activity, observed trend."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import binom, kendalltau, poisson, theilslopes

from src.config import (
    ALPHA_ACTIVE_MONTH, ALPHA_PERSISTENCE, ALPHA_TREND, MIN_ELIGIBLE_MONTHS_FOR_PERSISTENCE,
    MIN_ELIGIBLE_MONTHS_FOR_TREND, MIN_HISTORY_MONTHS, MIN_REPORTS_FOR_TREND, RECENT_MONTHS,
)

INSUFFICIENT = "Insufficient data"


def month_index(first: str, last: str) -> list[str]:
    return list(pd.period_range(first, last, freq="M").strftime("%Y-%m"))


def active_threshold(lam: float, alpha: float = ALPHA_ACTIVE_MONTH) -> tuple[int, float]:
    """Smallest count T>=1 such that P(Poisson(lam) >= T) <= alpha, and that tail
    probability p0. lam is the null expected reports for the unit in one month
    (city-wide rate per km2 x unit area)."""
    t = 1
    while poisson.sf(t - 1, lam) > alpha and t < 1000:
        t += 1
    return t, float(poisson.sf(t - 1, lam))


def persistence_threshold(n_months: int, p0: float, alpha: float = ALPHA_PERSISTENCE) -> int:
    """Smallest number of active months k with P(Binomial(n, p0) >= k) <= alpha."""
    k = 1
    while binom.sf(k - 1, n_months, p0) > alpha and k <= n_months:
        k += 1
    return k


def unit_monthly(df: pd.DataFrame, unit_col: str, months: list[str], units) -> pd.DataFrame:
    """Dense unit x month table. df needs columns: unit_col, month, is_pothole."""
    g = df.groupby([unit_col, "month"]).agg(all_complaints=("is_pothole", "size"),
                                            pothole_reports=("is_pothole", "sum")).reset_index()
    full = pd.MultiIndex.from_product([list(units), months], names=[unit_col, "month"]).to_frame(index=False)
    out = full.merge(g, on=[unit_col, "month"], how="left").fillna({"all_complaints": 0, "pothole_reports": 0})
    out[["all_complaints", "pothole_reports"]] = out[["all_complaints", "pothole_reports"]].astype(int)
    out["pothole_share"] = (out.pothole_reports / out.all_complaints.replace(0, np.nan)).round(4)
    return out.rename(columns={unit_col: "unit_id"})


def recent_vs_historical(series: np.ndarray) -> dict:
    n = len(series)
    if n < RECENT_MONTHS + MIN_HISTORY_MONTHS:
        return {"recent_3_month_count": INSUFFICIENT, "historical_average": INSUFFICIENT,
                "recent_vs_historical_change": INSUFFICIENT}
    recent = int(series[-RECENT_MONTHS:].sum())
    hist = float(series[:-RECENT_MONTHS].mean())
    change = INSUFFICIENT if hist == 0 else round((recent / RECENT_MONTHS - hist) / hist, 3)
    return {"recent_3_month_count": recent, "historical_average": round(hist, 3),
            "recent_vs_historical_change": change if hist > 0 else "No historical activity"}


def trend_stats(series: np.ndarray) -> dict:
    """Monthly Kendall tau against time + Theil-Sen slope. The label is assigned later,
    after Benjamini-Hochberg adjustment across units."""
    if len(series) < MIN_ELIGIBLE_MONTHS_FOR_TREND or series.sum() < MIN_REPORTS_FOR_TREND:
        return {"tau": None, "p_value": None, "slope_per_month": None, "trend_valid": False}
    if np.ptp(series) == 0:
        return {"tau": 0.0, "p_value": 1.0, "slope_per_month": 0.0, "trend_valid": True}
    tau, p = kendalltau(np.arange(len(series)), series)
    slope = float(theilslopes(series, np.arange(len(series)))[0])
    return {"tau": round(float(tau), 3), "p_value": float(p), "slope_per_month": round(slope, 4), "trend_valid": True}


def bh_adjust(p: np.ndarray) -> np.ndarray:
    n = len(p)
    order = np.argsort(p)
    ranked = p[order] * n / (np.arange(n) + 1)
    adj = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.minimum(adj, 1.0)
    return out


def label_trends(stats: list[dict]) -> list[dict]:
    """Add q_value and trend label ('Increasing'/'Stable'/'Decreasing'/'Insufficient data')."""
    idx = [i for i, s in enumerate(stats) if s["trend_valid"]]
    if idx:
        q = bh_adjust(np.array([stats[i]["p_value"] for i in idx]))
        for i, qi in zip(idx, q):
            stats[i]["q_value"] = float(qi)
    for s in stats:
        if not s["trend_valid"]:
            s["trend"] = INSUFFICIENT
        elif s["q_value"] < ALPHA_TREND and s["tau"] > 0:
            s["trend"] = "Increasing"
        elif s["q_value"] < ALPHA_TREND and s["tau"] < 0:
            s["trend"] = "Decreasing"
        else:
            s["trend"] = "Stable"
    return stats


def unit_metrics(series: np.ndarray, area_km2: float, rate_per_km2_month: float, test_persistence: bool = True) -> dict:
    """Persistence + activity for one unit's monthly pothole series."""
    n = len(series)
    lam = rate_per_km2_month * area_km2
    t, p0 = active_threshold(lam)
    active = int((series >= t).sum())
    out = {"area_km2": round(area_km2, 4), "expected_monthly_reports_null": round(lam, 4),
           "active_month_threshold": t, "active_months": active, "eligible_months": n,
           "total_reports": int(series.sum())}
    if n < MIN_ELIGIBLE_MONTHS_FOR_PERSISTENCE:
        out.update(persistence=None, persistent=None,
                   persistence_note="Persistence analysis not sufficiently supported by available data")
    elif not test_persistence:
        # Units chosen BECAUSE they are dense (DBSCAN clusters) cannot be tested against a uniform null
        # without circularity; only the descriptive active-month share is reported.
        out.update(persistence=round(active / n, 3), persistent=None,
                   persistence_note="descriptive share only; clusters are selected for density so no null test is applied")
    else:
        k = persistence_threshold(n, p0)
        out.update(persistence=round(active / n, 3), persistent=bool(active >= k), persistence_min_active_months=k)
    out.update(recent_vs_historical(series))
    out.update(trend_stats(series))
    return out
