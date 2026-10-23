import math

from app.constants import TRAVEL_SPEED_KMPH

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line (great-circle) distance in km between two coordinates."""
    lat1, lon1, lat2, lon2 = (float(x) for x in (lat1, lon1, lat2, lon2))
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def travel_minutes(distance_km: float, speed_kmph: float = TRAVEL_SPEED_KMPH) -> float:
    return (float(distance_km) / speed_kmph) * 60.0
