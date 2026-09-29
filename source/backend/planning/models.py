from dataclasses import dataclass
from typing import List, Optional, Set
from datetime import date

@dataclass
class Location:
    lat: float
    lon: float

@dataclass
class Client:
    id: str
    name: str
    latitude: float
    longitude: float
    revenue: float
    service_minutes: int
    cluster_id: Optional[int]
    source_index: int
    group: str
    city: str
    address: str

@dataclass
class LunchConfig:
    earliest: int
    latest_start: int
    duration: int

@dataclass
class WorkdayConfig:
    start: int
    end: int

@dataclass
class PlanningDay:
    date_val: date
    day_index: int
    weight: float = 1.0

@dataclass
class VisitSchedule:
    client_id: str
    arrival_minute: int
    visit_start: int
    visit_end: int
    lunch_before: bool
    travel_from_prev: int

@dataclass
class DayRoute:
    day: PlanningDay
    client_ids: List[str]
    client_indices: List[int]
    feasible: bool
    revenue: float
    travel_minutes: int
    return_minute: int
    visits: List[VisitSchedule]

@dataclass
class PlanningSolution:
    day_routes: List[DayRoute]
    total_revenue: float
    total_travel_minutes: float
    scheduled_client_ids: Set[str]

    @property
    def weighted_revenue(self) -> float:
        return sum(r.revenue * r.day.weight for r in self.day_routes)
