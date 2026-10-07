"""FastAPI application: serves precomputed results only."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.api import store
from src.config import REPORTS

log = logging.getLogger("api")
BASE = Path(__file__).resolve().parent
LIMITATION = ("This project identifies geographic concentrations of civic pothole complaints. It does not measure "
              "actual pothole density or physical road-condition severity.")

app = FastAPI(title="Bengaluru Pothole Hotspot Detector", version="1.0.0",
              description="Historical civic complaint analysis (DBSCAN). Not real-time.")
templates = Jinja2Templates(directory=str(BASE / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
if REPORTS.exists():
    app.mount("/reports-files", StaticFiles(directory=str(REPORTS)), name="reports-files")

PAGES = {
    "dashboard": ("/", "Dashboard"), "map": ("/map", "Map"), "hotspots": ("/hotspots", "Hotspots"),
    "timeline": ("/timeline", "Timeline"), "clusters": ("/clusters", "Cluster Explorer"),
    "spatial": ("/spatial", "Spatial Analysis"), "parameters": ("/parameters", "DBSCAN Parameters"),
    "quality": ("/quality", "Data Quality"), "about": ("/about", "About"),
}


def _need_analysis():
    if not store.db_ready():
        raise HTTPException(status_code=404, detail=store.NO_ANALYSIS)


def _page(request: Request, key: str):
    return templates.TemplateResponse(request, f"{key}.html", {
        "page": key, "pages": PAGES, "title": PAGES[key][1], "limitation": LIMITATION})


def _make_page(key: str):
    def view(request: Request):
        return _page(request, key)
    return view


for _k, (_path, _) in PAGES.items():
    app.add_api_route(_path, _make_page(_k), methods=["GET"], response_class=HTMLResponse, name=_k,
                      include_in_schema=False)


@app.get("/health")
def health():
    return {"status": "ok", "analysis_available": store.db_ready(), "data_type": "historical (not real-time)"}


@app.get("/api/data-status")
def data_status():
    gate = store.artifact("data_gate") if store.db_ready() else store.report_json("data_feasibility.json")
    return {
        "data_type": "Historical public civic complaint data",
        "coverage": "2019–2022",
        "source": "Janaagraha / I Change My City (hosted by OpenCity)",
        "realtime": False,
        "sources": store.sources(),
        "last_source_retrieval": next((s["retrieved_at"] for s in store.sources() if s["key"] == "icmyc_log"), None),
        "analysis_available": store.db_ready(),
        "message": None if store.db_ready() else store.NO_ANALYSIS,
        "date_min": gate and gate["date_min"], "date_max": gate and gate["date_max"],
        "gate": gate and {"passed": gate["gate_passed"], "rule": gate["gate_rule"], "pothole": gate["pothole"],
                          "row_count": gate["row_count"], "missing_coordinate_pct": gate["missing_coordinate_pct"],
                          "bengaluru_coverage": gate["bengaluru_coverage"], "duplicates": gate["duplicates"]},
        "secondary": store.artifact("secondary_comparison") if store.db_ready() else None,
        "limitation": LIMITATION,
    }


@app.get("/api/summary")
def summary():
    _need_analysis()
    run, hot = store.run(), store.artifact("hotspots")
    gate = store.artifact("data_gate")
    wards = store.artifact("wards")
    top = max(hot, key=lambda h: h["reports"]) if hot else None
    clustered = run["dataset_size"] - run["noise_count"]
    return {
        "total_pothole_reports": gate["pothole"]["taxonomy_rows"],
        "valid_coordinate_pothole_reports": gate["pothole"]["valid_coordinates"],
        "analysed_pothole_reports": run["dataset_size"],
        "clusters": run["cluster_count"], "clustered_reports": clustered,
        "noise_reports": run["noise_count"], "noise_percentage": run["noise_percentage"],
        "persistent_complaint_areas": sum(1 for w in wards if w.get("persistent")),
        "wards_total": len(wards),
        "highest_activity_cluster": top and {"cluster_id": top["cluster_id"], "reports": top["reports"], "radius_m": top["radius_m"]},
        "eps_meters": run["eps_meters"], "min_samples": run["min_samples"], "distance_metric": run["distance_metric"],
        "source_date_range": {"min": gate["date_min"], "max": gate["date_max"]},
        "last_source_retrieval": next((s["retrieved_at"] for s in store.sources() if s["key"] == "icmyc_log"), None),
        "analysis_run_at": run["created_at"],
        "city_trend": store.artifact("city_trend"), "city_recent": store.artifact("city_recent"),
        "limitation": LIMITATION,
    }


@app.get("/api/hotspots")
def hotspots(sort: str = Query("rank"), order: str = Query("asc", pattern="^(asc|desc)$"),
             min_reports: int = Query(0, ge=0), trend: str | None = None, limit: int = Query(200, ge=1, le=500)):
    _need_analysis()
    rows = store.artifact("hotspots")
    if rows and sort not in rows[0]:
        raise HTTPException(422, f"unknown sort field '{sort}'")
    rows = [r for r in rows if r["reports"] >= min_reports and (trend is None or r["observed_trend"] == trend)]

    def key(r):
        v = r[sort]
        return (isinstance(v, str) or v is None, v if not isinstance(v, str) and v is not None else 0)
    rows = sorted(rows, key=key, reverse=(order == "desc"))
    return {"count": len(rows), "city_recent": store.artifact("city_recent"), "hotspots": rows[:limit],
            "note": "Complaint activity, not pothole severity."}


@app.get("/api/hotspots/{cluster_id}")
def hotspot(cluster_id: int):
    _need_analysis()
    h = next((r for r in store.artifact("hotspots") if r["cluster_id"] == cluster_id), None)
    if h is None:
        raise HTTPException(404, f"cluster {cluster_id} not found")
    c = store.run()["clusters"][cluster_id]
    detail = {**h, "bbox": [c["bbox_min_lat"], c["bbox_min_lon"], c["bbox_max_lat"], c["bbox_max_lon"]],
              "boundary_area_km2": c["boundary_area_km2"], "monthly": store.unit_series("cluster", cluster_id),
              "boundary": c["boundary"], "boundary_kind": "cluster visualization boundary (not a pothole area)"}
    return detail


@app.get("/api/clusters")
def clusters():
    _need_analysis()
    run, hot = store.run(), {h["cluster_id"]: h for h in store.artifact("hotspots")}
    feats = []
    for cid, c in run["clusters"].items():
        h = hot[int(cid)]
        props = {k: h[k] for k in ("cluster_id", "rank", "reports", "radius_m", "density_per_km2", "date_min", "date_max",
                                   "persistence", "active_months", "eligible_months", "observed_trend",
                                   "complaint_share", "single_coordinate_cluster")}
        feats.append({"type": "Feature", "properties": props, "geometry": {"type": "Polygon", "coordinates": [c["boundary"]]}})
        feats.append({"type": "Feature", "properties": {**props, "feature": "centroid"},
                      "geometry": {"type": "Point", "coordinates": [round(c["centroid_longitude"], 4), round(c["centroid_latitude"], 4)]}})
    return {"type": "FeatureCollection", "features": feats,
            "metadata": {"eps_meters": run["eps_meters"], "min_samples": run["min_samples"], "noise_percentage": run["noise_percentage"],
                         "boundary_kind": "cluster visualization boundary (50 m-buffered convex hull; not a pothole area)"}}


@app.get("/api/grid")
def grid():
    """Privacy-preserving aggregation: 250 m cells with counts, no individual locations."""
    _need_analysis()
    return {"cell_meters": 250, "cells": store.artifact("grid_cells")}


@app.get("/api/timeline")
def timeline(unit_type: str = Query("city", pattern="^(city|ward|cluster)$"), unit_id: int | None = None):
    _need_analysis()
    if unit_type == "city":
        return {"unit_type": "city", "series": store.artifact("city_timeline"), "trend": store.artifact("city_trend"),
                "recent": store.artifact("city_recent")}
    if unit_id is None:
        raise HTTPException(422, "unit_id is required for ward/cluster timelines")
    series = store.unit_series(unit_type, unit_id)
    if not series:
        raise HTTPException(404, f"{unit_type} {unit_id} not found")
    return {"unit_type": unit_type, "unit_id": unit_id, "series": series}


@app.get("/api/spatial-units")
def spatial_units(geometry: bool = False):
    _need_analysis()
    out = {"unit": "BBMP 2015 ward", "boundary_source": "BBMP Ward Map - 2015 (OpenCity)",
           "persistence": store.artifact("persistence_definition"), "units": store.artifact("wards")}
    if geometry:
        out["geometries"] = store.artifact("ward_boundaries_simplified")
    return out


@app.get("/api/parameters")
def parameters():
    _need_analysis()
    run = store.run()
    return {"eps_meters": run["eps_meters"], "min_samples": run["min_samples"], "distance_metric": run["distance_metric"],
            "dataset_size": run["dataset_size"], "params": run["params"], "sweep": store.artifact("dbscan_sweep"),
            "warnings": store.artifact("dbscan_warnings")}


@app.get("/api/quality")
def quality():
    _need_analysis()
    gate = {k: v for k, v in store.artifact("data_gate").items() if k != "columns"}   # raw column names stay out of the API
    return {"gate": gate, "monthly": store.artifact("monthly_quality"),
            "categories": store.artifact("category_distribution"),
            "coordinate_quality": (store.report_json("data_quality.json") or {}).get("coordinate_quality"),
            "status_distribution": (store.report_json("data_quality.json") or {}).get("status_distribution")}


@app.exception_handler(HTTPException)
async def _http_exc(request: Request, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
