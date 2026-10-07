"""SQLite storage. Free-text/address/contact fields are never stored."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager

import pandas as pd

from src.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS ingestion_runs (
  id INTEGER PRIMARY KEY, source_key TEXT, source_identifier TEXT, retrieved_at TEXT,
  file_size INTEGER, sha256 TEXT, license TEXT, recorded_at TEXT);
CREATE TABLE IF NOT EXISTS complaints (
  rowid_ INTEGER PRIMARY KEY, request_id TEXT, created_at TEXT, month TEXT, issue_type TEXT,
  sub_issue_type TEXT, status TEXT, ward_id INTEGER, ward_name TEXT, source_ward_id INTEGER,
  latitude REAL, longitude REAL, is_pothole INTEGER, in_boundary INTEGER, usable INTEGER,
  suspect_fallback_pin INTEGER, coord_multiplicity INTEGER);
CREATE INDEX IF NOT EXISTS ix_c_created ON complaints(created_at);
CREATE INDEX IF NOT EXISTS ix_c_lat ON complaints(latitude);
CREATE INDEX IF NOT EXISTS ix_c_lon ON complaints(longitude);
CREATE INDEX IF NOT EXISTS ix_c_ward ON complaints(ward_id);
CREATE TABLE IF NOT EXISTS analysis_runs (
  run_id INTEGER PRIMARY KEY, created_at TEXT, eps_meters REAL, min_samples INTEGER,
  distance_metric TEXT, dataset_size INTEGER, cluster_count INTEGER, noise_count INTEGER,
  noise_percentage REAL, params_json TEXT);
CREATE TABLE IF NOT EXISTS clusters (
  run_id INTEGER, cluster_id INTEGER, payload TEXT, PRIMARY KEY (run_id, cluster_id));
CREATE TABLE IF NOT EXISTS cluster_membership (
  run_id INTEGER, complaint_rowid INTEGER, cluster_id INTEGER);
CREATE INDEX IF NOT EXISTS ix_cm ON cluster_membership(run_id, cluster_id);
CREATE TABLE IF NOT EXISTS spatial_unit_monthly (
  run_id INTEGER, unit_type TEXT, unit_id INTEGER, month TEXT, pothole_reports INTEGER,
  all_complaints INTEGER, pothole_share REAL, active_month INTEGER);
CREATE INDEX IF NOT EXISTS ix_sum ON spatial_unit_monthly(unit_type, unit_id);
CREATE TABLE IF NOT EXISTS artifacts (name TEXT PRIMARY KEY, run_id INTEGER, payload TEXT);
"""


@contextmanager
def connect(path=None):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path or DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _clean(o):
    """Replace NaN/inf (not valid JSON) by None, recursively."""
    if isinstance(o, float) and (o != o or o in (float("inf"), float("-inf"))):
        return None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def put_artifact(con, name: str, payload, run_id: int | None = None) -> None:
    payload = _clean(payload)
    con.execute("INSERT OR REPLACE INTO artifacts(name, run_id, payload) VALUES (?,?,?)",
                (name, run_id, json.dumps(payload, default=str)))


def get_artifact(con, name: str):
    r = con.execute("SELECT payload FROM artifacts WHERE name=?", (name,)).fetchone()
    return json.loads(r["payload"]) if r else None


def load_complaints(con, where: str = "1=1") -> pd.DataFrame:
    df = pd.read_sql(f"SELECT * FROM complaints WHERE {where}", con)
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True).dt.tz_convert("Asia/Kolkata")
    return df
