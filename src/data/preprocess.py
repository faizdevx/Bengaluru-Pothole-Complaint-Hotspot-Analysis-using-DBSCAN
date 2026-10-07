"""Schema validation, normalisation, pothole filtering, coordinate and
duplicate analysis. Free-text / address fields are dropped here and never
leave this module."""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from src.config import (
    DATA_RAW, DATE_FORMAT, FALLBACK_PIN_MIN_MULTIPLICITY, POTHOLE_SUBCATEGORIES,
    REQUIRED_COLUMNS, SENSITIVE_COLUMNS, SOURCE_TIMEZONE, SOURCES,
)
from src.geo.boundary import WardIndex


class SchemaError(ValueError):
    pass


def read_raw(path=None) -> tuple[pd.DataFrame, str]:
    path = path or DATA_RAW / SOURCES["icmyc_log"]["file"]
    for enc in ("utf-8", "cp1252"):
        try:
            return pd.read_csv(path, encoding=enc, low_memory=False), enc
        except UnicodeDecodeError:
            continue
    raise SchemaError("file is neither UTF-8 nor cp1252")


def validate_schema(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise SchemaError(f"missing required columns: {missing}")


def parse_timestamps(raw: pd.Series) -> pd.Series:
    """Parse month-first stamps ('1-1-2019 06:33' and '7/31/2022 14:03') and
    localise the naive values to Asia/Kolkata. Unparseable -> NaT."""
    s = raw.astype("string").str.strip().str.replace("/", "-", regex=False)
    t = pd.to_datetime(s, format=DATE_FORMAT, errors="coerce")
    return t.dt.tz_localize(SOURCE_TIMEZONE)


def pothole_mask(df: pd.DataFrame) -> pd.Series:
    """Taxonomy-based filter on sub_category_id; titles must match the verified
    inventory, otherwise the taxonomy has drifted and we abort."""
    for sid, (cat, sub) in POTHOLE_SUBCATEGORIES.items():
        rows = df[df["sub_category_id"] == sid]
        if len(rows) and (
            set(rows["sub_category_title"].dropna()) != {sub}
            or set(rows["category_title"].dropna()) - {cat}
        ):
            raise SchemaError(f"taxonomy drift for sub_category_id={sid}")
    return df["sub_category_id"].isin(POTHOLE_SUBCATEGORIES)


def make_request_id(row_key: pd.Series) -> pd.Series:
    """The source has NO request identifier. This is a surrogate content hash."""
    return row_key.map(lambda s: "icmyc-" + hashlib.sha1(s.encode()).hexdigest()[:12])


def coordinate_flags(df: pd.DataFrame) -> pd.DataFrame:
    lat, lon = df["latitude"], df["longitude"]
    out = pd.DataFrame(index=df.index)
    out["null_coord"] = lat.isna() | lon.isna()
    out["out_of_global_range"] = ~lat.between(-90, 90) | ~lon.between(-180, 180)
    out["zero_zero"] = (lat == 0) & (lon == 0)
    # swapped: lat looks like a Bengaluru longitude and vice versa
    out["swapped"] = lat.between(77, 78) & lon.between(12, 14)
    dec = lambda s: s.map(lambda v: len(repr(float(v)).split(".")[1].rstrip("0")) if pd.notna(v) else 0)
    out["decimals"] = np.minimum(dec(lat), dec(lon))
    out["coarse_rounded"] = out["decimals"] <= 3  # ~110 m resolution or worse
    return out


def normalise(raw: pd.DataFrame, ward_index: WardIndex) -> pd.DataFrame:
    validate_schema(raw)
    df = raw.copy()
    df["created_ts"] = parse_timestamps(df["created_at"])
    key = (df["created_at"].astype(str) + "|" + df["latitude"].astype(str) + "|"
           + df["longitude"].astype(str) + "|" + df["sub_category_id"].astype(str) + "|"
           + df["title"].astype(str) + "|" + df["description"].astype(str))
    request_id = make_request_id(key)
    is_pothole = pothole_mask(df)
    flags = coordinate_flags(df)
    poly_ward = ward_index.assign(df["latitude"], df["longitude"])
    names = {n: w["name"] for n, w in ward_index.wards.items()}
    out = pd.DataFrame({
        "request_id": request_id,
        "created_at": df["created_ts"],
        "issue_type": df["category_title"].fillna("Unknown"),
        "sub_issue_type": df["sub_category_title"].fillna("Unknown"),
        "status": df["complaint_status_title"],
        "source_ward_id": df["ward_id"],
        "ward_id": poly_ward,                       # polygon-derived (primary spatial unit)
        "ward_name": pd.Series(poly_ward, index=df.index).map(names),
        "latitude": df["latitude"],
        "longitude": df["longitude"],
        "is_pothole": is_pothole,
        "in_boundary": poly_ward >= 0,
    })
    out = pd.concat([out, flags], axis=1)
    # multiplicity of the exact coordinate across ALL complaint categories
    mult = out.groupby(["latitude", "longitude"])["request_id"].transform("size")
    out["coord_multiplicity"] = mult
    out["suspect_fallback_pin"] = mult >= FALLBACK_PIN_MIN_MULTIPLICITY
    out["valid_coord"] = ~(out.null_coord | out.out_of_global_range | out.zero_zero | out.swapped)
    out["usable"] = out.valid_coord & out.in_boundary & out.created_at.notna()
    assert not set(SENSITIVE_COLUMNS) & set(out.columns)
    return out
