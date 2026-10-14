"""Geometry helpers. A local equirectangular projection gives metre-accurate distances
at neighbourhood scale (~2 km), so shapely can work in metres."""

from __future__ import annotations

import math
from typing import Any

from shapely.geometry import LineString, Point, Polygon

_R = 6_371_000.0


def haversine_m(a: dict[str, float], b: dict[str, float]) -> float:
    """Great-circle distance in metres between two {lat, lng} points."""
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp, dl = p2 - p1, math.radians(b["lng"] - a["lng"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _R * math.asin(math.sqrt(h))


class LocalProjection:
    """Project lng/lat to local x/y metres around a reference latitude."""

    def __init__(self, ref_lat: float):
        self.kx = math.radians(1) * _R * math.cos(math.radians(ref_lat))
        self.ky = math.radians(1) * _R

    def xy(self, lng: float, lat: float) -> tuple[float, float]:
        return lng * self.kx, lat * self.ky

    def geom(self, g: dict[str, Any]):
        """Build a projected shape from `{"type": ..., "points": [{lat, lng}, ...]}`."""
        xy = [self.xy(p["lng"], p["lat"]) for p in g["points"]]
        if g["type"] == "Polygon":
            return Polygon(xy)
        if g["type"] == "LineString":
            return LineString(xy)
        raise ValueError(f"Unsupported geometry {g['type']}")

    def point(self, loc: dict[str, float]) -> Point:
        return Point(self.xy(loc["lng"], loc["lat"]))
