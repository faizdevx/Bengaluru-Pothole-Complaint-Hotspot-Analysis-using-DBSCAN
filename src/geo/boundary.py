"""BBMP ward polygons (2015, 198 wards): parsing, point-in-ward assignment and
the Bengaluru boundary (union of wards)."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.strtree import STRtree

from src.config import DATA_RAW, SOURCES

_NS = "{http://www.opengis.net/kml/2.2}"


def _ring(el) -> list[tuple[float, float]]:
    return [tuple(map(float, c.split(",")[:2])) for c in el.find(f"{_NS}coordinates").text.split()]


def parse_ward_kml(path: Path | None = None) -> dict[int, dict]:
    """Return {ward_number: {"name", "zone", "geometry"}} from the BBMP KML."""
    path = path or DATA_RAW / SOURCES["ward_map_2015"]["file"]
    wards: dict[int, dict] = {}
    for pm in ET.parse(path).getroot().iter(f"{_NS}Placemark"):
        num = int(re.search(r"\d+", pm.find(f"{_NS}name").text).group())
        ext = {d.get("name").strip(): d.find(f"{_NS}value").text for d in pm.iter(f"{_NS}Data")}
        polys = []
        for poly in pm.iter(f"{_NS}Polygon"):
            outer = _ring(poly.find(f"{_NS}outerBoundaryIs/{_NS}LinearRing"))
            inner = [_ring(e) for e in poly.findall(f"{_NS}innerBoundaryIs/{_NS}LinearRing")]
            polys.append(Polygon(outer, inner))
        geom = MultiPolygon(polys) if len(polys) > 1 else polys[0]
        if not geom.is_valid:
            geom = geom.buffer(0)
        wards[num] = {"name": ext.get("Ward Name"), "zone": ext.get("Zone"), "geometry": geom}
    return wards


class WardIndex:
    """Spatial index over ward polygons for point-in-polygon assignment."""

    def __init__(self, wards: dict[int, dict]):
        self.wards = wards
        self.numbers = list(wards)
        self.geoms = [wards[n]["geometry"] for n in self.numbers]
        self.tree = STRtree(self.geoms)
        self.union = shapely.union_all(self.geoms)

    def assign(self, lat, lon) -> np.ndarray:
        """Ward number containing each point, or -1 when outside every ward."""
        lat, lon = np.asarray(lat, float), np.asarray(lon, float)
        out = np.full(len(lat), -1, dtype=int)
        ok = np.isfinite(lat) & np.isfinite(lon)
        pts = shapely.points(lon[ok], lat[ok])
        pi, gi = self.tree.query(pts, predicate="within")
        idx = np.flatnonzero(ok)
        for p, g in zip(pi, gi):
            out[idx[p]] = self.numbers[g]
        return out

    def contains(self, lat, lon) -> np.ndarray:
        return self.assign(lat, lon) >= 0

    def ward_areas_km2(self) -> dict[int, float]:
        from src.geo.distance import to_xy
        areas = {}
        for n, g in zip(self.numbers, self.geoms):
            gp = shapely.transform(g, lambda c: np.column_stack(to_xy(c[:, 1], c[:, 0])))
            areas[n] = gp.area / 1e6
        return areas
