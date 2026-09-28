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
    save_geocache
)
from optimizer import optimize_visits

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCENARIO_CACHE_DIR = "/app/cache/scenarios"
PLANNER_CACHE_VERSION = "v2_workdays_flexible_lunch"
os.makedirs(SCENARIO_CACHE_DIR, exist_ok=True)
_scenario_memory_cache = {}

app = FastAPI(title="GeoAnalytics API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        df, companies = process_data(contents)
        
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


@app.get("/api/geocode")
async def geocode_endpoint(address: str, city: str = ""):
    try:
        geo_cache = load_geocache()
        lat, lon = geocode_address(address, city, geo_cache)
        save_geocache(geo_cache)
        if lat is not None and lon is not None:
            cache_key = ", ".join(part for part in [address, city, "Italy"] if part).upper()
            cached_item = geo_cache.get(cache_key) or {}
            display_name = cached_item.get("display_name", "")
            return {
                "success": True,
                "address": address,
                "city": city,
                "lat": lat,
                "lon": lon,
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


@app.post("/api/analyze")
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
    start_lon: float = Form(None)
):
    contents = await file.read()
    content_hash = hashlib.sha256(contents).hexdigest()[:16]

    # Determinazione dell'azienda richiesta
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

    loc_suffix = f"_{start_address or ''}_{start_lat or ''}_{start_lon or ''}"
    cache_key = f"{PLANNER_CACHE_VERSION}_{content_hash}_{target_company}_{days}_{hours_per_visit}_{work_hours}_{start_date}{loc_suffix}"

    # 1. Verifica cache in memoria
    if cache_key in _scenario_memory_cache:
        logger.info(f"Scenario cache HIT (memoria): {cache_key}")
        data = dict(_scenario_memory_cache[cache_key])
        data["from_cache"] = True
        return data

    # 2. Verifica cache su disco
    cache_path = os.path.join(SCENARIO_CACHE_DIR, f"{cache_key}.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
                cached_data["from_cache"] = True
                _scenario_memory_cache[cache_key] = cached_data
                logger.info(f"Scenario cache HIT (disco): {cache_key}")
                return cached_data
        except Exception as e:
            logger.warning(f"Errore lettura cache disco: {e}")

    # 3. Elaborazione del dataset
    try:
        df, available_companies = process_data(contents)
    except Exception as e:
        logger.error(f"Errore nel process_data: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Errore elaborazione dati: {e}")

    if not available_companies:
        return {
            "error": "Nessun gruppo aziendale valido identificato nel file.",
            "available_companies": []
        }

    if not target_company or target_company not in available_companies:
        target_company = available_companies[0]

    # Fatturato potenziale complessivo dell'azienda selezionata nel dataset
    company_potential = float(df[target_company].sum()) if target_company in df.columns else 0.0

    # Numero totale di clienti validi per l'azienda selezionata
    if target_company in df.columns:
        valid_clients_mask = pd.to_numeric(df[target_company], errors='coerce').fillna(0) > 0
        valid_clients_df = df[valid_clients_mask]
        total_clients = len(valid_clients_df)
        geocoded_clients = len(valid_clients_df[valid_clients_df['Lat'].notna() & valid_clients_df['Lon'].notna()])
    else:
        total_clients = 0
        geocoded_clients = 0

    try:
        schedule_df = optimize_visits(
            df,
            days,
            hours_per_visit,
            work_hours,
            [target_company],
            start_date=start_date,
            start_address=start_address,
            start_lat=start_lat,
            start_lon=start_lon
        )
    except Exception as e:
        logger.error(f"Errore in optimize_visits per {target_company}: {e}")
        logger.error(traceback.format_exc())
        schedule_df = pd.DataFrame()

    recovered_revenue = float(schedule_df["Fatturato Stimato"].sum()) if not schedule_df.empty and "Fatturato Stimato" in schedule_df.columns else 0.0
    visits_count = len(schedule_df)

    scheduled_client_names = set(schedule_df["Cliente"].dropna().unique()) if not schedule_df.empty and "Cliente" in schedule_df.columns else set()

    map_points = []
    # 1. Clienti pianificati per la visita
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

    # 2. Tutti gli altri clienti di quell'azienda localizzabili ma non pianificati
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
        "kpis": {
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

    _scenario_memory_cache[cache_key] = response_payload
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(response_payload, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Errore scrittura cache disco: {e}")

    return response_payload


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

