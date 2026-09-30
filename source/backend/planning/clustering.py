import math
from typing import List
import sklearn.cluster

from .config import PLANNING_RANDOM_SEED
from .models import Client, Location

def cluster_clients(clients: List[Client], depot: Location, target_cluster_size: int = 20) -> None:
    """Group clients into spatial clusters using equirectangular km projection and K-Means."""
    if not clients:
        return
        
    cluster_count = max(1, min(len(clients), math.ceil(len(clients) / max(1, target_cluster_size))))
    
    if len(clients) <= 1 or cluster_count <= 1:
        for c in clients:
            c.cluster_id = 0
        return
    
    # Project (lon, lat) to local Cartesian km (x, y) relative to depot.
    # 1 deg latitude ~ 111 km; longitude is scaled by cos(latitude) to account for meridian convergence.
    coords = []
    depot_lat_rad = math.radians(depot.lat)
    for c in clients:
        x = (c.longitude - depot.lon) * 111 * math.cos(depot_lat_rad)
        y = (c.latitude - depot.lat) * 111
        coords.append([x, y])
        
    kmeans = sklearn.cluster.KMeans(n_clusters=cluster_count, n_init=10, random_state=PLANNING_RANDOM_SEED)
    labels = kmeans.fit_predict(coords)
    
    for c, label in zip(clients, labels):
        c.cluster_id = int(label)
