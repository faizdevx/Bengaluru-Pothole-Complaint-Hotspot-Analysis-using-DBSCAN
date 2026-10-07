import json
import sqlite3

import pytest

from src.api import store
from src.config import DB_PATH, REPORTS, SENSITIVE_COLUMNS

pytestmark = pytest.mark.skipif(not store.db_ready(), reason="run `python scripts/run_pipeline.py` first")


def test_sensitive_columns_not_in_database():
    con = sqlite3.connect(DB_PATH)
    cols = {r[1] for r in con.execute("PRAGMA table_info(complaints)")}
    assert not cols & set(SENSITIVE_COLUMNS)
    assert not cols & {"description", "title", "address", "location", "phone"}


def test_api_never_returns_complaint_rows_or_text():
    from fastapi.testclient import TestClient
    from src.api.app import app
    c = TestClient(app)
    con = sqlite3.connect(DB_PATH)
    ids = [r[0] for r in con.execute("SELECT request_id FROM complaints LIMIT 200")]
    for url in ["/api/summary", "/api/hotspots", "/api/clusters", "/api/grid", "/api/spatial-units", "/api/quality",
                "/api/data-status", "/api/parameters", "/api/timeline"]:
        body = c.get(url).text
        for k in ("description", "address", "complainant", "phone"):
            assert k not in body.lower(), (url, k)
        assert not any(i in body for i in ids)


def test_committed_reports_do_not_contain_free_text():
    import pandas as pd
    for name in ["duplicate_coordinate_analysis.csv", "cluster_summary.csv"]:
        cols = set(pd.read_csv(REPORTS / name).columns)
        assert not cols & {"description", "title", "address", "location"}
    g = json.loads((REPORTS / "dbscan_clusters.geojson").read_text())
    assert all(set(f["properties"]) <= {"cluster_id", "rank", "reports", "radius_m", "boundary_kind", "feature"} for f in g["features"])


def test_logging_does_not_emit_complaint_text(caplog):
    import logging
    caplog.set_level(logging.DEBUG)
    from src.data.preprocess import normalise  # noqa: F401  (import-time logging only)
    assert not any("description" in r.getMessage().lower() for r in caplog.records)


def test_public_coordinates_are_coarse():
    import pandas as pd
    d = pd.read_csv(REPORTS / "duplicate_coordinate_analysis.csv")
    assert (d.latitude.astype(str).str.split(".").str[1].str.len() <= 3).all()
