"""Project-wide paths, source definitions and documented analysis constants."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
DATA_CACHE = ROOT / "data" / "cache"
DATA_META = ROOT / "data" / "metadata"
REPORTS = ROOT / "reports"
DB_PATH = DATA_PROCESSED / "hotspots.sqlite"

OPENCITY = "https://data.opencity.in"

# --- Sources (resource ids verified against the OpenCity CKAN API) ---------
SOURCES = {
    "icmyc_log": {
        "label": "I Change My City Complaints Log - 2019 - 2022",
        "publisher": "Janaagraha (I Change My City)",
        "host": "OpenCity",
        "dataset": "i-change-my-city-data",
        "package_id": "9183b0b2-b49a-40a9-b36d-275e1eaedb3f",
        "resource_id": "a60abf5c-3a15-4967-af32-c3074248580f",
        "license": "Creative Commons Attribution Share-Alike (CC BY-SA)",
        "url": (
            f"{OPENCITY}/dataset/9183b0b2-b49a-40a9-b36d-275e1eaedb3f/resource/"
            "a60abf5c-3a15-4967-af32-c3074248580f/download/"
            "5f99b09a-64b5-45f0-ab18-4cf0a0cabf6d.csv"
        ),
        "file": "icmyc_complaints_2019_2022.csv",
        "required": True,
    },
    "ward_map_2015": {
        "label": "BBMP Ward Map - 2015 (198 wards)",
        "publisher": "BBMP (as republished by OpenCity)",
        "host": "OpenCity",
        "dataset": "bbmp-ward-information",
        "package_id": "87b978d1-352e-4b90-aa2c-9991e55d3425",
        "resource_id": "a0329df6-2924-43f4-8fe4-7a6ffcc1d53d",
        "license": "Not specified in OpenCity metadata",
        "url": (
            f"{OPENCITY}/dataset/87b978d1-352e-4b90-aa2c-9991e55d3425/resource/"
            "a0329df6-2924-43f4-8fe4-7a6ffcc1d53d/download/"
            "806d6b9c-e8d9-4eb0-a3a3-b2ba68ec3cda.kml"
        ),
        "file": "bbmp_ward_map_2015.kml",
        "required": True,
    },
    "fms_kml": {
        "label": "BBMP Fix My Street Data - May and June 2022 (KML)",
        "publisher": "BBMP (as republished by OpenCity)",
        "host": "OpenCity",
        "dataset": "bbmp-fix-my-street-data",
        "package_id": "3a1a98f8-f924-4257-a2a1-3b957b55b9f5",
        "resource_id": "d1d4a437-95ee-4327-9154-f9a8933b2110",
        "license": "Other (Public Domain)",
        "url": (
            f"{OPENCITY}/dataset/3a1a98f8-f924-4257-a2a1-3b957b55b9f5/resource/"
            "d1d4a437-95ee-4327-9154-f9a8933b2110/download/"
            "63b30ddf-5919-43d0-a6cf-17d5cc90a35c.kml"
        ),
        "file": "bbmp_fixmystreet_2022.kml",
        "required": False,
    },
}

# --- Schema ------------------------------------------------------------------
REQUIRED_COLUMNS = [
    "created_at", "ward_id", "title", "description", "sub_category_id",
    "civic_agency_id", "location", "address", "latitude", "longitude",
    "ward_title", "category_id", "category_title", "sub_category_title",
    "civic_agency_title", "complaint_status_title", "comment_count",
]
# Fields that must never leave the preprocessing step (free text / addresses).
SENSITIVE_COLUMNS = ["title", "description", "location", "address"]
NORMALIZED_COLUMNS = [
    "request_id", "created_at", "issue_type", "sub_issue_type", "status",
    "ward_id", "ward_name", "latitude", "longitude",
]

# --- Pothole taxonomy filter (verified against the category inventory) -------
# Taxonomy ids + the exact titles they must carry; preprocessing aborts if the
# titles stop matching, so a silent taxonomy change cannot corrupt the filter.
POTHOLE_SUBCATEGORIES = {
    66: ("Mobility - Roads, Footpaths and Infrastructure", "Fixing/Reparing Potholes"),
    594: ("PWD", "Repair of Potholes on Roads"),
}

# --- Dates -------------------------------------------------------------------
# Source stamps are naive local times. Both '-' and '/' separated rows are
# month-first (verified: zero chronological inversions in file order).
SOURCE_TIMEZONE = "Asia/Kolkata"
DATE_FORMAT = "%m-%d-%Y %H:%M"

# --- Geography ---------------------------------------------------------------
BOUNDARY_SOURCE = "BBMP Ward Map - 2015 (198 wards), OpenCity bbmp-ward-information"
BOUNDARY_VINTAGE = "2015 delimitation (198 wards; in force through the data period)"
BOUNDARY_TYPE = "Union of official ward polygons (administrative; not an approximation)"
PROJECTED_CRS = "EPSG:32643"  # WGS 84 / UTM zone 43N, metres
EARTH_RADIUS_M = 6_371_008.8
GLOBAL_LAT_RANGE = (-90.0, 90.0)
GLOBAL_LON_RANGE = (-180.0, 180.0)

# A coordinate shared by this many (or more) complaints of ANY category is
# treated as a suspected default / geocoder-fallback pin (see DATASET_FEASIBILITY.md).
FALLBACK_PIN_MIN_MULTIPLICITY = 8

# --- DBSCAN ------------------------------------------------------------------
SWEEP_EPS_METERS = [75, 100, 150, 200, 250, 300, 400, 500, 750, 1000]
SWEEP_MIN_SAMPLES = [3, 4, 5, 6, 8, 10]
DEFAULT_K_FOR_KDIST = 5

# --- Temporal ----------------------------------------------------------------
MIN_ELIGIBLE_MONTHS_FOR_PERSISTENCE = 24
MIN_ELIGIBLE_MONTHS_FOR_TREND = 12
MIN_REPORTS_FOR_TREND = 10
RECENT_MONTHS = 3
MIN_HISTORY_MONTHS = 12
ALPHA_ACTIVE_MONTH = 0.05      # per-month false-activity rate under the null
ALPHA_PERSISTENCE = 0.01       # per-unit tail probability for "persistent"
ALPHA_TREND = 0.05             # BH-adjusted

# --- Data gate ---------------------------------------------------------------
GATE_MIN_USABLE_POTHOLE_POINTS = 500   # below this DBSCAN is not meaningful here
GATE_MIN_MONTHS_COVERED = 24
NEAR_DUPLICATE_METERS = 10
# Public outputs round coordinates to 3 decimals (~110 m) to avoid publishing exact complaint pins.
PUBLIC_COORD_DECIMALS = 3
GRID_CELL_METERS = 250
