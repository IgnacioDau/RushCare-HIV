# PEP Router — algorithm specification

Pure function. No I/O, no clock reads, no network calls. Everything it needs comes in
as arguments so it can be unit-tested and so the demo is reproducible.

All times are **minutes**. All money is **USD**. All coordinates are decimal degrees.

---

## 1. Constants

```
PEP_WINDOW_HOURS      = 72     # hard clinical deadline
SAFETY_BUFFER_MIN     = 120    # must be TREATED this long before the deadline
                               # not evidence-based: it absorbs bad travel estimates,
                               # worse-than-expected queues, and being sent elsewhere

# Mode boundaries, in hours of window remaining.
MODE_EMERGENCY_MAX_H  = 20     # < 20h left   -> emergency mode
MODE_NORMAL_MAX_H     = 30     # 20-30h left  -> normal mode
                               # > 30h left   -> margin mode
                               # Most real users arrive with 60-70h left, i.e. margin
                               # mode, where cost weighs most. That is intentional.

COST_WEIGHT = {                # USD -> "minute equivalents"; 1.0 means $1 == 1 minute
    "emergency": 0.0,          # cost is irrelevant, just get there
    "normal":    0.5,
    "margin":    1.0,
}

STREET_FACTOR         = 1.3    # straight-line km -> real street km (grid detour factor)
URBAN_SPEED_KMH       = 20     # door-to-door urban speed incl. lights, traffic, waiting
                               # both constants are unused when a routing API answers

MAX_RESULTS_VISIBLE   = 3      # shown immediately
MAX_RESULTS_EXPANDED  = 5      # behind a "more options" control
SCORE_CUTOFF_RATIO    = 2.0    # drop any extra result scoring worse than 2x the best,
                               # so thin hours are not padded with bad options

ALLOW_WAITING_FOR_OPENING = {  # may we recommend a site that is currently closed?
    "emergency": False,        # every hour of delay lowers PEP efficacy
    "normal":    True,
    "margin":    True,
}

MAX_WAIT_FOR_OPENING_MIN = 720 # never propose waiting more than 12h, even if the
                               # deadline allows it (e.g. waiting out a whole weekend)
```

> PEP efficacy decays continuously; it does not hold flat until hour 72 and then fall
> off. Any result that involves waiting MUST carry the sooner-is-better notice
> (see section 4), in every mode, including margin.

> DECISION POINTS — change these first if the behaviour feels wrong.
> The mode cutoffs (6/24), the cost weights, the safety buffer, and the speed
> assumption are all judgement calls, not derived values.

---

## 2. Entry point

```
FUNCTION route(exposure_time, now, user_lat, user_lon, insurance_profile, sites):

    minutes_since   = minutes_between(exposure_time, now)
    minutes_left    = PEP_WINDOW_HOURS * 60 - minutes_since

    # --- Out of window: this is a different product flow, not a ranking problem
    IF minutes_left <= 0:
        RETURN { outcome: "OUT_OF_WINDOW" }

    mode = mode_for(minutes_left)

    # --- Plan B is always the nearest ER. Computed once, used by every candidate.
    plan_b = nearest_feasible_er(user_lat, user_lon, now, sites, minutes_left)

    candidates = []
    FOR site IN sites:
        t = time_to_treatment(site, user_lat, user_lon, now, mode)
        IF t IS NULL:                       # closed, or no walk-in left today
            CONTINUE
        IF t + SAFETY_BUFFER_MIN > minutes_left:
            CONTINUE                        # cannot be treated in time
        IF site.meds_in_hand == "no_pep":
            CONTINUE

        candidates.APPEND({
            site:           site,
            time:           t,
            effective_time: effective_time(t, site.certainty, plan_b.time),
            cost:           cost_for(site, insurance_profile),
        })

    candidates = deduplicate_same_building(candidates)

    FOR c IN candidates:
        c.score = c.effective_time + COST_WEIGHT[mode] * c.cost

    ranked = SORT candidates BY score ASC, THEN BY site.certainty DESC

    # --- Safety floor: an ER must always be reachable from the results screen,
    #     because it is the only option guaranteed to be open and to have PEP.
    #     Synthetic or stale data must never be able to hide it.
    best  = ranked[0].score
    kept  = [r FOR r IN ranked IF r.score <= best * SCORE_CUTOFF_RATIO]
    results = kept[0 : MAX_RESULTS_EXPANDED]     # UI shows the first
                                                 # MAX_RESULTS_VISIBLE and hides the rest
                                                 # behind a "more options" control
    IF no site in results has site_type == "er" AND plan_b IS NOT NULL:
        results[LAST] = plan_b              # replace the weakest pick with the ER

    RETURN {
        outcome:        "OK",
        mode:           mode,
        minutes_left:   minutes_left,
        results:        results,
        fallback_er:    plan_b,
        demo_data_used: ANY(r.site.is_demo_data FOR r IN results),
    }
```

---

## 3. Helper functions

```
FUNCTION mode_for(minutes_left):
    IF minutes_left <  MODE_EMERGENCY_MAX_H * 60: RETURN "emergency"
    IF minutes_left <= MODE_NORMAL_MAX_H    * 60: RETURN "normal"
    RETURN "margin"
```

```
FUNCTION travel_minutes(user_lat, user_lon, site):
    # PRIMARY: one OpenRouteService Matrix call per user query returns the
    # travel time to every site at once. Cache it for the whole request.
    IF routing_matrix IS AVAILABLE:
        RETURN routing_matrix[site.id]

    # FALLBACK: never let an external API failure take the app down mid-demo.
    km = haversine(user_lat, user_lon, site.lat, site.lon) * STREET_FACTOR
    RETURN CEIL(km / URBAN_SPEED_KMH * 60)
```

### Mapping stack

| Need | Choice | Cost | Notes |
|---|---|---|---|
| Render the map | Leaflet + OpenStreetMap tiles | free, no key | ~40 KB, plain JS, no React needed |
| Travel times | OpenRouteService `/matrix` | free key, ~2,000-2,500 req/day | one request per user query, not one per site |
| Address -> coordinates | Nominatim (OSM), or a local lookup table | free | see the location-privacy note below |
| Transit times | MBTA V3 API | free (key optional; 20 req/min without) | post-MVP; matters because the T stops running at night |

The router must degrade gracefully: if the matrix call fails or times out, fall back to
the haversine estimate and carry on. Mark the result as an estimate in the UI.

### Precomputed travel matrix (recommended)

The 24 sites are fixed. Precompute travel times from ~30 Boston neighborhood centroids
to every site once, store them in the database, and serve them at runtime. Live routing
calls then only happen when the user enters an exact street address. Benefits: the quota
question disappears, the app works with no network, and no user location leaves the
server for the common path.

### Location input — no GPS

The browser's "share my location" prompt is a poor fit for a page about HIV exposure.
Intake offers two options instead:

1. a **neighborhood picker** — coordinates hardcoded locally, no external request at
   all, and it pairs with the precomputed matrix above;
2. a **map pin** the user drops on Leaflet, or a typed address.

A typed address must be geocoded, which means sending it to Nominatim. Say so in the
UI, or restrict MVP intake to options that never leave the server.

```
FUNCTION time_to_treatment(site, user_lat, user_lon, now, mode):
    # The real question is not "is it open now" but "can they see me when I arrive".
    travel  = travel_minutes(user_lat, user_lon, site)
    arrival = now + travel

    IF site_accepts_at(site, arrival):
        RETURN travel + site.typical_wait_min

    IF NOT ALLOW_WAITING_FOR_OPENING[mode]:
        RETURN NULL

    next_slot = next_time_site_accepts(site, arrival)   # NULL if none within window
    IF next_slot IS NULL:
        RETURN NULL
    IF minutes_between(now, next_slot) > MAX_WAIT_FOR_OPENING_MIN:
        RETURN NULL
    RETURN minutes_between(now, next_slot) + site.typical_wait_min
```

```
FUNCTION site_accepts_at(site, t):
    # Open, AND still taking someone who has no appointment.
    IF NOT open_at(site, t): RETURN FALSE
    IF site.walk_in == "appointment_only": RETURN FALSE      # MVP: cannot model booking
    IF site.walk_in_cutoff IS SET AND time_of_day(t) > site.walk_in_cutoff:
        RETURN FALSE
    RETURN TRUE
```

```
FUNCTION open_at(site, t):
    hours = site[weekday_column(t)]          # "08:00-19:00" | "24h" | "closed"
    IF hours == "24h":    RETURN TRUE
    IF hours == "closed": RETURN FALSE
    RETURN opens <= time_of_day(t) < closes
```

```
FUNCTION effective_time(t, certainty, plan_b_time):
    # If the site turns out not to provide PEP, the person still ends up at an ER.
    # Low certainty therefore costs real minutes, not just confidence.
    RETURN t + (1 - certainty) * plan_b_time
```

```
FUNCTION cost_for(site, insurance_profile):
    IF insurance_profile == "masshealth": RETURN site.est_cost_masshealth
    RETURN site.est_cost_uninsured       # "uninsured" and "prefer not to say"
```

```
FUNCTION deduplicate_same_building(candidates):
    # Fenway clinic + Fenway pharmacy share an address. Two of three result slots
    # spent on one destination is a waste of the screen.
    GROUP BY (ROUND(lat, 4), ROUND(lon, 4))
    KEEP the lowest-score member of each group
```

---

## 4. Output contract

Each result the UI receives:

```
{
    site:            <site row>,
    time:            <minutes until treated>,
    effective_time:  <minutes, risk-adjusted>,
    cost:            <USD for this insurance profile>,
    score:           <lower is better>,
    why:             <short reason string, built by the UI layer>,
    is_demo_data:    <boolean -> renders the "unverified" badge>,
}
```

The UI must render, for every result:

- an **unverified-data badge** when `is_demo_data` is true;
- the **Health Safety Net warning** when `cost > 0` and `accepts_hsn == "yes"`
  (the cost may end up at zero, but a bill can arrive first);
- the **sooner-is-better notice** whenever the result involves waiting for a site to
  open: "PEP works best the sooner you take it. Waiting is safe here, but going now
  is always the safer choice." This applies in every mode, margin included;
- the **out-of-pocket warning** for pharmacies on the uninsured profile.

---

## 5. Test cases

Run these before writing any UI. Each asserts the winner and the mode.

| # | Scenario | Expected mode | Expected winner | What it proves |
|---|---|---|---|---|
| 1 | Sunday 3 PM, 8h left, uninsured, Back Bay | emergency | an ER | Clinics closed; cost weight is 0 so only arrival time matters |
| 2 | Tuesday 10 AM, 60h left, MassHealth, Fenway area | margin | Fenway Health | All costs are 0 on this profile, so effective time alone decides |
| 3 | Saturday 2 AM, 69h left, uninsured, Dorchester | margin | an ER now, not waiting for Monday | Waiting is allowed in margin mode but still loses on total time |
| 4 | Tuesday 11 PM, 4h left, uninsured, Cambridge | emergency | nearest ER | Deepest urgency; nothing else can be reached in time |
| 4b | Tuesday 11 PM, 25h left, uninsured, Fenway | normal | Fenway at 8 AM, with the sooner-is-better notice | Waiting ~9h is under the 12h cap and leaves ~15h of window |
| 4c | Friday 11 PM, 65h left, uninsured, Dorchester | margin | an ER or a Saturday site, never "wait until Monday" | MAX_WAIT_FOR_OPENING_MIN blocks weekend-long waits |
| 5 | Exposure 80h ago | — | `OUT_OF_WINDOW` | Different flow: testing + PrEP, not PEP |
| 6 | Wednesday 5:45 PM, 28h left, uninsured, Roxbury | normal | Whittier Street | Walk-in cutoff respected; on-site pharmacy raises certainty |
| 7 | Any scenario where clinics beat every ER | any | results still contain one ER | Safety floor holds |
| 8 | Fenway clinic and Fenway pharmacy both qualify | any | only one appears | Deduplication works |

---

## 6. Known limitations (say these in the pitch before anyone asks)

- Travel time is a straight-line estimate, not a routed one.
- `appointment_only` sites are excluded entirely; the MVP cannot model booking
  availability, so Planned Parenthood never wins even when it might be right.
- Wait times are per-site averages, not live. Real ER load swings by hours.
- Holiday hours are not modelled.
- Travel assumes one generic urban speed: no distinction between someone who can
  afford a rideshare and someone walking to a bus at 2 AM.
- Costs are expected values, not quotes.

---

## 8. Multi-region support

The project now covers two regions: `boston_ma` and `mexico`. **The router must not
know which country it is in.** One `sites` table, one routing function; everything that
differs between regions lives in a `RegionConfig`.

```
RegionConfig = {
    "id":                       "boston_ma" | "mexico",
    "default_language":         "en" | "es",
    "available_languages":      ["en", "es", "ht"],

    # --- coverage
    "bounds":                   <bounding box or list of admin areas>,
    "out_of_area_message_key":  "coverage.out_of_area",

    # --- the always-available fallback: the site type that is open 24/7,
    #     stocks PEP, and is legally obliged to see anyone.
    "fallback_site_type":       "er"          # boston_ma
                              | "imss_urgencias",  # mexico - SEE CAVEAT BELOW

    # --- how people pay. NOT the same question in both countries.
    "coverage_schemes":         ["uninsured", "masshealth"]              # boston_ma
                              | ["imss", "issste", "imss_bienestar", "none"],  # mexico
    "cost_field_by_scheme":     { <scheme>: <column name> },

    # --- geography. Boston is a dense city; Mexico is a whole country.
    "urban_speed_kmh":          20    | 45,
    "street_factor":            1.3   | 1.25,
    "max_wait_for_opening_min": 720   | 1440,
    "safety_buffer_min":        120   | 180,
    "max_distance_km":          50    | 400,

    # --- mode boundaries and cost weights may also differ; default to the
    #     values in section 1 unless a region overrides them.
    "mode_boundaries_h":        {"emergency": 20, "normal": 30},
    "cost_weight":              {"emergency": 0.0, "normal": 0.5, "margin": 1.0},
}
```

`route()` gains one argument: `route(..., config)`. Every constant referenced in
sections 1-3 is read from `config` instead of from a module-level constant. No other
change to the algorithm.

### Region caveats

- **Mexico's fallback rests on a stated assumption.** IMSS public campaigns direct
  people with unprotected sexual exposure to Urgencias within 72 hours, but the only
  official IMSS clinical guideline found (GPC 241GER) covers *occupational* exposure in
  health workers. IMSS's own bulletin describes PEP as a service to *derechohabientes*;
  the broader "whether or not you are a beneficiary" claim comes from AHF, an NGO.
  The MVP proceeds on the universal-access assumption, states it in the UI
  (`legal.assumption_imss`) and in the pitch, and the copy tells anyone who is turned
  away to ask for their state's CAPASITS, which serves people regardless of affiliation.
- **All 997 IMSS-Bienestar units (Campeche, CDMX, Chiapas) are included** on a
  teammate's assertion that every one of them is legally required to provide PEP and
  keeps stock. Recorded as `data_origin = teammate_asserted`. They are differentiated
  by `facility_level`, not excluded:

  | facility_level | rows | hours | certainty | tier |
  |---|---|---|---|---|
  | third_level | 13 | 24h | 0.90 | 3 |
  | second_level | 101 | 24h | 0.90 | 3 |
  | first_level | 439 | estimated weekday office hours | 0.70 | 4 |
  | first_level_assumed | 353 | estimated weekday office hours | 0.65 | 4 |
  | mobile_unit | 91 | none | 0.60 | 4 |

  Two things this encodes. First, a first-level clinic is not an emergency department:
  claiming 24h hours for it would be a factual error regardless of whether it stocks
  PEP, so its hours are marked estimated and `hours_needs_review = TRUE`. Second,
  **mobile brigades (`is_mobile = TRUE`) have no fixed address** — their location
  rotates between communities — so the router skips them until a route and timetable
  exist. The rows stay in the dataset; the router decides.

  Tiering matters functionally: without it, ~1,000 always-open units would outrank
  every specialised HIV unit in those three states and a CAPASITS would never surface
  during its own opening hours.
- **Health Safety Net, EMTALA and MassHealth do not exist in Mexico.** These are named
  in user-facing copy, which is why strings are scoped by region, not only by language
  (see below).

### String files are scoped by region AND language

```
strings/
  boston_ma/  en.json   es.json   ht.json
  mexico/     es.json   en.json
```

A Spanish speaker in Boston and a Spanish speaker in Mexico need different copy, not
the same file: one is told about Health Safety Net, the other about derechohabiencia.
All files in a region must carry an identical key set; a missing key falls back to the
region's default language, never to another region.

`strings/boston_ma/ht.json` is a **machine draft** and must not be served until a
native Haitian Creole speaker reviews it. The loader should treat `_review_status:
machine_draft` as a reason to fall back to `en.json`.

### The "nothing open" state

Mexico has few weekend or night sites, so this state will be hit often. It is not an
error screen. It shows: that nothing is open now, which site opens first and at what
exact time, how many hours of window remain, a reminder control, and the fallback
option for someone who would rather not wait. Copy lives under the `nothing_open` key.

---

## 9. Still undecided

1. **Age** is not a required question. Treatment does not change with age, so intake
   offers an optional "I am under 18" toggle instead of a gate. When set, the UI shows
   the Massachusetts consent note and the insurance-EOB confidentiality warning, and
   the router prefers sites whose `serves_minors_without_parent` is `yes`. Nothing is
   filtered out on age alone.
2. **`OUT_OF_WINDOW` screen** — MVP ships a static page: PEP is no longer effective,
   get an HIV test now and again at 4-6 weeks and 3 months, and talk about PrEP. It is
   not a router flow. Expanding it into a testing-site finder is a pitch talking point.
3. **Out-of-area users** are out of scope for the MVP; the router still returns the
   nearest Massachusetts site. Consider a one-line guard: if the nearest site is over
   50 km away, show a coverage banner and link to locator.hiv.gov.
4. **UI language.** Spanish and Haitian Creole ARE part of the intended MVP, not a
   future nice-to-have: they are the languages of the communities most affected in
   Boston. They are built last, after the core flow works, purely as a sequencing
   decision. Architectural consequence, and it is cheap only if decided now: **no user
   facing string is hardcoded.** All copy lives in `strings/en.json`, `strings/es.json`,
   `strings/ht.json` and is looked up by key from the first line of code written.
   Retrofitting this later means touching every template.
