"""Read-only access to precomputed analysis outputs. No request ever recomputes
clustering; complaint-level rows are never returned."""
from __future__ import annotations

import json
import sqlite3
from functools import lru_cache

import pandas as pd

from src.config import DATA_META, DB_PATH, REPORTS

NO_ANALYSIS = "No analysis has been run yet."


def _con():
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def db_ready() -> bool:
    if not DB_PATH.exists():
        return False
    try:
        with _con() as con:
            return con.execute("SELECT COUNT(*) FROM analysis_runs").fetchone()[0] > 0
    except sqlite3.Error:
        return False


def _mtime() -> float:
    return DB_PATH.stat().st_mtime if DB_PATH.exists() else 0.0


@lru_cache(maxsize=64)
def _artifact(name: str, mtime: float):
    with _con() as con:
        r = con.execute("SELECT payload FROM artifacts WHERE name=?", (name,)).fetchone()
    return json.loads(r["payload"]) if r else None


def artifact(name: str):
    return _artifact(name, _mtime()) if DB_PATH.exists() else None


@lru_cache(maxsize=4)
def _run(mtime: float):
    with _con() as con:
        r = con.execute("SELECT * FROM analysis_runs ORDER BY run_id DESC LIMIT 1").fetchone()
        if r is None:
            return None
        run = dict(r)
        run["params"] = json.loads(run.pop("params_json"))
        run["clusters"] = {x["cluster_id"]: json.loads(x["payload"]) for x in
                           con.execute("SELECT cluster_id, payload FROM clusters WHERE run_id=?", (run["run_id"],))}
    return run


def run():
    return _run(_mtime()) if DB_PATH.exists() else None


def unit_series(unit_type: str, unit_id: int) -> list[dict]:
    with _con() as con:
        rows = con.execute("SELECT month, pothole_reports, all_complaints, pothole_share, active_month FROM spatial_unit_monthly "
                           "WHERE unit_type=? AND unit_id=? ORDER BY month", (unit_type, unit_id)).fetchall()
    return [dict(r) for r in rows]


def sources() -> list[dict]:
    out = []
    for p in sorted(DATA_META.glob("*.json")):
        m = json.loads(p.read_text())
        out.append({k: m.get(k) for k in ("key", "label", "publisher", "host", "license", "source_identifier",
                                          "retrieved_at", "file_size", "sha256")})
    return out


def report_json(name: str):
    p = REPORTS / name
    return json.loads(p.read_text()) if p.exists() else None


def report_csv(name: str) -> list[dict] | None:
    p = REPORTS / name
    return pd.read_csv(p).where(lambda d: d.notna(), None).to_dict("records") if p.exists() else None
