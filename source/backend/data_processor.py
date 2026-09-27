import pandas as pd
import random
import io

geocache = {
    "ROMA": (41.9028, 12.4964),
    "CAPALBIO": (42.4542, 11.4217),
}

def get_coords(city):
    city_upper = str(city).upper().strip() if pd.notnull(city) else "ROMA"
    base_lat, base_lon = geocache.get(city_upper, (41.9028, 12.4964))
    return base_lat + random.uniform(-0.06, 0.06), base_lon + random.uniform(-0.06, 0.06)

STANDARD_COL_MAP = {
    'rag. soc. (codice)': 'Ragione Sociale',
    'ragione sociale': 'Ragione Sociale',
    'cliente di consegna': 'Cliente',
    'cliente': 'Cliente',
    'indirizzo consegna': 'Indirizzo',
    'indirizzo': 'Indirizzo',
    'città consegna': 'Citta',
    'citta consegna': 'Citta',
    'città': 'Citta',
    'citta': 'Citta',
    'agente gruppo': 'Agente',
    'agente': 'Agente',
    'totali': 'Totale',
    'totale': 'Totale'
}

IGNORED_META_COLS = {
    'ragione sociale', 'cliente', 'indirizzo', 'citta', 'agente', 'totale', 'lat', 'lon'
}

def process_data(file_bytes):
    df = pd.read_excel(io.BytesIO(file_bytes))
    
    # Rimuove le righe di riepilogo "Totale"
    for col in df.columns:
        if any(term in str(col).lower() for term in ['rag', 'soc', 'codice', 'cliente']):
            df = df[~df[col].astype(str).str.contains('Totale', na=False, case=False)].copy()
            break
            
    # Mappatura delle colonne standard
    rename_dict = {}
    for col in df.columns:
        clean_col = str(col).strip().lower()
        if clean_col in STANDARD_COL_MAP:
            rename_dict[col] = STANDARD_COL_MAP[clean_col]
    df.rename(columns=rename_dict, inplace=True)
    
    # Rilevamento dinamico delle aziende / gruppi (tutte le colonne non anagrafiche)
    company_columns = [
        str(col).strip() for col in df.columns
        if str(col).strip().lower() not in IGNORED_META_COLS
        and not str(col).lower().startswith('unnamed')
    ]
    
    # Conversione numerica per le colonne dei gruppi
    for col in company_columns:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
    # Gestione colonna Totale
    if 'Totale' in df.columns:
        df['Totale'] = pd.to_numeric(df['Totale'], errors='coerce').fillna(0)
    elif company_columns:
        df['Totale'] = df[company_columns].sum(axis=1)
    else:
        df['Totale'] = 0.0
        
    # Calcolo coordinate geografiche
    if 'Citta' in df.columns:
        coords = df['Citta'].apply(get_coords)
        df['Lat'] = [c[0] for c in coords]
        df['Lon'] = [c[1] for c in coords]
    else:
        df['Lat'] = [41.9028 + random.uniform(-0.06, 0.06) for _ in range(len(df))]
        df['Lon'] = [12.4964 + random.uniform(-0.06, 0.06) for _ in range(len(df))]
        
    return df, company_columns

