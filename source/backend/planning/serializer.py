import pandas as pd
from typing import List
from .models import PlanningSolution, Client
from .calendar import GIORNI_IT

def format_time(minutes):
    hours = int(minutes // 60)
    minutes = int(minutes % 60)
    return f"{hours:02d}:{minutes:02d}"

def serialize_solution(solution: PlanningSolution, clients: List[Client]) -> pd.DataFrame:
    schedule = []
    
    for route in solution.day_routes:
        if not route.client_ids:
            continue
            
        date_str = route.day.date_val.strftime("%d/%m/%Y")
        day_str = GIORNI_IT[route.day.date_val.weekday()]
        
        for visit in route.visits:
            client = next(c for c in clients if c.id == visit.client_id)
            schedule.append({
                "Data Visita": date_str,
                "Giorno": day_str,
                "Orario": f"{format_time(visit.visit_start)} - {format_time(visit.visit_end)}",
                "Cliente": client.name,
                "Gruppo": client.group,
                "Città": client.city,
                "Indirizzo": client.address,
                "Fatturato Stimato": client.revenue,
                "Tempo Spostamento (min)": visit.travel_from_prev,
                "Lat": client.latitude,
                "Lon": client.longitude,
            })
            
    return pd.DataFrame(schedule)
