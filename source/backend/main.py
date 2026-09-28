from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd

from data_processor import (
    process_data,
    extract_companies_from_file
)

from optimizer import optimize_visits


app = FastAPI(
    title="Visits Optimizer API"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------
# Endpoint rapido:
# legge l'Excel e individua solo le aziende disponibili.
#
# NON esegue geocodifica.
# ---------------------------------------------------------

@app.post("/api/extract-companies")
async def extract_companies(
    file: UploadFile = File(...)
):
    contents = await file.read()

    available_companies = (
        extract_companies_from_file(
            contents
        )
    )

    return {
        "companies": available_companies
    }


# ---------------------------------------------------------
# Endpoint completo di analisi
#
# Qui vengono eseguite:
# - aggregazione
# - geocodifica
# - selezione aziende
# - ottimizzazione visite
# ---------------------------------------------------------

@app.post("/api/analyze")
async def analyze_data(
    file: UploadFile = File(...),
    days: int = Form(30),
    hours_per_visit: float = Form(3.5),
    work_hours: float = Form(8.0),
    companies: str = Form(None),
    start_date: str = Form(None)
):
    print(f"DEBUG: Received start_date: {start_date}", flush=True)
    contents = await file.read()

    df, available_companies = (
        process_data(
            contents
        )
    )

    # -----------------------------------------------------
    # 1. Individuazione aziende selezionate
    # -----------------------------------------------------

    if companies and companies.strip():
        selected_companies = [
            company.strip()
            for company in companies.split(",")
            if (
                company.strip()
                in available_companies
            )
        ]

        if not selected_companies:
            selected_companies = (
                available_companies
            )

    else:
        selected_companies = (
            available_companies
        )

    # -----------------------------------------------------
    # 2. Calcolo fatturato rilevante per lo scenario
    # -----------------------------------------------------

    if selected_companies:
        df["SelectedRevenue"] = (
            df[
                selected_companies
            ]
            .sum(
                axis=1
            )
        )

        df_filtered = df[
            df["SelectedRevenue"] > 0
        ].copy()

    else:
        df[
            "SelectedRevenue"
        ] = 0.0

        df_filtered = (
            pd.DataFrame()
        )

    # -----------------------------------------------------
    # 3. Preparazione punti mappa
    # -----------------------------------------------------

    map_points = []

    if not df_filtered.empty:
        for _, row in df_filtered.iterrows():

            # Salta eventuali indirizzi non geocodificati
            if (
                pd.isna(
                    row.get("Lat")
                )
                or pd.isna(
                    row.get("Lon")
                )
            ):
                continue

            # Azienda prevalente sul punto visita
            main_comp = (
                selected_companies[0]
            )

            max_val = -1

            for comp in selected_companies:
                value = float(
                    row.get(
                        comp,
                        0
                    )
                )

                if value > max_val:
                    max_val = value
                    main_comp = comp

            map_points.append({
                "cliente": row.get(
                    "Cliente",
                    row.get(
                        "Ragione Sociale",
                        "Sconosciuto"
                    )
                ),

                "lat": float(
                    row["Lat"]
                ),

                "lon": float(
                    row["Lon"]
                ),

                "totale": float(
                    row[
                        "SelectedRevenue"
                    ]
                ),

                "azienda": main_comp
            })

    # -----------------------------------------------------
    # 4. Ottimizzazione visite
    # -----------------------------------------------------

    schedule_df = optimize_visits(
        df,
        days,
        hours_per_visit,
        work_hours,
        selected_companies,
        start_date=start_date
    )

    if not schedule_df.empty:
        schedule = (
            schedule_df
            .to_dict(
                orient="records"
            )
        )

        total_revenue = float(
            schedule_df[
                "Fatturato Stimato"
            ].sum()
        )

    else:
        schedule = []
        total_revenue = 0.0

    # -----------------------------------------------------
    # 5. Risposta API
    # -----------------------------------------------------

    return {
        "available_companies":
            available_companies,

        "selected_companies":
            selected_companies,

        "map_points":
            map_points,

        "schedule":
            schedule,

        "metrics": {
            "total_visits":
                len(schedule),

            "expected_revenue":
                total_revenue,

            "companies_count":
                len(
                    selected_companies
                ),

            "available_visit_points":
                len(
                    df_filtered
                ),

            "geocoded_visit_points":
                len(
                    map_points
                )
        }
    }
