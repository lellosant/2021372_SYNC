import datetime

GIORNI_IT = {
    0: "Lunedì", 1: "Martedì", 2: "Mercoledì", 3: "Giovedì",
    4: "Venerdì", 5: "Sabato", 6: "Domenica",
}

import os

DEFAULT_FIXED_HOLIDAYS = {
    (1, 1), (1, 6), (4, 25), (5, 1), (6, 2), (8, 15),
    (10, 4), (11, 1), (12, 8), (12, 25), (12, 26)
}

_cached_holidays = None
_last_mtime = None

def _resolve_config_path() -> str | None:
    env_path = os.getenv("FESTE_CONFIG_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path
    
    candidates = [
        "/feste.config",
        "/app/feste.config",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "feste.config")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "feste.config")),
        os.path.abspath("feste.config"),
        os.path.abspath("source/feste.config"),
    ]

    for p in candidates:
        if os.path.isfile(p):
            return p
    return None

def load_fixed_holidays(config_path: str = None) -> set[tuple[int, int]]:
    """
    Carica i giorni festivi fissi da feste.config (formato GG/MM).
    Rileva automaticamente le modifiche al file (hot-reload).
    """
    global _cached_holidays, _last_mtime
    path = config_path or _resolve_config_path()
    if not path or not os.path.isfile(path):
        return set(DEFAULT_FIXED_HOLIDAYS)
    
    try:
        mtime = os.path.getmtime(path)
        if _cached_holidays is not None and _last_mtime == mtime and config_path is None:
            return _cached_holidays
        
        holidays = set()
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.split("#")[0].strip()
                if not line:
                    continue
                for sep in ["/", "-", ",", " "]:
                    if sep in line:
                        parts = [p.strip() for p in line.split(sep) if p.strip()]
                        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                            val1, val2 = int(parts[0]), int(parts[1])
                            # Formato GG/MM: val1 = giorno, val2 = mese
                            if val1 > 12:
                                holidays.add((val2, val1))
                            elif val2 > 12:
                                holidays.add((val1, val2))
                            else:
                                holidays.add((val2, val1))
                            break
        if holidays:
            _cached_holidays = holidays
            _last_mtime = mtime
            return holidays
    except Exception:
        pass
    return set(DEFAULT_FIXED_HOLIDAYS)


def _easter_sunday(year):
    a = year % 19; b = year // 100; c = year % 100
    d = b // 4; e = b % 4; f = (b + 8) // 25
    g = (b - f + 1) // 3; h = (19 * a + b - d - g + 15) % 30
    i = c // 4; k = c % 4; l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return datetime.date(year, month, day)

def _italian_holidays_for_year(year):
    fixed = load_fixed_holidays()
    holidays = {datetime.date(year, month, day) for month, day in fixed}
    holidays.add(_easter_sunday(year) + datetime.timedelta(days=1))
    return holidays


def is_business_day(day: datetime.date) -> bool:
    if day.weekday() > 4:
        return False
    return day not in _italian_holidays_for_year(day.year)

def build_business_days(start_date: datetime.date, count: int) -> list[datetime.date]:
    days = []
    current_date = start_date
    while len(days) < count:
        if is_business_day(current_date):
            days.append(current_date)
        current_date += datetime.timedelta(days=1)
    return days

def _next_business_day(day: datetime.date) -> datetime.date:
    while not is_business_day(day):
        day += datetime.timedelta(days=1)
    return day


def get_day_weight(day) -> float:
    import datetime
    weight = 1.0
    
    # Calcola i giorni di distanza dal prossimo giorno non lavorativo (festa o weekend)
    distance = 1
    while is_business_day(day + datetime.timedelta(days=distance)):
        distance += 1
        # Fallback di sicurezza
        if distance > 7:
            break
            
    # Incremento progressivo: più è vicino, più il peso aumenta
    # distance=1 (vigilia) -> +0.4
    # distance=2 -> +0.3
    # distance=3 -> +0.2
    # distance=4 -> +0.1
    # distance>=5 -> nessuna aggiunta per il fine settimana
    if distance < 5:
        weight += 0.5 - (0.1 * distance)
        
    # Fine estate (parametrico con valori di default in caso di errore)
    try:
        from backend.planning.config import (
            SUMMER_END_START_MONTH, SUMMER_END_START_DAY,
            SUMMER_END_END_MONTH, SUMMER_END_END_DAY
        )
        
        # Protezione addizionale nel caso in cui i valori letti siano None
        s_month = SUMMER_END_START_MONTH if SUMMER_END_START_MONTH is not None else 8
        s_day = SUMMER_END_START_DAY if SUMMER_END_START_DAY is not None else 20
        e_month = SUMMER_END_END_MONTH if SUMMER_END_END_MONTH is not None else 9
        e_day = SUMMER_END_END_DAY if SUMMER_END_END_DAY is not None else 15
    except ImportError:
        s_month, s_day = 8, 20
        e_month, e_day = 9, 15
    
    current_md = day.month * 100 + day.day
    start_md = s_month * 100 + s_day
    end_md = e_month * 100 + e_day
    
    if start_md <= end_md:
        if start_md <= current_md <= end_md:
            weight += 0.3
    else:
        # A cavallo di capodanno
        if current_md >= start_md or current_md <= end_md:
            weight += 0.3

    return round(weight, 2)
