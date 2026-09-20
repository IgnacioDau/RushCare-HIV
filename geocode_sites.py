#!/usr/bin/env python3
"""
Fill the lat/lon columns of a sites CSV using Nominatim (OpenStreetMap).

Run ONCE, locally, and commit the result. This is not a runtime dependency:
the app must never geocode while a user is waiting.

    pip install requests
    python geocode_sites.py sites_mexico.csv

Useful flags:
    --dry-run     show the queries that would be sent, contact nothing
    --limit N     stop after N rows (good for a first test)
    --force       re-geocode rows that already have coordinates

Safe to stop and restart: results are cached in .geocode_cache.json and the CSV
is saved every 20 rows.

Nominatim's usage policy requires a real User-Agent identifying your project and
at most one request per second. Both are enforced below. Do not remove them.
"""
import csv, sys, time, json, os, argparse

try:
    import requests
except ImportError:
    sys.exit("Missing dependency. Run:  pip install requests")

ENDPOINT = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "RushCareHIV-HackMIT/1.0 (contact: CHANGE-ME@example.com)"  # <-- EDIT THIS
CACHE_PATH = ".geocode_cache.json"
SLEEP_SECONDS = 1.1
SAVE_EVERY = 20

COUNTRY_BY_REGION = {"mexico": "mx", "boston_ma": "us"}

# Last-resort fallback, resolved locally with no request at all. A site pinned to
# its state capital is wrong by tens or hundreds of kilometres - but a site with
# no coordinates is invisible to the router, which is worse: the person is told
# nothing exists near them when a unit is ten minutes away. Rows that land here
# are marked state_centroid so the app can show them without a distance.
STATE_CENTROIDS = {
    "Aguascalientes": (21.8853, -102.2916), "Baja California": (32.6245, -115.4523),
    "Baja California Sur": (24.1426, -110.3128), "CDMX": (19.4326, -99.1332),
    "Campeche": (19.8301, -90.5349), "Chiapas": (16.7531, -93.1156),
    "Chihuahua": (28.6330, -106.0691), "Coahuila": (25.4232, -101.0053),
    "Colima": (19.2433, -103.7240), "Durango": (24.0277, -104.6532),
    "Estado de México": (19.2826, -99.6557), "Guanajuato": (21.0190, -101.2574),
    "Guerrero": (17.5506, -99.5024), "Hidalgo": (20.1011, -98.7591),
    "Jalisco": (20.6597, -103.3496), "Michoacán": (19.7008, -101.1844),
    "Morelos": (18.9242, -99.2216), "Nayarit": (21.5042, -104.8946),
    "Nuevo León": (25.6866, -100.3161), "Oaxaca": (17.0732, -96.7266),
    "Puebla": (19.0414, -98.2063), "Querétaro": (20.5888, -100.3899),
    "Quintana Roo": (18.5002, -88.2961), "San Luis Potosí": (22.1565, -100.9855),
    "Sinaloa": (24.8091, -107.3940), "Sonora": (29.0729, -110.9559),
    "Tabasco": (17.9892, -92.9475), "Tamaulipas": (23.7369, -99.1411),
    "Tlaxcala": (19.3139, -98.2404), "Veracruz": (19.5438, -96.9102),
    "Yucatán": (20.9674, -89.5926), "Zacatecas": (22.7709, -102.5832),
}


def load_cache():
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("Cache file was corrupt; starting a fresh one.")
    return {}


def save_cache(cache):
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, CACHE_PATH)


def build_queries(row):
    """Progressively coarser queries. Empty fields are skipped, so a row with only
    a name and a state still gets a usable attempt."""
    def clean(key):
        return (row.get(key) or "").strip()

    address, locality = clean("address"), clean("locality")
    state, name = clean("state"), clean("name")
    neighborhood = clean("neighborhood")
    out = []

    def add(label, parts):
        parts = [p for p in parts if p]
        if len(parts) >= 2:
            out.append((label, ", ".join(parts)))

    # Mexican addresses often read "s/n" (no street number) or "between X and Y",
    # which Nominatim cannot resolve. Trying the colonia alone rescues some.
    cleaned = address.replace(" s/n", " ").replace(" S/N", " ")
    add("full_address", [cleaned, locality or neighborhood, state])
    if "," in cleaned:
        add("address_tail", [cleaned.rsplit(",", 1)[-1].strip(), locality, state])
    add("name_and_place", [name, locality or neighborhood, state])
    add("name_and_state", [name, state])
    add("locality", [locality or neighborhood, state])

    seen, unique = set(), []
    for label, q in out:
        if q not in seen:
            seen.add(q)
            unique.append((label, q))
    return unique


def geocode(query, country, cache, session):
    key = f"{country}|{query}"
    if key in cache:
        return cache[key], True
    resp = session.get(
        ENDPOINT,
        params={"q": query, "format": "json", "limit": 1, "countrycodes": country},
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    if resp.status_code == 429:
        print("  rate limited — pausing 60s")
        time.sleep(60)
        return geocode(query, country, cache, session)
    resp.raise_for_status()
    data = resp.json()
    result = [data[0]["lat"], data[0]["lon"]] if data else None
    cache[key] = result
    time.sleep(SLEEP_SECONDS)
    return result, False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default="sites_mexico.csv")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if not args.dry_run and "CHANGE-ME" in USER_AGENT:
        sys.exit("Edit USER_AGENT at the top of this file to include a real contact "
                 "address. Nominatim blocks anonymous bulk requests.")

    with open(args.path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fields = list(reader.fieldnames)

    if not rows:
        sys.exit("That CSV has no rows.")
    for extra in ("geocode_precision", "geocode_query"):
        if extra not in fields:
            fields.append(extra)

    todo = [r for r in rows if args.force or not (r.get("lat") or "").strip()]
    if args.limit:
        todo = todo[: args.limit]

    print(f"{len(rows)} rows in file, {len(todo)} to locate.")
    if not args.dry_run:
        mins = len(todo) * 1.5 * SLEEP_SECONDS / 60
        print(f"Rough estimate: {mins:.0f} minutes. Safe to stop and rerun.\n")

    cache = load_cache()
    session = requests.Session()
    hits = misses = 0

    for n, row in enumerate(todo, 1):
        country = COUNTRY_BY_REGION.get((row.get("region") or "").strip(), "mx")
        queries = build_queries(row)
        row["geocode_precision"] = "none"
        row["geocode_query"] = ""

        if args.dry_run:
            print(f"[{n}] {row.get('name','')[:40]}")
            for label, q in queries:
                print(f"      {label}: {q}")
            continue

        for label, query in queries:
            try:
                found, cached = geocode(query, country, cache, session)
            except Exception as exc:
                print(f"  [{n}] error on '{query[:50]}': {exc}")
                found = None
            if found:
                row["lat"], row["lon"] = found
                row["geocode_precision"] = label
                row["geocode_query"] = query
                hits += 1
                break
        else:
            centroid = STATE_CENTROIDS.get((row.get("state") or "").strip())
            if centroid:
                row["lat"], row["lon"] = str(centroid[0]), str(centroid[1])
                row["geocode_precision"] = "state_centroid"
                row["geocode_query"] = f"(local fallback) {row.get('state')}"
            misses += 1

        mark = row["geocode_precision"]
        print(f"[{n}/{len(todo)}] {row.get('name','')[:42]:42} -> {mark}")

        if n % SAVE_EVERY == 0:
            save_cache(cache)
            write(args.path, fields, rows)
            print(f"  ...saved ({n}/{len(todo)})")

    if args.dry_run:
        return

    save_cache(cache)
    write(args.path, fields, rows)
    print(f"\nDone. {hits} located by lookup, {misses} fell back to a state centroid.")
    breakdown = {}
    for row in rows:
        key = row.get("geocode_precision") or "none"
        breakdown[key] = breakdown.get(key, 0) + 1
    print("\nPrecision breakdown:")
    for key in sorted(breakdown, key=lambda k: -breakdown[k]):
        print(f"  {key:16} {breakdown[key]}")
    print("\nHow the app must treat each level:")
    print("  full_address / address_tail / name_and_place -> a real distance, shown normally")
    print("  locality / name_and_state                    -> town-level; distance is rough")
    print("  state_centroid                               -> location unknown; the app must")
    print("                                                  show these without a distance")
    print("  none                                         -> invisible to the router entirely")


def write(path, fields, rows):
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    os.replace(tmp, path)


if __name__ == "__main__":
    main()
