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


# OSRM usa la rete stradale OpenStreetMap.
OSRM_BASE_URL = os.getenv(
    "OSRM_BASE_URL",
    "https://router.project-osrm.org"
).rstrip("/")

OSRM_TIMEOUT_SECONDS = float(
    os.getenv(
        "OSRM_TIMEOUT_SECONDS",
        "8"
    )
)

MAX_ROUTING_CANDIDATES = int(
    os.getenv(
        "MAX_ROUTING_CANDIDATES",
        "100"
    )
)

AVERAGE_FALLBACK_SPEED_KMH = float(
    os.getenv(
        "AVERAGE_FALLBACK_SPEED_KMH",
        "35"
    )
)


_matrix_cache = {}
_matrix_cache_lock = threading.Lock()


def format_time(minutes):

    hours = int(minutes // 60)
    minutes = int(minutes % 60)

    return f"{hours:02d}:{minutes:02d}"


def _parse_time_env(
    env_var,
    default_minutes
):

    value = os.getenv(env_var)

    if not value:
        return default_minutes

    try:

        hours, minutes = map(
            int,
            value.strip('"\'').split(':')
        )

        return hours * 60 + minutes

    except ValueError:

        return default_minutes


WORK_START_MIN = _parse_time_env(
    "WORK_START",
    9 * 60
)

WORK_END_MIN = _parse_time_env(
    "WORK_END",
    18 * 60
)

LUNCH_START_MIN = _parse_time_env(
    "LUNCH_START",
    13 * 60
)

LUNCH_END_MIN = _parse_time_env(
    "LUNCH_END",
    14 * 60
)


def _haversine_minutes(a, b):
    """
    Fallback rapido quando OSRM non è disponibile.
    """

    lat1, lon1 = a
    lat2, lon2 = b

    radius_km = 6371.0

    p1 = math.radians(lat1)
    p2 = math.radians(lat2)

    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)

    h = (
        math.sin(d_lat / 2) ** 2
        +
        math.cos(p1)
        * math.cos(p2)
        * math.sin(d_lon / 2) ** 2
    )

    straight_km = (
        2
        * radius_km
        * math.asin(
            min(
                1.0,
                math.sqrt(h)
            )
        )
    )

    # Approssimazione della distanza stradale
    road_km = straight_km * 1.25

    return (
        road_km
        / AVERAGE_FALLBACK_SPEED_KMH
    ) * 60


def _fallback_matrix(coords):

    return [
        [
            (
                0.0
                if i == j
                else _haversine_minutes(
                    origin,
                    destination
                )
            )

            for j, destination
            in enumerate(coords)
        ]

        for i, origin
        in enumerate(coords)
    ]


def _routing_matrix(coords):
    """
    Restituisce una matrice dei minuti di guida.
    Utilizza OSRM e, in caso di errore,
    la distanza geografica approssimata.
    """

    if not coords:
        return []

    rounded = tuple(
        (
            round(lat, 5),
            round(lon, 5)
        )
        for lat, lon in coords
    )

    with _matrix_cache_lock:

        cached = _matrix_cache.get(
            rounded
        )

    if cached is not None:
        return cached

    coordinate_string = ";".join(
        f"{lon},{lat}"
        for lat, lon in rounded
    )

    query = urllib.parse.urlencode({
        "annotations": "duration"
    })

    url = (
        f"{OSRM_BASE_URL}"
        f"/table/v1/driving/"
        f"{coordinate_string}"
        f"?{query}"
    )

    try:

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent":
                    "visits-optimizer/1.0"
            }
        )

        with urllib.request.urlopen(
            request,
            timeout=OSRM_TIMEOUT_SECONDS
        ) as response:

            payload = json.load(response)

        durations = payload.get(
            "durations"
        )

        if (
            payload.get("code") != "Ok"
            or not durations
        ):
            raise ValueError(
                payload.get(
                    "message",
                    "OSRM matrix unavailable"
                )
            )

        matrix = [
            [
                (
                    math.inf
                    if seconds is None
                    else float(seconds) / 60
                )

                for seconds in row
            ]

            for row in durations
        ]

    except (
        OSError,
        ValueError,
        KeyError,
        json.JSONDecodeError
    ):

        matrix = _fallback_matrix(
            coords
        )

    with _matrix_cache_lock:

        if len(_matrix_cache) >= 16:
            _matrix_cache.pop(
                next(
                    iter(_matrix_cache)
                )
            )

        _matrix_cache[rounded] = matrix

    return matrix


def _advance_past_lunch(
    start_minute,
    duration_minute
):

    if (
        start_minute < LUNCH_START_MIN
        and
        start_minute + duration_minute
        > LUNCH_START_MIN
    ):

        return LUNCH_END_MIN

    if (
        LUNCH_START_MIN
        <= start_minute
        < LUNCH_END_MIN
    ):

        return LUNCH_END_MIN

    return start_minute


def _next_business_day(day):

    while day.weekday() > 4:

        day += datetime.timedelta(
            days=1
        )

    return day


def optimize_visits(
    df,
    days,
    hours_per_visit,
    work_hours_per_day,
    companies_filter
):
    """
    Crea un piano euristico che cerca di massimizzare
    il fatturato delle AZIENDE SELEZIONATE,
    considerando anche il tempo di viaggio.

    Il problema è una variante dell'orienteering:
    viene utilizzata una strategia euristica greedy
    invece di un algoritmo esatto.
    """

    if (
        days <= 0
        or hours_per_visit <= 0
        or work_hours_per_day <= 0
    ):

        return pd.DataFrame()

    # ---------------------------------------------------------
    # 1. Identificazione delle aziende selezionate
    # ---------------------------------------------------------

    if companies_filter:

        valid_companies = [
            column
            for column in companies_filter
            if column in df.columns
        ]

        if not valid_companies:
            return pd.DataFrame()

    else:

        return pd.DataFrame()

    # ---------------------------------------------------------
    # 2. Calcolo del fatturato rilevante per lo scenario
    # ---------------------------------------------------------

    df_filtered = df.copy()

    df_filtered["SelectedRevenue"] = (
        df_filtered[valid_companies]
        .sum(axis=1)
    )

    df_filtered = df_filtered[
        df_filtered["SelectedRevenue"] > 0
    ].copy()

    # ---------------------------------------------------------
    # 3. Controllo delle colonne necessarie
    # ---------------------------------------------------------

    required = {
        "SelectedRevenue",
        "Lat",
        "Lon"
    }

    if (
        df_filtered.empty
        or not required.issubset(
            df_filtered.columns
        )
    ):

        return pd.DataFrame()

    # ---------------------------------------------------------
    # 4. Pulizia dei dati
    # ---------------------------------------------------------

    df_filtered["SelectedRevenue"] = (
        pd.to_numeric(
            df_filtered["SelectedRevenue"],
            errors="coerce"
        )
        .fillna(0)
    )

    df_filtered["Lat"] = (
        pd.to_numeric(
            df_filtered["Lat"],
            errors="coerce"
        )
    )

    df_filtered["Lon"] = (
        pd.to_numeric(
            df_filtered["Lon"],
            errors="coerce"
        )
    )

    df_filtered = (
        df_filtered
        .dropna(
            subset=[
                "Lat",
                "Lon"
            ]
        )
    )

    df_filtered = (
        df_filtered[
            df_filtered[
                "SelectedRevenue"
            ] > 0
        ]
        .sort_values(
            "SelectedRevenue",
            ascending=False
        )
    )

    if df_filtered.empty:
        return pd.DataFrame()

    # ---------------------------------------------------------
    # 5. Numero massimo teorico di visite
    # ---------------------------------------------------------

    max_visits = (
        days
        *
        max(
            1,
            int(
                work_hours_per_day
                // hours_per_visit
            )
        )
    )

    candidate_count = min(
        len(df_filtered),
        MAX_ROUTING_CANDIDATES,
        max(
            max_visits * 2,
            max_visits
        )
    )

    # Shortlist dei clienti economicamente più rilevanti
    candidates = (
        df_filtered
        .head(candidate_count)
        .reset_index(drop=True)
    )

    # ---------------------------------------------------------
    # 6. Matrice dei tempi di viaggio
    # ---------------------------------------------------------

    coords = list(
        zip(
            candidates["Lat"].astype(float),
            candidates["Lon"].astype(float)
        )
    )

    travel_matrix = _routing_matrix(
        coords
    )

    visit_minutes = int(
        round(
            hours_per_visit * 60
        )
    )

    day_start = WORK_START_MIN
    day_end = WORK_END_MIN

    # ---------------------------------------------------------
    # 7. Costruzione del calendario
    # ---------------------------------------------------------

    schedule = []

    remaining = set(
        range(
            len(candidates)
        )
    )

    current_date = _next_business_day(
        datetime.date.today()
    )

    for _ in range(days):

        if not remaining:
            break

        current_minute = day_start
        previous = None

        while remaining:

            feasible = []

            for index in remaining:

                if previous is None:

                    travel = 0

                else:

                    travel = (
                        travel_matrix[
                            previous
                        ][index]
                    )

                if not math.isfinite(
                    travel
                ):
                    continue

                arrival = (
                    current_minute
                    +
                    int(
                        math.ceil(
                            travel
                        )
                    )
                )

                visit_start = (
                    _advance_past_lunch(
                        arrival,
                        visit_minutes
                    )
                )

                visit_end = (
                    visit_start
                    +
                    visit_minutes
                )

                if visit_end <= day_end:

                    revenue = float(
                        candidates.at[
                            index,
                            "SelectedRevenue"
                        ]
                    )

                    # Rapporto tra valore commerciale
                    # e tempo richiesto
                    score = (
                        revenue
                        /
                        max(
                            1,
                            visit_minutes + travel
                        )
                    )

                    feasible.append(
                        (
                            score,
                            revenue,
                            -travel,
                            index,
                            arrival,
                            visit_start,
                            visit_end
                        )
                    )

            if not feasible:
                break

            (
                _,
                revenue,
                neg_travel,
                index,
                arrival,
                visit_start,
                visit_end
            ) = max(feasible)

            travel_minutes = int(
                math.ceil(
                    -neg_travel
                )
            )

            row = candidates.iloc[
                index
            ]

            schedule.append({

                "Data Visita":
                    current_date.strftime(
                        "%d/%m/%Y"
                    ),

                "Giorno":
                    GIORNI_IT[
                        current_date.weekday()
                    ],

                "Orario":
                    (
                        f"{format_time(visit_start)}"
                        f" - "
                        f"{format_time(visit_end)}"
                    ),

                "Cliente":
                    row.get(
                        "Cliente",
                        row.get(
                            "Ragione Sociale",
                            "Sconosciuto"
                        )
                    ),

                "Città":
                    row.get(
                        "Citta",
                        ""
                    ),

                "Fatturato Stimato":
                    revenue,

                "Tempo Spostamento (min)":
                    travel_minutes,

                "Lat":
                    float(
                        row["Lat"]
                    ),

                "Lon":
                    float(
                        row["Lon"]
                    ),
            })

            remaining.remove(
                index
            )

            previous = index

            current_minute = (
                visit_end
            )

        current_date = (
            _next_business_day(
                current_date
                +
                datetime.timedelta(
                    days=1
                )
            )
        )

    return pd.DataFrame(
        schedule
    )