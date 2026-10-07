"""DBSCAN stage: k-distance, parameter sweep with a baseline, selection,
final clustering, persistence of results."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.cluster import HDBSCAN
from sklearn.metrics import adjusted_rand_score

from src.analysis import dbscan as db
from src.config import (DEFAULT_K_FOR_KDIST, PUBLIC_COORD_DECIMALS, REPORTS, SWEEP_EPS_METERS,
                        SWEEP_MIN_SAMPLES)
from src.storage.db import connect, load_complaints, put_artifact

log = logging.getLogger("dbscan")
NULL_REPS = 20
SELECTION = {  # documented, explicit selection criteria (silhouette is NOT used)
    "max_noise_percentage": 75.0, "max_cluster_radius_m": 1000.0, "min_stability_ari": 0.6,
    "min_cluster_count": 20, "min_observed_to_baseline_cluster_ratio": 1.5, "no_sanity_warnings": True,
    "tie_break": "highest eps-neighbour stability (ARI), then lowest noise",
}


def _points(df):
    return df["latitude"].to_numpy(), df["longitude"].to_numpy()


def baseline_stats(base: pd.DataFrame, n: int, eps: float, ms: int, reps: int, seed: int = 42):
    rng = np.random.default_rng(seed)
    cs, ns = [], []
    for _ in range(reps):
        s = base.sample(n, random_state=int(rng.integers(1_000_000_000)))
        lab = db.run_dbscan(*_points(s), eps, ms)
        cs.append(len(set(lab) - {db.NOISE}))
        ns.append(100 * float((lab == db.NOISE).mean()))
    return float(np.mean(cs)), float(np.std(cs)), float(np.mean(ns))


def kdist_plot(lat, lon, chosen_eps: float, ks=(4, 5, 6, 8)) -> dict:
    fig, ax = plt.subplots(figsize=(8, 5))
    info = {}
    for k in ks:
        kd = db.k_distances(lat, lon, k)
        i = db.knee_index(kd)
        ax.plot(np.arange(len(kd)), kd, label=f"k={k}", lw=1.4)
        info[str(k)] = {"percentiles_m": {str(q): round(float(np.percentile(kd, q)), 1) for q in (10, 25, 50, 75, 90, 95)},
                        "knee_m": round(float(kd[i]), 1)}
    ax.axhline(chosen_eps, color="crimson", ls="--", lw=1.2, label=f"selected eps = {chosen_eps:g} m")
    ax.set_yscale("log")
    ax.set_xlabel("Reports, sorted by k-th nearest-neighbour distance")
    ax.set_ylabel("k-th nearest-neighbour distance (m, haversine, log scale)")
    ax.set_title("k-distance plot - pothole reports (fallback pins excluded)")
    ax.grid(alpha=.3, which="both")
    ax.legend()
    fig.tight_layout()
    fig.savefig(REPORTS / "k_distance_plot.png", dpi=130)
    plt.close(fig)
    return info


def select_config(sweep: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame]:
    s = SELECTION
    ok = sweep[(sweep.warnings == "") & (sweep.noise_percentage <= s["max_noise_percentage"])
               & (sweep.max_cluster_radius_m <= s["max_cluster_radius_m"])
               & (sweep.stability_ari >= s["min_stability_ari"]) & (sweep.cluster_count >= s["min_cluster_count"])
               & (sweep.cluster_ratio_vs_baseline >= s["min_observed_to_baseline_cluster_ratio"])]
    if ok.empty:
        raise RuntimeError("No DBSCAN configuration satisfies the documented selection criteria; "
                           "review reports/dbscan_parameter_sweep.csv")
    best = ok.sort_values(["stability_ari", "noise_percentage"], ascending=[False, True]).iloc[0]
    return best, ok


def run_dbscan_stage(eps_override: float | None = None, ms_override: int | None = None) -> dict:
    with connect() as con:
        allc = load_complaints(con)
    pot = allc[(allc.is_pothole == 1) & (allc.usable == 1)]
    pts = pot[pot.suspect_fallback_pin == 0].reset_index(drop=True)
    base = allc[(allc.is_pothole == 0) & (allc.usable == 1) & (allc.suspect_fallback_pin == 0)]
    lat, lon = _points(pts)
    log.info("points for DBSCAN: %d (baseline pool %d)", len(pts), len(base))

    sweep, labs = db.parameter_sweep(lat, lon, SWEEP_EPS_METERS, SWEEP_MIN_SAMPLES, with_silhouette=True)
    nb = [baseline_stats(base, len(pts), r.eps_meters, r.min_samples, NULL_REPS) for r in sweep.itertuples()]
    sweep["baseline_cluster_count_mean"] = [round(x[0], 1) for x in nb]
    sweep["baseline_cluster_count_sd"] = [round(x[1], 1) for x in nb]
    sweep["baseline_noise_percentage_mean"] = [round(x[2], 1) for x in nb]
    sweep["cluster_ratio_vs_baseline"] = (sweep.cluster_count / sweep.baseline_cluster_count_mean.replace(0, np.nan)).round(2)

    sweep.to_csv(REPORTS / "dbscan_parameter_sweep.csv", index=False)  # written first so a failed selection is reviewable
    if eps_override and ms_override:
        sel = sweep[(sweep.eps_meters == eps_override) & (sweep.min_samples == ms_override)].iloc[0]
        passing = sweep.iloc[0:0]
        rule = "manual override"
    else:
        sel, passing = select_config(sweep)
        rule = "documented selection criteria"
    eps, ms = float(sel.eps_meters), int(sel.min_samples)
    sweep["selected"] = (sweep.eps_meters == eps) & (sweep.min_samples == ms)
    sweep["passes_selection_criteria"] = sweep.index.isin(passing.index)
    sweep.to_csv(REPORTS / "dbscan_parameter_sweep.csv", index=False)
    warnings = [w for w in sweep.warnings if w]

    kd = kdist_plot(lat, lon, eps)
    labels = db.run_dbscan(lat, lon, eps, ms)
    clusters = db.cluster_table(pts, labels, eps)
    n, n_noise = len(labels), int((labels == db.NOISE).sum())

    # Sensitivity: include suspected fallback pins
    with_pins = pot.reset_index(drop=True)
    lab_p = db.run_dbscan(*_points(with_pins), eps, ms)
    sens = db.sweep_row(*_points(with_pins), lab_p, eps, ms)
    sens["note"] = "same eps/min_samples with suspected fallback-pin reports included"
    biggest_pin = with_pins[with_pins.suspect_fallback_pin == 1].groupby(["latitude", "longitude"]).size().max()
    sens["largest_single_coordinate_pin_reports"] = int(biggest_pin)

    # Secondary experiment: HDBSCAN (haversine, radians)
    coords = np.radians(np.column_stack([lat, lon]))
    h = HDBSCAN(min_cluster_size=ms, min_samples=ms, metric="haversine", copy=True).fit_predict(coords)
    hd = {"clusters": int(len(set(h) - {-1})), "noise_percentage": round(100 * float((h == -1).mean()), 2),
          "ari_vs_selected_dbscan": round(float(adjusted_rand_score(labels, h)), 3),
          "note": "secondary experiment only; min_cluster_size=min_samples=%d" % ms}

    # Parameter-neighbour stability of the selected config
    run_meta = {
        "eps_meters": eps, "min_samples": ms, "distance_metric": "haversine (radians; eps converted from metres, R=6371008.8 m)",
        "dataset_size": n, "selection_rule": rule, "selection_criteria": SELECTION,
        "selected_row": json.loads(sel.to_json()), "sweep_warning_count": len(warnings),
        "k_distance": {"k_values": list(kd), "details": kd,
                       "note": "k-distance knee is a heuristic; the knee falls well above the eps values that pass the "
                               "sanity checks because the tail of the curve reflects isolated points"},
        "sensitivity_with_fallback_pins": sens, "hdbscan_secondary": hd,
        "passing_eps_range_m": [float(passing.eps_meters.min()), float(passing.eps_meters.max())] if len(passing) else None,
        "passing_configs": passing[["eps_meters", "min_samples"]].to_dict("records"),
    }
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with connect() as con:
        con.execute("DELETE FROM analysis_runs"); con.execute("DELETE FROM clusters")
        con.execute("DELETE FROM cluster_membership"); con.execute("DELETE FROM spatial_unit_monthly")
        cur = con.execute("INSERT INTO analysis_runs(created_at,eps_meters,min_samples,distance_metric,dataset_size,"
                          "cluster_count,noise_count,noise_percentage,params_json) VALUES (?,?,?,?,?,?,?,?,?)",
                          (now, eps, ms, run_meta["distance_metric"], n, len(clusters), n_noise,
                           round(100 * n_noise / n, 2), json.dumps(run_meta, default=str)))
        run_id = cur.lastrowid
        for r in clusters.to_dict("records"):
            con.execute("INSERT INTO clusters VALUES (?,?,?)", (run_id, r["cluster_id"], json.dumps(r)))
        con.executemany("INSERT INTO cluster_membership VALUES (?,?,?)",
                        [(run_id, int(rid), int(c)) for rid, c in zip(pts.rowid_, labels)])
        put_artifact(con, "dbscan_sweep", sweep.to_dict("records"), run_id)
        put_artifact(con, "dbscan_warnings", warnings, run_id)
    log.info("selected eps=%s ms=%s -> %d clusters, noise %.1f%%", eps, ms, len(clusters), 100 * n_noise / n)
    return {"run_id": run_id, "eps": eps, "min_samples": ms, "clusters": len(clusters), "noise": n_noise, "n": n}
