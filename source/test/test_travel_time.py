import os
import sys
import argparse

# Configurazione percorsi di import
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "backend"))
SOURCE_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))

for p in [BACKEND_DIR, SOURCE_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from data_processor import geocode_address, load_geocache, save_geocache
from planning.models import Location, Client
from planning.routing import build_travel_matrix, _haversine_minutes
from planning.config import MIN_TRASFERTA_TRAVEL_MINUTES


def calculate_travel_time(
    origin_address: str,
    dest_address: str,
    origin_city: str = "",
    dest_city: str = "",
    cache: dict = None
) -> dict:
    """
    Calcola il tempo di viaggio tra due indirizzi utilizzando l'algoritmo
    del sistema (geocodifica OSM/Nominatim con cache + matrice OSRM con fallback Haversine).
    """
    if cache is None:
        cache = load_geocache()

    lat1, lon1 = geocode_address(origin_address, origin_city, cache)
    if lat1 is None or lon1 is None:
        raise ValueError(f"Impossibile geocodificare l'indirizzo di partenza: '{origin_address} {origin_city}'")

    lat2, lon2 = geocode_address(dest_address, dest_city, cache)
    if lat2 is None or lon2 is None:
        raise ValueError(f"Impossibile geocodificare l'indirizzo di destinazione: '{dest_address} {dest_city}'")

    # Salva in cache eventuali nuovi punti geocodificati
    save_geocache(cache)

    depot = Location(lat=lat1, lon=lon1)
    client = Client(
        id="dest",
        name="Destinazione",
        address=dest_address,
        city=dest_city,
        group="",
        latitude=lat2,
        longitude=lon2,
        revenue=0.0,
        service_minutes=0,
        cluster_id=None,
        source_index=0
    )

    # Calcolo con l'algoritmo del sistema (OSRM + fallback)
    matrix = build_travel_matrix(depot, [client])
    travel_minutes = matrix[0][1]
    return_minutes = matrix[1][0]

    hours = int(travel_minutes // 60)
    minutes = int(round(travel_minutes % 60))
    time_str = f"{hours}h {minutes:02d}m" if hours > 0 else f"{minutes} min"

    is_trasferta = travel_minutes >= MIN_TRASFERTA_TRAVEL_MINUTES

    return {
        "origin": f"{origin_address}, {origin_city}".strip(", "),
        "origin_coords": (lat1, lon1),
        "destination": f"{dest_address}, {dest_city}".strip(", "),
        "dest_coords": (lat2, lon2),
        "travel_time_minutes": round(travel_minutes, 1),
        "return_time_minutes": round(return_minutes, 1),
        "travel_time_human": time_str,
        "is_trasferta": is_trasferta,
        "min_trasferta_threshold": MIN_TRASFERTA_TRAVEL_MINUTES,
    }


# ==============================================================================
# Test automatici (pytest compatibili)
# ==============================================================================

def test_short_trip_intra_city():
    """Tratta urbana: Colosseo -> Piazza di Spagna (Roma)"""
    res = calculate_travel_time(
        origin_address="Piazza del Colosseo 1",
        origin_city="Roma",
        dest_address="Piazza di Spagna",
        dest_city="Roma"
    )
    assert res["travel_time_minutes"] > 0
    assert res["travel_time_minutes"] < 60
    assert not res["is_trasferta"], "Un tragitto cittadino breve non deve essere trasferta"


def test_medium_trip_trasferta():
    """Tratta media: Roma -> Napoli (> 120 min)"""
    res = calculate_travel_time(
        origin_address="Roma",
        origin_city="Roma",
        dest_address="Napoli",
        dest_city="Napoli"
    )
    assert res["travel_time_minutes"] > 60
    assert res["is_trasferta"], f"Roma -> Napoli ({res['travel_time_minutes']} min) deve essere trasferta (> {res['min_trasferta_threshold']} min)"


def test_long_trip_trasferta():
    """Tratta lunga: Roma -> Milano (> 120 min)"""
    res = calculate_travel_time(
        origin_address="Piazza del Colosseo 1",
        origin_city="Roma",
        dest_address="Piazza del Duomo",
        dest_city="Milano"
    )
    assert res["travel_time_minutes"] > 240
    assert res["is_trasferta"], "Roma -> Milano deve essere considerata trasferta"


def test_haversine_fallback_accuracy():
    """Verifica il calcolo matematico fallback tra Roma e Milano (~480 km lineari)"""
    lat1, lon1 = 41.8919, 12.5113
    lat2, lon2 = 45.4642, 9.1900
    mins = _haversine_minutes(lat1, lon1, lat2, lon2)
    assert mins > 300, f"Tempo stimato in fallback {mins} min deve essere coerente per Roma-Milano"


# ==============================================================================
# CLI runner
# ==============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calcolo del tempo di viaggio tra due indirizzi con l'algoritmo del sistema")
    parser.add_argument("origin", nargs="?", default=None, help="Indirizzo di partenza (es. 'Via del Corso 1, Roma')")
    parser.add_argument("destination", nargs="?", default=None, help="Indirizzo di arrivo (es. 'Piazza Maggiore, Bologna')")
    args = parser.parse_args()

    if args.origin and args.destination:
        print("\n" + "=" * 60)
        print("  CALCOLO TEMPO DI VIAGGIO (ALGORITMO SISTEMA)")
        print("=" * 60)
        res = calculate_travel_time(args.origin, args.destination)
        print(f" Partenza:      {res['origin']} {res['origin_coords']}")
        print(f" Destinazione:  {res['destination']} {res['dest_coords']}")
        print(f" Tempo andata:  {res['travel_time_human']} ({res['travel_time_minutes']} min)")
        print(f" Tempo ritorno: {res['return_time_minutes']} min")
        print(f" Trasferta:     {'SÌ (+1 gg / trasferta)' if res['is_trasferta'] else 'NO (entro soglia)'} (Soglia: {res['min_trasferta_threshold']} min)")
        print("=" * 60 + "\n")
    else:
        print("\n" + "=" * 60)
        print("  ESECUZIONE TEST TEMPI DI VIAGGIO (OSRM + FALLBACK)")
        print("=" * 60)

        # 1. Tratta urbana
        print("\n[1/3] Tratta urbana: Roma Colosseo -> Roma Piazza di Spagna")
        res1 = calculate_travel_time("Piazza del Colosseo 1", "Piazza di Spagna", "Roma", "Roma")
        print(f"  -> Tempo: {res1['travel_time_human']} ({res1['travel_time_minutes']} min)")
        print(f"  -> Trasferta: {res1['is_trasferta']}")
        assert not res1["is_trasferta"]

        # 2. Tratta media
        print("\n[2/3] Tratta media: Roma -> Napoli")
        res2 = calculate_travel_time("Roma", "Napoli", "Roma", "Napoli")
        print(f"  -> Tempo: {res2['travel_time_human']} ({res2['travel_time_minutes']} min)")
        print(f"  -> Trasferta: {res2['is_trasferta']}")
        assert res2["is_trasferta"]

        # 3. Tratta lunga
        print("\n[3/3] Tratta lunga: Roma -> Milano")
        res3 = calculate_travel_time("Piazza del Colosseo 1", "Piazza del Duomo", "Roma", "Milano")
        print(f"  -> Tempo: {res3['travel_time_human']} ({res3['travel_time_minutes']} min)")
        print(f"  -> Trasferta: {res3['is_trasferta']}")
        assert res3["is_trasferta"]

        # 4. Fallback test
        test_haversine_fallback_accuracy()

        print("\n" + "=" * 60)
        print("  TUTTI I TEST SUI TEMPI DI VIAGGIO SONO PASSATI CON SUCCESSO!")
        print("=" * 60 + "\n")
