from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
from data_processor import process_data
from optimizer import optimize_visits

app = FastAPI(title="Visits Optimizer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/extract-companies")
async def extract_companies(file: UploadFile = File(...)):
    contents = await file.read()
    _, available_companies = process_data(contents)
    return {"companies": available_companies}

@app.post("/api/analyze")
async def analyze_data(
    file: UploadFile = File(...),
    days: int = Form(30),
    hours_per_visit: float = Form(3.5),
    work_hours: float = Form(8.0),
    companies: str = Form(None)
):
    contents = await file.read()
    df, available_companies = process_data(contents)
    
    if companies and companies.strip():
        selected_companies = [c.strip() for c in companies.split(",") if c.strip() in available_companies]
        if not selected_companies:
            selected_companies = available_companies
    else:
        selected_companies = available_companies
    
    df_filtered = df[df[selected_companies].sum(axis=1) > 0].copy() if selected_companies else pd.DataFrame()
    
    map_points = []
    if not df_filtered.empty:
        for _, row in df_filtered.iterrows():
            main_comp = selected_companies[0] if selected_companies else ""
            max_val = -1
            for comp in selected_companies:
                val = float(row.get(comp, 0))
                if val > max_val:
                    max_val = val
                    main_comp = comp
            
            if max_val > 0:
                map_points.append({
                    "cliente": row.get('Cliente', row.get('Ragione Sociale', 'Sconosciuto')),
                    "lat": row['Lat'],
                    "lon": row['Lon'],
                    "totale": float(row.get('Totale', 0)),
                    "azienda": main_comp
                })
                
    schedule_df = optimize_visits(df, days, hours_per_visit, work_hours, selected_companies)
    schedule = schedule_df.to_dict(orient="records") if not schedule_df.empty else []
    total_revenue = schedule_df['Fatturato Stimato'].sum() if not schedule_df.empty else 0
    
    return {
        "available_companies": available_companies,
        "selected_companies": selected_companies,
        "map_points": map_points,
        "schedule": schedule,
        "metrics": {
            "total_visits": len(schedule),
            "expected_revenue": float(total_revenue),
            "companies_count": len(selected_companies)
        }
    }

