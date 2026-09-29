import os

WORK_END_GRACE_MINUTES = int(os.getenv("WORK_END_GRACE_MINUTES", "15"))
OSRM_BASE_URL = os.getenv("OSRM_BASE_URL", "https://router.project-osrm.org").rstrip("/")
OSRM_TIMEOUT_SECONDS = float(os.getenv("OSRM_TIMEOUT_SECONDS", "8"))
MAX_ROUTING_CANDIDATES = int(os.getenv("MAX_ROUTING_CANDIDATES", "100"))
AVERAGE_FALLBACK_SPEED_KMH = float(os.getenv("AVERAGE_FALLBACK_SPEED_KMH", "35"))
PLANNING_RANDOM_SEED = int(os.getenv("PLANNING_RANDOM_SEED", "42"))
PLANNING_TIME_LIMIT_SECONDS = float(os.getenv("PLANNING_TIME_LIMIT_SECONDS", "5"))
PLANNING_MAX_ITERATIONS = int(os.getenv("PLANNING_MAX_ITERATIONS", "500"))
PLANNING_POOL_MULTIPLIER = int(os.getenv("PLANNING_POOL_MULTIPLIER", "5"))
MIN_TRASFERTA_TRAVEL_MINUTES = int(os.getenv("MIN_TRASFERTA_TRAVEL_MINUTES", "120"))

def _parse_time_val(val, default_minutes):
    if val is None:
        return default_minutes
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str):
        val = val.strip().strip('"\'')
        if not val:
            return default_minutes
        try:
            parts = val.split(':')
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            return int(float(parts[0]))
        except (ValueError, TypeError):
            return default_minutes
    return default_minutes
