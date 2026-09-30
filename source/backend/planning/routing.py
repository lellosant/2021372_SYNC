import math
import urllib.parse
import urllib.request
import json
import threading
from typing import List

from .config import (
    AVERAGE_FALLBACK_SPEED_KMH,
    OSRM_BASE_URL,
    OSRM_TIMEOUT_SECONDS
)
from .models import Location, Client

_matrix_cache = {}
_matrix_cache_lock = threading.Lock()

def _haversine_minutes(lat1, lon1, lat2, lon2):
    """Estimate driving minutes using Haversine distance, 1.25 winding factor, and average fallback speed."""
    radius_km = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    h = math.sin(d_lat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d_lon / 2) ** 2
    straight_km = 2 * radius_km * math.asin(min(1.0, math.sqrt(h)))
    road_km = straight_km * 1.25
    return (road_km / AVERAGE_FALLBACK_SPEED_KMH) * 60

def _fallback_matrix(coords):
    """Compute NxN travel matrix using the Haversine distance fallback."""
    return [
        [
            0.0 if i == j else _haversine_minutes(lat1, lon1, lat2, lon2)
            for j, (lat2, lon2) in enumerate(coords)
        ]
        for i, (lat1, lon1) in enumerate(coords)
    ]

def build_travel_matrix_with_status(depot: Location, clients: List[Client]):
    """Fetch driving duration matrix from OSRM Table API with thread-safe LRU caching and Haversine fallback."""
    coords = [(depot.lat, depot.lon)] + [(c.latitude, c.longitude) for c in clients]
    if not coords:
        return [], False
        
    rounded = tuple((round(lat, 5), round(lon, 5)) for lat, lon in coords)

    # Check in-memory matrix cache
    with _matrix_cache_lock:
        if rounded in _matrix_cache:
            return _matrix_cache[rounded], False

    # OSRM public table API limits requests to ~100 coordinates
    if len(coords) > 100:
        return _fallback_matrix(coords), "too_large"

    coordinate_string = ";".join(f"{lon},{lat}" for lat, lon in rounded)
    query = urllib.parse.urlencode({"annotations": "duration"})
    url = f"{OSRM_BASE_URL}/table/v1/driving/{coordinate_string}?{query}"

    is_fallback = False
    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "visits-optimizer/1.0"}
        )
        with urllib.request.urlopen(request, timeout=OSRM_TIMEOUT_SECONDS) as response:
            payload = json.load(response)

        durations = payload.get("durations")
        if payload.get("code") != "Ok" or not durations:
            raise ValueError(payload.get("message", "OSRM matrix unavailable"))

        # Convert seconds to minutes
        matrix = [
            [
                math.inf if seconds is None else float(seconds) / 60
                for seconds in row
            ]
            for row in durations
        ]
    except Exception:
        # Fall back to Haversine if network times out or OSRM is unreachable
        matrix = _fallback_matrix(coords)
        is_fallback = True

    with _matrix_cache_lock:
        if not is_fallback:
            if len(_matrix_cache) >= 16:
                _matrix_cache.pop(next(iter(_matrix_cache)))
            _matrix_cache[rounded] = matrix

    return matrix, is_fallback

def build_travel_matrix(depot: Location, clients: List[Client]) -> List[List[float]]:
    """Build pairwise driving travel matrix between depot (index 0) and all candidate clients."""
    matrix, _ = build_travel_matrix_with_status(depot, clients)
    return matrix

