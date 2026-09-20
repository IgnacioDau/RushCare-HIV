"""
End-to-end check: real database, real router, no fixtures.

    python load_sites.py      # build pep.db first
    python test_store.py

Unlike test_router.py, this one talks to SQLite. It exists to catch the failures
that unit tests with hand-built fixtures cannot see: a column renamed in the CSV,
a cost that did not load, a region whose sites have no coordinates yet.
"""

import os
import sys
from datetime import datetime, timedelta

from router import (
    OUTCOME_OK,
    OUTCOME_OUT_OF_WINDOW,
    Point,
)
from store import SiteStore

DB = "pep.db"

FENWAY_AREA = Point(42.3467, -71.0972)
MONDAY_10AM = datetime(2026, 9, 21, 10, 0)

PASSED, FAILED = [], []


def check(label, condition, detail=""):
    (PASSED if condition else FAILED).append(label)
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}"
          + (f"  -- {detail}" if detail and not condition else ""))


def main():
    if not os.path.exists(DB):
        sys.exit(f"{DB} not found. Run:  python load_sites.py")

    store = SiteStore(DB)

    print("Database health")
    for region, stats in store.health().items():
        print(f"  {region}: {stats['total']} sites, {stats['no_coords']} without "
              f"coordinates, {stats['fallbacks']} fallbacks, {stats['mobile']} mobile, "
              f"{stats['unverified']} unverified")
    print()

    print("Loading")
    boston = store.sites("boston_ma")
    check("boston_ma loads", len(boston) > 0, len(boston))
    check("costs come through",
          any(site.costs for site in boston),
          "no site has any cost attached")
    check("hours come through",
          any(site.hours.get("mon") for site in boston))
    check("fallbacks are flagged", any(s.is_fallback for s in boston))
    check("closed-community sites are flagged",
          any(s.community for s in boston),
          "no site carries a community")
    print()

    print("Presentation details")
    sample = next(s for s in boston if s.lat is not None)
    details = store.details(sample.id)
    check("a site carries an address", bool(details.get("address")), details)
    check("region_attrs parse as a dict", isinstance(details.get("region_attrs"), dict))
    print()

    print("Location picker")
    picker = store.neighborhoods("boston_ma")
    check("neighborhoods load", len(picker) >= 20, len(picker))
    check("every neighborhood has coordinates",
          all(n["lat"] and n["lon"] for n in picker))
    print()

    print("Routing against the real database")
    exposure = MONDAY_10AM - timedelta(hours=12)
    result = store.route(
        region="boston_ma",
        exposure_time=exposure,
        now=MONDAY_10AM,
        origin=FENWAY_AREA,
        coverage_scheme="uninsured",
    )
    check("returns options", result.outcome == OUTCOME_OK, result.outcome)
    check("at most five results", len(result.results) <= 5, len(result.results))
    check("a fallback is always present",
          any(c.site.is_fallback for c in result.results),
          [c.site.name for c in result.results])
    check("demo data is flagged", result.uses_demo_data is True)
    for candidate in result.results:
        info = store.details(candidate.site.id)
        print(f"    {candidate.site.name[:38]:38} {candidate.minutes_to_treatment:>4} min "
              f"${candidate.cost:>5.0f}  {info.get('phone') or 'no phone'}")
    print()

    print("Edge cases")
    stale = store.route("boston_ma", MONDAY_10AM - timedelta(hours=80), MONDAY_10AM,
                        FENWAY_AREA, "uninsured")
    check("past 72 hours short-circuits", stale.outcome == OUTCOME_OUT_OF_WINDOW,
          stale.outcome)

    try:
        store.config("atlantis")
        check("an unknown region raises", False, "no error raised")
    except ValueError:
        check("an unknown region raises", True)
    print()

    print("Campus sites")
    general = store.route("boston_ma", exposure, MONDAY_10AM, FENWAY_AREA, "uninsured")
    check("campus health is hidden from the general public",
          all(not c.site.community for c in general.results),
          [c.site.name for c in general.results])
    mit = store.route("boston_ma", exposure, MONDAY_10AM, Point(42.3612, -71.0866),
                      "uninsured", affiliation="mit")
    check("the MIT chip unlocks MIT Health",
          any(c.site.community == "mit" for c in mit.results),
          [c.site.name for c in mit.results])
    print()

    print(f"{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
