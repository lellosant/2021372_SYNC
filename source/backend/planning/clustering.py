import math
from typing import List
import sklearn.cluster

from .config import PLANNING_RANDOM_SEED
from .models import Client, Location

def cluster_clients(clients: List[Client], depot: Location, num_days: int) -> None:
    if len(clients) <= 1:
        for c in clients:
            c.cluster_id = 0
        return
        
    cluster_count = min(num_days, max(1, math.ceil(len(clients) / 20)))
    
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
