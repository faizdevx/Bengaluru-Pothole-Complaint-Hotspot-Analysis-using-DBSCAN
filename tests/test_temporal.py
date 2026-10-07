import numpy as np
import pandas as pd

from src.analysis import temporal as T


def test_monthly_aggregation_and_share():
    df = pd.DataFrame({"ward_id": [1, 1, 1, 2], "month": ["2020-01", "2020-01", "2020-03", "2020-02"],
                       "is_pothole": [1, 0, 1, 1]})
    out = T.unit_monthly(df, "ward_id", ["2020-01", "2020-02", "2020-03"], [1, 2])
    r = out[(out.unit_id == 1) & (out.month == "2020-01")].iloc[0]
    assert r.all_complaints == 2 and r.pothole_reports == 1 and r.pothole_share == 0.5
    assert np.isnan(out[(out.unit_id == 2) & (out.month == "2020-01")].iloc[0].pothole_share)   # no complaints -> undefined
    assert len(out) == 6


def test_month_index():
    assert T.month_index("2019-11", "2020-02") == ["2019-11", "2019-12", "2020-01", "2020-02"]


def test_active_threshold_is_monotone_in_rate():
    t_low, p_low = T.active_threshold(0.05)
    t_high, _ = T.active_threshold(2.0)
    assert t_low == 1 and p_low <= 0.05 and t_high > t_low


def test_persistence_threshold_and_insufficient_data():
    k = T.persistence_threshold(43, 0.03)
    assert 3 <= k <= 10
    short = T.unit_metrics(np.ones(10, dtype=int), 3.0, 0.07)
    assert short["persistence"] is None and "not sufficiently supported" in short["persistence_note"]
    full = T.unit_metrics(np.r_[np.ones(20), np.zeros(23)].astype(int), 3.0, 0.07)
    assert full["persistence"] == round(full["active_months"] / 43, 3)


def test_recent_vs_historical():
    s = np.r_[np.full(40, 2), [4, 4, 4]]
    r = T.recent_vs_historical(s)
    assert r["recent_3_month_count"] == 12 and r["historical_average"] == 2.0 and r["recent_vs_historical_change"] == 1.0
    assert T.recent_vs_historical(np.ones(10))["recent_3_month_count"] == "Insufficient data"


def test_trend_labels():
    inc = np.arange(36) // 3 + np.random.default_rng(0).integers(0, 2, 36)
    flat = np.random.default_rng(1).integers(0, 3, 36)
    tiny = np.array([1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    labels = T.label_trends([T.trend_stats(inc), T.trend_stats(flat), T.trend_stats(tiny)])
    assert labels[0]["trend"] == "Increasing"
    assert labels[1]["trend"] == "Stable"
    assert labels[2]["trend"] == "Insufficient data"


def test_one_noisy_month_is_not_a_trend():
    s = np.zeros(36, dtype=int); s[-1] = 12
    assert T.label_trends([T.trend_stats(s)])[0]["trend"] != "Increasing" or T.trend_stats(s)["p_value"] < 0.05


def test_bh_adjust():
    q = T.bh_adjust(np.array([0.01, 0.04, 0.03]))
    assert np.all(q >= np.array([0.01, 0.04, 0.03])) and q.max() <= 1
