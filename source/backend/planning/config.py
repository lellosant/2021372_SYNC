from __future__ import annotations
import os

DEFAULT_CONFIG = {
    # Workday and lunch break hours
    "WORK_START": "09:00",
    "WORK_END": "18:00",
    "LUNCH_EARLIEST": "12:00",
    "LUNCH_LATEST_START": "14:00",
    "LUNCH_DURATION_MINUTES": 60,
    "WORK_END_GRACE_MINUTES": 15,

    # Daily capacity and visit parameters
    "DEFAULT_VISIT_HOURS": 3.5,
    "MAX_WORK_HOURS_PER_DAY": 8.0,

    # Metaheuristic optimizer parameters (ALNS)
    "PLANNING_RANDOM_SEED": 42,
    "PLANNING_TIME_LIMIT_SECONDS": 30.0,
    "PLANNING_MAX_ITERATIONS": 500,
    "PLANNING_POOL_MULTIPLIER": 5,

    # Routing and OSRM parameters
    "OSRM_BASE_URL": "https://router.project-osrm.org",
    "OSRM_TIMEOUT_SECONDS": 8.0,
    "MAX_ROUTING_CANDIDATES": 100,
    "AVERAGE_FALLBACK_SPEED_KMH": 35.0,

    # Seasonal weighting (late summer rush)
    "SUMMER_END_START_MONTH": 8,
    "SUMMER_END_START_DAY": 20,
    "SUMMER_END_END_MONTH": 9,
    "SUMMER_END_END_DAY": 15,
}


def _resolve_planner_config_path() -> str | None:
    """Search known container and relative host paths for planner.config."""
    env_path = os.getenv("PLANNER_CONFIG_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path
    
    candidates = [
        "/planner.config",
        "/app/planner.config",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "planner.config")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "planner.config")),
        os.path.abspath("planner.config"),
        os.path.abspath("source/planner.config"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None

def _load_planner_config() -> dict:
    """Load configuration from planner.config file with environment variable overrides."""
    cfg = dict(DEFAULT_CONFIG)
    config_path = _resolve_planner_config_path()
    if config_path and os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.split("#")[0].strip()
                    if not line or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"\'')
                    if key in DEFAULT_CONFIG:
                        default_val = DEFAULT_CONFIG[key]
                        if isinstance(default_val, int):
                            try:
                                cfg[key] = int(val)
                            except ValueError:
                                pass
                        elif isinstance(default_val, float):
                            try:
                                cfg[key] = float(val)
                            except ValueError:
                                pass
                        else:
                            cfg[key] = str(val).rstrip("/")
        except Exception:
            pass
            
    # Apply environment variable overrides if present
    for key, default_val in cfg.items():
        env_val = os.getenv(key)
        if env_val is not None:
            if isinstance(default_val, int):
                try:
                    cfg[key] = int(env_val)
                except ValueError:
                    pass
            elif isinstance(default_val, float):
                try:
                    cfg[key] = float(env_val)
                except ValueError:
                    pass
            else:
                cfg[key] = str(env_val).rstrip("/")

    return cfg

_CONFIG = _load_planner_config()

WORK_START = _CONFIG["WORK_START"]
WORK_END = _CONFIG["WORK_END"]
LUNCH_EARLIEST = _CONFIG["LUNCH_EARLIEST"]
LUNCH_LATEST_START = _CONFIG["LUNCH_LATEST_START"]
LUNCH_DURATION_MINUTES = _CONFIG["LUNCH_DURATION_MINUTES"]
WORK_END_GRACE_MINUTES = _CONFIG["WORK_END_GRACE_MINUTES"]
DEFAULT_VISIT_HOURS = _CONFIG["DEFAULT_VISIT_HOURS"]
MAX_WORK_HOURS_PER_DAY = _CONFIG["MAX_WORK_HOURS_PER_DAY"]

OSRM_BASE_URL = _CONFIG["OSRM_BASE_URL"]
OSRM_TIMEOUT_SECONDS = _CONFIG["OSRM_TIMEOUT_SECONDS"]
MAX_ROUTING_CANDIDATES = _CONFIG["MAX_ROUTING_CANDIDATES"]
AVERAGE_FALLBACK_SPEED_KMH = _CONFIG["AVERAGE_FALLBACK_SPEED_KMH"]
PLANNING_RANDOM_SEED = _CONFIG["PLANNING_RANDOM_SEED"]
PLANNING_TIME_LIMIT_SECONDS = _CONFIG["PLANNING_TIME_LIMIT_SECONDS"]
PLANNING_MAX_ITERATIONS = _CONFIG["PLANNING_MAX_ITERATIONS"]
PLANNING_POOL_MULTIPLIER = _CONFIG["PLANNING_POOL_MULTIPLIER"]

SUMMER_END_START_MONTH = _CONFIG["SUMMER_END_START_MONTH"]
SUMMER_END_START_DAY = _CONFIG["SUMMER_END_START_DAY"]
SUMMER_END_END_MONTH = _CONFIG["SUMMER_END_END_MONTH"]
SUMMER_END_END_DAY = _CONFIG["SUMMER_END_END_DAY"]



def _parse_time_val(val, default_minutes):
    """Parse "HH:MM" string or numeric minutes into integer minutes from midnight."""
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
