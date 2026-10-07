"""BBMP Fix My Street (May-June 2022) - secondary, separately-labelled source.

The KML carries complainant names, phone numbers and free text; only the
fields listed in KEEP are read, everything else is discarded while streaming.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from src.config import DATA_RAW, SOURCES

KEEP = {"Open_Date": "open_date", "Latitude": "latitude", "Longitude": "longitude", "Status": "status"}
_K = "{http://www.opengis.net/kml/2.2}"


def parse_fms_kml(path=None) -> pd.DataFrame:
    path = path or DATA_RAW / SOURCES["fms_kml"]["file"]
    rows = []
    for _, el in ET.iterparse(path, events=("end",)):
        if el.tag == f"{_K}Placemark":
            rec = {}
            for sd in el.iter(f"{_K}SimpleData"):
                name = sd.get("name")
                if name in KEEP:
                    rec[KEEP[name]] = sd.text
            rows.append(rec)
            el.clear()
    df = pd.DataFrame(rows)
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["open_date"] = pd.to_datetime(df["open_date"], format="%d/%m/%Y", errors="coerce")  # day-first (verified vs documented May-June 2022 window)
    return df


def compare_with_primary(fms: pd.DataFrame, ward_index, primary: pd.DataFrame) -> dict:
    """Ward-level comparison for the overlapping months. Sources stay separate."""
    f = fms.dropna(subset=["latitude", "longitude"]).copy()
    f["ward_id"] = ward_index.assign(f.latitude, f.longitude)
    inside = f[f.ward_id >= 0]
    months = sorted(set(inside.open_date.dt.strftime("%Y-%m").dropna()))
    p = primary[(primary.is_pothole == 1) & (primary.usable == 1) & (primary.month.isin(["2022-05", "2022-06"]))]
    a = inside.groupby("ward_id").size()
    b = p.groupby("ward_id").size()
    j = pd.concat([a.rename("fms"), b.rename("icmyc")], axis=1).fillna(0)
    out = {
        "fms_records": int(len(fms)), "fms_with_valid_coordinates": int(len(f)),
        "fms_inside_bengaluru_boundary": int(len(inside)),
        "fms_months": months,
        "fms_date_min": str(fms.open_date.min()), "fms_date_max": str(fms.open_date.max()),
        "icmyc_pothole_reports_same_months_inside_boundary": int(len(p)),
        "wards_compared": int(len(j)),
        "scale_ratio_fms_to_icmyc": round(float(len(inside) / max(len(p), 1)), 1),
    }
    if len(j) >= 10:
        rho, pv = spearmanr(j.fms, j.icmyc)
        out["spearman_ward_counts"] = {"rho": round(float(rho), 3), "p_value": float(pv)}
        top = lambda s: set(s.sort_values(ascending=False).head(20).index)
        out["top20_ward_overlap"] = len(top(j.fms) & top(j.icmyc))
    out["note"] = ("Independent source with a different reporting channel and ~%sx the volume in the overlapping months; "
                   "used only for validation / triangulation, never merged." % out["scale_ratio_fms_to_icmyc"])
    return out
