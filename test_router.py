"""
Router tests. Run with:  python test_router.py

The fixtures are a deliberately small stand-in for the real database: enough
sites to exercise every branch, few enough that a failure points at one rule.
Coordinates are real Boston ones so distances are plausible.
"""

from datetime import datetime, timedelta

from router import (
    BOSTON,
    OUTCOME_NOTHING_OPEN,
    OUTCOME_OK,
    OUTCOME_OUT_OF_AREA,
    OUTCOME_OUT_OF_WINDOW,
    MODE_EMERGENCY,
    MODE_MARGIN,
    MODE_NORMAL,
    Point,
    RegionConfig,
    Site,
    route,
)

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def hours(weekday=None, sat=None, sun=None, every=None):
    if every:
        return {d: every for d in DAYS}
    spec = {d: weekday or "closed" for d in DAYS[:5]}
    spec["sat"] = sat or "closed"
    spec["sun"] = sun or "closed"
    return spec


# --------------------------------------------------------------------------- #
# Fixtures - Boston
# --------------------------------------------------------------------------- #

BMC_ER = Site(
    id=1, name="Boston Medical Center - ER", site_type="er", region="boston_ma",
    lat=42.3350945, lon=-71.0727384, is_fallback=True,
    hours=hours(every="24h"), meds_in_hand="starter_pack", certainty=0.95,
    typical_wait_min=200, costs={"uninsured": 150, "masshealth": 0},
    serves_minors_without_parent="yes",
)

MGH_ER = Site(
    id=2, name="Massachusetts General Hospital - ER", site_type="er", region="boston_ma",
    lat=42.3628259, lon=-71.0691788, is_fallback=True,
    hours=hours(every="24h"), meds_in_hand="starter_pack", certainty=0.95,
    typical_wait_min=300, costs={"uninsured": 200, "masshealth": 0},
    serves_minors_without_parent="yes",
)

FENWAY = Site(
    id=3, name="Fenway Health", site_type="sexual_health_clinic", region="boston_ma",
    lat=42.3440746, lon=-71.0989723,
    hours=hours(weekday="08:00-19:00"), walk_in_cutoff="18:00",
    meds_in_hand="full_28_day_course", certainty=0.95, typical_wait_min=45,
    costs={"uninsured": 0, "masshealth": 0}, serves_minors_without_parent="yes",
)

FENWAY_PHARMACY = Site(  # same building as FENWAY - must be deduplicated
    id=4, name="Fenway Pharmacy", site_type="pharmacy", region="boston_ma",
    lat=42.3440746, lon=-71.0989723,
    hours=hours(weekday="08:30-18:30"),
    meds_in_hand="full_28_day_course", certainty=0.85, typical_wait_min=20,
    costs={"uninsured": 0, "masshealth": 0},
)

CVS_24H = Site(
    id=5, name="CVS Boylston (24h)", site_type="pharmacy", region="boston_ma",
    lat=42.3505234, lon=-71.0769630,
    hours=hours(every="24h"), meds_in_hand="varies_unknown", certainty=0.50,
    typical_wait_min=25, costs={"uninsured": 700, "masshealth": 0},
)

WHITTIER = Site(
    id=6, name="Whittier Street Health Center", site_type="community_health_center",
    region="boston_ma", lat=42.3329447, lon=-71.0918706,
    hours=hours(weekday="08:30-20:00", sat="09:00-17:00"), walk_in_cutoff="19:00",
    meds_in_hand="starter_pack", certainty=0.80, typical_wait_min=70,
    costs={"uninsured": 0, "masshealth": 0}, serves_minors_without_parent="yes",
)

PLANNED_PARENTHOOD = Site(
    id=7, name="Planned Parenthood", site_type="sexual_health_clinic", region="boston_ma",
    lat=42.3525745, lon=-71.1228908,
    hours=hours(weekday="07:30-18:00"), walk_in="appointment_only",
    meds_in_hand="prescription_only", certainty=0.60, typical_wait_min=60,
    costs={"uninsured": 50, "masshealth": 0},
)

BOSTON_SITES = [BMC_ER, MGH_ER, FENWAY, FENWAY_PHARMACY, CVS_24H, WHITTIER, PLANNED_PARENTHOOD]

BACK_BAY = Point(42.3505, -71.0810)
ROXBURY = Point(42.3152, -71.0914)
FENWAY_AREA = Point(42.3467, -71.0972)

# A Monday, so weekday hours apply.
MONDAY_10AM = datetime(2026, 9, 21, 10, 0)


def exposure_leaving(hours_left: float, now: datetime) -> datetime:
    return now - timedelta(hours=72 - hours_left)


PASSED = []
FAILED = []


def check(label, condition, detail=""):
    (PASSED if condition else FAILED).append(label)
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {label}" + (f"  -- {detail}" if detail and not condition else ""))


def names(result):
    return [c.site.name for c in result.results]


# --------------------------------------------------------------------------- #
# Cases
# --------------------------------------------------------------------------- #


def case_1_sunday_afternoon_uninsured():
    """Sunday 3 PM, 8h left, uninsured. Clinics closed, emergency mode:
    cost weight is 0, so the nearest always-open site wins."""
    now = datetime(2026, 9, 20, 15, 0)  # Sunday
    result = route(exposure_leaving(8, now), now, BACK_BAY, "uninsured",
                   BOSTON_SITES, BOSTON)
    check("1. mode is emergency", result.mode == MODE_EMERGENCY, str(result.mode))
    check("1. an always-open site wins",
          result.results[0].site.site_type in ("er", "pharmacy"), names(result))
    check("1. an ER is present", any(c.site.is_fallback for c in result.results),
          names(result))


def case_2_weekday_masshealth():
    """Tuesday 10 AM, 60h left, MassHealth. Everything is free on this scheme,
    so effective time alone decides and the specialised clinic should win."""
    now = MONDAY_10AM
    result = route(exposure_leaving(60, now), now, FENWAY_AREA, "masshealth",
                   BOSTON_SITES, BOSTON)
    check("2. mode is margin", result.mode == MODE_MARGIN, str(result.mode))
    check("2. Fenway wins", result.results[0].site.name.startswith("Fenway"), names(result))


def case_3_saturday_night_uninsured():
    """Saturday 2 AM, 69h left, uninsured. Waiting is allowed in margin mode,
    but the 12h cap must stop it from proposing a wait until Monday."""
    now = datetime(2026, 9, 19, 2, 0)  # Saturday
    result = route(exposure_leaving(69, now), now, ROXBURY, "uninsured",
                   BOSTON_SITES, BOSTON)
    check("3. returns options", result.outcome == OUTCOME_OK, result.outcome)
    waits = [c for c in result.results if c.waits_for_opening]
    check("3. no wait exceeds the cap",
          all(c.minutes_to_treatment <= BOSTON.max_wait_for_opening_min + c.site.typical_wait_min
              for c in waits),
          [(c.site.name, c.minutes_to_treatment) for c in waits])


def case_4_deep_emergency():
    """4h left. Only something reachable and open right now can qualify."""
    now = datetime(2026, 9, 22, 23, 0)
    result = route(exposure_leaving(4, now), now, Point(42.3612, -71.0866), "uninsured",
                   BOSTON_SITES, BOSTON)
    check("4. mode is emergency", result.mode == MODE_EMERGENCY, str(result.mode))
    check("4. every result fits inside the window",
          all(c.minutes_to_treatment + BOSTON.safety_buffer_min <= result.minutes_left
              for c in result.results))
    check("4. nothing that waits is offered",
          not any(c.waits_for_opening for c in result.results))


def case_4b_delay_outweighs_cost():
    """Monday 11 PM, 25h left, uninsured. Waiting IS permitted here and the wait
    is under the cap, yet a nearby paid ER still wins.

    This is the intended behaviour, and the arithmetic is worth stating because
    it is not obvious. Waiting nine hours costs 540 minute-equivalents. At the
    normal-mode weight of 0.5, a $150 ER visit costs 75. For waiting to win, the
    price gap would have to exceed about $1,080 (about $540 at the margin-mode
    weight of 1.0). In practice that only happens against an uninsured pharmacy.

    Consequence: whenever an always-open site is nearby, the router sends people
    now rather than telling them to wait. Medically that is the right default -
    PEP efficacy decays continuously. The waiting machinery still earns its place
    in regions with no 24/7 option in range, which is the Mexican case.

    If a future team wants money to weigh more heavily, the lever is
    RegionConfig.cost_weight, not this test."""
    now = datetime(2026, 9, 21, 23, 0)
    result = route(exposure_leaving(25, now), now, FENWAY_AREA, "uninsured",
                   BOSTON_SITES, BOSTON)
    check("4b. mode is normal", result.mode == MODE_NORMAL, str(result.mode))
    winner = result.results[0]
    check("4b. a nearby open site beats a nine-hour wait",
          not winner.waits_for_opening,
          f"{winner.site.name} waits={winner.waits_for_opening}")
    # The morning options are not merely outranked, they fall outside the score
    # cutoff: Fenway scores 595 against a best of 294, and 2x294 = 589. The app
    # should not pad a results screen with an option that much worse.
    best = result.results[0].score
    check("4b. every result stays within the score cutoff",
          all(c.score <= best * BOSTON.score_cutoff_ratio for c in result.results),
          [(c.site.name, round(c.score)) for c in result.results])


def case_4c_waiting_wins_without_a_nearby_fallback():
    """The mirror of 4b: with no always-open site in range, waiting for the
    morning is the correct recommendation rather than a dead end."""
    now = datetime(2026, 9, 21, 23, 0)
    result = route(exposure_leaving(40, now), now, FENWAY_AREA, "uninsured",
                   [FENWAY, WHITTIER], BOSTON)
    check("4c. returns options", result.outcome == OUTCOME_OK, result.outcome)
    check("4c. the winner is a morning opening",
          result.results[0].waits_for_opening,
          [(c.site.name, c.waits_for_opening) for c in result.results])


def case_5_out_of_window():
    now = MONDAY_10AM
    result = route(now - timedelta(hours=80), now, BACK_BAY, "uninsured",
                   BOSTON_SITES, BOSTON)
    check("5. outcome is OUT_OF_WINDOW", result.outcome == OUTCOME_OUT_OF_WINDOW,
          result.outcome)
    check("5. no sites are offered", result.results == [])


def case_6_walk_in_cutoff():
    """Monday 5:45 PM from Roxbury. Fenway closes walk-ins at 18:00 and is ~15
    minutes away, so it must not be offered as open on arrival."""
    now = datetime(2026, 9, 21, 17, 45)
    result = route(exposure_leaving(28, now), now, ROXBURY, "uninsured",
                   BOSTON_SITES, BOSTON)
    fenway = [c for c in result.results if c.site.id == FENWAY.id]
    check("6. Fenway is not offered as open past its walk-in cutoff",
          all(c.waits_for_opening for c in fenway),
          [(c.site.name, c.waits_for_opening) for c in fenway])


def case_7_safety_floor():
    """Even when clinics outrank every ER, an ER must still appear."""
    now = MONDAY_10AM
    result = route(exposure_leaving(60, now), now, FENWAY_AREA, "masshealth",
                   BOSTON_SITES, BOSTON)
    check("7. an ER is always present", any(c.site.is_fallback for c in result.results),
          names(result))


def case_8_deduplication():
    """Fenway clinic and Fenway pharmacy share an address: only one may appear."""
    now = MONDAY_10AM
    result = route(exposure_leaving(60, now), now, FENWAY_AREA, "masshealth",
                   BOSTON_SITES, BOSTON)
    coords = [(round(c.site.lat, 4), round(c.site.lon, 4)) for c in result.results]
    check("8. no two results share a location", len(coords) == len(set(coords)), coords)


def case_9_appointment_only_excluded():
    now = MONDAY_10AM
    result = route(exposure_leaving(60, now), now, BACK_BAY, "uninsured",
                   BOSTON_SITES, BOSTON)
    check("9. appointment-only sites never appear",
          all(c.site.walk_in != "appointment_only" for c in result.results), names(result))


def case_10_nothing_open():
    """A region whose only sites are weekday clinics, at 3 AM in emergency mode:
    no candidate qualifies, but the screen must still say what opens next."""
    now = datetime(2026, 9, 21, 3, 0)
    weekday_only = [FENWAY, WHITTIER]
    result = route(exposure_leaving(10, now), now, FENWAY_AREA, "uninsured",
                   weekday_only, BOSTON)
    check("10. outcome is NOTHING_OPEN", result.outcome == OUTCOME_NOTHING_OPEN,
          result.outcome)
    check("10. the next opening is reported", result.next_opening is not None)
    if result.next_opening:
        check("10. it names a time", result.next_opening.opens_at is not None,
              str(result.next_opening.opens_at))


def case_11_out_of_area():
    now = MONDAY_10AM
    far_away = Point(40.7128, -74.0060)  # New York
    result = route(exposure_leaving(60, now), now, far_away, "uninsured",
                   BOSTON_SITES, BOSTON)
    check("11. outcome is OUT_OF_AREA", result.outcome == OUTCOME_OUT_OF_AREA,
          result.outcome)


def case_12_mobile_units_skipped():
    now = MONDAY_10AM
    mobile = Site(id=99, name="Caravana de la Salud", site_type="imss_bienestar_mobile",
                  region="mexico", lat=42.3450, lon=-71.0900, is_mobile=True,
                  hours=hours(every="24h"), certainty=0.6, costs={"none": 0})
    result = route(exposure_leaving(60, now), now, FENWAY_AREA, "masshealth",
                   BOSTON_SITES + [mobile], BOSTON)
    check("12. mobile units are never offered",
          all(not c.site.is_mobile for c in result.results), names(result))


def case_13_unknown_scheme_is_not_free():
    """An unrecognised coverage scheme must fall back to the highest cost we
    hold, never to zero."""
    now = MONDAY_10AM
    result = route(exposure_leaving(60, now), now, BACK_BAY, "some_unknown_plan",
                   BOSTON_SITES, BOSTON)
    cvs = [c for c in result.results if c.site.id == CVS_24H.id]
    check("13. unknown scheme does not price a site at zero",
          all(c.cost > 0 for c in cvs) if cvs else True)


def case_15_minor_preference():
    """Under-18 nudges ranking toward sites known to see minors alone, without
    filtering anything out."""
    now = MONDAY_10AM
    unknown_policy = Site(
        id=300, name="Clinic with unknown minor policy",
        site_type="community_health_center", region="boston_ma",
        lat=42.3468, lon=-71.0975, hours=hours(weekday="08:00-19:00"),
        meds_in_hand="full_28_day_course", certainty=0.95, typical_wait_min=40,
        costs={"uninsured": 0, "masshealth": 0}, serves_minors_without_parent="unknown",
    )
    sites = [s for s in BOSTON_SITES if s.id != FENWAY_PHARMACY.id] + [unknown_policy]
    adult = route(exposure_leaving(60, now), now, FENWAY_AREA, "masshealth",
                  sites, BOSTON, under_18=False)
    minor = route(exposure_leaving(60, now), now, FENWAY_AREA, "masshealth",
                  sites, BOSTON, under_18=True)
    check("15. the unknown-policy clinic leads for an adult",
          adult.results[0].site.id == unknown_policy.id, names(adult))
    check("15. a minor is steered to the known-friendly site",
          minor.results[0].site.serves_minors_without_parent == "yes", names(minor))
    check("15. the unknown-policy site is still offered, not removed",
          any(c.site.id == unknown_policy.id for c in minor.results), names(minor))


def case_16_eligibility_is_enforced():
    """Sites that would turn the person away are never offered, however well
    they score. This is the failure the fixture tests missed and the real
    database exposed: a paediatric ER was being inserted as an adult's fallback,
    and a campus-only clinic was topping the list for the general public."""
    now = MONDAY_10AM

    childrens = Site(
        id=400, name="Boston Children's - ER", site_type="er", region="boston_ma",
        lat=42.3375472, lon=-71.1061959, is_fallback=True, hours=hours(every="24h"),
        meds_in_hand="starter_pack", certainty=0.92, typical_wait_min=180,
        costs={"uninsured": 150, "masshealth": 0},
        serves_minors_without_parent="yes", max_age=18,
    )
    campus = Site(
        id=401, name="MIT Health (campus only)", site_type="university_health",
        region="boston_ma", lat=42.3470, lon=-71.0975, hours=hours(weekday="08:00-20:00"),
        meds_in_hand="starter_pack", certainty=0.85, typical_wait_min=40,
        costs={"uninsured": 0, "masshealth": 0}, must_be_existing_patient="yes",
        community="mit",
    )
    adults_only = Site(
        id=402, name="Adults-only clinic", site_type="sexual_health_clinic",
        region="boston_ma", lat=42.3460, lon=-71.0960, hours=hours(weekday="08:00-19:00"),
        meds_in_hand="full_28_day_course", certainty=0.95, typical_wait_min=30,
        costs={"uninsured": 0, "masshealth": 0}, min_age=18,
    )
    sites = BOSTON_SITES + [childrens, campus, adults_only]

    adult = route(exposure_leaving(60, now), now, FENWAY_AREA, "uninsured",
                  sites, BOSTON)
    check("16. a paediatric ER is not offered to an adult",
          all(c.site.id != childrens.id for c in adult.results), names(adult))
    check("16. a campus-only site is not offered to the general public",
          all(c.site.id != campus.id for c in adult.results), names(adult))
    check("16. an adult still gets a fallback",
          any(c.site.is_fallback for c in adult.results), names(adult))

    member = route(exposure_leaving(60, now), now, FENWAY_AREA, "uninsured",
                   sites, BOSTON, affiliation="mit")
    check("16. the campus site returns for someone in that community",
          any(c.site.id == campus.id for c in member.results), names(member))

    other = route(exposure_leaving(60, now), now, FENWAY_AREA, "uninsured",
                  sites, BOSTON, affiliation="harvard")
    check("16. a different campus does not unlock it",
          all(c.site.id != campus.id for c in other.results), names(other))

    patient = route(exposure_leaving(60, now), now, FENWAY_AREA, "uninsured",
                    sites, BOSTON, is_existing_patient=True)
    check("16. being an existing patient elsewhere does not unlock a campus site",
          all(c.site.id != campus.id for c in patient.results), names(patient))

    minor = route(exposure_leaving(60, now), now, FENWAY_AREA, "uninsured",
                  sites, BOSTON, under_18=True)
    check("16. a minor may be sent to the paediatric ER",
          any(c.site.id == childrens.id for c in minor.results)
          or all(c.site.serves_minors_without_parent == "yes" for c in minor.results),
          names(minor))
    check("16. an adults-only site is not offered to a minor",
          all(c.site.id != adults_only.id for c in minor.results), names(minor))


def case_17_ineligible_sites_cannot_become_plan_b():
    """The safety floor must not smuggle in a site the person cannot use."""
    now = datetime(2026, 9, 20, 3, 0)  # Sunday, everything else shut
    childrens = Site(
        id=400, name="Boston Children's - ER", site_type="er", region="boston_ma",
        lat=42.3375472, lon=-71.1061959, is_fallback=True, hours=hours(every="24h"),
        meds_in_hand="starter_pack", certainty=0.92, typical_wait_min=180,
        costs={"uninsured": 150, "masshealth": 0}, max_age=18,
    )
    result = route(exposure_leaving(40, now), now, FENWAY_AREA, "uninsured",
                   [childrens, FENWAY], BOSTON)
    if result.outcome == OUTCOME_OK:
        check("17. an ineligible site is never the fallback",
              result.fallback is None or result.fallback.site.id != childrens.id,
              result.fallback.site.name if result.fallback else None)
        check("17. it does not appear in results either",
              all(c.site.id != childrens.id for c in result.results), names(result))
    else:
        check("17. nothing eligible is open, reported honestly",
              result.outcome == OUTCOME_NOTHING_OPEN, result.outcome)


def main():
    print("Router tests\n")
    for case in [
        case_1_sunday_afternoon_uninsured,
        case_2_weekday_masshealth,
        case_3_saturday_night_uninsured,
        case_4_deep_emergency,
        case_4b_delay_outweighs_cost,
        case_4c_waiting_wins_without_a_nearby_fallback,
        case_5_out_of_window,
        case_6_walk_in_cutoff,
        case_7_safety_floor,
        case_8_deduplication,
        case_9_appointment_only_excluded,
        case_10_nothing_open,
        case_11_out_of_area,
        case_12_mobile_units_skipped,
        case_13_unknown_scheme_is_not_free,
        case_15_minor_preference,
        case_16_eligibility_is_enforced,
        case_17_ineligible_sites_cannot_become_plan_b,
    ]:
        print(case.__doc__.strip().splitlines()[0] if case.__doc__ else case.__name__)
        case()
        print()

    print(f"{len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        for label in FAILED:
            print(f"  failed: {label}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
