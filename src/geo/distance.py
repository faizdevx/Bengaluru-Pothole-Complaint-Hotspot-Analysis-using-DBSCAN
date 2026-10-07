"""Geographic distance helpers. All distances are metres on a spherical Earth
(haversine) or planar metres in the projected CRS."""
from __future__ import annotations

import numpy as np

from src.config import EARTH_RADIUS_M, PROJECTED_CRS


def haversine_m(lat1, lon1, lat2, lon2) -> np.ndarray:
    """Great-circle distance in metres; inputs in degrees, broadcastable."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = p2 - p1
    dlmb = np.radians(lon2) - np.radians(lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


def meters_to_radians(meters: float) -> float:
    return meters / EARTH_RADIUS_M


_TRANSFORMERS: dict = {}


def to_xy(lat, lon):
    """WGS84 degrees -> projected metres (UTM 43N)."""
    from pyproj import Transformer
    if "fwd" not in _TRANSFORMERS:
        _TRANSFORMERS["fwd"] = Transformer.from_crs("EPSG:4326", PROJECTED_CRS, always_xy=True)
    x, y = _TRANSFORMERS["fwd"].transform(np.asarray(lon), np.asarray(lat))
    return np.asarray(x), np.asarray(y)


def to_latlon(x, y):
    from pyproj import Transformer
    if "inv" not in _TRANSFORMERS:
        _TRANSFORMERS["inv"] = Transformer.from_crs(PROJECTED_CRS, "EPSG:4326", always_xy=True)
    lon, lat = _TRANSFORMERS["inv"].transform(np.asarray(x), np.asarray(y))
    return np.asarray(lat), np.asarray(lon)


def centroid(lat, lon) -> tuple[float, float]:
    """Centroid of points computed in projected metres (not by averaging degrees
    blindly across a large extent), returned as (lat, lon)."""
    x, y = to_xy(lat, lon)
    la, lo = to_latlon(x.mean(), y.mean())
    return float(la), float(lo)


def radius_m(lat, lon, c_lat: float, c_lon: float) -> float:
    """Approximate cluster radius: max haversine distance from centroid to member."""
    return float(np.max(haversine_m(np.asarray(lat), np.asarray(lon), c_lat, c_lon)))
