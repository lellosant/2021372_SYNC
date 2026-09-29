from typing import List
from .models import Client, Location
from .routing import _haversine_minutes
from .clustering import cluster_clients
import math
from .config import PLANNING_POOL_MULTIPLIER

def build_candidate_pool(
    all_clients: List[Client],
    depot: Location,
    num_days: int,
    work_start: int,
    work_end: int,
    lunch_duration: int,
    service_minutes: int
) -> List[Client]:
    if not all_clients:
        return []
        
    available_minutes = work_end - work_start - lunch_duration
    max_visits_per_day = max(1, available_minutes // service_minutes)
    estimated_visits = num_days * max_visits_per_day
    pool_size = min(len(all_clients), max(100, estimated_visits * PLANNING_POOL_MULTIPLIER))
    
    # Raggruppamento geografico con cluster tarati su 3 giorni di lavoro
    target_cluster_size = max(1, max_visits_per_day * 3)
    cluster_clients(all_clients, depot, target_cluster_size=target_cluster_size)
    
    clients_by_rev = sorted(all_clients, key=lambda c: c.revenue, reverse=True)
    
    for c in all_clients:
        dist = _haversine_minutes(depot.lat, depot.lon, c.latitude, c.longitude)
        c._score = c.revenue / max(1.0, dist)
    clients_by_score = sorted(all_clients, key=lambda c: c._score, reverse=True)
    
    pool_set = set()
    pool = []
    
    def add_client(c: Client):
        if c.id not in pool_set:
            pool_set.add(c.id)
            pool.append(c)
            
    for i in range(len(all_clients)):
        if len(pool) >= pool_size:
            break
        if i < len(clients_by_rev): add_client(clients_by_rev[i])
        if len(pool) >= pool_size: break
        if i < len(clients_by_score): add_client(clients_by_score[i])
        
    for cluster_id in set(c.cluster_id for c in all_clients if c.cluster_id is not None):
        if len(pool) >= pool_size:
            break
        cluster_members = [c for c in all_clients if c.cluster_id == cluster_id]
        if cluster_members:
            best_in_cluster = max(cluster_members, key=lambda c: c.revenue)
            add_client(best_in_cluster)
            
    return pool[:pool_size]
