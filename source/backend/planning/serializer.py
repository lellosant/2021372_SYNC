import pandas as pd
import datetime
from typing import List
from .models import PlanningSolution, Client
from .calendar import GIORNI_IT

def format_time(minutes):
    """Convert minutes from midnight into HH:MM string format."""
    hours = int(minutes // 60)
    minutes = int(minutes % 60)
    return f"{hours:02d}:{minutes:02d}"

def serialize_solution(solution: PlanningSolution, clients: List[Client]) -> pd.DataFrame:
    """Transform PlanningSolution dataclass models into a tabular DataFrame for the API and frontend."""
    schedule = []
    
    # Map day indices to business calendar dates
    day_date_map = {}
    for r in solution.day_routes:
        if hasattr(r.day, 'day_index') and hasattr(r.day, 'date_val'):
            day_date_map[r.day.day_index] = r.day.date_val

    for route in solution.day_routes:
        if not route.client_ids:
            continue
            
        for visit in route.visits:
            client = next(c for c in clients if c.id == visit.client_id)
            time_str = f"{format_time(visit.visit_start)} - {format_time(visit.visit_end)}"
            
            # Resolve actual date accounting for multi-day transfer day offsets
            day_offset = getattr(visit, 'day_offset', 0)
            actual_day_idx = getattr(route.day, 'day_index', 0) + day_offset
            
            if actual_day_idx in day_date_map:
                actual_date = day_date_map[actual_day_idx]
            else:
                actual_date = route.day.date_val + datetime.timedelta(days=day_offset)
                
            date_str = actual_date.strftime("%d/%m/%Y")
            day_name = GIORNI_IT[actual_date.weekday()]
            
            # Label transfer departure vs continuation days
            is_multi = getattr(route, 'spans_days', 1) > 1
            if is_multi:
                day_ds = f"{day_name} (+{day_offset}gg)" if day_offset > 0 else f"{day_name} (Partenza trasferta)"
            else:
                day_ds = day_name
            
            schedule.append({
                "Data Visita": date_str,
                "Giorno": day_ds,
                "Orario": time_str,
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
