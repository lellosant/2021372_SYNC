import sys
import os
import datetime

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from planning.models import Client, WorkdayConfig, LunchConfig, PlanningDay
from planning.trasferte import evaluate_transfer


def test_local_clients_under_120min_rejected_as_multi_day():
    # 4 clients in Rome (travel from depot = 20 min <= 120 min)
    # Each client needs 210 minutes (3.5 hours) -> 4 * 210 = 840 min (exceeds 1 workday = 540 min)
    workday = WorkdayConfig(start=9 * 60, end=18 * 60)
    lunch = LunchConfig(earliest=12 * 60, latest_start=14 * 60, duration=60)
    day = PlanningDay(date_val=datetime.date(2026, 9, 29), day_index=0)

    clients = [
        Client(id=f"c{i}", name=f"Client {i}", latitude=41.9, longitude=12.5, revenue=1000.0,
               service_minutes=210, cluster_id=1, source_index=i, group="WINES", city="ROMA", address="Via Roma")
        for i in range(4)
    ]

    # Travel matrix: 0 is depot. Depot to each client = 20 min. Travel between clients = 15 min.
    n = len(clients) + 1
    matrix = [[20.0 if (i == 0 or j == 0) and i != j else (15.0 if i != j else 0.0) for j in range(n)] for i in range(n)]

    # Attempt evaluate_transfer for all 4 clients with max_giorni_trasferta=3
    route = evaluate_transfer(
        client_indices=[0, 1, 2, 3],
        clients=clients,
        travel_matrix=matrix,
        day=day,
        workday=workday,
        lunch=lunch,
        work_end_grace_minutes=15,
        max_giorni_trasferta=3,
        min_trasferta_minutes=120
    )

    # Since all clients are <= 120 min from depot, this CANNOT be a multi-day transfer!
    # evaluate_transfer must return feasible=False, forcing separate 1-day local routes.
    assert not route.feasible, "I clienti entro 120 min dalla sede non devono essere pianificati come trasferta multi-giorno (+1gg)!"
    print("Test passed: i clienti locali entro 120 min non vengono pianificati come trasferta multi-giorno.")


def test_remote_clients_over_120min_accepted_as_multi_day():
    # Clients in Milan (travel from Rome depot = 240 min > 120 min)
    workday = WorkdayConfig(start=9 * 60, end=18 * 60)
    lunch = LunchConfig(earliest=12 * 60, latest_start=14 * 60, duration=60)
    day = PlanningDay(date_val=datetime.date(2026, 9, 29), day_index=0)

    clients = [
        Client(id="c0", name="Milano 1", latitude=45.46, longitude=9.19, revenue=5000.0,
               service_minutes=180, cluster_id=2, source_index=0, group="WINES", city="MILANO", address="Via Milano 1"),
        Client(id="c1", name="Milano 2", latitude=45.47, longitude=9.20, revenue=6000.0,
               service_minutes=180, cluster_id=2, source_index=1, group="WINES", city="MILANO", address="Via Milano 2"),
    ]

    # Travel matrix: depot to Milano = 240 min (> 120 min). Between clients = 20 min.
    matrix = [
        [0.0, 240.0, 240.0],
        [240.0, 0.0, 20.0],
        [240.0, 20.0, 0.0]
    ]

    route = evaluate_transfer(
        client_indices=[0, 1],
        clients=clients,
        travel_matrix=matrix,
        day=day,
        workday=workday,
        lunch=lunch,
        work_end_grace_minutes=15,
        max_giorni_trasferta=3,
        min_trasferta_minutes=120
    )

    # Since Milano travel > 120 min, it is a valid multi-day transfer!
    assert route.feasible, "I clienti con viaggio > 120 min devono essere pianificati come trasferta!"
    assert route.spans_days >= 2, "La trasferta a Milano deve durare almeno 2 giorni"
    assert any(v.day_offset > 0 for v in route.visits), "Le visite del secondo giorno devono avere day_offset > 0"
    print("Test passed: i clienti remoti (> 120 min) vengono correttamente pianificati in trasferta con day_offset.")


if __name__ == "__main__":
    test_local_clients_under_120min_rejected_as_multi_day()
    test_remote_clients_over_120min_accepted_as_multi_day()
    print("Tutti i test delle trasferte sono passati!")
