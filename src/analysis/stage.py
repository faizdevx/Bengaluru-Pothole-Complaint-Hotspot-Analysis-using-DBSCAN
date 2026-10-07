"""Temporal/spatial stage: wards + cluster footprints, hotspots table, outputs."""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import Point, Polygon

from src.analysis import temporal as T
from src.config import GRID_CELL_METERS, PUBLIC_COORD_DECIMALS, REPORTS, MIN_ELIGIBLE_MONTHS_FOR_PERSISTENCE
from src.data.secondary import compare_with_primary, parse_fms_kml
from src.geo.boundary import WardIndex, parse_ward_kml
from src.geo.distance import to_xy
from src.storage.db import connect, get_artifact, load_complaints, put_artifact

log = logging.getLogger("temporal")


def _poly_area_km2(boundary) -> float:
    lon = np.array([b[0] for b in boundary]); lat = np.array([b[1] for b in boundary])
    x, y = to_xy(lat, lon)
    return Polygon(np.column_stack([x, y])).area / 1e6


def run_temporal_stage() -> dict:
    with connect() as con:
        run = con.execute("SELECT * FROM analysis_runs ORDER BY run_id DESC LIMIT 1").fetchone()
        if run is None:
            raise RuntimeError("No analysis has been run yet")
        run_id = run["run_id"]
        allc = load_complaints(con)
        cl = {r["cluster_id"]: json.loads(r["payload"]) for r in con.execute("SELECT * FROM clusters WHERE run_id=?", (run_id,))}
        mem = pd.read_sql("SELECT complaint_rowid, cluster_id FROM cluster_membership WHERE run_id=?", con, params=(run_id,))

    wards = parse_ward_kml(); widx = WardIndex(wards); areas = widx.ward_areas_km2()
    city_area = sum(areas.values())
    base = allc[(allc.usable == 1) & (allc.suspect_fallback_pin == 0)].copy()   # analysis set (same as DBSCAN)
    months = T.month_index(allc.month.min(), allc.month.max())
    n_months = len(months)
    pot_total = int(base.is_pothole.sum())
    rate = pot_total / (city_area * n_months)   # null: city-wide reports per km2 per month

    # ---- wards -----------------------------------------------------------
    wm = T.unit_monthly(base, "ward_id", months, sorted(wards))
    ward_rows = []
    for uid, g in wm.groupby("unit_id"):
        s = g.pothole_reports.to_numpy()
        m = T.unit_metrics(s, areas[uid], rate)
        al = int(g.all_complaints.sum())
        m.update(unit_id=int(uid), ward_name=wards[uid]["name"], zone=wards[uid]["zone"], all_complaints=al,
                 pothole_share=round(int(s.sum()) / al, 4) if al else None)
        ward_rows.append(m)
    T.label_trends(ward_rows)
    thr = {r["unit_id"]: r["active_month_threshold"] for r in ward_rows}
    wm["active_month"] = (wm.pothole_reports >= wm.unit_id.map(thr)).astype(int)
    wards_df = pd.DataFrame(ward_rows)

    # ---- city series ------------------------------------------------------
    city = wm.groupby("month")[["pothole_reports", "all_complaints"]].sum().reindex(months).reset_index()
    city["pothole_share"] = (city.pothole_reports / city.all_complaints.replace(0, np.nan)).round(4)
    city_trend = T.label_trends([T.trend_stats(city.pothole_reports.to_numpy())])[0]
    city_share_trend = T.label_trends([T.trend_stats((city.pothole_share.fillna(0) * 1000).round().to_numpy())])[0]

    # ---- clusters ---------------------------------------------------------
    pts = base[base.is_pothole == 1].merge(mem, left_on="rowid_", right_on="complaint_rowid", how="inner")
    cl_rows, cl_monthly = [], []
    for cid, c in sorted(cl.items()):
        poly = Polygon(c["boundary"])
        area = max(_poly_area_km2(c["boundary"]), c["boundary_area_km2"])
        member = pts[pts.cluster_id == cid]
        series = member.groupby("month").size().reindex(months, fill_value=0).to_numpy()
        inside = shapely.contains_xy(poly, base.longitude.to_numpy(), base.latitude.to_numpy())
        foot = base[inside]
        all_series = foot.groupby("month").size().reindex(months, fill_value=0).to_numpy()
        m = T.unit_metrics(series, area, rate, test_persistence=False)
        al = int(all_series.sum())
        m.update(unit_id=int(cid), all_complaints_in_footprint=al,
                 complaint_share=round(len(member) / al, 4) if al else None,
                 share_of_city_pothole_reports=round(len(member) / pot_total, 4))
        cl_rows.append(m)
        for mo, pr, ac in zip(months, series, all_series):
            cl_monthly.append({"unit_id": int(cid), "month": mo, "pothole_reports": int(pr), "all_complaints": int(ac),
                               "pothole_share": round(pr / ac, 4) if ac else None,
                               "active_month": int(pr >= m["active_month_threshold"])})
    T.label_trends(cl_rows)

    hotspots = []
    for m in cl_rows:
        c = cl[m["unit_id"]]
        hotspots.append({
            "cluster_id": m["unit_id"], "reports": c["report_count"], "radius_m": c["approx_radius_meters"],
            "persistence": m["persistence"], "active_months": m["active_months"], "eligible_months": m["eligible_months"],
            "persistent": m["persistent"],
            "recent_3_month_count": m["recent_3_month_count"], "historical_average": m["historical_average"],
            "recent_vs_historical_change": m["recent_vs_historical_change"],
            "observed_trend": m["trend"], "trend_tau": m["tau"], "trend_q_value": m.get("q_value"),
            "complaint_share": m["complaint_share"], "share_of_city_pothole_reports": m["share_of_city_pothole_reports"],
            "all_complaints_in_footprint": m["all_complaints_in_footprint"],
            "density_per_km2": c["density_reports_per_km2"], "date_min": c["date_min"], "date_max": c["date_max"],
            "centroid_latitude": round(c["centroid_latitude"], 4), "centroid_longitude": round(c["centroid_longitude"], 4),
            "single_coordinate_cluster": c["single_coordinate_cluster"], "distinct_coordinates": c["distinct_coordinates"],
            "active_month_threshold": m["active_month_threshold"],
        })
    hotspots.sort(key=lambda h: (-h["reports"], -h["density_per_km2"]))
    for i, h in enumerate(hotspots, 1):
        h["rank"] = i

    # ---- secondary dataset (separate, validation only) ---------------------
    secondary = None
    try:
        fms = parse_fms_kml()
        secondary = compare_with_primary(fms, widx, allc)
        union = shapely.union_all([Polygon(c["boundary"]) for c in cl.values()]) if cl else None
        if union is not None:
            f = fms.dropna(subset=["latitude", "longitude"])
            f = f[widx.contains(f.latitude, f.longitude)]
            ins = shapely.contains_xy(union, f.longitude.to_numpy(), f.latitude.to_numpy())
            ux, uy = to_xy(*[np.array(a) for a in zip(*[(y, x) for x, y in union.exterior.coords])]) if union.geom_type == "Polygon" else (None, None)
            a_in = sum(_poly_area_km2(list(p.exterior.coords)) for p in (union.geoms if union.geom_type == "MultiPolygon" else [union]))
            d_in = ins.sum() / a_in
            d_out = (~ins).sum() / max(city_area - a_in, 1e-9)
            secondary["fms_density_inside_icmyc_cluster_footprints_per_km2"] = round(float(d_in), 1)
            secondary["fms_density_elsewhere_per_km2"] = round(float(d_out), 1)
            secondary["density_ratio_inside_vs_elsewhere"] = round(float(d_in / d_out), 2)
            secondary["cluster_footprint_area_km2"] = round(a_in, 2)
    except Exception as exc:  # secondary source is optional
        log.warning("secondary dataset unavailable: %s", type(exc).__name__)
        secondary = {"status": "unavailable", "error": type(exc).__name__}

    # ---- privacy-preserving grid (250 m cells) ------------------------------
    gp = base[base.is_pothole == 1].merge(mem, left_on="rowid_", right_on="complaint_rowid", how="left")
    gp["clustered"] = gp.cluster_id.notna() & (gp.cluster_id != -1)
    x, y = to_xy(gp.latitude.to_numpy(), gp.longitude.to_numpy())
    gp["gx"] = np.floor(x / GRID_CELL_METERS).astype(int); gp["gy"] = np.floor(y / GRID_CELL_METERS).astype(int)
    from src.geo.distance import to_latlon
    cells = []
    for (gx, gy), g in gp.groupby(["gx", "gy"]):
        la, lo = to_latlon((gx + .5) * GRID_CELL_METERS, (gy + .5) * GRID_CELL_METERS)
        cells.append({"lat": round(float(la), 4), "lon": round(float(lo), 4), "reports": int(len(g)),
                      "clustered": int(g.clustered.sum()), "noise": int((~g.clustered).sum())})

    # ---- persist -------------------------------------------------------------
    sum_rows = pd.concat([
        wm.assign(unit_type="ward")[["unit_type", "unit_id", "month", "pothole_reports", "all_complaints", "pothole_share", "active_month"]],
        pd.DataFrame(cl_monthly).assign(unit_type="cluster")[["unit_type", "unit_id", "month", "pothole_reports", "all_complaints", "pothole_share", "active_month"]],
    ])
    n_persist = int(wards_df.persistent.fillna(False).sum()) if wards_df.persistent.notna().any() else None
    persistence_def = {
        "unit": "BBMP 2015 ward (polygon-assigned) for spatial-unit analysis; DBSCAN cluster footprint for hotspots",
        "eligible_months": n_months, "minimum_eligible_months_required": MIN_ELIGIBLE_MONTHS_FOR_PERSISTENCE,
        "city_pothole_rate_per_km2_month": round(rate, 5),
        "active_month_rule": "unit-month is active when pothole reports >= T, where T is the smallest count with "
                             "P(Poisson(rate x unit area) >= T) <= 0.05 (null: reports spread uniformly at the city-wide rate)",
        "persistent_rule": "persistent when active months >= smallest k with P(Binomial(eligible_months, p0) >= k) <= 0.01",
        "ward_active_threshold_distribution": {str(k): int(v) for k, v in wards_df.active_month_threshold.value_counts().sort_index().items()},
        "persistent_wards": n_persist,
        "supported": n_months >= MIN_ELIGIBLE_MONTHS_FOR_PERSISTENCE,
        "caveat": "Null ignores population and app-adoption differences; 'persistent' means complaint activity repeatedly "
                  "above the city-wide uniform expectation, not poor road condition.",
    }
    with connect() as con:
        con.execute("DELETE FROM spatial_unit_monthly")
        sum_rows.assign(run_id=run_id).to_sql("spatial_unit_monthly", con, if_exists="append", index=False)
        put_artifact(con, "hotspots", hotspots, run_id)
        put_artifact(con, "wards", wards_df.to_dict("records"), run_id)
        put_artifact(con, "city_timeline", city.to_dict("records"), run_id)
        put_artifact(con, "city_trend", {"pothole_count": city_trend, "pothole_share_x1000": city_share_trend}, run_id)
        put_artifact(con, "city_recent", T.recent_vs_historical(city.pothole_reports.to_numpy()), run_id)
        put_artifact(con, "persistence_definition", persistence_def, run_id)
        put_artifact(con, "secondary_comparison", secondary, run_id)
        put_artifact(con, "grid_cells", cells, run_id)
        put_artifact(con, "ward_boundaries_simplified", {
            str(n): {"name": w["name"], "zone": w["zone"],
                     "geometry": json.loads(shapely.to_geojson(w["geometry"].simplify(0.0003)))} for n, w in wards.items()}, run_id)

    sum_rows[sum_rows.unit_type == "ward"].drop(columns="unit_type").rename(columns={"unit_id": "ward_id"}).to_csv(REPORTS / "spatial_unit_monthly.csv", index=False)
    return {"hotspots": len(hotspots), "persistent_wards": n_persist, "city_trend": city_trend["trend"] if "trend" in city_trend else None}
