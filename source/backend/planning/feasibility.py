import math
from typing import List
from .models import Client, LunchConfig, WorkdayConfig, PlanningDay, DayRoute, VisitSchedule
from .trasferte import evaluate_transfer
from .config import MIN_TRASFERTA_TRAVEL_MINUTES

def evaluate_day_route(
    client_indices: List[int],
    clients: List[Client],
    travel_matrix: List[List[float]],
    day: PlanningDay,
    workday: WorkdayConfig,
    lunch: LunchConfig,
    work_end_grace_minutes: int,
    enable_trasferte: bool = False,
    max_giorni_trasferta: int = 1,
    min_trasferta_minutes: int = MIN_TRASFERTA_TRAVEL_MINUTES
) -> DayRoute:
    if enable_trasferte:
        return evaluate_transfer(client_indices, clients, travel_matrix, day, workday, lunch, work_end_grace_minutes, max_giorni_trasferta, min_trasferta_minutes)

    current_minute = workday.start
    lunch_taken = False
    visits = []
    revenue = 0.0
    travel_minutes = 0
    current_loc_idx = 0
    client_ids = []
    
    is_feas = True
    arrival_depot = 0
    
    for idx in client_indices:
        client = clients[idx]
        client_ids.append(client.id)
        target_idx = idx + 1
        
        travel = travel_matrix[current_loc_idx][target_idx]
        if not math.isfinite(travel):
            is_feas = False
            break
            
        travel_int = int(math.ceil(travel))
        arrival = current_minute + travel_int
        
        lunch_before = False
        direct_end = arrival + client.service_minutes
        
        if not lunch_taken and direct_end > lunch.latest_start:
            lunch_start = max(arrival, lunch.earliest)
            visit_start = lunch_start + lunch.duration
            lunch_before = True
        else:
            visit_start = arrival
            
        visit_end = visit_start + client.service_minutes
        
        if visit_end > workday.end:
            is_feas = False
            break

        if lunch_before and max(arrival, lunch.earliest) > lunch.latest_start:
            is_feas = False
            break

        visits.append(VisitSchedule(
            client_id=client.id,
            arrival_minute=arrival,
            visit_start=visit_start,
            visit_end=visit_end,
            lunch_before=lunch_before,
            travel_from_prev=travel_int
        ))
        
        revenue += client.revenue
        travel_minutes += travel_int
        
        if lunch_before:
            lunch_taken = True
            current_minute = visit_end
        else:
            current_minute = visit_end
            if not lunch_taken and visit_end >= lunch.earliest:
                current_minute = visit_end + lunch.duration
                lunch_taken = True
                
        current_loc_idx = target_idx

    if is_feas:
        travel_to_depot = travel_matrix[current_loc_idx][0]
        if not math.isfinite(travel_to_depot):
            is_feas = False
        else:
            travel_to_depot_int = int(math.ceil(travel_to_depot))
            arrival_depot = current_minute + travel_to_depot_int
            
            if not lunch_taken:
                if arrival_depot > lunch.latest_start:
                    lunch_start = max(current_minute, lunch.earliest)
                    if lunch_start > lunch.latest_start:
                         is_feas = False
                    arrival_depot = lunch_start + lunch.duration + travel_to_depot_int
                    
            if arrival_depot > workday.end + work_end_grace_minutes:
                is_feas = False
            
            travel_minutes += travel_to_depot_int

    if is_feas:
        return DayRoute(day, client_ids, client_indices.copy(), True, revenue, travel_minutes, arrival_depot, visits, 1)

    return DayRoute(day, client_ids, client_indices.copy(), False, 0.0, 0, 0, [], 1)
