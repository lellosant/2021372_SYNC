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

NOMINATIM_URL = os.getenv(
    "NOMINATIM_URL",
    "https://nominatim.openstreetmap.org/search"
)

PHOTON_URL = os.getenv(
    "PHOTON_URL",
    "http://photon:2322/api"
)

USE_LOCAL_PHOTON = os.getenv(
    "USE_LOCAL_PHOTON",
    "false"
).lower() == "true"

GEOCACHE_FILE = os.getenv(
    "GEOCACHE_FILE",
    "/app/cache/geocache.json"
)

GEOCODING_DELAY_SECONDS = float(
    os.getenv(
        "GEOCODING_DELAY_SECONDS",
        "0.0" if os.getenv("PHOTON_URL") else "1.1"
    )
)

USER_AGENT = os.getenv(
    "NOMINATIM_USER_AGENT",
    "sales-visit-optimizer-hackathon/1.0"
)


def query_photon(plan_val, plan_type, base_url=None):
    """Interroga un'istanza di Photon (locale o pubblica) e mappa il GeoJSON nello schema atteso dallo scoring."""
    target_url = base_url or PHOTON_URL
    if not target_url:
        return []

    if plan_type == "structured" and isinstance(plan_val, dict):
        q = f"{plan_val.get('street', '')} {plan_val.get('city', '')} {plan_val.get('country', '')}".strip()
    else:
        q = str(plan_val)

    params = {"q": q, "limit": 5}
    target = target_url.rstrip("/") + "/?"
    url = f"{target}{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=3) as response:
        payload = json.load(response)
        features = payload.get("features", [])
        if not features:
            return []

        results = []
        for feat in features:
            props = feat.get("properties", {})
            geom = feat.get("geometry", {})
            coords = geom.get("coordinates", [0, 0])
            lon, lat = coords[0], coords[1]
            parts = [
                props.get("name") or props.get("street") or "",
                props.get("housenumber") or "",
                props.get("district") or "",
                props.get("city") or "",
                props.get("county") or "",
                props.get("state") or "",
                props.get("country") or ""
            ]
            disp = ", ".join(p for p in parts if p)
            results.append({
                "lat": lat,
                "lon": lon,
                "type": props.get("osm_value") or props.get("osm_key") or "",
                "display_name": disp,
                "address": {
                    "house_number": props.get("housenumber"),
                    "road": props.get("street") or props.get("name"),
                    "city": props.get("city"),
                    "county": props.get("county"),
                    "state": props.get("state")
                }
            })
        return results


def query_nominatim(plan_val, plan_type):
    """Interroga Nominatim pubblico con query strutturata o testuale."""
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
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


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

    # Protezione: unisci sempre con la cache esistente su disco per evitare che test o chiamate parziali la cancellino
    disk_cache = load_geocache()
    if disk_cache and cache is not disk_cache:
        cache_to_save = dict(disk_cache)
        cache_to_save.update(cache)
    else:
        cache_to_save = cache

    with open(
        GEOCACHE_FILE,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            cache_to_save,
            file,
            ensure_ascii=False,
            indent=2
        )


# ---------------------------------------------------------
# Sanitizzazione, correzione toponomastica e Geocodifica
# ---------------------------------------------------------

TOPONYM_REPLACEMENTS = [
    # Refusi tipo via / piazza / corso / viale / circonvallazione
    (r'\b(VUA|VOA)\b', 'VIA'),
    (r'\b(PÈIAZZA|PEIAZZA|PZZA|P\.ZZA|PIAZ\.)\b', 'PIAZZA'),
    (r'\b(V\.LE|VLE)\b', 'VIALE'),
    (r'\b(C\.SO|CSO)\b', 'CORSO'),
    (r'\bCIRC(?:ONV)?\.\b', 'CIRCONVALLAZIONE'),
    (r'\bLUNGO\s+TEVERE\b', 'LUNGOTEVERE'),
    (r'\bL\.TEVERE\b', 'LUNGOTEVERE'),
    (r'\bF\.LLI\b', 'FRATELLI'),
    (r'\bSS\.\b', 'SANTI'),
    (r'\bSANTISSIMI\b', 'SANTI'),
    (r'\bS\.\s*(?=[A-Z])', 'SAN '),
    (r'\bSTA\.\s*(?=[A-Z])', 'SANTA '),
    # Refusi ed errori toponomastici frequenti
    (r"\bDOI\s+SANT'", "DI SANT'"),
    (r'\bCARACCI\b', 'CARRACCI'),
    (r'\bMANUNZIO\b', 'MANUZIO'),
    (r'\bSIMMONE\b', 'SIMONE'),
    (r'\bFONTATA\b', 'FONTANA'),
    (r'\bCASILIA\b', 'CASILINA'),
    (r'\bPIERLGUIGI\b', 'PIERLUIGI'),
    (r'\bDEBENDETTI\b', 'DEBENEDETTI'),
    (r'\bANNI\s+A\s+FAUSTIAN\b', 'ANNIA FAUSTINA'),
    (r'\bSCANDENBERG\b', 'SKANDERBEG'),
    (r'\bGIORG[IA]A?\s+DE[L\s]+LEONTINI\b', 'GORGIA DI LEONTINI'),
    (r'\bDELL\s+PACE\b', 'DELLA PACE'),
    (r'\bSANTA\s+MARIE\b', 'SANTA MARIA'),
    (r'\bMENEMIO\b', 'MENENIO'),
    (r'\bSAN\s+ERASMO\b', "SANT'ERASMO"),
    (r'\bTOR\s+DEI\s+CONTI\b', "TOR DE' CONTI"),
    (r"\bDE'\s+PENITENZIERI\b", 'DEI PENITENZIERI'),
    (r"\bCAMPO\s+DE\s+FIORI\b", "CAMPO DE' FIORI"),
    (r'\bFULCERI\b', 'FULCIERI'),
    (r'\bPAOLUCCI\b', 'PAULUCCI'),
    (r'\bLEOMBARDO\b', 'LOMBARDO'),
]


def sanitize_address_string(address):
    """
    Ripulisce la stringa di indirizzo da rumore logistico (note di consegna, piani,
    scale, incroci, snc, km) e corregge automaticamente refusi toponomastici noti.
    """
    if not address or pd.isna(address):
        return ""

    s = str(address).strip()
    s = s.replace('’', "'").replace('`', "'").replace("\\'", "'").replace('--', '-')

    # Prefissi tipo via
    s = re.sub(r'(?i)\bS\.?S\.?\s*(\d+)?\s*', 'VIA ', s)
    s = re.sub(r'(?i)^V\.\s+', 'VIA ', s)
    s = re.sub(r'(?i)\bV\.\s+([A-Z])', r'VIA \1', s)

    # Rimuovi note logistiche e istruzioni di consegna
    s = re.sub(r'(?i)\bC/O\b.*', '', s)
    s = re.sub(r'(?i)\b\d+°\s*(?:PIANO|P\b).*', '', s)
    s = re.sub(r'(?i)\b(?:PIANO|SCALA|INTERNO|INT\.)\s+[A-Za-z0-9]+', '', s)
    s = re.sub(r'(?i)\bANG(?:OLO|\.VIA|\.)\b.*', '', s)
    s = re.sub(r'(?i)\b(?:ISOLA|LOTTO|COMPRENSORIO)\s+[A-Za-z0-9]+', '', s)
    s = re.sub(r'(?i)\b(?:LOC\.|LOCALIT[AÀ]|BIVIO)\s*[^,]+', '', s)
    s = re.sub(r'(?i)\b(?:USCITA|SVINCOLO|CASELLO)\s+[^,]+', '', s)
    s = re.sub(r'(?i)\(?\bKM\.?\s*\d+(?:[.,+]\d+)?\)?', '', s)
    s = re.sub(r'(?i)\b(?:S\.?N\.?C\.?|SENZA\s+NUMERO)\b', '', s)

    # Correzioni toponomastiche
    for pattern, replacement in TOPONYM_REPLACEMENTS:
        s = re.sub(pattern, replacement, s, flags=re.I)

    # Spazia lettere puntate attaccate (es: 'G.PACINI' -> 'G. PACINI')
    s = re.sub(r'\b([A-Za-z])\.([A-Za-z])', r'\1. \2', s)

    # Normalizza spazi
    s = re.sub(r'\s+', ' ', s).strip(' ,.-')
    return s


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

    # Se già geocodificato con successo valido, usa la cache
    if cache_key in cache:
        cached_value = cache[cache_key]
        if cached_value is not None:
            return (
                cached_value["lat"],
                cached_value["lon"]
            )

    # -----------------------------------------------------
    # Sanitizzazione intelligente della stringa di ricerca
    # -----------------------------------------------------
    sanitized_raw = sanitize_address_string(address)
    s_street, s_civic, s_detected_city = parse_address_and_civic(sanitized_raw, effective_city)
    
    clean_street = s_street or street
    clean_civic = s_civic or civic
    clean_city = s_detected_city or effective_city

    # Versione della via senza iniziale puntata (es. 'Via G. Pacini' -> 'Via Pacini')
    street_no_init = re.sub(r'\b[A-Za-z]\.\s+', '', clean_street).strip()

    # -----------------------------------------------------
    # Costruzione piani di query a cascata (resilient fallback)
    # -----------------------------------------------------
    query_plans = []

    # 1. Ricerca specifica con civico
    if clean_civic:
        if clean_city:
            query_plans.append(("structured", {"street": f"{clean_civic} {clean_street}", "city": clean_city, "country": "Italy"}))
        query_plans.append(("q", f"{clean_street} {clean_civic}, {clean_city}, Italy".replace(", ,", ",").strip(", ")))
        query_plans.append(("q", f"{clean_civic} {clean_street}, {clean_city}, Italy".replace(", ,", ",").strip(", ")))
        
        # Con civico ma senza iniziale puntata
        if street_no_init and street_no_init != clean_street:
            query_plans.append(("q", f"{street_no_init} {clean_civic}, {clean_city}, Italy".replace(", ,", ",").strip(", ")))

    # 2. Ricerca standard
    if clean_city:
        query_plans.append(("q", f"{clean_street}, {clean_city}, Italy".replace(", ,", ",").strip(", ")))
    query_plans.append(("q", f"{sanitized_raw or address}, {clean_city}, Italy".replace(", ,", ",").strip(", ")))

    # 3. Ricerca senza iniziale puntata (spesso OSM registra solo il cognome)
    if street_no_init and street_no_init != clean_street and clean_city:
        query_plans.append(("q", f"{street_no_init}, {clean_city}, Italy".replace(", ,", ",").strip(", ")))

    # 4. Varianti toponomastiche comuni (es. 'via san' vs 'via di san')
    sub_di = re.sub(r'(?i)\bvia\s+(san|santa|sant\')\b', r'via di \1', clean_street)
    if sub_di != clean_street:
        query_plans.append(("q", f"{sub_di} {clean_civic or ''}, {clean_city}, Italy".replace(", ,", ",").strip(", ")))
        query_plans.append(("q", f"{sub_di}, {clean_city}, Italy".replace(", ,", ",").strip(", ")))

    best_item = None
    best_score = -1
    used_photon = False

    for plan_type, plan_val in query_plans:
        results = None
        # 1. Prova prima con Photon locale
        if USE_LOCAL_PHOTON and PHOTON_URL:
            try:
                results = query_photon(plan_val, plan_type, base_url=PHOTON_URL)
                if results:
                    used_photon = True
            except Exception:
                results = None

        # 2. Se Photon locale non risponde ancora, usa Photon pubblico (veloce, nessun delay artificiale)
        if results is None:
            try:
                results = query_photon(plan_val, plan_type, base_url="https://photon.komoot.io/api")
                if results:
                    used_photon = True
            except Exception:
                results = None

        # 3. Fallback estremo su Nominatim pubblico
        if results is None:
            try:
                results = query_nominatim(plan_val, plan_type)
            except Exception:
                continue

        if not results:
            continue

        for r in results:
            score = 0
            addr_info = r.get("address", {})
            r_civic = addr_info.get("house_number")
            r_type = r.get("type", "")
            dn = r.get("display_name", "")

            # 1. Pertinenza città (FONDAMENTALE per evitare vie omonime in altre città)
            c_low = clean_city.lower() if clean_city else ""
            r_city = (addr_info.get("city") or "").lower()
            dn_low = dn.lower()
            city_tokens = [tok for tok in re.split(r'[\s\-,/]+', c_low) if len(tok) > 2]
            if c_low:
                if c_low in dn_low or c_low in r_city or any(tok in dn_low or tok in r_city for tok in city_tokens):
                    score += 2000
                else:
                    score -= 5000

            # 2. Priorità al numero civico esatto o parziale
            if clean_civic:
                if r_civic and str(r_civic).strip() == str(clean_civic).strip():
                    score += 1000
                elif clean_civic in dn.split(","):
                    score += 500
                elif clean_civic in dn:
                    score += 300

            # 3. Punteggio tipologia immobile/punto esatto o strada
            if r_type in ["house", "building", "residential", "commercial", "retail", "shop", "office"]:
                score += 100
            elif r_type in ["street", "highway", "pedestrian", "footway", "living_street", "road"]:
                score += 40

            if score > best_score:
                best_score = score
                best_item = r

        # Se abbiamo trovato un civico esatto o quasi esatto nella città corretta
        if best_score >= 3000 or (clean_civic and best_score >= 2500):
            break

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

    # Pausa solo per Nominatim pubblico per rispettare i ToS
    if not used_photon and GEOCODING_DELAY_SECONDS > 0:
        time.sleep(GEOCODING_DELAY_SECONDS)

    return lat, lon



_geocoding_progress = {
    "active": False,
    "phase": "idle",
    "current": 0,
    "total": 0,
    "address": "",
    "geocoded": 0,
    "failed": 0
}


def get_progress_status():
    """Restituisce una copia dello stato attuale di avanzamento della geocodifica / analisi."""
    res = dict(_geocoding_progress)
    res["stage"] = res.get("phase", "idle")
    res["current_address"] = res.get("address", "")
    return res


def set_progress_status(active, phase, current=0, total=0, address="", geocoded=0, failed=0):
    """Aggiorna lo stato di avanzamento in modo thread-safe e sincrono."""
    _geocoding_progress["active"] = bool(active)
    _geocoding_progress["phase"] = str(phase)
    _geocoding_progress["current"] = int(current)
    _geocoding_progress["total"] = int(total)
    _geocoding_progress["address"] = str(address)
    _geocoding_progress["geocoded"] = int(geocoded)
    _geocoding_progress["failed"] = int(failed)


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
    geocoded_so_far = 0
    failed_so_far = 0
    set_progress_status(True, "geocoding", 0, total_points, "Avvio geocodifica...", 0, 0)

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

        display_addr = f"{address}, {city}".strip(" ,")
        set_progress_status(True, "geocoding", position, total_points, display_addr, geocoded_so_far, failed_so_far)

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

        if lat is not None and lon is not None:
            geocoded_so_far += 1
        else:
            failed_so_far += 1

        latitudes.append(
            lat
        )

        longitudes.append(
            lon
        )

    set_progress_status(True, "optimizing", total_points, total_points, "Geocodifica completata. Ottimizzazione visite...", geocoded_so_far, failed_so_far)

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
