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

def parse_address_and_civic(address, city=""):
    """
    Estrae via, numero civico e città da una stringa indirizzo italiana.
    Supporta formati come 'Via del Corso 184', 'Via del Corso, 184', 'Via del Corso n. 184',
    'Via del Corso civico 184', 'Largo Corrado Ricci 40/43 A', 'Via Roma 10, Milano'.
    """
    address = (str(address) if pd.notnull(address) else "").strip()
    city = (str(city) if pd.notnull(city) else "").strip()

    # Se la città non è fornita, prova ad estrarla se separata da virgola
    if "," in address:
        parts = [p.strip() for p in address.split(",") if p.strip()]
        if len(parts) >= 2:
            # Se l'ultima parte è una città (testo senza numeri)
            if not city and re.search(r"^[a-zA-Z\s\'-]+$", parts[-1]):
                city = parts.pop()
                address = ", ".join(parts)
            # Oppure CAP + Città (es. '00186 Roma')
            elif not city and re.search(r"^\d{5}\s+[a-zA-Z\s\'-]+$", parts[-1]):
                city = re.sub(r"^\d{5}\s+", "", parts.pop())
                address = ", ".join(parts)

    civic = None
    street = address

    # Pattern 1: 'n. 12', 'n° 12', 'num. 12', 'civico 12'
    m = re.search(r"(?i)\b(?:n\.?|n°|num\.?|numero|civico)\s*[:.]?\s*(\d+[a-zA-Z]?(?:[/-]\d+[a-zA-Z]?)?)", address)
    if m:
        first_num = re.match(r"^\d+", m.group(1))
        civic = first_num.group(0) if first_num else m.group(1)
        street = address[:m.start()].strip().rstrip(",").strip() + " " + address[m.end():].strip()
        street = street.strip().rstrip(",").strip()
    else:
        # Pattern 2: numero civico (anche con lettere/barre) dopo spazio o virgola
        m2 = re.search(r"(?i)(?:,\s*|\s+)(\d+)(?:[/\-a-zA-Z0-9\s]*)$", address)
        if m2:
            civic = m2.group(1)
            street = address[:m2.start()].strip().rstrip(",").strip()

    return street.strip(), civic, city.strip()


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

    # Estrazione via, civico e città normalizzata
    street, civic, detected_city = parse_address_and_civic(address, city)
    effective_city = detected_city or city or ""

    query = ", ".join(
        part
        for part in [
            address,
            effective_city,
            "Italy"
        ]
        if part
    )

    cache_key = query.upper()

    # Se già geocodificato con successo, usa la cache
    if cache_key in cache:
        cached_value = cache[cache_key]
        if cached_value is None:
            return None, None
        return (
            cached_value["lat"],
            cached_value["lon"]
        )

    # Costruzione delle query per Nominatim in ordine di priorità
    # 1. Ricerca con civico strutturata ed esplicita
    query_plans = []
    if civic:
        if effective_city:
            query_plans.append(("structured", {"street": f"{civic} {street}", "city": effective_city, "country": "Italy"}))
        query_plans.append(("q", f"{street} {civic}, {effective_city}, Italy".replace(", ,", ",").strip(", ")))
        query_plans.append(("q", f"{civic} {street}, {effective_city}, Italy".replace(", ,", ",").strip(", ")))

    # 2. Ricerca standard
    if effective_city:
        query_plans.append(("q", f"{street}, {effective_city}, Italy"))
    query_plans.append(("q", f"{address}, {effective_city}, Italy".replace(", ,", ",").strip(", ")))

    # Varianti toponomastiche comuni
    sub_di = re.sub(r'(?i)\bvia\s+(san|santa|sant\')\b', r'via di \1', street)
    if sub_di != street:
        query_plans.append(("q", f"{sub_di} {civic or ''}, {effective_city}, Italy".replace(", ,", ",").strip(", ")))

    best_item = None
    best_score = -1

    for plan_type, plan_val in query_plans:
        if plan_type == "structured":
            params = dict(plan_val)
        else:
            params = {"q": plan_val}

        params.update({
            "format": "jsonv2",
            "limit": 5,
            "countrycodes": "it",
            "addressdetails": 1
        })

        url = f"{NOMINATIM_URL}?{urllib.parse.urlencode(params)}"
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

                for r in results:
                    score = 0
                    addr_info = r.get("address", {})
                    r_civic = addr_info.get("house_number")
                    r_type = r.get("type", "")
                    dn = r.get("display_name", "")

                    # Priorità massima al numero civico esatto
                    if civic:
                        if r_civic and str(r_civic).strip() == str(civic).strip():
                            score += 1000
                        elif civic in dn.split(","):
                            score += 500
                        elif civic in dn:
                            score += 300

                    # Punteggio pertinenza città
                    if effective_city and effective_city.lower() in dn.lower():
                        score += 150
                    elif "roma" in dn.lower() and (not effective_city or "roma" in effective_city.lower()):
                        score += 50

                    # Punteggio tipologia immobile/punto esatto
                    if r_type in ["house", "building", "residential", "commercial", "retail", "shop", "office"]:
                        score += 100

                    if score > best_score:
                        best_score = score
                        best_item = r

                # Se abbiamo trovato un civico esatto o quasi esatto, abbiamo la risposta migliore
                if best_score >= 1000 or (civic and best_score >= 500):
                    break
        except Exception:
            continue

    if best_item:
        lat = float(best_item["lat"])
        lon = float(best_item["lon"])
        matched_house_number = best_item.get("address", {}).get("house_number") or (civic if best_score >= 300 else None)
        cache[cache_key] = {
            "lat": lat,
            "lon": lon,
            "display_name": best_item.get("display_name", ""),
            "house_number": matched_house_number,
            "house_number_exact": bool(best_item.get("address", {}).get("house_number") == civic)
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
