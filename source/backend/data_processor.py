import pandas as pd
import io
import json
import os
import re
import time
import urllib.parse
import urllib.request


# ---------------------------------------------------------
# Configurazione geocodifica
# ---------------------------------------------------------

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

GEOCACHE_FILE = os.getenv(
    "GEOCACHE_FILE",
    "/app/cache/geocache.json"
)

GEOCODING_DELAY_SECONDS = float(
    os.getenv(
        "GEOCODING_DELAY_SECONDS",
        "1.1"
    )
)

USER_AGENT = os.getenv(
    "NOMINATIM_USER_AGENT",
    "sales-visit-optimizer-hackathon/1.0"
)


# ---------------------------------------------------------
# Mappatura colonne ERP
# ---------------------------------------------------------

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
    'ragione sociale',
    'cliente',
    'indirizzo',
    'citta',
    'agente',
    'totale',
    'lat',
    'lon'
}


# ---------------------------------------------------------
# Funzioni comuni di lettura / normalizzazione
# ---------------------------------------------------------

def read_and_normalize_dataframe(file_bytes):
    """
    Legge l'Excel, elimina le righe di riepilogo e normalizza
    i nomi delle colonne. NON esegue geocodifica.
    """

    df = pd.read_excel(
        io.BytesIO(file_bytes)
    )

    # Rimozione delle righe di riepilogo "Totale"
    for col in df.columns:
        if any(
            term in str(col).lower()
            for term in [
                'rag',
                'soc',
                'codice',
                'cliente'
            ]
        ):
            df = df[
                ~df[col]
                .astype(str)
                .str.contains(
                    'Totale',
                    na=False,
                    case=False
                )
            ].copy()

            break

    # Normalizzazione dei nomi delle colonne
    rename_dict = {}

    for col in df.columns:
        clean_col = (
            str(col)
            .strip()
            .lower()
        )

        if clean_col in STANDARD_COL_MAP:
            rename_dict[col] = STANDARD_COL_MAP[
                clean_col
            ]

    df.rename(
        columns=rename_dict,
        inplace=True
    )

    return df


def detect_company_columns(df):
    """
    Individua dinamicamente le colonne delle aziende.
    """

    return [
        str(col).strip()
        for col in df.columns
        if (
            str(col).strip().lower()
            not in IGNORED_META_COLS
            and not str(col).lower().startswith(
                'unnamed'
            )
        )
    ]


def extract_companies_from_file(file_bytes):
    """
    Legge solo la struttura dell'Excel e restituisce
    le aziende disponibili.

    Importante:
    NON aggrega i punti visita e NON geocodifica.
    """

    df = read_and_normalize_dataframe(
        file_bytes
    )

    return detect_company_columns(
        df
    )


# ---------------------------------------------------------
# Cache geocodifica
# ---------------------------------------------------------

def load_geocache():
    if not os.path.exists(
        GEOCACHE_FILE
    ):
        return {}

    try:
        with open(
            GEOCACHE_FILE,
            "r",
            encoding="utf-8"
        ) as file:
            return json.load(file)

    except (
        json.JSONDecodeError,
        OSError
    ):
        return {}


def save_geocache(cache):
    cache_directory = os.path.dirname(
        GEOCACHE_FILE
    )

    os.makedirs(
        cache_directory,
        exist_ok=True
    )

    with open(
        GEOCACHE_FILE,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            cache,
            file,
            ensure_ascii=False,
            indent=2
        )


# ---------------------------------------------------------
# Geocodifica reale con Nominatim
# ---------------------------------------------------------

def geocode_address(
    address,
    city,
    cache
):
    address = (
        str(address).strip()
        if pd.notnull(address)
        else ""
    )

    city = (
        str(city).strip()
        if pd.notnull(city)
        else ""
    )

    if not address and not city:
        return None, None

    query = ", ".join(
        part
        for part in [
            address,
            city,
            "Italy"
        ]
        if part
    )

    cache_key = query.upper()

    # Se già geocodificato, usa la cache
    if cache_key in cache:
        cached_value = cache[cache_key]
        if cached_value is None:
            return None, None
        return (
            cached_value["lat"],
            cached_value["lon"]
        )

    # Genera varianti di query per gestire abbreviazioni toponomastiche comuni
    variants = [query]
    sub_di = re.sub(r'(?i)\bvia\s+(san|santa|sant\')\b', r'via di \1', query)
    if sub_di != query:
        variants.append(sub_di)
    sub_ariosto = re.sub(r'(?i)\bvia\s+ariosto\b', 'via ludovico ariosto', query)
    if sub_ariosto != query:
        variants.append(sub_ariosto)

    best_match = None
    fallback_match = None

    for v in variants:
        params = urllib.parse.urlencode({
            "q": v,
            "format": "jsonv2",
            "limit": 5,
            "countrycodes": "it"
        })
        url = f"{NOMINATIM_URL}?{params}"
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT
            }
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                results = json.load(response)
                if not results:
                    continue
                if fallback_match is None:
                    fallback_match = results[0]
                # Se tra i risultati ce n'è uno nel comune/centro di Roma (es. Municipio Roma o Roma centro)
                for r in results:
                    dn = r.get("display_name", "")
                    if "Municipio Roma" in dn or ", Roma, Roma Capitale" in dn:
                        best_match = r
                        break
                if best_match:
                    break
        except Exception:
            continue

    chosen = best_match or fallback_match
    if chosen:
        lat = float(chosen["lat"])
        lon = float(chosen["lon"])
        cache[cache_key] = {
            "lat": lat,
            "lon": lon,
            "display_name": chosen.get("display_name", "")
        }
    else:
        lat = None
        lon = None
        cache[cache_key] = None

    # Salvataggio progressivo della cache
    save_geocache(cache)

    # Pausa per rispettare il servizio pubblico Nominatim
    time.sleep(GEOCODING_DELAY_SECONDS)

    return lat, lon


# ---------------------------------------------------------
# Elaborazione completa dataset ERP
# ---------------------------------------------------------

def process_data(file_bytes):
    """
    Esegue l'elaborazione completa:
    - lettura Excel
    - normalizzazione colonne
    - identificazione aziende
    - aggregazione per punto visita
    - geocodifica reale
    """

    df = read_and_normalize_dataframe(
        file_bytes
    )

    # -----------------------------------------------------
    # 1. Identificazione dinamica aziende
    # -----------------------------------------------------

    company_columns = detect_company_columns(
        df
    )

    # -----------------------------------------------------
    # 2. Conversione fatturati
    # -----------------------------------------------------

    for col in company_columns:
        df[col] = pd.to_numeric(
            df[col],
            errors='coerce'
        ).fillna(0)

    # -----------------------------------------------------
    # 3. Gestione colonna Totale
    # -----------------------------------------------------

    if 'Totale' in df.columns:
        df['Totale'] = pd.to_numeric(
            df['Totale'],
            errors='coerce'
        ).fillna(0)

    elif company_columns:
        df['Totale'] = df[
            company_columns
        ].sum(
            axis=1
        )

    else:
        df['Totale'] = 0.0

    # -----------------------------------------------------
    # 4. Aggregazione per punto visita
    #
    # Una visita =
    # Cliente + Indirizzo + Città
    # -----------------------------------------------------

    group_columns = [
        'Cliente',
        'Indirizzo',
        'Citta'
    ]

    group_columns = [
        col
        for col in group_columns
        if col in df.columns
    ]

    aggregation_rules = {
        company: 'sum'
        for company in company_columns
    }

    if 'Ragione Sociale' in df.columns:
        aggregation_rules[
            'Ragione Sociale'
        ] = lambda values: ', '.join(
            sorted({
                str(value).strip()
                for value in values
                if (
                    pd.notnull(value)
                    and str(value).strip()
                )
            })
        )

    if 'Agente' in df.columns:
        aggregation_rules[
            'Agente'
        ] = lambda values: ', '.join(
            sorted({
                str(value).strip()
                for value in values
                if (
                    pd.notnull(value)
                    and str(value).strip()
                )
            })
        )

    df = (
        df
        .groupby(
            group_columns,
            dropna=False,
            as_index=False
        )
        .agg(
            aggregation_rules
        )
    )

    # -----------------------------------------------------
    # 5. Ricalcolo del Totale
    # -----------------------------------------------------

    if company_columns:
        df['Totale'] = df[
            company_columns
        ].sum(
            axis=1
        )
    else:
        df['Totale'] = 0.0

    print(
        "Numero punti visita dopo aggregazione:",
        len(df),
        flush=True
    )

    # -----------------------------------------------------
    # 6. Geocodifica reale
    # -----------------------------------------------------

    cache = load_geocache()

    latitudes = []
    longitudes = []

    total_points = len(df)

    for position, (_, row) in enumerate(
        df.iterrows(),
        start=1
    ):
        address = row.get(
            "Indirizzo",
            ""
        )

        city = row.get(
            "Citta",
            ""
        )

        print(
            f"Geocodifica "
            f"{position}/{total_points}: "
            f"{address}, {city}",
            flush=True
        )

        lat, lon = geocode_address(
            address,
            city,
            cache
        )

        latitudes.append(
            lat
        )

        longitudes.append(
            lon
        )

    df["Lat"] = latitudes
    df["Lon"] = longitudes

    # -----------------------------------------------------
    # 7. Statistiche geocodifica
    # -----------------------------------------------------

    geocoded_count = (
        df["Lat"]
        .notna()
        .sum()
    )

    failed_count = (
        len(df)
        -
        geocoded_count
    )

    print(
        f"Punti geocodificati: "
        f"{geocoded_count}",
        flush=True
    )

    print(
        f"Punti non geocodificati: "
        f"{failed_count}",
        flush=True
    )

    # -----------------------------------------------------
    # 8. Restituzione dataset
    # -----------------------------------------------------

    return (
        df,
        company_columns
    )
