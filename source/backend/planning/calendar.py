import datetime

GIORNI_IT = {
    0: "Lunedì", 1: "Martedì", 2: "Mercoledì", 3: "Giovedì",
    4: "Venerdì", 5: "Sabato", 6: "Domenica",
}

FIXED_ITALIAN_HOLIDAYS = {
    (1, 1), (1, 6), (4, 25), (5, 1), (6, 2), (8, 15),
    (10, 4), (11, 1), (12, 8), (12, 25), (12, 26)
}

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
    holidays = {datetime.date(year, month, day) for month, day in FIXED_ITALIAN_HOLIDAYS}
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
    # Pre-festivo se il giorno dopo, o il secondo giorno dopo, non è lavorativo (fino a coprire i venerdì)
    next_day = day + datetime.timedelta(days=1)
    if not is_business_day(next_day):
        weight += 0.3
    # Fine estate
    if (day.month == 8 and day.day >= 20) or (day.month == 9 and day.day <= 15):
        weight += 0.3
    return weight
