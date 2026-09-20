"""
Data access between pep.db and the router.

The router is a pure function and knows nothing about storage; this module is
the only place that touches SQLite. Nothing here computes or decides anything
about routing - it loads rows and hands them over.

    store = SiteStore("pep.db")
    result = store.route(
        region="boston_ma",
        exposure_time=...,
        now=...,
        origin=Point(42.3467, -71.0972),
        coverage_scheme="uninsured",
    )

Sites are loaded once per region and cached in memory. The whole dataset is
about 1,200 rows, so holding it costs almost nothing and spares a query on
every request - which matters, because a person is waiting.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Optional

from router import (
    BOSTON,
    DAYS,
    Point,
    RegionConfig,
    RouteResult,
    Site,
    route,
)

REGION_CONFIGS = {
    "boston_ma": BOSTON,
}

_SITE_COLUMNS = """
    id, region, name, site_type, priority_tier, is_fallback, is_mobile,
    area, admin_region, address, lat, lon, geocode_precision,
    phone, alt_phone, email, open_24h, mon, tue, wed, thu, fri, sat, sun,
    walk_in, walk_in_cutoff, must_be_existing_patient, community,
    serves_minors_without_parent, min_age, max_age, languages,
    meds_in_hand, starter_pack_days, certainty, typical_wait_min,
    data_origin, operational_data_origin, is_demo_data, last_verified,
    app_notes, region_attrs
"""


class SiteStore:
    def __init__(self, path: str = "pep.db"):
        self.path = path
        self._cache: dict[str, list[Site]] = {}
        self._details: dict[int, dict] = {}

    # -- connection ------------------------------------------------------- #

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    # -- loading ---------------------------------------------------------- #

    def sites(self, region: str) -> list[Site]:
        """All routable sites for a region. Cached after the first call."""
        if region in self._cache:
            return self._cache[region]

        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT {_SITE_COLUMNS} FROM sites WHERE region = ?", (region,)
            ).fetchall()

            # One query for every cost, joined in Python. Querying per site would
            # mean ~1,200 round trips for the Mexican region.
            costs: dict[int, dict] = {}
            for cost_row in connection.execute(
                "SELECT c.site_id, c.scheme, c.cost FROM site_costs c "
                "JOIN sites s ON s.id = c.site_id WHERE s.region = ?",
                (region,),
            ):
                costs.setdefault(cost_row["site_id"], {})[cost_row["scheme"]] = cost_row["cost"]

        sites = []
        for row in rows:
            site = Site(
                id=row["id"],
                name=row["name"],
                site_type=row["site_type"],
                region=row["region"],
                lat=row["lat"],
                lon=row["lon"],
                is_fallback=bool(row["is_fallback"]),
                is_mobile=bool(row["is_mobile"]),
                hours={day: row[day] for day in DAYS},
                walk_in=row["walk_in"] or "walk_in_ok",
                walk_in_cutoff=row["walk_in_cutoff"] or None,
                meds_in_hand=row["meds_in_hand"] or "varies_unknown",
                certainty=row["certainty"] if row["certainty"] is not None else 0.5,
                typical_wait_min=row["typical_wait_min"] or 60,
                costs=costs.get(row["id"], {}),
                serves_minors_without_parent=row["serves_minors_without_parent"] or "unknown",
                must_be_existing_patient=row["must_be_existing_patient"] or "unknown",
                community=row["community"],
                min_age=row["min_age"],
                max_age=row["max_age"],
                is_demo_data=bool(row["is_demo_data"]),
                priority_tier=row["priority_tier"] or 3,
            )
            sites.append(site)
            # Everything the results screen needs but the router does not.
            self._details[row["id"]] = {
                "address": row["address"],
                "area": row["area"],
                "admin_region": row["admin_region"],
                "phone": row["phone"],
                "alt_phone": row["alt_phone"],
                "email": row["email"],
                "languages": row["languages"],
                "geocode_precision": row["geocode_precision"],
                "data_origin": row["data_origin"],
                "operational_data_origin": row["operational_data_origin"],
                "last_verified": row["last_verified"],
                "app_notes": row["app_notes"],
                "region_attrs": json.loads(row["region_attrs"]) if row["region_attrs"] else {},
                "starter_pack_days": row["starter_pack_days"],
                "must_be_existing_patient": row["must_be_existing_patient"],
                "min_age": row["min_age"],
            }
        self._cache[region] = sites
        return sites

    def details(self, site_id: int) -> dict:
        """Presentation fields for one site. Loading a region populates these."""
        return self._details.get(site_id, {})

    def config(self, region: str) -> RegionConfig:
        if region not in REGION_CONFIGS:
            raise ValueError(
                f"Unknown region {region!r}. Known: {sorted(REGION_CONFIGS)}"
            )
        return REGION_CONFIGS[region]

    def neighborhoods(self, region: str) -> list[dict]:
        """Options for the location picker, ordered by name."""
        with self._connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT id, name, kind, lat, lon FROM neighborhoods "
                    "WHERE region = ? ORDER BY kind, name",
                    (region,),
                )
            ]

    # -- routing ---------------------------------------------------------- #

    def route(
        self,
        region: str,
        exposure_time: datetime,
        now: datetime,
        origin: Point,
        coverage_scheme: str,
        under_18: bool = False,
        is_existing_patient: bool = False,
        affiliation: str = None,
        travel_provider=None,
    ) -> RouteResult:
        return route(
            exposure_time=exposure_time,
            now=now,
            origin=origin,
            coverage_scheme=coverage_scheme,
            sites=self.sites(region),
            config=self.config(region),
            under_18=under_18,
            is_existing_patient=is_existing_patient,
            affiliation=affiliation,
            travel_provider=travel_provider,
        )

    # -- diagnostics ------------------------------------------------------ #

    def health(self) -> dict:
        """Counts a human should glance at before trusting a demo. Missing
        coordinates are the failure that produces plausible-looking wrong
        answers rather than an error."""
        with self._connect() as connection:
            report = {}
            for row in connection.execute(
                """SELECT region,
                          COUNT(*)                                   AS total,
                          SUM(lat IS NULL)                           AS no_coords,
                          SUM(is_fallback)                           AS fallbacks,
                          SUM(is_mobile)                             AS mobile,
                          SUM(is_demo_data)                          AS unverified,
                          SUM(hours_needs_review)                    AS hours_to_review
                     FROM sites GROUP BY region"""
            ):
                report[row["region"]] = dict(row)
        return report


def routable_count(store: SiteStore, region: str) -> int:
    """Sites the router could actually offer: located, not mobile, not ruled out."""
    return sum(
        1
        for site in store.sites(region)
        if site.point is not None and not site.is_mobile and site.meds_in_hand != "no_pep"
    )
