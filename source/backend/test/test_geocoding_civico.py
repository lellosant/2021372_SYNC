import os
import sys
import math

# Configurazione path di import
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
SOURCE_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

for p in [BACKEND_DIR, SOURCE_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from data_processor import parse_address_and_civic, geocode_address


def haversine_distance_meters(lat1, lon1, lat2, lon2):
    """Calcola la distanza in metri tra due coordinate geografiche."""
    r = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
    return 2.0 * r * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def test_parse_address_and_civic_various_formats():
    """Verifica che il parser estragga correttamente via, civico e città da tutti i formati comuni."""
    cases = [
        ("Via del Corso 184", "Via del Corso", "184", ""),
        ("Via del Corso, 184, Roma", "Via del Corso", "184", "Roma"),
        ("Via del Corso n. 184, Roma", "Via del Corso", "184", "Roma"),
        ("Via del Corso n° 184", "Via del Corso", "184", ""),
        ("Via del Corso civico 184", "Via del Corso", "184", ""),
        ("Via del Corso 184/A", "Via del Corso", "184", ""),
        ("Largo Corrado Ricci 40/43 A, Roma", "Largo Corrado Ricci", "40", "Roma"),
        ("Piazza Scipione Borghese  5", "Piazza Scipione Borghese", "5", ""),
        ("Strada di Macchiatonda SNC", "Strada di Macchiatonda SNC", None, ""),
        ("Piazza di Spagna, Roma", "Piazza di Spagna", None, "Roma"),
    ]

    for raw, exp_street, exp_civic, exp_city in cases:
        street, civic, city = parse_address_and_civic(raw)
        assert street.lower() == exp_street.lower(), f"Street errata per '{raw}': attesa '{exp_street}', ottenuta '{street}'"
        assert civic == exp_civic, f"Civico errato per '{raw}': atteso '{exp_civic}', ottenuto '{civic}'"
        if exp_city:
            assert city.lower() == exp_city.lower(), f"Città errata per '{raw}': attesa '{exp_city}', ottenuta '{city}'"


def test_geocoding_distinguishes_house_numbers_on_same_street():
    """Verifica che due numeri civici diversi della stessa via abbiano coordinate distinte e coerenti."""
    cache = {}
    lat1, lon1 = geocode_address("Via del Corso 184", "Roma", cache)
    lat2, lon2 = geocode_address("Via del Corso 120", "Roma", cache)

    assert lat1 is not None and lon1 is not None, "Geocodifica fallita per Via del Corso 184"
    assert lat2 is not None and lon2 is not None, "Geocodifica fallita per Via del Corso 120"

    # Le coordinate non devono coincidere (non devono essere appiattite al centro strada)
    dist = haversine_distance_meters(lat1, lon1, lat2, lon2)
    assert dist > 100.0, f"Distanza tra civico 184 e 120 troppo piccola ({dist:.1f} m): devono essere punti distinti!"
    assert dist < 1200.0, f"Distanza tra civico 184 e 120 troppo grande ({dist:.1f} m): sono sulla stessa via!"


def test_geocoding_handles_prefixes_consistently():
    """Verifica che 'Via del Corso n. 184' e 'Via del Corso 184' producano le stesse coordinate esatte."""
    cache = {}
    lat_clean, lon_clean = geocode_address("Via del Corso 184", "Roma", cache)
    lat_pref, lon_pref = geocode_address("Via del Corso n. 184", "Roma", cache)

    assert lat_clean is not None and lat_pref is not None
    assert abs(lat_clean - lat_pref) < 1e-4, "Il prefisso 'n.' non deve alterare le coordinate del civico"
    assert abs(lon_clean - lon_pref) < 1e-4, "Il prefisso 'n.' non deve alterare le coordinate del civico"


def test_geocoding_cache_includes_house_number_details():
    """Verifica che la cache memorizzi il numero civico e l'informazione di match esatto."""
    cache = {}
    geocode_address("Via del Corso 184", "Roma", cache)

    cache_key = "VIA DEL CORSO 184, ROMA, ITALY"
    assert cache_key in cache, f"Chiave {cache_key} non presente in cache"
    cached = cache[cache_key]
    assert cached["house_number"] == "184", f"Numero civico non registrato in cache: {cached.get('house_number')}"
    assert cached.get("house_number_exact") is True, "house_number_exact deve essere True per civico mappato"


if __name__ == "__main__":
    print("\n" + "=" * 65)
    print("  TEST GEOCODIFICA E GESTIONE NUMERI CIVICI")
    print("=" * 65)

    print("\n[1/4] Test parsing formati indirizzo e civico...")
    test_parse_address_and_civic_various_formats()
    print("  -> OK: Formati italiani (n., civico, virgole, composti) parsati con successo.")

    print("\n[2/4] Test distinzione civici diversi sulla stessa via...")
    test_geocoding_distinguishes_house_numbers_on_same_street()
    print("  -> OK: Civico 184 e civico 120 producono punti geografici distinti e precisi.")

    print("\n[3/4] Test equivalenza con prefisso 'n.'...")
    test_geocoding_handles_prefixes_consistently()
    print("  -> OK: 'Via del Corso n. 184' equivale a 'Via del Corso 184'.")

    print("\n[4/4] Test metadati civico in geocache...")
    test_geocoding_cache_includes_house_number_details()
    print("  -> OK: Cache registra correttamente house_number e house_number_exact.")

    print("\n" + "=" * 65)
    print("  TUTTI I TEST SUI NUMERI CIVICI SONO PASSATI CON SUCCESSO!")
    print("=" * 65 + "\n")
