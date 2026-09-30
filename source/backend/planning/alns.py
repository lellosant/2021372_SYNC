import random
import time
import copy
from typing import List
from .models import Client, PlanningSolution, WorkdayConfig, LunchConfig
from .config import PLANNING_TIME_LIMIT_SECONDS, PLANNING_MAX_ITERATIONS, PLANNING_RANDOM_SEED
from .construction import _find_best_insertion, _get_covered_days
from .feasibility import evaluate_day_route
from .trasferte import is_trasferta_trip

# --- Destroy Operators ---

def destroy_random(solution: PlanningSolution, clients: List[Client], matrix, workday, lunch, work_end_grace_minutes, enable_trasferte, max_giorni_trasferta):
    """Randomly drop 10-20% of visits from planned days to escape local minima."""
    new_solution = copy.deepcopy(solution)
    removed_clients = []
    
    covered_days = _get_covered_days(new_solution.day_routes)
    
    for d_idx, route in enumerate(new_solution.day_routes):
        if d_idx in covered_days:
            continue
        if route.client_indices:
            num_remove = max(1, int(len(route.client_indices) * random.uniform(0.1, 0.2)))
            indices_to_remove = random.sample(range(len(route.client_indices)), min(num_remove, len(route.client_indices)))
            for idx in sorted(indices_to_remove, reverse=True):
                client_idx = route.client_indices.pop(idx)
                removed_clients.append(client_idx)
                new_solution.scheduled_client_ids.remove(clients[client_idx].id)
            new_r = evaluate_day_route(route.client_indices, clients, matrix, route.day, workday, lunch, work_end_grace_minutes, enable_trasferte, max_giorni_trasferta)
            new_solution.day_routes[d_idx] = new_r
            
    return new_solution, removed_clients

def destroy_cluster(solution: PlanningSolution, clients: List[Client], matrix, workday, lunch, work_end_grace_minutes, enable_trasferte, max_giorni_trasferta):
    """Pick an active spatial cluster and drop up to half its visits to allow tighter regrouping."""
    new_solution = copy.deepcopy(solution)
    removed_clients = []
    
    covered_days = _get_covered_days(new_solution.day_routes)
    
    clusters_present = set()
    for d_idx, route in enumerate(new_solution.day_routes):
        if d_idx in covered_days:
            continue
        for cid in route.client_indices:
            if clients[cid].cluster_id is not None:
                clusters_present.add(clients[cid].cluster_id)
                
    if not clusters_present:
        return new_solution, []
        
    target_cluster = random.choice(list(clusters_present))
    
    for d_idx, route in enumerate(new_solution.day_routes):
        if d_idx in covered_days:
            continue
        new_indices = []
        for cid in route.client_indices:
            if clients[cid].cluster_id == target_cluster and random.random() < 0.5:
                removed_clients.append(cid)
                new_solution.scheduled_client_ids.remove(clients[cid].id)
            else:
                new_indices.append(cid)
        if len(new_indices) != len(route.client_indices):
             new_solution.day_routes[d_idx] = evaluate_day_route(new_indices, clients, matrix, route.day, workday, lunch, work_end_grace_minutes, enable_trasferte, max_giorni_trasferta)
             
    return new_solution, removed_clients


# --- Repair Operator ---

def repair_greedy(solution: PlanningSolution, removed_clients: List[int], clients: List[Client], pool: List[Client], matrix, workday, lunch, work_end_grace_minutes, enable_trasferte, max_giorni_trasferta):
    """Greedy best-insertion for removed clients plus a small random sample of unscheduled pool clients."""
    candidates = removed_clients.copy()
    unscheduled = [c.source_index for c in pool if c.id not in solution.scheduled_client_ids]
    candidates.extend(random.sample(unscheduled, min(5, len(unscheduled))))
    
    # Prioritize remote / multi-day candidates when trasferte are enabled
    def is_remote_client(i: int) -> bool:
        if not enable_trasferte: return False
        t1 = matrix[0][i+1]
        t2 = clients[i].service_minutes
        t3 = matrix[i+1][0]
        if t1 == float('inf') or t3 == float('inf'): return False
        return is_trasferta_trip(t1, t2, t3, workday.end - workday.start)
        
    candidates.sort(key=lambda i: (1 if is_remote_client(i) else 0, clients[i].revenue), reverse=True)

    for client_idx in candidates:
        if clients[client_idx].id in solution.scheduled_client_ids: continue
        client = clients[client_idx]
        insertion = _find_best_insertion(client_idx, client, solution.day_routes, clients, matrix, workday, lunch, work_end_grace_minutes, False, enable_trasferte, max_giorni_trasferta)
        if insertion:
            d_idx, pos, new_route, _ = insertion
            solution.day_routes[d_idx] = new_route
            solution.scheduled_client_ids.add(client.id)
            
    covered = _get_covered_days(solution.day_routes)
    solution.total_revenue = sum(r.revenue for i, r in enumerate(solution.day_routes) if i not in covered)
    solution.total_travel_minutes = sum(r.travel_minutes for i, r in enumerate(solution.day_routes) if i not in covered)
    return solution


# --- Local Search & Post-Processing ---

def local_search_swap(solution: PlanningSolution, clients, matrix, workday, lunch, work_end_grace_minutes, enable_trasferte, max_giorni_trasferta):
    """2-opt style swap between two distinct days if feasible and Pareto-improving."""
    if len(solution.day_routes) < 2: return False
    
    covered_days = _get_covered_days(solution.day_routes)
    available_indices = [i for i in range(len(solution.day_routes)) if i not in covered_days and solution.day_routes[i].client_indices]
    
    if len(available_indices) < 2: return False
    
    d1_idx, d2_idx = random.sample(available_indices, 2)
    r1 = solution.day_routes[d1_idx]
    r2 = solution.day_routes[d2_idx]
    
    c1_idx = random.randint(0, len(r1.client_indices) - 1)
    c2_idx = random.randint(0, len(r2.client_indices) - 1)
    
    new_r1_ids = r1.client_indices.copy()
    new_r2_ids = r2.client_indices.copy()
    
    new_r1_ids[c1_idx] = r2.client_indices[c2_idx]
    new_r2_ids[c2_idx] = r1.client_indices[c1_idx]
    
    new_r1 = evaluate_day_route(new_r1_ids, clients, matrix, r1.day, workday, lunch, work_end_grace_minutes, enable_trasferte, max_giorni_trasferta)
    new_r2 = evaluate_day_route(new_r2_ids, clients, matrix, r2.day, workday, lunch, work_end_grace_minutes, enable_trasferte, max_giorni_trasferta)
    
    if new_r1.feasible and new_r2.feasible:
        # Check capacity when multi-day routes change span
        can_fit = True
        for (idx, old_r, new_r) in [(d1_idx, r1, new_r1), (d2_idx, r2, new_r2)]:
            if new_r.spans_days > old_r.spans_days:
                extra = new_r.spans_days - old_r.spans_days
                if idx + new_r.spans_days - 1 >= len(solution.day_routes):
                    can_fit = False
                    break
                for k in range(old_r.spans_days, new_r.spans_days):
                    if solution.day_routes[idx + k].client_indices or (idx + k) in covered_days:
                        can_fit = False
                        break
        
        if can_fit:
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

def _sol_score(s: PlanningSolution):
    # Lexicographic score: Total Revenue > Calendar-Weighted Revenue > Minimum Travel Time
    return (
        round(s.total_revenue, 2),
        round(s.weighted_revenue, 2),
        -round(s.total_travel_minutes, 2)
    )

def optimize_days_assignment(
    solution: PlanningSolution,
    clients: List[Client],
    matrix: List[List[float]],
    workday: WorkdayConfig,
    lunch: LunchConfig,
    work_end_grace_minutes: int,
    enable_trasferte: bool,
    max_giorni_trasferta: int
) -> PlanningSolution:
    """Swap whole day routes so higher-revenue days align with higher-weight calendar days (e.g. pre-holidays)."""
    routes = solution.day_routes
    n = len(routes)
    improved = True
    while improved:
        improved = False
        for i in range(n):
            if routes[i].spans_days > 1 or not routes[i].client_indices:
                continue
            for j in range(i + 1, n):
                if routes[j].spans_days > 1 or not routes[j].client_indices:
                    continue
                w_i = routes[i].day.weight
                w_j = routes[j].day.weight
                if abs(w_i - w_j) < 1e-4:
                    continue
                rev_i = routes[i].revenue
                rev_j = routes[j].revenue
                
                current_weighted = rev_i * w_i + rev_j * w_j
                swapped_weighted = rev_j * w_i + rev_i * w_j
                if swapped_weighted > current_weighted + 0.01:
                    new_r_i = evaluate_day_route(routes[j].client_indices, clients, matrix, routes[i].day, workday, lunch, work_end_grace_minutes, enable_trasferte, max_giorni_trasferta)
                    new_r_j = evaluate_day_route(routes[i].client_indices, clients, matrix, routes[j].day, workday, lunch, work_end_grace_minutes, enable_trasferte, max_giorni_trasferta)
                    if new_r_i.feasible and new_r_j.feasible:
                        routes[i] = new_r_i
                        routes[j] = new_r_j
                        improved = True
                        break
            if improved:
                break
    covered = _get_covered_days(routes)
    solution.total_revenue = sum(r.revenue for k, r in enumerate(routes) if k not in covered)
    solution.total_travel_minutes = sum(r.travel_minutes for k, r in enumerate(routes) if k not in covered)
    return solution


# --- Main Metaheuristic Loop ---

def run_alns(
    initial_solution: PlanningSolution,
    pool: List[Client], 
    matrix: List[List[float]],
    workday: WorkdayConfig,
    lunch: LunchConfig,
    work_end_grace_minutes: int,
    enable_trasferte: bool,
    max_giorni_trasferta: int
) -> PlanningSolution:
    random.seed(PLANNING_RANDOM_SEED)
    initial_solution = optimize_days_assignment(initial_solution, pool, matrix, workday, lunch, work_end_grace_minutes, enable_trasferte, max_giorni_trasferta)
    best_solution = copy.deepcopy(initial_solution)
    current_solution = copy.deepcopy(initial_solution)
    
    start_time = time.time()
    iterations = 0
    
    while iterations < PLANNING_MAX_ITERATIONS and (time.time() - start_time) < PLANNING_TIME_LIMIT_SECONDS:
        iterations += 1
        destroy_op = random.choice([destroy_random, destroy_cluster])
        temp_solution, removed = destroy_op(current_solution, pool, matrix, workday, lunch, work_end_grace_minutes, enable_trasferte, max_giorni_trasferta)
        temp_solution = repair_greedy(temp_solution, removed, pool, pool, matrix, workday, lunch, work_end_grace_minutes, enable_trasferte, max_giorni_trasferta)
        
        # 10% chance to run 2-opt inter-day swap
        if random.random() < 0.1:
             local_search_swap(temp_solution, pool, matrix, workday, lunch, work_end_grace_minutes, enable_trasferte, max_giorni_trasferta)
             
        covered = _get_covered_days(temp_solution.day_routes)
        temp_solution.total_revenue = sum(r.revenue for i, r in enumerate(temp_solution.day_routes) if i not in covered)
        temp_solution.total_travel_minutes = sum(r.travel_minutes for i, r in enumerate(temp_solution.day_routes) if i not in covered)
        
        temp_score = _sol_score(temp_solution)
        current_score = _sol_score(current_solution)
        
        # Acceptance: accept improvements immediately, worse moves with 5% probability (SA temperature floor)
        if temp_score > current_score:
            current_solution = temp_solution
            if temp_score > _sol_score(best_solution):
                best_solution = copy.deepcopy(temp_solution)
        else:
            if random.random() < 0.05:
                current_solution = temp_solution
                
    # Final pass to align high-revenue routes with weighted days
    best_solution = optimize_days_assignment(best_solution, pool, matrix, workday, lunch, work_end_grace_minutes, enable_trasferte, max_giorni_trasferta)
    return best_solution
