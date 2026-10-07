"""Data-quality measurements and the data gate. Every number is computed from
the downloaded file."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

from src.config import (
    BOUNDARY_SOURCE, BOUNDARY_TYPE, BOUNDARY_VINTAGE, EARTH_RADIUS_M, GATE_MIN_MONTHS_COVERED,
    GATE_MIN_USABLE_POTHOLE_POINTS, NEAR_DUPLICATE_METERS, POTHOLE_SUBCATEGORIES,
    PUBLIC_COORD_DECIMALS, FALLBACK_PIN_MIN_MULTIPLICITY,
)


def category_distribution(raw: pd.DataFrame) -> pd.DataFrame:
    g = (raw.fillna({"category_title": "(missing)", "sub_category_title": "(missing)"})
         .groupby(["category_id", "category_title", "sub_category_id", "sub_category_title"], dropna=False)
         .size().reset_index(name="count"))
    g["included_as_pothole"] = g["sub_category_id"].isin(POTHOLE_SUBCATEGORIES)
    g["share_pct"] = (100 * g["count"] / len(raw)).round(3)
    return g.sort_values("count", ascending=False)


def monthly_quality(d: pd.DataFrame) -> pd.DataFrame:
    d = d[d.created_at.notna()].copy()
    d["month"] = d.created_at.dt.strftime("%Y-%m")
    months = pd.period_range(d.month.min(), d.month.max(), freq="M").strftime("%Y-%m")
    m = pd.DataFrame({"month": months})
    allc = d.groupby("month").size().rename("all_complaints")
    pot = d[d.is_pothole].groupby("month").size().rename("pothole_reports")
    use = d[d.is_pothole & d.usable & ~d.suspect_fallback_pin].groupby("month").size().rename("pothole_usable_for_dbscan")
    m = m.join(allc, on="month").join(pot, on="month").join(use, on="month").fillna(0)
    for c in m.columns[1:]:
        m[c] = m[c].astype(int)
    m["pothole_share"] = (m.pothole_reports / m.all_complaints.replace(0, np.nan)).round(4)
    return m


def coordinate_quality(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for scope, s in (("all_complaints", d), ("pothole_reports", d[d.is_pothole])):
        n = len(s)
        checks = {
            "null_coordinates": s.null_coord, "out_of_global_range": s.out_of_global_range,
            "zero_zero": s.zero_zero, "swapped_lat_lon": s.swapped,
            "coarse_rounded_(<=3_decimals)": s.coarse_rounded,
            "outside_bengaluru_boundary": ~s.in_boundary,
            f"suspect_fallback_pin_(multiplicity>={FALLBACK_PIN_MIN_MULTIPLICITY})": s.suspect_fallback_pin,
            "ward_id_disagrees_with_polygon_(inside_boundary_only)": (s.source_ward_id != s.ward_id) & s.in_boundary,
            "usable_valid_inside_boundary": s.usable,
        }
        for name, mask in checks.items():
            rows.append({"scope": scope, "check": name, "count": int(mask.sum()),
                         "pct": round(100 * mask.sum() / n, 3) if n else 0.0})
    return pd.DataFrame(rows)


def duplicate_analysis(d: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    p = d[d.is_pothole]
    exact_rows = int(d.duplicated(["request_id"], keep="first").sum())
    stats = {
        "request_id_available_in_source": False,
        "note": "Source has no request identifier; request_id is a surrogate content hash, so "
                "duplicate request IDs equal exact duplicate rows.",
        "exact_duplicate_rows_all": exact_rows,
        "exact_duplicate_rows_pothole": int(p.duplicated(["request_id"], keep="first").sum()),
        "unique_coordinates_all": int(d.groupby(["latitude", "longitude"]).ngroups),
        "unique_coordinates_pothole": int(p.groupby(["latitude", "longitude"]).ngroups),
        "pothole_reports_sharing_exact_coordinate_with_another_pothole_report":
            int(p.duplicated(["latitude", "longitude"], keep=False).sum()),
        "all_reports_sharing_exact_coordinate": int(d.duplicated(["latitude", "longitude"], keep=False).sum()),
    }
    pp = p[p.valid_coord]
    if len(pp):
        tree = BallTree(np.radians(pp[["latitude", "longitude"]].to_numpy()), metric="haversine")
        cnt = tree.query_radius(np.radians(pp[["latitude", "longitude"]].to_numpy()),
                                r=NEAR_DUPLICATE_METERS / EARTH_RADIUS_M, count_only=True)
        stats[f"pothole_reports_with_another_pothole_report_within_{NEAR_DUPLICATE_METERS}m"] = int((cnt > 1).sum())
    g = d.groupby(["latitude", "longitude"]).agg(
        reports_all_categories=("request_id", "size"),
        pothole_reports=("is_pothole", "sum"),
        distinct_sub_issue_types=("sub_issue_type", "nunique"),
        distinct_months=("created_at", lambda s: s.dt.strftime("%Y-%m").nunique()),
        first_report=("created_at", "min"), last_report=("created_at", "max"),
        suspect_fallback_pin=("suspect_fallback_pin", "first"),
    ).reset_index()
    g = g[(g.reports_all_categories >= 2) & (g.pothole_reports >= 1)].copy()
    g["latitude"] = g["latitude"].round(PUBLIC_COORD_DECIMALS)   # privacy: coarse public coords
    g["longitude"] = g["longitude"].round(PUBLIC_COORD_DECIMALS)
    g["first_report"] = g["first_report"].dt.strftime("%Y-%m-%d")
    g["last_report"] = g["last_report"].dt.strftime("%Y-%m-%d")
    g["pothole_reports"] = g["pothole_reports"].astype(int)
    g = g.sort_values(["reports_all_categories", "pothole_reports"], ascending=False)
    mult = d.groupby(["latitude", "longitude"]).size()
    stats["coordinate_multiplicity_distribution_all"] = {str(k): int(v) for k, v in mult.value_counts().sort_index().head(12).items()}
    stats["max_coordinate_multiplicity_all_categories"] = int(mult.max())
    stats["max_coordinate_multiplicity_pothole_reports"] = int(p.groupby(["latitude", "longitude"]).size().max())
    stats["fallback_pin_sensitivity_pothole_rows"] = {
        str(t): int(p[p.coord_multiplicity >= t].shape[0]) for t in (3, 5, 8, 15, 30)}
    return g, stats


def data_gate(d: pd.DataFrame, raw: pd.DataFrame, enc: str) -> dict:
    p = d[d.is_pothole]
    usable = p[p.usable & ~p.suspect_fallback_pin]
    months_cov = int(usable.created_at.dt.strftime("%Y-%m").nunique())
    passed = len(usable) >= GATE_MIN_USABLE_POTHOLE_POINTS and months_cov >= GATE_MIN_MONTHS_COVERED
    t = d.created_at
    return {
        "gate_passed": bool(passed),
        "gate_rule": f"usable pothole points >= {GATE_MIN_USABLE_POTHOLE_POINTS} and months covered >= {GATE_MIN_MONTHS_COVERED}",
        "file_encoding": enc,
        "row_count": int(len(raw)), "column_count": int(raw.shape[1]), "columns": list(raw.columns),
        "date_min": t.min().isoformat(), "date_max": t.max().isoformat(),
        "missing_timestamps": int(t.isna().sum()),
        "months_with_data": int(t.dt.strftime("%Y-%m").nunique()),
        "bengaluru_coverage": {
            "rows_inside_boundary": int(d.in_boundary.sum()),
            "rows_inside_boundary_pct": round(100 * d.in_boundary.mean(), 2),
            "boundary_source": BOUNDARY_SOURCE, "boundary_vintage": BOUNDARY_VINTAGE, "boundary_type": BOUNDARY_TYPE,
        },
        "coordinate_range_all": {
            "lat_min": float(d.latitude.min()), "lat_max": float(d.latitude.max()),
            "lon_min": float(d.longitude.min()), "lon_max": float(d.longitude.max())},
        "missing_coordinate_count": int(d.null_coord.sum()),
        "missing_coordinate_pct": round(100 * d.null_coord.mean(), 3),
        "valid_coordinate_count": int(d.valid_coord.sum()),
        "pothole": {
            "taxonomy_rows": int(len(p)),
            "valid_coordinates": int(p.valid_coord.sum()),
            "inside_boundary": int(p.usable.sum()),
            "suspect_fallback_pin_rows_inside_boundary": int((p.usable & p.suspect_fallback_pin).sum()),
            "usable_for_dbscan": int(len(usable)),
            "months_covered": months_cov,
            "date_min": p.created_at.min().isoformat(), "date_max": p.created_at.max().isoformat(),
        },
        "fallback_pin_rule": f"coordinate shared by >= {FALLBACK_PIN_MIN_MULTIPLICITY} complaints of any category",
    }
