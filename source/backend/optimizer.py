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


# ---------------------------------------------------------
# Routing
# ---------------------------------------------------------

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


# ---------------------------------------------------------
# Orario di lavoro e pausa pranzo flessibile
# ---------------------------------------------------------

WORK_START_MIN = _parse_time_env(
    "WORK_START",
    9 * 60
)

WORK_END_MIN = _parse_time_env(
    "WORK_END",
    18 * 60
)

# La pausa non è più fissata rigidamente 13:00-14:00.
# Può essere collocata in modo flessibile nella finestra indicata.
LUNCH_EARLIEST_MIN = _parse_time_env(
    "LUNCH_EARLIEST",
    12 * 60
)

LUNCH_LATEST_START_MIN = _parse_time_env(
    "LUNCH_LATEST_START",
    14 * 60
)

LUNCH_DURATION_MIN = int(
    os.getenv(
        "LUNCH_DURATION_MINUTES",
        "60"
    )
)


# ---------------------------------------------------------
# Calendario lavorativo italiano
# ---------------------------------------------------------

FIXED_ITALIAN_HOLIDAYS = {
    (1, 1),    # Capodanno
    (1, 6),    # Epifania
    (4, 25),   # Festa della Liberazione
    (5, 1),    # Festa dei Lavoratori
    (6, 2),    # Festa della Repubblica
    (8, 15),   # Ferragosto
    (11, 1),   # Ognissanti
    (12, 8),   # Immacolata Concezione
    (12, 25),  # Natale
    (12, 26),  # Santo Stefano
}


def _easter_sunday(year):
    """
    Calcola la data della Pasqua gregoriana
    con l'algoritmo di Meeus/Jones/Butcher.
    """

    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451

    month = (
        h + l - 7 * m + 114
    ) // 31

    day = (
        (h + l - 7 * m + 114) % 31
    ) + 1

    return datetime.date(
        year,
        month,
        day
    )


def _italian_holidays_for_year(year):
    holidays = {
        datetime.date(
            year,
            month,
            day
        )
        for month, day
        in FIXED_ITALIAN_HOLIDAYS
    }

    # Pasquetta (lunedì dell'Angelo)
    holidays.add(
        _easter_sunday(year)
        + datetime.timedelta(days=1)
    )

    return holidays


def _is_business_day(day):
    if day.weekday() > 4:
        return False

    return (
        day
        not in _italian_holidays_for_year(
            day.year
        )
    )


def _next_business_day(day):
    while not _is_business_day(day):
        day += datetime.timedelta(
            days=1
        )

    return day


# ---------------------------------------------------------
# Routing helpers
# ---------------------------------------------------------

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
            payload = json.load(
                response
            )

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

        _matrix_cache[
            rounded
        ] = matrix

    return matrix


# ---------------------------------------------------------
# Scheduling helper per pausa pranzo
# ---------------------------------------------------------

def _fit_visit_with_lunch(
    arrival,
    visit_minutes,
    lunch_taken
):
    """
    Determina quando può iniziare la visita.

    La pausa pranzo è flessibile:
    - se una visita può terminare entro l'orario massimo
      di inizio pausa, la visita può essere effettuata prima;
    - altrimenti la pausa viene inserita prima della visita.

    Restituisce:
    (visit_start, visit_end, lunch_before_visit)
    """

    if lunch_taken:
        visit_start = arrival
        return (
            visit_start,
            visit_start + visit_minutes,
            False
        )

    direct_end = (
        arrival
        +
        visit_minutes
    )

    # La visita può essere svolta prima di pranzo.
    # La pausa verrà eventualmente inserita subito dopo.
    if direct_end <= LUNCH_LATEST_START_MIN:
        return (
            arrival,
            direct_end,
            False
        )

    # Altrimenti facciamo prima la pausa.
    lunch_start = max(
        arrival,
        LUNCH_EARLIEST_MIN
    )

    visit_start = (
        lunch_start
        +
        LUNCH_DURATION_MIN
    )

    return (
        visit_start,
        visit_start + visit_minutes,
        True
    )


# ---------------------------------------------------------
# Ottimizzazione
# ---------------------------------------------------------

def optimize_visits(
    df,
    days,
    hours_per_visit,
    work_hours_per_day,
    companies_filter,
    start_date=None,
    start_address=None,
    start_lat=None,
    start_lon=None,
    **kwargs
):
    """
    Crea un piano euristico che cerca di massimizzare
    il fatturato delle aziende selezionate,
    considerando anche il tempo di viaggio.

    I "days" sono giorni LAVORATIVI:
    vengono automaticamente esclusi
    sabato, domenica e festività nazionali italiane.

    La pausa pranzo è flessibile e non forza più
    rigidamente gli slot 09-11 / 14-16.
    """

    if (
        days <= 0
        or hours_per_visit <= 0
        or work_hours_per_day <= 0
    ):
        return pd.DataFrame()

    # -----------------------------------------------------
    # 1. Aziende selezionate
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # 2. Fatturato dello scenario
    # -----------------------------------------------------

    df_filtered = df.copy()

    df_filtered[
        "SelectedRevenue"
    ] = (
        df_filtered[
            valid_companies
        ]
        .sum(axis=1)
    )

    df_filtered = df_filtered[
        df_filtered[
            "SelectedRevenue"
        ] > 0
    ].copy()

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

    # -----------------------------------------------------
    # 3. Pulizia dati
    # -----------------------------------------------------

    df_filtered[
        "SelectedRevenue"
    ] = (
        pd.to_numeric(
            df_filtered[
                "SelectedRevenue"
            ],
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

    # -----------------------------------------------------
    # 4. Shortlist candidati
    # -----------------------------------------------------

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

    candidates = (
        df_filtered
        .head(candidate_count)
        .reset_index(drop=True)
    )

    # -----------------------------------------------------
    # 5. Tempi stradali
    # -----------------------------------------------------

    coords = list(
        zip(
            candidates[
                "Lat"
            ].astype(float),
            candidates[
                "Lon"
            ].astype(float)
        )
    )

    travel_matrix = (
        _routing_matrix(
            coords
        )
    )

    visit_minutes = int(
        round(
            hours_per_visit
            * 60
        )
    )

    day_start = WORK_START_MIN
    day_end = WORK_END_MIN

    # -----------------------------------------------------
    # 6. Data iniziale
    # -----------------------------------------------------

    if start_date:
        if isinstance(
            start_date,
            str
        ):
            base_date = (
                datetime.datetime
                .strptime(
                    start_date,
                    "%Y-%m-%d"
                )
                .date()
            )
        else:
            base_date = start_date
    else:
        base_date = (
            datetime.date.today()
        )

    current_date = (
        _next_business_day(
            base_date
        )
    )

    # -----------------------------------------------------
    # 7. Costruzione calendario
    # -----------------------------------------------------

    schedule = []

    remaining = set(
        range(
            len(candidates)
        )
    )

    for _ in range(days):

        if not remaining:
            break

        # Sicurezza ulteriore:
        # ogni iterazione parte sempre da un giorno lavorativo.
        current_date = (
            _next_business_day(
                current_date
            )
        )

        current_minute = (
            day_start
        )

        previous = None
        lunch_taken = False

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

                (
                    visit_start,
                    visit_end,
                    lunch_before
                ) = _fit_visit_with_lunch(
                    arrival,
                    visit_minutes,
                    lunch_taken
                )

                if visit_end <= day_end:
                    revenue = float(
                        candidates.at[
                            index,
                            "SelectedRevenue"
                        ]
                    )

                    effective_minutes = (
                        visit_minutes
                        +
                        travel
                    )

                    # La pausa è obbligatoria per tutti:
                    # non la usiamo come penalizzazione economica.
                    score = (
                        revenue
                        /
                        max(
                            1,
                            effective_minutes
                        )
                    )

                    feasible.append(
                        (
                            score,
                            revenue,
                            -travel,
                            index,
                            visit_start,
                            visit_end,
                            lunch_before
                        )
                    )

            if not feasible:
                break

            (
                _,
                revenue,
                neg_travel,
                index,
                visit_start,
                visit_end,
                lunch_before
            ) = max(
                feasible
            )

            travel_minutes = int(
                math.ceil(
                    -neg_travel
                )
            )

            row = candidates.iloc[
                index
            ]

            main_comp = ""

            if companies_filter:
                max_val = -1

                for comp in companies_filter:
                    try:
                        val = float(
                            row.get(
                                comp,
                                0
                            )
                        )

                        if (
                            pd.notna(val)
                            and val > max_val
                        ):
                            max_val = val
                            main_comp = comp

                    except (
                        ValueError,
                        TypeError
                    ):
                        pass

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

                "Gruppo":
                    main_comp,

                "Città":
                    row.get(
                        "Citta",
                        ""
                    ),

                "Indirizzo":
                    row.get(
                        "Indirizzo",
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

            # Se la pausa è stata inserita prima della visita,
            # da questo momento risulta già effettuata.
            if lunch_before:
                lunch_taken = True
                current_minute = visit_end

            else:
                current_minute = visit_end

                # Se abbiamo terminato una visita nell'area pranzo
                # e la pausa non è stata ancora fatta,
                # la inseriamo immediatamente dopo.
                if (
                    not lunch_taken
                    and
                    visit_end
                    >= LUNCH_EARLIEST_MIN
                ):
                    current_minute = (
                        visit_end
                        +
                        LUNCH_DURATION_MIN
                    )

                    lunch_taken = True

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
