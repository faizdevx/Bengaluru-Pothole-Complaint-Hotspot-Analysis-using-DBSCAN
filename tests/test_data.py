import pandas as pd
import pytest

from src.config import REQUIRED_COLUMNS, SENSITIVE_COLUMNS
from src.data.preprocess import (SchemaError, coordinate_flags, make_request_id, parse_timestamps,
                                 pothole_mask, validate_schema)


def _row(**kw):
    base = dict(created_at="1-1-2019 06:33", ward_id=1, title="t", description="d", sub_category_id=66,
                civic_agency_id=1.0, location="l", address="a", latitude=12.97, longitude=77.59, ward_title="w",
                category_id=15.0, category_title="Mobility - Roads, Footpaths and Infrastructure",
                sub_category_title="Fixing/Reparing Potholes", civic_agency_title="BBMP",
                complaint_status_title="Open", comment_count=0)
    base.update(kw)
    return base


def test_schema_validation_ok_and_missing():
    df = pd.DataFrame([_row()])
    validate_schema(df)
    with pytest.raises(SchemaError):
        validate_schema(df.drop(columns=["latitude"]))


def test_pothole_filter_uses_taxonomy_not_keywords():
    df = pd.DataFrame([
        _row(),
        _row(sub_category_id=594, category_title="PWD", sub_category_title="Repair of Potholes on Roads"),
        _row(sub_category_id=67, sub_category_title="Tarring Or Asphalting Of Existing Road", title="pothole everywhere"),
    ])
    assert pothole_mask(df).tolist() == [True, True, False]


def test_pothole_filter_detects_taxonomy_drift():
    df = pd.DataFrame([_row(sub_category_title="Something else")])
    with pytest.raises(SchemaError):
        pothole_mask(df)


def test_timestamp_parsing_both_formats_month_first():
    t = parse_timestamps(pd.Series(["1-2-2019 06:33", "7/31/2022 14:03", "garbage", None]))
    assert t.iloc[0].month == 1 and t.iloc[0].day == 2          # '-' rows are month-first too
    assert t.iloc[1].month == 7 and t.iloc[1].day == 31
    assert t.isna().tolist() == [False, False, True, True]
    assert str(t.iloc[0].tz) == "Asia/Kolkata"


def test_coordinate_flags():
    df = pd.DataFrame({"latitude": [12.97, 0.0, 77.6, None, 95.0, 12.9], "longitude": [77.59, 0.0, 12.9, 77.5, 77.5, 77.5]})
    f = coordinate_flags(df)
    assert f.zero_zero.tolist() == [False, True, False, False, False, False]
    assert f.swapped.tolist() == [False, False, True, False, False, False]
    assert f.null_coord.tolist() == [False, False, False, True, False, False]
    assert f.out_of_global_range.tolist()[4] is True
    assert f.coarse_rounded.iloc[5]          # 12.9 / 77.5 are low-precision


def test_duplicates_share_surrogate_id():
    ids = make_request_id(pd.Series(["a", "a", "b"]))
    assert ids.iloc[0] == ids.iloc[1] != ids.iloc[2]


def test_sensitive_columns_not_in_normalised_output():
    import numpy as np
    from src.data.preprocess import normalise

    class FakeIndex:
        wards = {1: {"name": "W"}}
        def assign(self, lat, lon):
            return np.ones(len(lat), dtype=int)
    out = normalise(pd.DataFrame([_row(), _row(latitude=12.98)]), FakeIndex())
    assert not set(SENSITIVE_COLUMNS) & set(out.columns)
    assert out.is_pothole.all() and out.usable.all()
