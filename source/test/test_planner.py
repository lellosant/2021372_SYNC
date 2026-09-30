import datetime
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from planning.feasibility import evaluate_day_route
from planning.models import Client, WorkdayConfig, LunchConfig, PlanningDay
from planning.calendar import _next_business_day
from planning.trasferte import is_trasferta_trip

def test_four_two_hour_visits_fit_in_one_day():
    """
    Business meaning: Checks that four 2-hour visits fit perfectly in an 8-hour workday,
    considering a 1-hour lunch break in the middle.
    """
    clients = [
        Client(id="1", name="C1", latitude=0.0, longitude=0.0, revenue=100.0, service_minutes=120, cluster_id=0, source_index=0, group="A", city="Rome", address="Via A"),
        Client(id="2", name="C2", latitude=0.0, longitude=0.0, revenue=100.0, service_minutes=120, cluster_id=0, source_index=1, group="A", city="Rome", address="Via B"),
        Client(id="3", name="C3", latitude=0.0, longitude=0.0, revenue=100.0, service_minutes=120, cluster_id=0, source_index=2, group="A", city="Rome", address="Via C"),
        Client(id="4", name="C4", latitude=0.0, longitude=0.0, revenue=100.0, service_minutes=120, cluster_id=0, source_index=3, group="A", city="Rome", address="Via D")
    ]
    
    # Zero travel time matrix
    travel_matrix = [[0.0] * 5 for _ in range(5)]
    
    workday = WorkdayConfig(start=540, end=1080) # 09:00 to 18:00
    lunch = LunchConfig(earliest=720, latest_start=840, duration=60) # 12:00 to 14:00, 60 mins
    day = PlanningDay(date_val=datetime.date(2026, 10, 5), day_index=0)
    
    route = evaluate_day_route(
        client_indices=[0, 1, 2, 3],
        clients=clients,
        travel_matrix=travel_matrix,
        day=day,
        workday=workday,
        lunch=lunch,
        work_end_grace_minutes=0
    )
    
    assert route.feasible is True
    assert len(route.client_indices) == 4

def test_weekend_is_skipped():
    """
    Business meaning: Checks that weekend dates are bypassed by the planner.
    Saturday 2026-10-03 becomes Monday 2026-10-05.
    """
    sat = datetime.date(2026, 10, 3)
    next_day = _next_business_day(sat)
    assert next_day == datetime.date(2026, 10, 5)

def test_christmas_is_skipped():
    """
    Business meaning: Checks that national holidays (Christmas) are bypassed.
    2026-12-25 becomes 2026-12-28.
    """
    christmas = datetime.date(2026, 12, 25)
    next_day = _next_business_day(christmas)
    assert next_day == datetime.date(2026, 12, 28)

def test_easter_monday_is_skipped():
    """
    Business meaning: Checks that variable holidays like Easter Monday are skipped.
    2027-03-29 becomes 2027-03-30.
    """
    easter_monday = datetime.date(2027, 3, 29)
    next_day = _next_business_day(easter_monday)
    assert next_day == datetime.date(2027, 3, 30)

def test_local_trip_is_not_a_transfer():
    """
    Business meaning: Checks that normal local travel (short outbound, local visits, short return) 
    is not incorrectly classified as a multi-day transfer trip.
    """
    is_trasferta = is_trasferta_trip(t1=20, t2=210, t3=20, available_time=540)
    assert is_trasferta is False

def test_remote_trip_is_a_transfer():
    """
    Business meaning: Checks that travelling for many hours to a distant region 
    and staying there for visits triggers the transfer (trasferta) logic.
    """
    is_trasferta = is_trasferta_trip(t1=240, t2=180, t3=240, available_time=540)
    assert is_trasferta is True
