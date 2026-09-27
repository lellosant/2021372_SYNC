import pandas as pd
import datetime

GIORNI_IT = {
    0: 'Lunedì',
    1: 'Martedì',
    2: 'Mercoledì',
    3: 'Giovedì',
    4: 'Venerdì',
    5: 'Sabato',
    6: 'Domenica'
}

def format_time(minutes):
    h = int((minutes // 60) % 24)
    m = int(minutes % 60)
    return f"{h:02d}:{m:02d}"

def optimize_visits(df, days, hours_per_visit, work_hours_per_day, companies_filter):
    visits_per_day = int(work_hours_per_day // hours_per_visit)
    if visits_per_day < 1: visits_per_day = 1
    total_max_visits = int(days * visits_per_day)
    
    if companies_filter:
        df_filtered = df[df[companies_filter].sum(axis=1) > 0].copy()
    else:
        df_filtered = df.copy()
        
    if df_filtered.empty: return pd.DataFrame()
        
    df_filtered.sort_values(by='Totale', ascending=False, inplace=True)
    top_clients = df_filtered.head(total_max_visits).copy()
    
    schedule = []
    current_date = datetime.date.today()
    while current_date.weekday() > 4: current_date += datetime.timedelta(days=1)
        
    visits_today = 0
    current_minute = 9 * 60  # Inizio giornata lavorativa alle 09:00
    visit_duration_min = int(hours_per_visit * 60)

    for _, row in top_clients.iterrows():
        if visits_today >= visits_per_day:
            visits_today = 0
            current_date += datetime.timedelta(days=1)
            while current_date.weekday() > 4: current_date += datetime.timedelta(days=1)
            current_minute = 9 * 60
                
        start_str = format_time(current_minute)
        end_minute = current_minute + visit_duration_min
        end_str = format_time(end_minute)
        orario_str = f"{start_str} - {end_str}"

        schedule.append({
            'Data Visita': current_date.strftime("%d/%m/%Y"),
            'Giorno': GIORNI_IT.get(current_date.weekday(), current_date.strftime("%A")),
            'Orario': orario_str,
            'Cliente': row.get('Cliente', row.get('Ragione Sociale', 'Sconosciuto')),
            'Città': row.get('Citta', ''),
            'Fatturato Stimato': float(row.get('Totale', 0))
        })
        visits_today += 1
        
        # Calcolo orario per la visita successiva nella stessa giornata
        if end_minute <= 13 * 60 and (end_minute + visit_duration_min) > 13 * 60:
            current_minute = 14 * 60  # Pausa pranzo fino alle 14:00
        else:
            current_minute = end_minute + 30  # 30 min per spostamento e pausa

    return pd.DataFrame(schedule)
