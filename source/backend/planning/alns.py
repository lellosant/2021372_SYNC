import random
import time
import copy
from typing import List
from .models import Client, PlanningSolution, WorkdayConfig, LunchConfig
from .config import PLANNING_TIME_LIMIT_SECONDS, PLANNING_MAX_ITERATIONS, PLANNING_RANDOM_SEED
from .construction import _find_best_insertion
from .feasibility import evaluate_day_route

def destroy_random(solution: PlanningSolution, clients: List[Client], matrix, workday, lunch, work_end_grace_minutes):
    new_solution = copy.deepcopy(solution)
    removed_clients = []
    
    for route in new_solution.day_routes:
        if route.client_indices:
            num_remove = max(1, int(len(route.client_indices) * random.uniform(0.1, 0.2)))
            indices_to_remove = random.sample(range(len(route.client_indices)), min(num_remove, len(route.client_indices)))
            for idx in sorted(indices_to_remove, reverse=True):
                client_idx = route.client_indices.pop(idx)
                removed_clients.append(client_idx)
                new_solution.scheduled_client_ids.remove(clients[client_idx].id)
            new_solution.day_routes[route.day.day_index] = evaluate_day_route(route.client_indices, clients, matrix, route.day, workday, lunch, work_end_grace_minutes)
            
    return new_solution, removed_clients

def destroy_cluster(solution: PlanningSolution, clients: List[Client], matrix, workday, lunch, work_end_grace_minutes):
    new_solution = copy.deepcopy(solution)
    removed_clients = []
    
    clusters_present = set()
    for route in new_solution.day_routes:
        for cid in route.client_indices:
            if clients[cid].cluster_id is not None:
                clusters_present.add(clients[cid].cluster_id)
                
    if not clusters_present:
        return new_solution, []
        
    target_cluster = random.choice(list(clusters_present))
    
    for route in new_solution.day_routes:
        new_indices = []
        for cid in route.client_indices:
            if clients[cid].cluster_id == target_cluster and random.random() < 0.5:
                removed_clients.append(cid)
                new_solution.scheduled_client_ids.remove(clients[cid].id)
            else:
                new_indices.append(cid)
        if len(new_indices) != len(route.client_indices):
             new_solution.day_routes[route.day.day_index] = evaluate_day_route(new_indices, clients, matrix, route.day, workday, lunch, work_end_grace_minutes)
             
    return new_solution, removed_clients
    
def repair_greedy(solution: PlanningSolution, removed_clients: List[int], clients: List[Client], pool: List[Client], matrix, workday, lunch, work_end_grace_minutes):
    candidates = removed_clients.copy()
    unscheduled = [c.source_index for c in pool if c.id not in solution.scheduled_client_ids]
    candidates.extend(random.sample(unscheduled, min(5, len(unscheduled))))
    
    for client_idx in candidates:
        if clients[client_idx].id in solution.scheduled_client_ids: continue
        client = clients[client_idx]
        insertion = _find_best_insertion(client_idx, client, solution.day_routes, clients, matrix, workday, lunch, work_end_grace_minutes, False)
        if insertion:
            d_idx, pos, new_route, _ = insertion
            solution.day_routes[d_idx] = new_route
            solution.scheduled_client_ids.add(client.id)
            
    solution.total_revenue = sum(r.revenue for r in solution.day_routes)
    solution.total_travel_minutes = sum(r.travel_minutes for r in solution.day_routes)
    return solution

def local_search_swap(solution: PlanningSolution, clients, matrix, workday, lunch, work_end_grace_minutes):
    if len(solution.day_routes) < 2: return False
    
    d1_idx, d2_idx = random.sample(range(len(solution.day_routes)), 2)
    r1 = solution.day_routes[d1_idx]
    r2 = solution.day_routes[d2_idx]
    
    if not r1.client_indices or not r2.client_indices: return False
    
    c1_idx = random.randint(0, len(r1.client_indices) - 1)
    c2_idx = random.randint(0, len(r2.client_indices) - 1)
    
    new_r1_ids = r1.client_indices.copy()
    new_r2_ids = r2.client_indices.copy()
    
    new_r1_ids[c1_idx] = r2.client_indices[c2_idx]
    new_r2_ids[c2_idx] = r1.client_indices[c1_idx]
    
    new_r1 = evaluate_day_route(new_r1_ids, clients, matrix, r1.day, workday, lunch, work_end_grace_minutes)
    new_r2 = evaluate_day_route(new_r2_ids, clients, matrix, r2.day, workday, lunch, work_end_grace_minutes)
    
    if new_r1.feasible and new_r2.feasible:
        old_rev = r1.revenue + r2.revenue
        new_rev = new_r1.revenue + new_r2.revenue
        old_w_rev = r1.revenue * r1.day.weight + r2.revenue * r2.day.weight
        new_w_rev = new_r1.revenue * new_r1.day.weight + new_r2.revenue * new_r2.day.weight
        old_trv = r1.travel_minutes + r2.travel_minutes
        new_trv = new_r1.travel_minutes + new_r2.travel_minutes
        
        if (new_rev, new_w_rev, -new_trv) > (old_rev, old_w_rev, -old_trv):
            solution.day_routes[d1_idx] = new_r1
            solution.day_routes[d2_idx] = new_r2
            solution.total_revenue += (new_rev - old_rev)
            solution.total_travel_minutes += (new_trv - old_trv)
            return True
    return False

def run_alns(
    initial_solution: PlanningSolution,
    pool: List[Client], 
    matrix: List[List[float]],
    workday: WorkdayConfig,
    lunch: LunchConfig,
    work_end_grace_minutes: int
) -> PlanningSolution:
    random.seed(PLANNING_RANDOM_SEED)
    best_solution = copy.deepcopy(initial_solution)
    current_solution = copy.deepcopy(initial_solution)
    
    start_time = time.time()
    iterations = 0
    
    while iterations < PLANNING_MAX_ITERATIONS and (time.time() - start_time) < PLANNING_TIME_LIMIT_SECONDS:
        iterations += 1
        destroy_op = random.choice([destroy_random, destroy_cluster])
        temp_solution, removed = destroy_op(current_solution, pool, matrix, workday, lunch, work_end_grace_minutes)
        temp_solution = repair_greedy(temp_solution, removed, pool, pool, matrix, workday, lunch, work_end_grace_minutes)
        
        if random.random() < 0.1:
             local_search_swap(temp_solution, pool, matrix, workday, lunch, work_end_grace_minutes)
             
        temp_score = (temp_solution.total_revenue, temp_solution.weighted_revenue, -temp_solution.total_travel_minutes)
        current_score = (current_solution.total_revenue, current_solution.weighted_revenue, -current_solution.total_travel_minutes)
        
        if temp_score > current_score:
            current_solution = temp_solution
            if temp_score > (best_solution.total_revenue, best_solution.weighted_revenue, -best_solution.total_travel_minutes):
                best_solution = copy.deepcopy(temp_solution)
        else:
            if random.random() < 0.05:
                current_solution = temp_solution
                
    import logging; logging.getLogger(__name__).info(f"iterazioni ALNS: {iterations}"); return best_solution
