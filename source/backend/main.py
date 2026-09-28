import hashlib
import json
import logging
import os
import traceback

import pandas as pd
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from data_processor import extract_companies_from_file, process_data
from optimizer import optimize_visits

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCENARIO_CACHE_DIR = "/app/cache/scenarios"
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
        companies = extract_companies_from_file(contents)
        return {"companies": companies}
    except Exception as e:
        logger.error(f"Errore in /api/upload: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analyze")
async def analyze_data(
    file: UploadFile = File(...),
    days: int = Form(30),
    hours_per_visit: float = Form(3.5),
    work_hours: float = Form(8.0),
    company: str = Form(None),
    companies: str = Form(None),
    start_date: str = Form(None)
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

    cache_key = f"{content_hash}_{target_company}_{days}_{hours_per_visit}_{work_hours}_{start_date}"

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
            start_date=start_date
        )
    except Exception as e:
        logger.error(f"Errore in optimize_visits per {target_company}: {e}")
        logger.error(traceback.format_exc())
        schedule_df = pd.DataFrame()

    recovered_revenue = float(schedule_df["Fatturato Stimato"].sum()) if not schedule_df.empty and "Fatturato Stimato" in schedule_df.columns else 0.0
    visits_count = len(schedule_df)

    map_points = []
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
                    "time": row.get("Orario", "")
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

