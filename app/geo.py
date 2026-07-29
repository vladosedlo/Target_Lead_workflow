"""Гео-геометрия: расстояния, проверка точки в полигоне и в секторе ЗРК."""
from __future__ import annotations

import math
from typing import Iterable, Tuple

R_EARTH = 6371000.0  # м


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1 = math.radians(lat1); p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R_EARTH * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1 = math.radians(lat1); p2 = math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1)*math.sin(p2) - math.sin(p1)*math.cos(p2)*math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def point_in_polygon(lat: float, lon: float, poly: Iterable[Tuple[float, float]]) -> bool:
    pts = list(poly)
    if len(pts) < 3:
        return False
    inside = False
    j = len(pts) - 1
    for i in range(len(pts)):
        yi, xi = pts[i]
        yj, xj = pts[j]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def in_sector(plane_lat: float, plane_lon: float,
              site_lat: float, site_lon: float,
              az_start: float, az_end: float,
              max_range_m: float) -> bool:
    """Точка в секторе: азимут отсчитывается от севера по часовой стрелке.
    az_start → az_end — по часовой. Если az_end < az_start, сектор пересекает 0°.
    """
    dist = haversine_m(site_lat, site_lon, plane_lat, plane_lon)
    if dist > max_range_m:
        return False
    az = bearing_deg(site_lat, site_lon, plane_lat, plane_lon)
    a0 = az_start % 360; a1 = az_end % 360
    if a0 <= a1:
        return a0 <= az <= a1
    else:
        return az >= a0 or az <= a1