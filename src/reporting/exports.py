"""Cluster CSV / GeoJSON exports. Public coordinates are coarsened; polygons are
50 m-buffered visualisation boundaries."""
from __future__ import annotations

import json

import pandas as pd

from src.config import REPORTS
from src.storage.db import connect, get_artifact


def export_cluster_files() -> None:
    with connect() as con:
        run = con.execute("SELECT * FROM analysis_runs ORDER BY run_id DESC LIMIT 1").fetchone()
        rid = run["run_id"]
        cl = {r["cluster_id"]: json.loads(r["payload"]) for r in con.execute("SELECT * FROM clusters WHERE run_id=?", (rid,))}
        hot = {h["cluster_id"]: h for h in get_artifact(con, "hotspots")}
    rows, feats = [], []
    for cid, c in cl.items():
        h = hot[cid]
        row = {k: v for k, v in c.items() if k != "boundary"}
        row["centroid_latitude"] = round(row["centroid_latitude"], 4)
        row["centroid_longitude"] = round(row["centroid_longitude"], 4)
        for k in ("bbox_min_lat", "bbox_min_lon", "bbox_max_lat", "bbox_max_lon"):
            row[k] = round(row[k], 3)
        row.update({k: h[k] for k in ("rank", "persistence", "active_months", "recent_3_month_count",
                                      "recent_vs_historical_change", "observed_trend", "complaint_share")})
        rows.append(row)
        props = {"cluster_id": cid, "rank": h["rank"], "reports": c["report_count"], "radius_m": c["approx_radius_meters"],
                 "boundary_kind": "cluster visualization boundary (50 m-buffered convex hull; not a pothole area)"}
        feats.append({"type": "Feature", "properties": props,
                      "geometry": {"type": "Polygon", "coordinates": [c["boundary"]]}})
        feats.append({"type": "Feature", "properties": {**props, "feature": "centroid"},
                      "geometry": {"type": "Point", "coordinates": [row["centroid_longitude"], row["centroid_latitude"]]}})
    pd.DataFrame(rows).sort_values("rank").to_csv(REPORTS / "cluster_summary.csv", index=False)
    (REPORTS / "dbscan_clusters.geojson").write_text(json.dumps({
        "type": "FeatureCollection",
        "metadata": {"eps_meters": run["eps_meters"], "min_samples": run["min_samples"], "dataset_size": run["dataset_size"]},
        "features": feats}))
