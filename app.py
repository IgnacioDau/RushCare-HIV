"""
PEP finder - Flask shell for two regional modules.

    pip install flask
    python app.py          ->  http://127.0.0.1:5000

The two regions answer different questions, because the two health systems pose
different problems:

  /mexico  Access is free and universal, so the hard part is FINDING a place.
           Served as a client-side directory (the original static app), ranked
           by distance. No Python involved beyond serving the page.

  /boston  Access is fragmented by insurance, hours and eligibility, so the hard
           part is CHOOSING one in time. Goes through the Python router, which
           weighs distance, opening hours, cost and the chance of actually
           leaving with medication.

Only the shell, the styling, the map component and the copy are shared.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from router import (
    OUTCOME_NOTHING_OPEN,
    OUTCOME_OK,
    OUTCOME_OUT_OF_AREA,
    OUTCOME_OUT_OF_WINDOW,
    PEP_WINDOW_HOURS,
    Point,
)
from store import SiteStore

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "pep.db"
STRINGS_DIR = BASE_DIR / "strings"

app = Flask(__name__)
store = SiteStore(str(DB_PATH))

REGION_LANGUAGES = {
    "boston_ma": ("en", "es", "ht"),
    "mexico": ("es",),
}


def load_strings(region: str, language: str) -> dict:
    """Copy for one region and language, falling back to the region's first
    language. Never falls back to another region: a Spanish speaker in Boston
    needs Health Safety Net, one in Mexico needs derechohabiencia."""
    languages = REGION_LANGUAGES.get(region, ("en",))
    if language not in languages:
        language = languages[0]
    path = STRINGS_DIR / region / f"{language}.json"
    if not path.exists():
        path = STRINGS_DIR / region / f"{languages[0]}.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("_review_status") == "machine_draft":
        # An unreviewed machine translation of emergency health copy must not
        # reach a user. Fall back rather than ship it.
        fallback = STRINGS_DIR / region / f"{languages[0]}.json"
        if fallback.exists() and fallback != path:
            return json.loads(fallback.read_text(encoding="utf-8"))
    return data


def requested_language(region: str) -> str:
    return request.args.get("lang") or REGION_LANGUAGES.get(region, ("en",))[0]


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #


@app.route("/")
def home():
    """Explicit region choice. Auto-detection guesses wrong often enough that
    in this context the cost of guessing outweighs the saved tap."""
    return render_template("home.html")


@app.route("/boston")
def boston():
    language = requested_language("boston_ma")
    return render_template(
        "boston.html",
        strings=load_strings("boston_ma", language),
        language=language,
        languages=REGION_LANGUAGES["boston_ma"],
        neighborhoods=store.neighborhoods("boston_ma"),
        window_hours=PEP_WINDOW_HOURS,
    )


@app.route("/mexico")
def mexico():
    language = requested_language("mexico")
    return render_template(
        "mexico.html",
        strings=load_strings("mexico", language),
        language=language,
        window_hours=PEP_WINDOW_HOURS,
    )


# --------------------------------------------------------------------------- #
# Boston API
# --------------------------------------------------------------------------- #


@app.post("/api/boston/route")
def api_boston_route():
    payload = request.get_json(silent=True) or {}

    try:
        hours_ago = float(payload.get("hours_ago", 0))
        lat = float(payload["lat"])
        lon = float(payload["lon"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "lat, lon and hours_ago are required"}), 400

    # `now` is injected rather than read inside the router, so a demo can be
    # replayed at a fixed moment and the tests stay deterministic.
    now = datetime.now()
    if payload.get("now"):
        try:
            now = datetime.fromisoformat(payload["now"])
        except ValueError:
            pass

    result = store.route(
        region="boston_ma",
        exposure_time=now - timedelta(hours=hours_ago),
        now=now,
        origin=Point(lat, lon),
        coverage_scheme=payload.get("coverage_scheme", "uninsured"),
        under_18=bool(payload.get("under_18")),
        affiliation=payload.get("affiliation") or None,
    )
    return jsonify(serialise(result, now))


def serialise(result, now: datetime) -> dict:
    out = {
        "outcome": result.outcome,
        "mode": result.mode,
        "minutes_left": result.minutes_left,
        "uses_demo_data": result.uses_demo_data,
        "results": [serialise_candidate(c, now) for c in result.results],
    }
    if result.outcome == OUTCOME_NOTHING_OPEN and result.next_opening:
        out["next_opening"] = serialise_candidate(result.next_opening, now)
    return out


def serialise_candidate(candidate, now: datetime) -> dict:
    site = candidate.site
    info = store.details(site.id)
    attrs = info.get("region_attrs", {})
    return {
        "id": site.id,
        "name": site.name,
        "site_type": site.site_type,
        "is_fallback": site.is_fallback,
        "lat": site.lat,
        "lon": site.lon,
        "address": info.get("address"),
        "area": info.get("area"),
        "phone": info.get("phone"),
        "languages": info.get("languages"),
        "minutes": candidate.minutes_to_treatment,
        "travel_minutes": candidate.travel_minutes,
        "cost": candidate.cost,
        "waits_for_opening": candidate.waits_for_opening,
        "opens_at": candidate.opens_at.strftime("%H:%M") if candidate.opens_at else None,
        "opens_in_minutes": (
            round((candidate.opens_at - now).total_seconds() / 60)
            if candidate.opens_at
            else None
        ),
        "meds_in_hand": site.meds_in_hand,
        "starter_pack_days": info.get("starter_pack_days"),
        # Everything the UI needs to decide which warnings to render.
        "flags": {
            "unverified": site.is_demo_data,
            "hsn": attrs.get("accepts_hsn") == "yes" and candidate.cost > 0,
            "out_of_pocket": site.site_type == "pharmacy" and candidate.cost > 0,
            "waiting": candidate.waits_for_opening,
            "campus": bool(site.community),
        },
    }


@app.get("/api/boston/health")
def api_health():
    return jsonify(store.health())


if __name__ == "__main__":
    if not DB_PATH.exists():
        raise SystemExit("pep.db not found. Run:  python load_sites.py")
    app.run(debug=bool(os.environ.get("FLASK_DEBUG")), port=5000)
