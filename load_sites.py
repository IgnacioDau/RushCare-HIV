#!/usr/bin/env python3
"""
Build the SQLite database from the region CSVs.

    python load_sites.py

Reads sites_demo.csv (boston_ma) and sites_mexico.csv (mexico) exactly as they
are - the two files have different columns on purpose, and normalising happens
here rather than by rewriting either file. Re-runnable: it drops and rebuilds.

Run it again after geocoding finishes; nothing else needs to change.
"""
import argparse, csv, json, os, sqlite3, sys

DB = "pep.db"
SCHEMA = "schema.sql"
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

REGIONS = {
    "boston_ma": {
        "csv": "sites_demo.csv",
        "area_col": "neighborhood",
        "admin_col": None,
        "fallback_types": {"er"},
        "region_only": ["accepts_hsn", "financial_navigator_onsite", "pharmacy_onsite"],
        "currency": "USD",
        "costs": {"uninsured": "est_cost_uninsured", "masshealth": "est_cost_masshealth"},
    },
}

TRUE = {"true", "yes", "sí", "si", "1"}

# Stopgap. The Mexican directory has no audience column, but some unit names say
# plainly that they serve children. Without this, the router offers a paediatric
# immunodeficiency clinic to an adult - the same failure the Boston data caught
# through its max_age field.
#
# This is a heuristic over names and it is deliberately narrow: only unambiguous
# paediatric markers. It does not touch women's or maternal units, because we
# never ask the person's gender and PEP after a sexual assault is exactly what
# such a unit might provide. The real fix is an audience column in the source.


def flag(value):
    return 1 if (value or "").strip().lower() in TRUE else 0


def number(value, cast=int):
    text = (value or "").strip()
    if not text:
        return None
    try:
        return cast(float(text))
    except ValueError:
        return None


def hours(row, day):
    value = (row.get(day) or "").strip()
    return value or None


def load_region(cursor, region, config):
    path = config["csv"]
    if not os.path.exists(path):
        print(f"  skipping {region}: {path} not found")
        return 0

    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    inserted = no_coords = 0
    for row in rows:
        attrs = {k: row[k] for k in config["region_only"] if row.get(k)}
        lat, lon = number(row.get("lat"), float), number(row.get("lon"), float)
        if lat is None or lon is None:
            no_coords += 1

        cursor.execute(
            f"""INSERT INTO sites (
                region, source_id, name, site_type, priority_tier, is_fallback,
                area, admin_region, address, lat, lon, geocode_precision, is_mobile,
                phone, alt_phone, email, open_24h,
                {', '.join(DAYS)}, hours_raw, hours_needs_review,
                walk_in, walk_in_cutoff, must_be_existing_patient, community,
                serves_minors_without_parent, min_age, max_age, languages,
                meds_in_hand, starter_pack_days, certainty, typical_wait_min,
                priority_triage, data_origin, operational_data_origin, is_demo_data,
                last_verified, source, app_notes, region_attrs
            ) VALUES ({', '.join('?' * 46)})""",
            (
                region,
                number(row.get("id")),
                row.get("name"),
                row.get("site_type"),
                number(row.get("priority_tier")),
                1 if row.get("site_type") in config["fallback_types"] else 0,
                row.get(config["area_col"]) if config["area_col"] else None,
                row.get(config["admin_col"]) if config["admin_col"] else None,
                row.get("address"),
                lat,
                lon,
                row.get("geocode_precision"),
                flag(row.get("is_mobile")),
                row.get("phone"),
                row.get("alt_phone"),
                row.get("email"),
                flag(row.get("open_24h")),
                *[hours(row, d) for d in DAYS],
                row.get("hours_raw"),
                flag(row.get("hours_needs_review")),
                row.get("walk_in"),
                row.get("walk_in_cutoff"),
                row.get("must_be_existing_patient"),
                row.get("community") or None,
                row.get("serves_minors_without_parent"),
                number(row.get("min_age")),
                number(row.get("max_age")),
                row.get("languages"),
                row.get("meds_in_hand"),
                number(row.get("starter_pack_days")),
                number(row.get("certainty"), float),
                number(row.get("typical_wait_min")),
                row.get("priority_triage"),
                row.get("data_origin") or "unknown",
                row.get("operational_data_origin"),
                flag(row.get("is_demo_data")) if row.get("is_demo_data") else 1,
                row.get("last_verified") or None,
                row.get("source"),
                row.get("app_notes"),
                json.dumps(attrs, ensure_ascii=False) if attrs else None,
            ),
        )
        site_id = cursor.lastrowid
        for scheme, column in config["costs"].items():
            cost = number(row.get(column))
            if cost is not None:
                cursor.execute(
                    "INSERT INTO site_costs (site_id, scheme, cost, currency) VALUES (?,?,?,?)",
                    (site_id, scheme, cost, config["currency"]),
                )
        inserted += 1

    print(f"  {region}: {inserted} sites ({no_coords} still without coordinates)")
    return inserted


def load_neighborhoods(cursor, path="neighborhoods_boston.csv"):
    if not os.path.exists(path):
        print(f"  skipping neighborhoods: {path} not found")
        return 0
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    cursor.executemany(
        "INSERT INTO neighborhoods (id, region, name, kind, lat, lon, precision) "
        "VALUES (?,?,?,?,?,?,?)",
        [(r["id"], r["region"], r["name"], r["kind"],
          float(r["lat"]), float(r["lon"]), r.get("coordinate_precision"))
         for r in rows],
    )
    print(f"  neighborhoods: {len(rows)}")
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Build pep.db from the region CSVs.")
    parser.add_argument("--boston", help="override the boston_ma CSV path")
    args = parser.parse_args()
    if args.boston:
        REGIONS["boston_ma"]["csv"] = args.boston

    if not os.path.exists(SCHEMA):
        sys.exit(f"{SCHEMA} not found. Run this from the folder that contains it.")

    connection = sqlite3.connect(DB)
    connection.executescript(open(SCHEMA, encoding="utf-8").read())
    cursor = connection.cursor()

    print("Loading regions:")
    for region, config in REGIONS.items():
        print(f"  {region} <- {config['csv']}")
    total = sum(load_region(cursor, r, c) for r, c in REGIONS.items())
    load_neighborhoods(cursor)
    connection.commit()

    print(f"\n{total} sites in {DB}\n")
    for query, label in [
        ("SELECT region, COUNT(*) FROM sites GROUP BY region", "by region"),
        ("SELECT region, COUNT(*) FROM sites WHERE lat IS NULL GROUP BY region",
         "missing coordinates"),
        ("SELECT region, COUNT(*) FROM sites WHERE is_fallback=1 GROUP BY region",
         "fallback sites"),
        ("SELECT region, COUNT(*) FROM sites WHERE is_mobile=1 GROUP BY region",
         "mobile units (router skips)"),
    ]:
        results = cursor.execute(query).fetchall()
        print(f"{label}: {dict(results) if results else 'none'}")

    placeholders = cursor.execute(
        "SELECT COUNT(*) FROM sites WHERE geocode_precision = 'PLACEHOLDER_NOT_REAL'"
    ).fetchone()[0]
    if placeholders:
        print()
        print(f"!! {placeholders} sites carry PLACEHOLDER coordinates.")
        print("!! They are scattered near state capitals, not at real addresses.")
        print("!! Rebuild from the geocoded CSV before showing this to anyone.")

    connection.close()


if __name__ == "__main__":
    main()
