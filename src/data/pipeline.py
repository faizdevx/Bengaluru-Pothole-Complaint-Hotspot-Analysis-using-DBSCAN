from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

import pandas as pd

from src.config import DATA_META, REPORTS, SOURCES
from src.data import quality
from src.data.preprocess import normalise, read_raw
from src.geo.boundary import WardIndex, parse_ward_kml
from src.storage.db import connect, put_artifact

log = logging.getLogger("preprocess")


def run_preprocess() -> dict:
    REPORTS.mkdir(exist_ok=True)
    raw, enc = read_raw()
    wards = parse_ward_kml()
    d = normalise(raw, WardIndex(wards))
    log.info("rows=%d columns=%d encoding=%s", len(raw), raw.shape[1], enc)

    gate = quality.data_gate(d, raw, enc)
    cat = quality.category_distribution(raw)
    cat.to_csv(REPORTS / "category_distribution.csv", index=False)
    monthly = quality.monthly_quality(d)
    monthly.to_csv(REPORTS / "monthly_data_quality.csv", index=False)
    coord = quality.coordinate_quality(d)
    coord.to_csv(REPORTS / "coordinate_quality.csv", index=False)
    dup_df, dup_stats = quality.duplicate_analysis(d)
    dup_df.to_csv(REPORTS / "duplicate_coordinate_analysis.csv", index=False)

    dup_stats["exact_duplicate_rows_raw_all_columns"] = int(raw.duplicated().sum())
    dup_stats["duplicate_surrogate_key_all"] = dup_stats.pop("exact_duplicate_rows_all")
    dup_stats["duplicate_surrogate_key_pothole"] = dup_stats.pop("exact_duplicate_rows_pothole")
    dup_stats["note"] = ("Source has no request identifier. request_id is a surrogate hash of (timestamp, coordinates, sub-category and "
                         "the report free text); duplicate_surrogate_key_* counts rows repeating that key.")
    status = d.groupby("status").size().to_dict()
    gate["duplicates"] = dup_stats
    gate["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    gate["taxonomy"] = {
        "included": [{"sub_category_id": k, "category": v[0], "sub_category": v[1]} for k, v in
                     __import__("src.config", fromlist=["x"]).POTHOLE_SUBCATEGORIES.items()],
        "excluded_related_example": "Tarring Or Asphalting Of Existing Road (1623 rows) - resurfacing requests, "
                                    "not pothole reports under the source taxonomy",
    }
    (REPORTS / "data_feasibility.json").write_text(json.dumps(gate, indent=2, default=str))
    (REPORTS / "data_quality.json").write_text(json.dumps({
        "missing_values_by_column": raw.isna().sum().astype(int).to_dict(),
        "status_distribution": {str(k): int(v) for k, v in status.items()},
        "month_gaps": [m for m, c in zip(monthly.month, monthly.all_complaints) if c == 0],
        "coordinate_quality": coord.to_dict("records"),
        "duplicates": dup_stats,
        "timestamp_note": "Source stamps are naive local times, treated as Asia/Kolkata; both '-' and '/' "
                          "separated rows are month-first (0 chronological inversions in file order).",
    }, indent=2, default=str))

    if not gate["gate_passed"]:
        log.error("DATA GATE FAILED: %s", gate["gate_rule"])
        return gate

    out = d.copy()
    out["month"] = out.created_at.dt.strftime("%Y-%m")
    out["created_at"] = out.created_at.dt.tz_convert("UTC").dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    cols = ["request_id", "created_at", "month", "issue_type", "sub_issue_type", "status", "ward_id",
            "ward_name", "source_ward_id", "latitude", "longitude", "is_pothole", "in_boundary", "usable",
            "suspect_fallback_pin", "coord_multiplicity"]
    with connect() as con:
        con.execute("DELETE FROM complaints")
        out[cols].astype({c: int for c in ("is_pothole", "in_boundary", "usable", "suspect_fallback_pin")}) \
            .to_sql("complaints", con, if_exists="append", index=False)
        con.execute("DELETE FROM ingestion_runs")
        for key in SOURCES:
            p = DATA_META / f"{key}.json"
            if p.exists():
                m = json.loads(p.read_text())
                con.execute("INSERT INTO ingestion_runs(source_key,source_identifier,retrieved_at,file_size,sha256,license,recorded_at)"
                            " VALUES (?,?,?,?,?,?,?)", (key, m["source_identifier"], m["retrieved_at"], m["file_size"],
                                                        m["sha256"], m["license"], gate["generated_at"]))
        put_artifact(con, "data_gate", gate)
        put_artifact(con, "category_distribution", cat.head(40).to_dict("records"))
        put_artifact(con, "monthly_quality", monthly.to_dict("records"))
        put_artifact(con, "ward_polygons", {str(n): {"name": w["name"], "zone": w["zone"]} for n, w in wards.items()})
    log.info("stored %d complaints (pothole=%d, usable pothole=%d)", len(out), int(out.is_pothole.sum()),
             gate["pothole"]["usable_for_dbscan"])
    return gate
