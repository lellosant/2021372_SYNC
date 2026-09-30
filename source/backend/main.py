import asyncio
import hashlib
import json
import logging
import os
import traceback

import pandas as pd
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from data_processor import (
    extract_companies_from_file,
    process_data,
    geocode_address,
    load_geocache,
    save_geocache,
    get_progress_status,
    set_progress_status
)
from optimizer import optimize_visits
from planning.config import _load_planner_config

logging.basicConfig(level=logging.INFO)
import atexit
import contextlib

logger = logging.getLogger(__name__)

SCENARIO_CACHE_DIR = "/app/cache/scenarios" if os.path.exists("/app") else os.path.join(os.path.dirname(__file__), "cache", "scenarios")
PLANNER_CACHE_VERSION = "v5_day_weights_swap_alns"
os.makedirs(SCENARIO_CACHE_DIR, exist_ok=True)
_scenario_memory_cache = {}
_processed_dataset_cache = {}


def clean_scenarios_cache():
    """Clear scenario caches in memory and on disk."""
    global _scenario_memory_cache
    _scenario_memory_cache.clear()
    try:
        if os.path.exists(SCENARIO_CACHE_DIR):
            for fname in os.listdir(SCENARIO_CACHE_DIR):
                fpath = os.path.join(SCENARIO_CACHE_DIR, fname)
                if os.path.isfile(fpath) and fname.endswith(".json"):
                    try:
                        os.remove(fpath)
                    except OSError:
                        pass
            logger.info("Cache scenari svuotata con successo.")
    except Exception as e:
        logger.warning(f"Errore durante la pulizia della cache scenari: {e}")


# Clean scenario cache on process termination
atexit.register(clean_scenarios_cache)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Clean cache on application startup and shutdown
    clean_scenarios_cache()
    yield
    clean_scenarios_cache()


app = FastAPI(
    title="GeoAnalytics API",
    description="API for geocoding, route optimization, sales visit scheduling, and multi-day travel management.",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/upload", tags=["Upload"], summary="Upload and process ERP dataset", description="Upload an Excel or CSV file, detect companies, and geocode client locations.")
async def upload_file(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        content_hash = hashlib.sha256(contents).hexdigest()[:16]
        df, companies = await asyncio.to_thread(process_data, contents)
        _processed_dataset_cache[content_hash] = (df.copy(), list(companies))
        
        company_clients = {}
        for comp in companies:
            if comp in df.columns:
                mask = (pd.to_numeric(df[comp], errors='coerce').fillna(0) > 0) & df['Lat'].notna() & df['Lon'].notna()
                comp_df = df[mask]
                clients_list = []
                for _, r in comp_df.iterrows():
                    clients_list.append({
                        "name": str(r.get("Cliente", "Cliente")),
                        "address": str(r.get("Indirizzo", "")),
                        "city": str(r.get("Città", "")),
                        "lat": float(r["Lat"]),
                        "lon": float(r["Lon"]),
                        "revenue": float(r.get(comp, 0))
                    })
                company_clients[comp] = clients_list

        return {
            "companies": companies,
            "company_clients": company_clients
        }
    except Exception as e:
        logger.error(f"Errore in /api/upload: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        set_progress_status(False, "idle")


@app.get("/api/progress", tags=["Progress"], summary="Geocoding and optimization progress")
def api_progress_endpoint():
    """Return real-time geocoding and optimization progress status."""
    return get_progress_status()


@app.get("/api/geocode", tags=["Geocoding"], summary="Geocode address", description="Geocode an address string using OpenStreetMap / Photon with local caching.")
async def geocode_endpoint(address: str, city: str = ""):
    try:
        geo_cache = load_geocache()
        lat, lon = geocode_address(address, city, geo_cache)
        save_geocache(geo_cache)
        if lat is not None and lon is not None:
            from data_processor import parse_address_and_civic
            street, civic, detected_city = parse_address_and_civic(address, city)
            effective_city = detected_city or city or ""
            cache_key = ", ".join(part for part in [address, effective_city, "Italy"] if part).upper()
            cached_item = geo_cache.get(cache_key) or {}
            display_name = cached_item.get("display_name", "")
            return {
                "success": True,
                "address": address,
                "city": effective_city,
                "lat": lat,
                "lon": lon,
                "house_number": cached_item.get("house_number") or civic,
                "house_number_exact": cached_item.get("house_number_exact", False),
                "display_name": display_name
            }

        return {
            "success": False,
            "message": "Indirizzo non trovato su OpenStreetMap. Inserisci manualmente le coordinate GPS."
        }
    except Exception as e:
        logger.error(f"Errore geocodifica indirizzo '{address}': {e}")
        return {
            "success": False,
            "message": f"Errore durante la geocodifica: {str(e)}"
        }


@app.get("/api/config", tags=["Configuration"], summary="Default planner configuration", description="Return default working hours, lunch break, visit duration, and grace limits from planner.config.")
async def get_config():
    """Return default work schedule and planner settings from planner.config."""
    cfg = _load_planner_config()
    return {
        "work_start": cfg["WORK_START"],
        "work_end": cfg["WORK_END"],
        "lunch_earliest": cfg["LUNCH_EARLIEST"],
        "lunch_latest_start": cfg["LUNCH_LATEST_START"],
        "lunch_duration_minutes": cfg["LUNCH_DURATION_MINUTES"],
        "default_visit_hours": cfg["DEFAULT_VISIT_HOURS"],
        "max_work_hours_per_day": cfg["MAX_WORK_HOURS_PER_DAY"],
        "work_end_grace_minutes": cfg["WORK_END_GRACE_MINUTES"]
    }


@app.get("/api/travel-time", tags=["Routing"], summary="Compute travel time between two addresses", description="Compute travel duration between two addresses using OSRM + Haversine fallback and check multi-day trip feasibility.")
async def travel_time_endpoint(
    origin: str,
    destination: str,
    visit_hours: float = 3.5,
    work_hours: float = 8.0
):
    try:
        from test.test_travel_time import calculate_travel_time
        service_minutes = int(round(visit_hours * 60))
        agent_available_minutes = int(round(work_hours * 60))
        res = calculate_travel_time(
            origin,
            destination,
            service_minutes=service_minutes,
            agent_available_minutes=agent_available_minutes
        )
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/analyze", tags=["Planning"], summary="Optimize visit schedule", description="Plan and optimize the sales visit schedule across available working days with multi-day trip support.")
async def analyze_data(
    file: UploadFile = File(...),
    days: int = Form(30),
    hours_per_visit: float = Form(3.5),
    work_hours: float = Form(8.0),
    company: str = Form(None),
    companies: str = Form(None),
    start_date: str = Form(None),
    start_address: str = Form(None),
    start_lat: float = Form(None),
    start_lon: float = Form(None),
    work_start: str = Form(None),
    work_end: str = Form(None),
    lunch_earliest: str = Form(None),
    lunch_latest_start: str = Form(None),
    lunch_duration_minutes: int = Form(None),
    enable_trasferte: bool = Form(False),
    max_giorni_trasferta: int = Form(3)
):
    contents = await file.read()
    content_hash = hashlib.sha256(contents).hexdigest()[:16]

    # Resolve target company name
    target_company = company
    if not target_company and companies:
        try:
            parsed = json.loads(companies)
            if isinstance(parsed, list) and len(parsed) > 0:
                target_company = parsed[0]
            elif isinstance(parsed, str):
                target_company = parsed
        except Exception:
            target_company = companies.split(',')[0].strip()

    # Load working hours and lunch break defaults from planner.config
    cfg = _load_planner_config()
    eff_work_start = work_start.strip() if work_start and work_start.strip() else cfg["WORK_START"]
    eff_work_end = work_end.strip() if work_end and work_end.strip() else cfg["WORK_END"]
    eff_lunch_earliest = lunch_earliest.strip() if lunch_earliest and lunch_earliest.strip() else cfg["LUNCH_EARLIEST"]
    eff_lunch_latest_start = lunch_latest_start.strip() if lunch_latest_start and lunch_latest_start.strip() else cfg["LUNCH_LATEST_START"]
    try:
        eff_lunch_duration = int(lunch_duration_minutes) if lunch_duration_minutes is not None and str(lunch_duration_minutes).strip() != "" else cfg["LUNCH_DURATION_MINUTES"]
    except (ValueError, TypeError):
        eff_lunch_duration = cfg["LUNCH_DURATION_MINUTES"]


    loc_suffix = f"_{start_address or ''}_{start_lat or ''}_{start_lon or ''}"
    time_suffix = f"_{eff_work_start}_{eff_work_end}_{eff_lunch_earliest}_{eff_lunch_latest_start}_{eff_lunch_duration}"
    cache_key = f"{PLANNER_CACHE_VERSION}_{content_hash}_{target_company}_{days}_{hours_per_visit}_{work_hours}_{start_date}{loc_suffix}{time_suffix}_{enable_trasferte}_{max_giorni_trasferta}"

    # 1. Check in-memory scenario cache
    if cache_key in _scenario_memory_cache:
        logger.info(f"Scenario cache HIT (memoria): {cache_key}")
        data = dict(_scenario_memory_cache[cache_key])
        if "days" not in data or data["days"] is None:
            data["days"] = days
        if "start_date" not in data:
            data["start_date"] = start_date
        data["from_cache"] = True
        return data

    # 2. Check on-disk scenario cache
    cache_path = os.path.join(SCENARIO_CACHE_DIR, f"{cache_key}.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
                if "days" not in cached_data or cached_data["days"] is None:
                    cached_data["days"] = days
                if "start_date" not in cached_data:
                    cached_data["start_date"] = start_date
                cached_data["from_cache"] = True
                _scenario_memory_cache[cache_key] = cached_data
                logger.info(f"Scenario cache HIT (disco): {cache_key}")
                return cached_data
        except Exception as e:
            logger.warning(f"Errore lettura cache disco: {e}")

    # 3. Process dataset (reuse pre-geocoded dataframe from memory when available)
    try:
        if content_hash in _processed_dataset_cache:
            logger.info(f"Dataset pre-geocodificato riusato dalla memoria per hash {content_hash}")
            cached_df, cached_companies = _processed_dataset_cache[content_hash]
            df = cached_df.copy()
            available_companies = list(cached_companies)
            set_progress_status(True, "optimizing", len(df), len(df), "Ottimizzazione visite in corso...", len(df), 0)
        else:
            df, available_companies = await asyncio.to_thread(process_data, contents)
            _processed_dataset_cache[content_hash] = (df.copy(), list(available_companies))
    except Exception as e:
        set_progress_status(False, "idle")
        logger.error(f"Errore nel process_data: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Errore elaborazione dati: {e}")

    if not available_companies:
        set_progress_status(False, "idle")
        return {
            "error": "Nessun gruppo aziendale valido identificato nel file.",
            "available_companies": []
        }

    if not target_company or target_company not in available_companies:
        target_company = available_companies[0]

    # Total potential revenue for the selected company
    company_potential = float(df[target_company].sum()) if target_company in df.columns else 0.0

    # Count valid and geocoded clients for the selected company
    if target_company in df.columns:
        valid_clients_mask = pd.to_numeric(df[target_company], errors='coerce').fillna(0) > 0
        valid_clients_df = df[valid_clients_mask]
        total_clients = len(valid_clients_df)
        geocoded_clients = len(valid_clients_df[valid_clients_df['Lat'].notna() & valid_clients_df['Lon'].notna()])
    else:
        total_clients = 0
        geocoded_clients = 0

    try:
        schedule_df = await asyncio.to_thread(
            optimize_visits,
            df,
            days,
            hours_per_visit,
            work_hours,
            [target_company],
            start_date=start_date,
            start_address=start_address,
            start_lat=start_lat,
            start_lon=start_lon,
            work_start=eff_work_start,
            work_end=eff_work_end,
            lunch_earliest=eff_lunch_earliest,
            lunch_latest_start=eff_lunch_latest_start,
            lunch_duration_minutes=eff_lunch_duration,
            enable_trasferte=enable_trasferte,
            max_giorni_trasferta=max_giorni_trasferta
        )
    except Exception as e:
        logger.error(f"Errore in optimize_visits per {target_company}: {e}")
        logger.error(traceback.format_exc())
        schedule_df = pd.DataFrame()

    recovered_revenue = float(schedule_df["Fatturato Stimato"].sum()) if not schedule_df.empty and "Fatturato Stimato" in schedule_df.columns else 0.0
    visits_count = len(schedule_df)

    scheduled_client_names = set(schedule_df["Cliente"].dropna().unique()) if not schedule_df.empty and "Cliente" in schedule_df.columns else set()

    map_points = []
    # 1. Planned visit stops on the map
    if not schedule_df.empty:
        for _, row in schedule_df.iterrows():
            lat = row.get("Lat")
            lon = row.get("Lon")
            if pd.notna(lat) and pd.notna(lon):
                map_points.append({
                    "lat": float(lat),
                    "lon": float(lon),
                    "name": row.get("Cliente", "Sconosciuto"),
                    "revenue": float(row.get("Fatturato Stimato", 0)),
                    "main_company": target_company,
                    "address": row.get("Indirizzo", ""),
                    "city": row.get("Città", ""),
                    "day": row.get("Giorno", ""),
                    "date": row.get("Data Visita", ""),
                    "time": row.get("Orario", ""),
                    "planned": True
                })

    # 2. Remaining localized clients not scheduled
    if target_company in df.columns:
        for _, row in valid_clients_df.iterrows():
            client_name = row.get("Cliente", "")
            if client_name not in scheduled_client_names:
                lat = row.get("Lat")
                lon = row.get("Lon")
                if pd.notna(lat) and pd.notna(lon):
                    map_points.append({
                        "lat": float(lat),
                        "lon": float(lon),
                        "name": str(client_name),
                        "revenue": float(row.get(target_company, 0)),
                        "main_company": target_company,
                        "address": row.get("Indirizzo", ""),
                        "city": row.get("Città", ""),
                        "day": "",
                        "date": "",
                        "time": "",
                        "planned": False
                    })

    schedule_records = schedule_df.to_dict(orient="records") if not schedule_df.empty else []

    response_payload = {
        "from_cache": False,
        "target_company": target_company,
        "available_companies": available_companies,
        "days": days,
        "start_date": start_date,
        "kpis": {
            "is_fallback": getattr(schedule_df, 'attrs', {}).get('is_fallback', False),
            "total_days_spanned": getattr(schedule_df, 'attrs', {}).get('total_days_spanned', 0),
            "company_potential": company_potential,
            "recovered_revenue": recovered_revenue,
            "visits": visits_count,
            "total_clients": total_clients,
            "geocoded_clients": geocoded_clients,
            "recovery_rate_pct": round((recovered_revenue / company_potential * 100), 1) if company_potential > 0 else 0.0
        },
        "schedule": schedule_records,
        "map_points": map_points,
        "agent_start_location": {
            "address": start_address,
            "lat": start_lat,
            "lon": start_lon
        },
        "time_params": {
            "work_start": eff_work_start,
            "work_end": eff_work_end,
            "lunch_earliest": eff_lunch_earliest,
            "lunch_latest_start": eff_lunch_latest_start,
            "lunch_duration_minutes": eff_lunch_duration
        },
        "companies_data": {
            target_company: {
                "schedule": schedule_records,
                "map_points": map_points,
                "kpis": {
                    "potential_revenue": company_potential,
                    "recovered_revenue": recovered_revenue,
                    "visits": visits_count,
                    "total_clients": total_clients,
                    "geocoded_clients": geocoded_clients
                }
            }
        }
    }

    # Save solution to cache if optimization succeeded or fallback was intentional
    is_fallback = response_payload["kpis"].get("is_fallback", False)
    if is_fallback in (False, "too_large"):
        _scenario_memory_cache[cache_key] = response_payload
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(response_payload, f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Errore scrittura cache disco: {e}")
    set_progress_status(False, "idle")

    return response_payload


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
