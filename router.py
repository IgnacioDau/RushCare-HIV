"""
PEP router.

A pure function. No I/O, no clock reads, no network. Everything it needs arrives
as an argument, so it is unit-testable and the demo is reproducible.

    result = route(
        exposure_time=datetime(...),
        now=datetime(...),
        origin=Point(lat, lon),
        coverage_scheme="uninsured",
        sites=[...],
        config=BOSTON,
    )

Units: minutes for time, local currency for cost, decimal degrees for coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, time as clock_time
from math import asin, cos, radians, sin, sqrt
from typing import Callable, Iterable, Optional

# --------------------------------------------------------------------------- #
# Vocabulary
# --------------------------------------------------------------------------- #

PEP_WINDOW_HOURS = 72

MODE_EMERGENCY = "emergency"
MODE_NORMAL = "normal"
MODE_MARGIN = "margin"

OUTCOME_OK = "OK"
OUTCOME_OUT_OF_WINDOW = "OUT_OF_WINDOW"
OUTCOME_OUT_OF_AREA = "OUT_OF_AREA"
OUTCOME_NOTHING_OPEN = "NOTHING_OPEN"

WALK_IN_OK = "walk_in_ok"
APPOINTMENT_ONLY = "appointment_only"
SAME_DAY_APPOINTMENT = "same_day_appointment"

NO_PEP = "no_pep"

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
CLOSED = "closed"
ALL_DAY = "24h"


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Point:
    lat: float
    lon: float


@dataclass
class Site:
    id: int
    name: str
    site_type: str
    region: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    is_fallback: bool = False
    is_mobile: bool = False

    # hours: "HH:MM-HH:MM" | "24h" | "closed" | None (unknown)
    hours: dict = field(default_factory=dict)
    walk_in: str = WALK_IN_OK
    walk_in_cutoff: Optional[str] = None

    meds_in_hand: str = "varies_unknown"
    certainty: float = 0.5
    typical_wait_min: int = 60

    costs: dict = field(default_factory=dict)  # scheme -> amount

    # Eligibility. These are not preferences: a site that will turn the person
    # away must never be offered, however well it scores.
    serves_minors_without_parent: str = "unknown"
    must_be_existing_patient: str = "unknown"   # yes | no | unknown
    community: Optional[str] = None             # "mit", "harvard": a closed
                                                # community, not merely a site
                                                # that prefers its own patients
    min_age: Optional[int] = None
    max_age: Optional[int] = None               # e.g. 18 for a paediatric ER

    is_demo_data: bool = True
    priority_tier: int = 3

    # How well we know where this site is. "state_centroid" means we do not:
    # the row is kept so the site can still be reached by phone, but it must
    # never be ranked as though its distance were known.

    @property
    def point(self) -> Optional[Point]:
        if self.lat is None or self.lon is None:
            return None
        return Point(self.lat, self.lon)


@dataclass(frozen=True)
class RegionConfig:
    id: str
    default_language: str = "en"

    # mode boundaries, in hours of window remaining
    emergency_max_h: int = 20
    normal_max_h: int = 30

    # USD-equivalent minutes per unit of currency. NOTE: these are currency
    # dependent. A weight of 1.0 against MXN is not the same trade-off as 1.0
    # against USD; retune per region rather than copying the Boston numbers.
    cost_weight: dict = field(
        default_factory=lambda: {MODE_EMERGENCY: 0.0, MODE_NORMAL: 0.5, MODE_MARGIN: 1.0}
    )

    allow_waiting: dict = field(
        default_factory=lambda: {MODE_EMERGENCY: False, MODE_NORMAL: True, MODE_MARGIN: True}
    )

    safety_buffer_min: int = 120
    max_wait_for_opening_min: int = 720
    max_distance_km: float = 50.0

    # used only when no routing provider is supplied
    urban_speed_kmh: float = 20.0
    street_factor: float = 1.3

    # Precision levels that are too coarse to rank on distance. Sites at these
    # levels are returned separately, phone first, with no travel time shown.

    results_visible: int = 3
    results_expanded: int = 5
    score_cutoff_ratio: float = 2.0

    # minutes added to a site that is not known to see minors unaccompanied,
    # applied only when the person said they are under 18. A nudge, not a filter:
    # excluding these outright could leave a minor with nothing.
    unknown_minor_policy_penalty_min: int = 45


BOSTON = RegionConfig(id="boston_ma", default_language="en")


@dataclass
class Candidate:
    site: Site
    minutes_to_treatment: int
    effective_minutes: float
    cost: float
    score: float
    waits_for_opening: bool
    opens_at: Optional[datetime]
    travel_minutes: int


@dataclass
class RouteResult:
    outcome: str
    mode: Optional[str] = None
    minutes_left: Optional[int] = None
    results: list = field(default_factory=list)
    # Sites in the person's area whose exact location is unknown. Not ranked and
    # shown without a distance, but listed so a real unit is never hidden just
    # because geocoding failed on it.
    fallback: Optional[Candidate] = None
    next_opening: Optional[Candidate] = None
    uses_demo_data: bool = False
    notes: list = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Geometry and time
# --------------------------------------------------------------------------- #


def haversine_km(a: Point, b: Point) -> float:
    radius = 6371.0
    dlat = radians(b.lat - a.lat)
    dlon = radians(b.lon - a.lon)
    h = sin(dlat / 2) ** 2 + cos(radians(a.lat)) * cos(radians(b.lat)) * sin(dlon / 2) ** 2
    return 2 * radius * asin(sqrt(h))


def estimate_travel_minutes(origin: Point, site: Site, config: RegionConfig) -> Optional[int]:
    """Fallback used when no routing provider is available. Swapping in a real
    routing matrix replaces this and nothing else."""
    if site.point is None:
        return None
    km = haversine_km(origin, site.point) * config.street_factor
    return max(1, round(km / config.urban_speed_kmh * 60))


def _parse_clock(text: str) -> Optional[clock_time]:
    try:
        hour, minute = text.strip().split(":")
        return clock_time(int(hour), int(minute))
    except (ValueError, AttributeError):
        return None


def _day_hours(site: Site, moment: datetime) -> Optional[str]:
    return site.hours.get(DAYS[moment.weekday()])


def is_open_at(site: Site, moment: datetime) -> bool:
    spec = (_day_hours(site, moment) or "").strip()
    if not spec or spec == CLOSED:
        return False
    if spec == ALL_DAY:
        return True
    if "-" not in spec:
        return False
    opens, closes = (_parse_clock(p) for p in spec.split("-", 1))
    if opens is None or closes is None:
        return False
    current = moment.time()
    if closes <= opens:  # spans midnight
        return current >= opens or current < closes
    return opens <= current < closes


def accepts_at(site: Site, moment: datetime) -> bool:
    """Open AND still taking someone who has no appointment."""
    if site.walk_in == APPOINTMENT_ONLY:
        return False
    if not is_open_at(site, moment):
        return False
    if site.walk_in_cutoff:
        cutoff = _parse_clock(site.walk_in_cutoff)
        if cutoff and moment.time() > cutoff and _day_hours(site, moment) != ALL_DAY:
            return False
    return True


def next_acceptance(site: Site, after: datetime, horizon_days: int = 8) -> Optional[datetime]:
    """First moment from `after` at which the site would take a walk-in.
    Scans in 15-minute steps; the horizon covers a full week plus a day so a
    site open one day a week is still found."""
    if site.walk_in == APPOINTMENT_ONLY:
        return None
    step = timedelta(minutes=15)
    moment = after.replace(second=0, microsecond=0)
    moment += timedelta(minutes=(-moment.minute) % 15)
    limit = after + timedelta(days=horizon_days)
    while moment <= limit:
        if accepts_at(site, moment):
            return moment
        moment += step
    return None


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #


def mode_for(minutes_left: int, config: RegionConfig) -> str:
    hours_left = minutes_left / 60
    if hours_left < config.emergency_max_h:
        return MODE_EMERGENCY
    if hours_left <= config.normal_max_h:
        return MODE_NORMAL
    return MODE_MARGIN


def cost_for(site: Site, scheme: str) -> float:
    if scheme in site.costs:
        return float(site.costs[scheme])
    # An unknown scheme must never look free. Fall back to the most expensive
    # figure we hold for the site.
    return float(max(site.costs.values())) if site.costs else 0.0


def is_eligible(
    site: Site,
    under_18: bool,
    is_existing_patient: bool,
    affiliation: Optional[str] = None,
) -> bool:
    """Would this site actually see this person?

    Separate from scoring on purpose. Being turned away at the door costs the
    whole trip, and in a 72-hour window that is the most expensive failure the
    app can cause. Only refusals we can prove are applied; anything uncertain
    stays in and is handled by scoring.
    """
    # A campus health service: open only to that community, and to nobody else
    # however close or well-scoring it is. Kept separate from the
    # existing-patient rule below, so a "I study at MIT" answer never unlocks a
    # community health centre that simply prefers its own patients.
    if site.community:
        return site.community == affiliation

    if site.must_be_existing_patient == "yes" and not is_existing_patient:
        return False

    # A paediatric hospital, for someone who told us they are not a minor.
    # 18 is the usual cutoff; the bound is read from data, not hardcoded per site.
    if not under_18 and site.max_age is not None and site.max_age <= 18:
        return False

    # A site with a minimum age, for someone who told us they are under 18. We
    # do not know their exact age, so only a bound above 18 can rule them out.
    if under_18 and site.min_age is not None and site.min_age >= 18:
        return False

    return True


def _build_candidate(
    site: Site,
    origin: Point,
    now: datetime,
    mode: str,
    config: RegionConfig,
    scheme: str,
    travel_provider: Optional[Callable[[Point, Site], Optional[int]]],
    under_18: bool = False,
    is_existing_patient: bool = False,
    affiliation: Optional[str] = None,
) -> Optional[Candidate]:
    if site.is_mobile or site.meds_in_hand == NO_PEP or site.point is None:
        return None
    if not is_eligible(site, under_18, is_existing_patient, affiliation):
        return None

    travel = (
        travel_provider(origin, site) if travel_provider else estimate_travel_minutes(origin, site, config)
    )
    if travel is None:
        return None
    if haversine_km(origin, site.point) > config.max_distance_km:
        return None

    arrival = now + timedelta(minutes=travel)
    if accepts_at(site, arrival):
        minutes = travel + site.typical_wait_min
        waits, opens_at = False, None
    else:
        if not config.allow_waiting[mode]:
            return None
        opens_at = next_acceptance(site, arrival)
        if opens_at is None:
            return None
        wait = (opens_at - now).total_seconds() / 60
        if wait > config.max_wait_for_opening_min:
            return None
        minutes = round(wait) + site.typical_wait_min
        waits = True

    return Candidate(
        site=site,
        minutes_to_treatment=int(minutes),
        effective_minutes=float(minutes),  # adjusted once plan B is known
        cost=cost_for(site, scheme),
        score=0.0,
        waits_for_opening=waits,
        opens_at=opens_at,
        travel_minutes=travel,
    )


def _dedupe_same_place(candidates: list) -> list:
    """A clinic and the pharmacy inside the same building should not take two of
    three result slots. Keeps the better-scoring member of each location."""
    best = {}
    for candidate in candidates:
        key = (round(candidate.site.lat, 4), round(candidate.site.lon, 4))
        if key not in best or candidate.score < best[key].score:
            best[key] = candidate
    return sorted(best.values(), key=lambda c: c.score)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def route(
    exposure_time: datetime,
    now: datetime,
    origin: Point,
    coverage_scheme: str,
    sites: Iterable[Site],
    config: RegionConfig,
    under_18: bool = False,
    is_existing_patient: bool = False,
    affiliation: Optional[str] = None,
    travel_provider: Optional[Callable[[Point, Site], Optional[int]]] = None,
) -> RouteResult:
    minutes_left = int(PEP_WINDOW_HOURS * 60 - (now - exposure_time).total_seconds() / 60)
    if minutes_left <= 0:
        return RouteResult(outcome=OUTCOME_OUT_OF_WINDOW, minutes_left=minutes_left)

    sites = list(sites)
    mode = mode_for(minutes_left, config)

    located = [s for s in sites if s.point is not None and not s.is_mobile]
    if located and all(haversine_km(origin, s.point) > config.max_distance_km for s in located):
        return RouteResult(
            outcome=OUTCOME_OUT_OF_AREA, mode=mode, minutes_left=minutes_left
        )

    def feasible(candidate: Candidate) -> bool:
        return candidate.minutes_to_treatment + config.safety_buffer_min <= minutes_left

    candidates = []
    for site in sites:
        candidate = _build_candidate(
            site, origin, now, mode, config, coverage_scheme, travel_provider,
            under_18=under_18, is_existing_patient=is_existing_patient,
            affiliation=affiliation,
        )
        if candidate and feasible(candidate):
            candidates.append(candidate)

    # Plan B: the nearest feasible fallback site. Its time is what a failed visit
    # elsewhere actually costs the person, which is why low certainty is priced
    # in minutes rather than as an abstract penalty.
    fallbacks = [c for c in candidates if c.site.is_fallback]
    plan_b = min(fallbacks, key=lambda c: c.minutes_to_treatment) if fallbacks else None

    if not candidates:
        return RouteResult(
            outcome=OUTCOME_NOTHING_OPEN,
            mode=mode,
            minutes_left=minutes_left,
            next_opening=_soonest_opening(
                sites, origin, now, config, coverage_scheme, travel_provider,
                under_18, is_existing_patient, affiliation,
            ),
        )

    weight = config.cost_weight[mode]
    for candidate in candidates:
        # If nothing can serve as plan B, a failed visit is assumed to cost about
        # as much again as the visit itself.
        plan_b_minutes = plan_b.minutes_to_treatment if plan_b else candidate.minutes_to_treatment
        candidate.effective_minutes = candidate.minutes_to_treatment + (
            1 - candidate.site.certainty
        ) * plan_b_minutes
        penalty = 0.0
        if under_18 and candidate.site.serves_minors_without_parent != "yes":
            penalty = config.unknown_minor_policy_penalty_min
        candidate.score = candidate.effective_minutes + weight * candidate.cost + penalty

    ranked = _dedupe_same_place(candidates)
    ranked.sort(key=lambda c: (c.score, -c.site.certainty))

    best = ranked[0].score
    kept = [c for c in ranked if c.score <= best * config.score_cutoff_ratio or c is ranked[0]]
    results = kept[: config.results_expanded]

    # Safety floor: a fallback site must always be reachable from the results
    # screen. It is the only option guaranteed to be open and stocked, so no
    # synthetic or stale row may be allowed to hide it.
    notes = []
    if plan_b and not any(c.site.is_fallback for c in results):
        if len(results) >= config.results_expanded:
            results[-1] = plan_b
        else:
            results.append(plan_b)
        notes.append("fallback_inserted")

    return RouteResult(
        outcome=OUTCOME_OK,
        mode=mode,
        minutes_left=minutes_left,
        results=results,
        fallback=plan_b,
        uses_demo_data=any(c.site.is_demo_data for c in results),
        notes=notes,
    )


def _soonest_opening(
    sites, origin, now, config, scheme, travel_provider,
    under_18=False, is_existing_patient=False, affiliation=None
) -> Optional[Candidate]:
    """Used by the NOTHING_OPEN screen. Ignores the mode's waiting rule on
    purpose: the person needs to know what time to set an alarm for even when
    the router would not have recommended waiting."""
    soonest = None
    for site in sites:
        if site.is_mobile or site.point is None or site.meds_in_hand == NO_PEP:
            continue
        if not is_eligible(site, under_18, is_existing_patient, affiliation):
            continue
        travel = (
            travel_provider(origin, site)
            if travel_provider
            else estimate_travel_minutes(origin, site, config)
        )
        if travel is None or haversine_km(origin, site.point) > config.max_distance_km:
            continue
        opens_at = next_acceptance(site, now + timedelta(minutes=travel))
        if opens_at is None:
            continue
        if soonest is None or opens_at < soonest.opens_at:
            minutes = round((opens_at - now).total_seconds() / 60) + site.typical_wait_min
            soonest = Candidate(
                site=site,
                minutes_to_treatment=int(minutes),
                effective_minutes=float(minutes),
                cost=cost_for(site, scheme),
                score=float(minutes),
                waits_for_opening=True,
                opens_at=opens_at,
                travel_minutes=travel,
            )
    return soonest
