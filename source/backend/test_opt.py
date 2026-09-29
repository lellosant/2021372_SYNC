import datetime
import pandas as pd

import optimizer
from planning import calendar, routing


def zero_travel_matrix(coords):
    return [
        [0.0 for _ in coords]
        for _ in coords
    ]


# Evita dipendenze dalla rete nel test.
routing._routing_matrix = zero_travel_matrix
# For the planning package, I can just patch the build_travel_matrix
def _mock_build_travel_matrix(depot, clients):
    coords = [(depot.lat, depot.lon)] + [(c.latitude, c.longitude) for c in clients]
    return zero_travel_matrix(coords)
import planning.facade
planning.facade.build_travel_matrix = _mock_build_travel_matrix

def test_four_two_hour_visits_fit_in_one_day():
    df = pd.DataFrame({
        "Lat": [41.90, 41.91, 41.92, 41.93],
        "Lon": [12.50, 12.51, 12.52, 12.53],
        "WINES": [4000, 3000, 2000, 1000],
        "Cliente": ["A", "B", "C", "D"],
        "Citta": ["ROMA"] * 4,
        "Indirizzo": ["A", "B", "C", "D"]
    })

    result = optimizer.optimize_visits(
        df,
        days=1,
        hours_per_visit=2.0,
        work_hours_per_day=8.0,
        companies_filter=["WINES"],
        start_date="2026-09-28",
        start_lat=41.90, 
        start_lon=12.50
    )

    assert len(result) == 4
    assert result["Orario"].tolist() == [
        "09:00 - 11:00",
        "11:00 - 13:00",
        "14:00 - 16:00",
        "16:00 - 18:00",
    ]


def test_weekend_is_skipped():
    assert calendar._next_business_day(
        datetime.date(2026, 10, 3)  # sabato
    ) == datetime.date(2026, 10, 5)


def test_christmas_is_skipped():
    assert calendar._next_business_day(
        datetime.date(2026, 12, 25)
    ) == datetime.date(2026, 12, 28)


def test_easter_monday_is_skipped():
    # Pasqua 2027: 28 marzo -> Pasquetta 29 marzo.
    assert calendar._next_business_day(
        datetime.date(2027, 3, 29)
    ) == datetime.date(2027, 3, 30)


if __name__ == "__main__":
    test_four_two_hour_visits_fit_in_one_day()
    test_weekend_is_skipped()
    test_christmas_is_skipped()
    test_easter_monday_is_skipped()
    print("Tutti i test del planner sono passati.")
