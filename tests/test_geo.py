import numpy as np
from shapely.geometry import Polygon

from src.geo.boundary import WardIndex
from src.geo.distance import centroid, haversine_m, radius_m, to_latlon, to_xy


def test_haversine_known_distance():
    # 0.01 deg of latitude is ~1111.95 km/100
    d = haversine_m(12.0, 77.0, 12.01, 77.0)
    assert abs(float(d) - 1111.95) < 2
    # longitude shrinks with cos(latitude)
    d2 = haversine_m(12.97, 77.59, 12.97, 77.60)
    assert abs(float(d2) - 1111.95 * np.cos(np.radians(12.97))) < 3


def test_projection_roundtrip_and_metres():
    x, y = to_xy(12.97, 77.59)
    lat, lon = to_latlon(x, y)
    assert abs(float(lat) - 12.97) < 1e-6 and abs(float(lon) - 77.59) < 1e-6
    x2, y2 = to_xy(12.97, 77.59 + 0.001)
    assert abs(float(np.hypot(x2 - x, y2 - y)) - float(haversine_m(12.97, 77.59, 12.97, 77.591))) < 1.0


def test_centroid_and_radius():
    lat = np.array([12.97, 12.97, 12.971, 12.971]); lon = np.array([77.59, 77.591, 77.59, 77.591])
    c = centroid(lat, lon)
    assert abs(c[0] - 12.9705) < 1e-4 and abs(c[1] - 77.5905) < 1e-4
    r = radius_m(lat, lon, *c)
    assert 50 < r < 100


def test_spatial_assignment_to_wards():
    wards = {1: {"name": "A", "zone": "z", "geometry": Polygon([(77, 12), (77.1, 12), (77.1, 12.1), (77, 12.1)])},
             2: {"name": "B", "zone": "z", "geometry": Polygon([(77.1, 12), (77.2, 12), (77.2, 12.1), (77.1, 12.1)])}}
    idx = WardIndex(wards)
    got = idx.assign([12.05, 12.05, 12.5, np.nan], [77.05, 77.15, 77.05, 77.05])
    assert got.tolist() == [1, 2, -1, -1]
    assert idx.contains([12.05], [77.05]).tolist() == [True]
