import numpy as np
import pytest

from src.analysis import dbscan as db


def blob(lat, lon, n, spread_m, rng):
    dlat = rng.normal(0, spread_m / 111_000, n); dlon = rng.normal(0, spread_m / 108_000, n)
    return lat + dlat, lon + dlon


def test_known_clusters_and_noise():
    rng = np.random.default_rng(0)
    a = blob(12.95, 77.55, 30, 40, rng); b = blob(13.05, 77.65, 30, 40, rng)
    lat = np.r_[a[0], b[0], 12.80]; lon = np.r_[a[1], b[1], 77.40]   # last point is isolated
    lab = db.run_dbscan(lat, lon, 200, 5)
    assert len(set(lab) - {db.NOISE}) == 2
    assert lab[-1] == db.NOISE
    assert (lab[:30] == lab[0]).all() and (lab[30:60] == lab[30]).all() and lab[0] != lab[30]


def test_eps_is_metres_not_degrees():
    lat = np.array([12.97, 12.97]); lon = np.array([77.59, 77.5918])      # ~195 m apart
    assert (db.run_dbscan(lat, lon, 250, 2) != db.NOISE).all()
    assert (db.run_dbscan(lat, lon, 100, 2) == db.NOISE).all()


def test_parameter_validation():
    with pytest.raises(ValueError):
        db.run_dbscan([12.9], [77.5], 0, 5)
    with pytest.raises(ValueError):
        db.run_dbscan([12.9], [77.5], 100, 0)


def test_sweep_columns_and_warnings():
    rng = np.random.default_rng(1)
    a = blob(12.95, 77.55, 60, 50, rng)
    df, _ = db.parameter_sweep(a[0], a[1], [50, 5000], [5], with_silhouette=False)
    for c in ["eps_meters", "min_samples", "cluster_count", "noise_count", "noise_percentage", "largest_cluster_size",
              "largest_cluster_share", "median_cluster_size", "stability_ari"]:
        assert c in df.columns
    huge = df[df.eps_meters == 5000].iloc[0]
    assert db.sanity_warnings(huge.to_dict()) == [] or any("WARNING" in w for w in db.sanity_warnings(huge.to_dict()))


def test_warning_text_for_dominant_cluster():
    row = {"eps_meters": 500, "min_samples": 5, "cluster_count": 4, "noise_percentage": 20.0, "largest_cluster_share": 0.63,
           "max_cluster_radius_m": 100, "single_coordinate_cluster_share": 0.0}
    assert any("63% of clustered reports" in w for w in db.sanity_warnings(row))
    row.update(noise_percentage=95.0, largest_cluster_share=0.1)
    assert any("noise" in w for w in db.sanity_warnings(row))


def test_cluster_table_values():
    import pandas as pd
    rng = np.random.default_rng(2)
    a = blob(12.95, 77.55, 20, 40, rng)
    pts = pd.DataFrame({"latitude": a[0], "longitude": a[1],
                        "created_at": pd.date_range("2020-01-01", periods=20, freq="D", tz="Asia/Kolkata")})
    lab = np.zeros(20, dtype=int)
    t = db.cluster_table(pts, lab, 200)
    r = t.iloc[0]
    assert r.report_count == 20 and 20 < r.approx_radius_meters < 250
    assert r.date_min.startswith("2020-01-01") and r.date_max.startswith("2020-01-20")
    assert r.boundary[0] == r.boundary[-1]
    assert abs(r.centroid_latitude - 12.95) < 0.002
