import math
from typing import List, Optional
from .models import Client, LunchConfig, WorkdayConfig, PlanningDay, DayRoute, VisitSchedule


def is_trasferta_trip(
    t1: float,
    t2: float,
    t3: float,
    available_time: float
) -> bool:
    """Determine whether a destination qualifies as a remote trip:
    t1 = outbound travel (depot -> client)
    t2 = visit service time
    t3 = return travel (client -> depot)
    A trip requires an overnight stay if t1 + t2 + t3 exceeds the agent's available daily working hours.
    """
    return (t1 + t2 + t3) > available_time


def evaluate_transfer(
    client_indices: List[int],
    clients: List[Client],
    travel_matrix: List[List[float]],
    day: PlanningDay,
    workday: WorkdayConfig,
    lunch: LunchConfig,
    work_end_grace_minutes: int,
    max_giorni_trasferta: int,
    agent_available_minutes: Optional[int] = None
) -> DayRoute:
    """Evaluate feasibility of a multi-day route spanning consecutive workdays with overnight stays."""
    current_day = 1
    current_minute = workday.start
    lunch_taken_today = False
    
    visits = []
    revenue = 0.0
    travel_minutes = 0
    current_loc_idx = 0
    client_ids = []
    
    for idx in client_indices:
        client = clients[idx]
        client_ids.append(client.id)
        target_idx = idx + 1
        
        travel = travel_matrix[current_loc_idx][target_idx]
        if not math.isfinite(travel):
            return DayRoute(day, client_ids, client_indices.copy(), False, 0.0, 0, 0, [], 1)
            
        travel_int = int(math.ceil(travel))
        travel_minutes += travel_int
        
        # Advance time across days if travel extends past end of workday
        remaining_travel = travel_int
        while remaining_travel > 0:
            time_to_end = workday.end - current_minute
            if remaining_travel <= time_to_end:
                current_minute += remaining_travel
                remaining_travel = 0
            else:
                remaining_travel -= max(0, time_to_end)
                current_day += 1
                current_minute = workday.start
                lunch_taken_today = False
                if current_day > max_giorni_trasferta:
                    return DayRoute(day, client_ids, client_indices.copy(), False, 0.0, 0, 0, [], 1)

        arrival = current_minute
        direct_end = arrival + client.service_minutes
        lunch_before = False
        
        # Insert lunch before visit if visit would finish past latest lunch start
        if lunch.duration > 0 and not lunch_taken_today and direct_end > lunch.latest_start:
            lunch_start = max(arrival, lunch.earliest)
            if lunch_start + lunch.duration + client.service_minutes > workday.end:
                current_day += 1
                current_minute = workday.start
                lunch_taken_today = False
                arrival = current_minute
                if current_day > max_giorni_trasferta:
                    return DayRoute(day, client_ids, client_indices.copy(), False, 0.0, 0, 0, [], 1)
            else:
                current_minute = lunch_start + lunch.duration
                lunch_taken_today = True
                lunch_before = True

        visit_start = current_minute
        visit_end = visit_start + client.service_minutes
        
        # Move to next day if visit exceeds end of current workday
        if visit_end > workday.end:
            current_day += 1
            current_minute = workday.start
            lunch_taken_today = False
            arrival = current_minute
            visit_start = current_minute
            visit_end = visit_start + client.service_minutes
            if current_day > max_giorni_trasferta:
                return DayRoute(day, client_ids, client_indices.copy(), False, 0.0, 0, 0, [], 1)
                
        visits.append(VisitSchedule(
            client_id=client.id,
            arrival_minute=arrival,
            visit_start=visit_start,
            visit_end=visit_end,
            lunch_before=lunch_before,
            travel_from_prev=travel_int,
            day_offset=current_day - 1
        ))
        
        revenue += client.revenue
        if lunch_before:
            current_minute = visit_end
        else:
            current_minute = visit_end
            if lunch.duration > 0 and not lunch_taken_today and visit_end >= lunch.earliest:
                current_minute = visit_end + lunch.duration
                lunch_taken_today = True
                
        current_loc_idx = target_idx

    # Return travel to home base (depot)
    travel_to_depot = travel_matrix[current_loc_idx][0]
    if not math.isfinite(travel_to_depot):
        return DayRoute(day, client_ids, client_indices.copy(), False, 0.0, 0, 0, [], 1)
        
    travel_to_depot_int = int(math.ceil(travel_to_depot))
    travel_minutes += travel_to_depot_int
    
    remaining_travel = travel_to_depot_int
    while remaining_travel > 0:
        time_to_end = workday.end - current_minute
        if remaining_travel <= time_to_end + work_end_grace_minutes:
            current_minute += remaining_travel
            remaining_travel = 0
        else:
            remaining_travel -= max(0, time_to_end)
            current_day += 1
            current_minute = workday.start
            lunch_taken_today = False
            if current_day > max_giorni_trasferta:
                 return DayRoute(day, client_ids, client_indices.copy(), False, 0.0, 0, 0, [], 1)

    if current_day > 1:
        # Multi-day transfer is only justified if at least one client qualifies as a remote trip
        # (t1 + t2 + t3 > available_time). Otherwise, visits must be scheduled as separate local days.
        available_time = agent_available_minutes if agent_available_minutes is not None else (workday.end - workday.start)

        has_remote_trip = False
        if client_indices:
            for idx in client_indices:
                target_idx = idx + 1
                t1 = travel_matrix[0][target_idx]
                t2 = clients[idx].service_minutes
                t3 = travel_matrix[target_idx][0]
                if is_trasferta_trip(t1, t2, t3, available_time):
                    has_remote_trip = True
                    break

        if not has_remote_trip:
            return DayRoute(day, client_ids, client_indices.copy(), False, 0.0, 0, 0, [], 1)
                 
    return DayRoute(day, client_ids, client_indices.copy(), True, revenue, travel_minutes, current_minute, visits, current_day)
