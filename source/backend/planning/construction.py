import random
from typing import List, Tuple
from .models import Client, PlanningDay, DayRoute, LunchConfig, WorkdayConfig, PlanningSolution
from .feasibility import evaluate_day_route
from .config import PLANNING_RANDOM_SEED

def _find_best_insertion(
    client_idx: int,
    client: Client,
    current_routes: List[DayRoute],
    clients: List[Client],
    matrix: List[List[float]],
    workday: WorkdayConfig,
    lunch: LunchConfig,
    work_end_grace_minutes: int,
    is_randomized: bool
) -> Tuple[int, int, DayRoute, float]:
    best_score = -1.0
    best_insertion = None
    
    for d_idx, route in enumerate(current_routes):
        bonus = route.day.weight
        if route.client_indices:
            clusters = [clients[i].cluster_id for i in route.client_indices if clients[i].cluster_id is not None]
            if clusters and max(set(clusters), key=clusters.count) == client.cluster_id:
                bonus = 1.10

        for pos in range(len(route.client_indices) + 1):
            new_indices = route.client_indices[:pos] + [client_idx] + route.client_indices[pos:]
            new_route = evaluate_day_route(new_indices, clients, matrix, route.day, workday, lunch, work_end_grace_minutes)
            if new_route.feasible:
                added_minutes = new_route.travel_minutes - route.travel_minutes
                score = (client.revenue / max(1, added_minutes)) * bonus
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
    work_end_grace_minutes: int
) -> PlanningSolution:
    
    routes = []
    
    for day in days:
        empty_route = evaluate_day_route([], pool, matrix, day, workday, lunch, work_end_grace_minutes)
        routes.append(empty_route)
        
    unassigned = list(range(len(pool)))
    
    if strategy == "revenue-first":
        unassigned.sort(key=lambda i: pool[i].revenue, reverse=True)
    elif strategy == "revenue-density-first":
        unassigned.sort(key=lambda i: pool[i]._score if hasattr(pool[i], '_score') else pool[i].revenue, reverse=True)
    elif strategy == "randomized":
        random.seed(PLANNING_RANDOM_SEED)
        unassigned.sort(key=lambda i: pool[i].revenue, reverse=True)
    else:
        raise ValueError("Unknown strategy")
        
    scheduled_ids = set()
    
    for client_idx in unassigned:
        client = pool[client_idx]
        insertion = _find_best_insertion(
            client_idx, client, routes, pool, matrix, workday, lunch, work_end_grace_minutes, strategy=="randomized"
        )
        if insertion:
            d_idx, pos, new_route, _ = insertion
            routes[d_idx] = new_route
            scheduled_ids.add(client.id)
            
    total_rev = sum(r.revenue for r in routes)
    total_travel = sum(r.travel_minutes for r in routes)
    return PlanningSolution(routes, total_rev, total_travel, scheduled_ids)

def construct_best_initial(
    pool: List[Client],
    matrix: List[List[float]],
    days: List[PlanningDay],
    workday: WorkdayConfig,
    lunch: LunchConfig,
    work_end_grace_minutes: int
) -> PlanningSolution:
    
    s1 = build_initial_solution("revenue-first", pool, matrix, days, workday, lunch, work_end_grace_minutes)
    s2 = build_initial_solution("revenue-density-first", pool, matrix, days, workday, lunch, work_end_grace_minutes)
    s3 = build_initial_solution("randomized", pool, matrix, days, workday, lunch, work_end_grace_minutes)
    
    def key(s: PlanningSolution):
        return (s.total_revenue, s.weighted_revenue, -s.total_travel_minutes)
        
    return max([s1, s2, s3], key=key)
