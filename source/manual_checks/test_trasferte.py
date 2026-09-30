import sys
import os
import datetime

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from planning.models import Client, WorkdayConfig, LunchConfig, PlanningDay
from planning.trasferte import evaluate_transfer, is_trasferta_trip


def test_local_clients_rejected_as_multi_day():
    """
    Clienti locali (Roma):
    t1 = 20 min, t2 = 210 min, t3 = 20 min -> t1 + t2 + t3 = 250 min <= tempo agente (540 min).
    Poiché nessun cliente soddisfa la condizione t1 + t2 + t3 > tempo a disposizione,
    non è giustificata una trasferta multi-giorno (+1gg hotel).
    """
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
        max_giorni_trasferta=3
    )

    # I clienti locali (t1 + t2 + t3 <= available_time) non devono essere pianificati come trasferta multi-giorno
    assert not route.feasible, "I clienti entro il tempo a disposizione non devono essere pianificati come trasferta multi-giorno (+1gg)!"
    print("Test passed: i clienti locali (t1+t2+t3 <= tempo agente) non vengono pianificati come trasferta multi-giorno.")


def test_remote_clients_accepted_as_multi_day():
    """
    Clienti remoti (Milano):
    t1 = 240 min, t2 = 180 min, t3 = 240 min -> t1 + t2 + t3 = 660 min > tempo agente (540 min).
    Condizione soddisfatta: è un viaggio di trasferta.
    """
    workday = WorkdayConfig(start=9 * 60, end=18 * 60)
    lunch = LunchConfig(earliest=12 * 60, latest_start=14 * 60, duration=60)
    day = PlanningDay(date_val=datetime.date(2026, 9, 29), day_index=0)

    clients = [
        Client(id="c0", name="Milano 1", latitude=45.46, longitude=9.19, revenue=5000.0,
               service_minutes=180, cluster_id=2, source_index=0, group="WINES", city="MILANO", address="Via Milano 1"),
        Client(id="c1", name="Milano 2", latitude=45.47, longitude=9.20, revenue=6000.0,
               service_minutes=180, cluster_id=2, source_index=1, group="WINES", city="MILANO", address="Via Milano 2"),
    ]

    # Travel matrix: depot to Milano = 240 min. Between clients = 20 min.
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
        max_giorni_trasferta=3
    )

    # Poiché t1 + t2 + t3 > tempo a disposizione, è una valida trasferta multi-giorno
    assert route.feasible, "I clienti con t1 + t2 + t3 > tempo a disposizione devono essere pianificati come trasferta!"
    assert route.spans_days >= 2, "La trasferta a Milano deve durare almeno 2 giorni"
    assert any(v.day_offset > 0 for v in route.visits), "Le visite del secondo giorno devono avere day_offset > 0"
    print("Test passed: i clienti remoti (t1+t2+t3 > tempo agente) vengono correttamente pianificati in trasferta con day_offset.")


def test_parametric_trip_boundary_condition():
    """
    Verifica puntuale della formula parametrica:
    t1 + t2 + t3 > available_time
    """
    available_time = 540  # 9 ore (dalle 09:00 alle 18:00)

    # Caso 1: t1=100, t2=240, t3=100 -> somma = 440 <= 540 -> NON è un viaggio/trasferta
    assert not is_trasferta_trip(t1=100, t2=240, t3=100, available_time=available_time)

    # Caso 2: t1=160, t2=240, t3=160 -> somma = 560 > 540 -> È un viaggio/trasferta
    assert is_trasferta_trip(t1=160, t2=240, t3=160, available_time=available_time)

    # Caso 3: viaggio breve ma visita molto lunga: t1=60, t2=450, t3=60 -> somma = 570 > 540 -> È un viaggio/trasferta
    assert is_trasferta_trip(t1=60, t2=450, t3=60, available_time=available_time)

    print("Test passed: la verifica algebrica parametrica (t1 + t2 + t3 > tempo agente) è corretta.")


if __name__ == "__main__":
    test_local_clients_rejected_as_multi_day()
    test_remote_clients_accepted_as_multi_day()
    test_parametric_trip_boundary_condition()
    print("Tutti i test delle trasferte sono passati!")
