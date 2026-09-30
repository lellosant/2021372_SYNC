import datetime
import logging
import time
import pandas as pd
from typing import List

from .config import _parse_time_val, WORK_END_GRACE_MINUTES
from .models import Location, Client, LunchConfig, WorkdayConfig, PlanningDay
from .calendar import build_business_days, _next_business_day
from .candidates import build_candidate_pool
from .routing import build_travel_matrix
from .construction import construct_best_initial
from .alns import run_alns
from .feasibility import evaluate_day_route
from .serializer import serialize_solution

logger = logging.getLogger(__name__)

def optimize_visits(
    df,
    days,
    hours_per_visit,
    work_hours_per_day,
    companies_filter,
    start_date=None,
    start_address=None,
    start_lat=None,
    start_lon=None,
    work_start=None,
    work_end=None,
    lunch_earliest=None,
    lunch_latest_start=None,
    lunch_duration_minutes=None,
    enable_trasferte=False,
    max_giorni_trasferta=3,
    **kwargs
):
    # 1. Basic validation and time configuration
    if days <= 0 or hours_per_visit <= 0:
        return pd.DataFrame()

    if start_lat is None or start_lon is None:
        raise ValueError("Sede (start_lat, start_lon) è obbligatoria.")
        
    depot = Location(lat=float(start_lat), lon=float(start_lon))
    
    day_start = _parse_time_val(work_start, 9 * 60)
    day_end = _parse_time_val(work_end, 18 * 60)
    lunch_earliest_min = _parse_time_val(lunch_earliest, 12 * 60)
    lunch_latest_start_min = _parse_time_val(lunch_latest_start, 14 * 60)
    try:
        lunch_duration_min = int(lunch_duration_minutes) if (lunch_duration_minutes is not None and str(lunch_duration_minutes).strip() != "") else 60
    except (ValueError, TypeError):
        lunch_duration_min = 60
        
    workday = WorkdayConfig(start=day_start, end=day_end)
    lunch = LunchConfig(earliest=lunch_earliest_min, latest_start=lunch_latest_start_min, duration=lunch_duration_min)
    service_minutes = int(round(hours_per_visit * 60))
    
    # 2. Build working calendar and day priorities
    if start_date:
        if isinstance(start_date, str):
            base_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
        else:
            base_date = start_date
    else:
        base_date = datetime.date.today()
    if not isinstance(base_date, datetime.date) or isinstance(base_date, datetime.datetime):
        if hasattr(base_date, 'date'):
             base_date = base_date.date()
    
    business_dates = build_business_days(base_date, days)
    from .calendar import get_day_weight
    planning_days = [PlanningDay(d, i, get_day_weight(d)) for i, d in enumerate(business_dates)]
    
    # 3. Filter clients for target company and parse coordinates
    if companies_filter:
        valid_companies = [c for c in companies_filter if c in df.columns]
        if not valid_companies: return pd.DataFrame()
    else:
        return pd.DataFrame()
        
    df_filtered = df.copy()
    df_filtered["SelectedRevenue"] = df_filtered[valid_companies].sum(axis=1)
    df_filtered["Lat"] = pd.to_numeric(df_filtered["Lat"], errors="coerce")
    df_filtered["Lon"] = pd.to_numeric(df_filtered["Lon"], errors="coerce")
    df_filtered = df_filtered.dropna(subset=["Lat", "Lon"])
    df_filtered = df_filtered[df_filtered["SelectedRevenue"] > 0]
    
    clients = []
    for idx, row in df_filtered.iterrows():
        main_comp = ""
        max_val = -1
        for comp in valid_companies:
            try:
                val = float(row.get(comp, 0))
                if pd.notna(val) and val > max_val:
                    max_val = val
                    main_comp = comp
            except: pass
            
        c = Client(
            id=str(idx),
            name=row.get("Cliente", row.get("Ragione Sociale", "Sconosciuto")),
            latitude=float(row["Lat"]),
            longitude=float(row["Lon"]),
            revenue=float(row["SelectedRevenue"]),
            service_minutes=service_minutes,
            cluster_id=None,
            source_index=len(clients),
            group=main_comp,
            city=row.get("Citta", row.get("Città", "")),
            address=row.get("Indirizzo", "")
        )
        clients.append(c)
        
    logger.info(f"numero clienti input: {len(df)}")
    logger.info(f"numero clienti validi: {len(clients)}")
    
    if not clients: return pd.DataFrame()
    
    # 4. Build candidate pool and spatial clusters
    pool = build_candidate_pool(clients, depot, days, day_start, day_end, lunch_duration_min, service_minutes)
    for i, c in enumerate(pool):
        c.source_index = i
        
    logger.info(f"numero candidati: {len(pool)}")
    logger.info(f"numero cluster: {len(set(c.cluster_id for c in pool if c.cluster_id is not None))}")
    
    # 5. Calculate travel distance and duration matrix
    from .routing import build_travel_matrix_with_status
    matrix, is_fallback = build_travel_matrix_with_status(depot, pool)
    
    # 6. Construct initial greedy/heuristic solution
    best_initial = construct_best_initial(pool, matrix, planning_days, workday, lunch, WORK_END_GRACE_MINUTES, enable_trasferte, max_giorni_trasferta)
    logger.info(f"fatturato soluzione iniziale: {best_initial.total_revenue}")
    
    # 7. Optimize routes using ALNS
    alns_start = time.time()
    final_solution = run_alns(best_initial, pool, matrix, workday, lunch, WORK_END_GRACE_MINUTES, enable_trasferte, max_giorni_trasferta)
    alns_time = time.time() - alns_start
    
    logger.info(f"fatturato soluzione finale: {final_solution.total_revenue}")
    logger.info(f"minuti di viaggio: {final_solution.total_travel_minutes}")
    logger.info(f"runtime ALNS: {alns_time:.2f}s")
    
    if best_initial.total_revenue > 0:
        improvement = ((final_solution.total_revenue - best_initial.total_revenue) / best_initial.total_revenue) * 100
        logger.info(f"miglioramento percentuale: {improvement:.2f}%")
        

    # Compattazione dell'agenda (rimozione giorni vuoti in mezzo)
    from .construction import _get_covered_days
    covered = _get_covered_days(final_solution.day_routes)
    blocks = [r.client_indices for i, r in enumerate(final_solution.day_routes) if i not in covered and r.client_indices]
    
    new_routes = []
    block_idx = 0
    day_idx = 0
    last_used_day = 0
    while day_idx < len(planning_days):
        day = planning_days[day_idx]
        if block_idx < len(blocks):
            r = evaluate_day_route(blocks[block_idx], pool, matrix, day, workday, lunch, WORK_END_GRACE_MINUTES, enable_trasferte, max_giorni_trasferta)
            new_routes.append(r)
            day_idx += r.spans_days
            for k in range(1, r.spans_days):
                if day_idx <= len(planning_days):
                   empty_day = planning_days[day_idx - r.spans_days + k]
                   new_routes.append(evaluate_day_route([], pool, matrix, empty_day, workday, lunch, WORK_END_GRACE_MINUTES, enable_trasferte, max_giorni_trasferta))
            block_idx += 1
            last_used_day = day_idx
        else:
            new_routes.append(evaluate_day_route([], pool, matrix, day, workday, lunch, WORK_END_GRACE_MINUTES, enable_trasferte, max_giorni_trasferta))
            day_idx += 1
            
    final_solution.day_routes = new_routes[:len(planning_days)]

    # 8. Feasibility sanity check and serialization
    for i, route in enumerate(final_solution.day_routes):
        val = evaluate_day_route(route.client_indices, pool, matrix, route.day, workday, lunch, WORK_END_GRACE_MINUTES, enable_trasferte, max_giorni_trasferta)
        if not val.feasible:
            logger.error(f"Errore: giornata {i} non valida alla fine.")
            raise RuntimeError(f"Soluzione finale contiene una giornata non valida: {i}")
        final_solution.day_routes[i] = val
        
    df_out = serialize_solution(final_solution, pool)
    df_out.attrs['is_fallback'] = is_fallback
    df_out.attrs['total_days_spanned'] = last_used_day if 'last_used_day' in locals() else 0
    return df_out
