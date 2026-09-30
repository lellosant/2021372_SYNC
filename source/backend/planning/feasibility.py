import math
from typing import List, Optional
from .models import Client, LunchConfig, WorkdayConfig, PlanningDay, DayRoute, VisitSchedule
from .trasferte import evaluate_transfer

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
    agent_available_minutes: Optional[int] = None
) -> DayRoute:
    """Evaluate feasibility and timing for a single-day visit sequence."""
    # Delegate to multi-day transfer evaluator if enabled
    if enable_trasferte:
        return evaluate_transfer(
            client_indices,
            clients,
            travel_matrix,
            day,
            workday,
            lunch,
            work_end_grace_minutes,
            max_giorni_trasferta,
            agent_available_minutes=agent_available_minutes
        )

    current_minute = workday.start
    lunch_taken = False
    visits = []
    revenue = 0.0
    travel_minutes = 0
    current_loc_idx = 0
    client_ids = []
    
    is_feas = True
    arrival_depot = 0
    
    # Process each client in visit order
    for idx in client_indices:
        client = clients[idx]
        client_ids.append(client.id)
        target_idx = idx + 1
        
        # Travel time from previous stop
        travel = travel_matrix[current_loc_idx][target_idx]
        if not math.isfinite(travel):
            is_feas = False
            break
            
        travel_int = int(math.ceil(travel))
        arrival = current_minute + travel_int
        
        # Dynamic lunch scheduling: insert lunch before visit if visit would finish past latest lunch start
        lunch_before = False
        direct_end = arrival + client.service_minutes
        
        if lunch.duration > 0 and not lunch_taken and direct_end > lunch.latest_start:
            lunch_start = max(arrival, lunch.earliest)
            visit_start = lunch_start + lunch.duration
            lunch_before = True
        else:
            visit_start = arrival
            
        visit_end = visit_start + client.service_minutes
        
        # Visit must complete before workday ends
        if visit_end > workday.end:
            is_feas = False
            break

        # Lunch cannot start later than allowed window
        if lunch.duration > 0 and lunch_before and max(arrival, lunch.earliest) > lunch.latest_start:
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
        
        # Advance clock and take lunch after visit if eligible and not taken yet
        if lunch_before:
            lunch_taken = True
            current_minute = visit_end
        else:
            current_minute = visit_end
            if lunch.duration > 0 and not lunch_taken and visit_end >= lunch.earliest:
                current_minute = visit_end + lunch.duration
                lunch_taken = True
                
        current_loc_idx = target_idx

    # Return leg to depot
    if is_feas:
        travel_to_depot = travel_matrix[current_loc_idx][0]
        if not math.isfinite(travel_to_depot):
            is_feas = False
        else:
            travel_to_depot_int = int(math.ceil(travel_to_depot))
            arrival_depot = current_minute + travel_to_depot_int
            
            # Account for lunch before return if not yet taken
            if lunch.duration > 0 and not lunch_taken:
                if arrival_depot > lunch.latest_start:
                    lunch_start = max(current_minute, lunch.earliest)
                    if lunch_start > lunch.latest_start:
                         is_feas = False
                    arrival_depot = lunch_start + lunch.duration + travel_to_depot_int
                    
            # Return must be within grace window
            if arrival_depot > workday.end + work_end_grace_minutes:
                is_feas = False
            
            travel_minutes += travel_to_depot_int

    if is_feas:
        return DayRoute(day, client_ids, client_indices.copy(), True, revenue, travel_minutes, arrival_depot, visits, 1)

    return DayRoute(day, client_ids, client_indices.copy(), False, 0.0, 0, 0, [], 1)
