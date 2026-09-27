import datetime
import json
import math
import os
import threading
import urllib.parse
import urllib.request

import pandas as pd


GIORNI_IT = {
    0: "Lunedì",
    1: "Martedì",
    2: "Mercoledì",
    3: "Giovedì",
    4: "Venerdì",
    5: "Sabato",
    6: "Domenica",
}

# OSRM usa la rete stradale OpenStreetMap. In produzione è preferibile impostare
# OSRM_BASE_URL a un'istanza dedicata, per non dipendere dal server dimostrativo.
OSRM_BASE_URL = os.getenv("OSRM_BASE_URL", "https://router.project-osrm.org").rstrip("/")
OSRM_TIMEOUT_SECONDS = float(os.getenv("OSRM_TIMEOUT_SECONDS", "8"))
MAX_ROUTING_CANDIDATES = int(os.getenv("MAX_ROUTING_CANDIDATES", "100"))
AVERAGE_FALLBACK_SPEED_KMH = float(os.getenv("AVERAGE_FALLBACK_SPEED_KMH", "35"))

_matrix_cache = {}
_matrix_cache_lock = threading.Lock()


def format_time(minutes):
    h = int(minutes // 60)
    m = int(minutes % 60)
    return f"{h:02d}:{m:02d}"


def _parse_time_env(env_var, default_minutes):
    val = os.getenv(env_var)
    if not val:
        return default_minutes
    try:
        h, m = map(int, val.strip('"\'').split(':'))
        return h * 60 + m
    except ValueError:
        return default_minutes


WORK_START_MIN = _parse_time_env("WORK_START", 9 * 60)
WORK_END_MIN = _parse_time_env("WORK_END", 18 * 60)
LUNCH_START_MIN = _parse_time_env("LUNCH_START", 13 * 60)
LUNCH_END_MIN = _parse_time_env("LUNCH_END", 14 * 60)


def _haversine_minutes(a, b):
    """Fallback rapido quando OSRM non è disponibile."""
    lat1, lon1 = a
    lat2, lon2 = b
    radius_km = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    h = math.sin(d_lat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d_lon / 2) ** 2
    straight_km = 2 * radius_km * math.asin(min(1.0, math.sqrt(h)))
    # Il fattore 1,25 approssima la differenza tra distanza in linea d'aria e stradale.
    return (straight_km * 1.25 / AVERAGE_FALLBACK_SPEED_KMH) * 60


def _fallback_matrix(coords):
    return [
        [0.0 if i == j else _haversine_minutes(origin, destination) for j, destination in enumerate(coords)]
        for i, origin in enumerate(coords)
    ]


def _routing_matrix(coords):
    """Restituisce una matrice di minuti di guida, con cache tra what-if analysis."""
    if not coords:
        return []

    rounded = tuple((round(lat, 5), round(lon, 5)) for lat, lon in coords)
    with _matrix_cache_lock:
        cached = _matrix_cache.get(rounded)
    if cached is not None:
        return cached

    coordinate_string = ";".join(f"{lon},{lat}" for lat, lon in rounded)
    query = urllib.parse.urlencode({"annotations": "duration"})
    url = f"{OSRM_BASE_URL}/table/v1/driving/{coordinate_string}?{query}"

    try:
        request = urllib.request.Request(url, headers={"User-Agent": "visits-optimizer/1.0"})
        with urllib.request.urlopen(request, timeout=OSRM_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
        durations = payload.get("durations")
        if payload.get("code") != "Ok" or not durations:
            raise ValueError(payload.get("message", "matrice OSRM non disponibile"))
        matrix = [
            [math.inf if seconds is None else float(seconds) / 60 for seconds in row]
            for row in durations
        ]
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        matrix = _fallback_matrix(coords)

    with _matrix_cache_lock:
        # Limite semplice per processi backend longevi e ripetuti upload.
        if len(_matrix_cache) >= 16:
            _matrix_cache.pop(next(iter(_matrix_cache)))
        _matrix_cache[rounded] = matrix
    return matrix


def _advance_past_lunch(start_minute, duration_minute):
    if start_minute < LUNCH_START_MIN and start_minute + duration_minute > LUNCH_START_MIN:
        return LUNCH_END_MIN
    if LUNCH_START_MIN <= start_minute < LUNCH_END_MIN:
        return LUNCH_END_MIN
    return start_minute


def _next_business_day(day):
    while day.weekday() > 4:
        day += datetime.timedelta(days=1)
    return day


def optimize_visits(df, days, hours_per_visit, work_hours_per_day, companies_filter):
    """Crea un piano euristico che massimizza il fatturato rispettando i tempi stradali.

    Il problema è una variante dell'orienteering con finestre temporali (NP-hard): per
    mantenere fluida la dashboard si usa una shortlist per fatturato e una selezione
    greedy revenue/time sulla matrice OSRM, anziché un solver esatto su ~2.000 righe.
    """
    if days <= 0 or hours_per_visit <= 0 or work_hours_per_day <= 0:
        return pd.DataFrame()

    if companies_filter:
        valid_companies = [column for column in companies_filter if column in df.columns]
        if not valid_companies:
            return pd.DataFrame()
        df_filtered = df[df[valid_companies].sum(axis=1) > 0].copy()
    else:
        df_filtered = df.copy()

    required = {"Totale", "Lat", "Lon"}
    if df_filtered.empty or not required.issubset(df_filtered.columns):
        return pd.DataFrame()

    df_filtered["Totale"] = pd.to_numeric(df_filtered["Totale"], errors="coerce").fillna(0)
    df_filtered["Lat"] = pd.to_numeric(df_filtered["Lat"], errors="coerce")
    df_filtered["Lon"] = pd.to_numeric(df_filtered["Lon"], errors="coerce")
    df_filtered = df_filtered.dropna(subset=["Lat", "Lon"])
    df_filtered = df_filtered[df_filtered["Totale"] > 0].sort_values("Totale", ascending=False)
    if df_filtered.empty:
        return pd.DataFrame()

    # Nessuna soluzione può contenere più visite di quante ne entrino senza viaggi.
    max_visits = days * max(1, int(work_hours_per_day // hours_per_visit))
    candidate_count = min(len(df_filtered), MAX_ROUTING_CANDIDATES, max(max_visits * 2, max_visits))
    candidates = df_filtered.head(candidate_count).reset_index(drop=True)
    coords = list(zip(candidates["Lat"].astype(float), candidates["Lon"].astype(float)))
    travel_matrix = _routing_matrix(coords)

    visit_minutes = int(round(hours_per_visit * 60))
    day_start = WORK_START_MIN
    day_end = WORK_END_MIN

    schedule = []
    remaining = set(range(len(candidates)))
    current_date = _next_business_day(datetime.date.today())

    for _ in range(days):
        if not remaining:
            break
        current_minute = day_start
        previous = None

        while remaining:
            feasible = []
            for index in remaining:
                travel = 0 if previous is None else travel_matrix[previous][index]
                if not math.isfinite(travel):
                    continue
                arrival = current_minute + int(math.ceil(travel))
                visit_start = _advance_past_lunch(arrival, visit_minutes)
                visit_end = visit_start + visit_minutes
                if visit_end <= day_end:
                    revenue = float(candidates.at[index, "Totale"])
                    # Favorisce fatturato elevato, penalizzando solo il tempo marginale di viaggio.
                    score = revenue / max(1, visit_minutes + travel)
                    feasible.append((score, revenue, -travel, index, arrival, visit_start, visit_end))

            if not feasible:
                break

            _, revenue, neg_travel, index, arrival, visit_start, visit_end = max(feasible)
            travel_minutes = int(math.ceil(-neg_travel))
            row = candidates.iloc[index]
            schedule.append({
                "Data Visita": current_date.strftime("%d/%m/%Y"),
                "Giorno": GIORNI_IT[current_date.weekday()],
                "Orario": f"{format_time(visit_start)} - {format_time(visit_end)}",
                "Cliente": row.get("Cliente", row.get("Ragione Sociale", "Sconosciuto")),
                "Città": row.get("Citta", ""),
                "Fatturato Stimato": revenue,
                "Tempo Spostamento (min)": travel_minutes,
            })
            remaining.remove(index)
            previous = index
            current_minute = visit_end

        current_date = _next_business_day(current_date + datetime.timedelta(days=1))

    return pd.DataFrame(schedule)
