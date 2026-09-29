import random
from typing import List, Tuple, Set
from .models import Client, PlanningDay, DayRoute, LunchConfig, WorkdayConfig, PlanningSolution
from .feasibility import evaluate_day_route
from .config import PLANNING_RANDOM_SEED

def _get_covered_days(routes: List[DayRoute]) -> Set[int]:
    covered = set()
    for i, r in enumerate(routes):
        if r.spans_days > 1:
            for k in range(1, r.spans_days):
                covered.add(i + k)
    return covered

def _find_best_insertion(
    client_idx: int,
    client: Client,
    current_routes: List[DayRoute],
    clients: List[Client],
    matrix: List[List[float]],
    workday: WorkdayConfig,
    lunch: LunchConfig,
    work_end_grace_minutes: int,
    is_randomized: bool,
    enable_trasferte: bool,
    max_giorni_trasferta: int
) -> Tuple[int, int, DayRoute, float]:
    best_score = -1.0
    best_insertion = None
    
    covered_days = _get_covered_days(current_routes)
    
    for d_idx, route in enumerate(current_routes):
        if d_idx in covered_days:
            continue
            
        bonus = route.day.weight
        if route.client_indices:
            clusters = [clients[i].cluster_id for i in route.client_indices if clients[i].cluster_id is not None]
            if clusters and max(set(clusters), key=clusters.count) == client.cluster_id:
                bonus = 1.10

        for pos in range(len(route.client_indices) + 1):
            new_indices = route.client_indices[:pos] + [client_idx] + route.client_indices[pos:]
            new_route = evaluate_day_route(new_indices, clients, matrix, route.day, workday, lunch, work_end_grace_minutes, enable_trasferte, max_giorni_trasferta)
            
            if new_route.feasible:
                added_capacity = new_route.spans_days - route.spans_days
                if added_capacity > 0:
                    can_fit = True
                    if d_idx + new_route.spans_days - 1 >= len(current_routes):
                        can_fit = False
                    else:
                        for k in range(1, new_route.spans_days):
                            if current_routes[d_idx + k].client_indices or (d_idx + k) in covered_days:
                                can_fit = False
                                break
                    if not can_fit:
                        continue
                        
                added_minutes = new_route.travel_minutes - route.travel_minutes
                workday_minutes = workday.end - workday.start
                effective_cost = added_minutes + (added_capacity * workday_minutes)
                score = (client.revenue / max(1, effective_cost)) * bonus
                
                if is_randomized:
                    score *= random.uniform(0.8, 1.2)
                if score > best_score:
                    best_score = score
                    best_insertion = (d_idx, pos, new_route, score)
                    
    return best_insertion

def build_initial_solution(
    strategy: str,
    pool: List[Client],
    matrix: List[List[float]],
    days: List[PlanningDay],
    workday: WorkdayConfig,
    lunch: LunchConfig,
    work_end_grace_minutes: int,
    enable_trasferte: bool,
    max_giorni_trasferta: int
) -> PlanningSolution:
    
    routes = []
    for day in days:
        empty_route = evaluate_day_route([], pool, matrix, day, workday, lunch, work_end_grace_minutes)
        routes.append(empty_route)
        
    unassigned = list(range(len(pool)))
    
    if strategy == "revenue-first" or strategy == "revenue-density-first":
        unassigned.sort(key=lambda i: pool[i].revenue, reverse=True)
    elif strategy == "randomized":
        random.seed(PLANNING_RANDOM_SEED)
        unassigned.sort(key=lambda i: pool[i].revenue, reverse=True)
        
    scheduled_ids = set()
    
    for client_idx in unassigned:
        client = pool[client_idx]
        insertion = _find_best_insertion(
            client_idx, client, routes, pool, matrix, workday, lunch, work_end_grace_minutes, strategy=="randomized", enable_trasferte, max_giorni_trasferta
        )
        if insertion:
            d_idx, pos, new_route, _ = insertion
            routes[d_idx] = new_route
            scheduled_ids.add(client.id)
            
    total_rev = sum(r.revenue for d_idx, r in enumerate(routes) if d_idx not in _get_covered_days(routes))
    total_travel = sum(r.travel_minutes for d_idx, r in enumerate(routes) if d_idx not in _get_covered_days(routes))
    return PlanningSolution(routes, total_rev, total_travel, scheduled_ids)

def construct_best_initial(
    pool: List[Client],
    matrix: List[List[float]],
    days: List[PlanningDay],
    workday: WorkdayConfig,
    lunch: LunchConfig,
    work_end_grace_minutes: int,
    enable_trasferte: bool,
    max_giorni_trasferta: int
) -> PlanningSolution:
    
    s1 = build_initial_solution("revenue-first", pool, matrix, days, workday, lunch, work_end_grace_minutes, enable_trasferte, max_giorni_trasferta)
    s2 = build_initial_solution("revenue-density-first", pool, matrix, days, workday, lunch, work_end_grace_minutes, enable_trasferte, max_giorni_trasferta)
    s3 = build_initial_solution("randomized", pool, matrix, days, workday, lunch, work_end_grace_minutes, enable_trasferte, max_giorni_trasferta)
    
    def key(s: PlanningSolution):
        return (s.total_revenue, s.weighted_revenue, -s.total_travel_minutes)
        
    return max([s1, s2, s3], key=key)
