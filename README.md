# PEP Finder — get PEP in time

A web app that helps someone who may have been exposed to HIV get **PEP**
(post-exposure prophylaxis) inside the **72-hour window** in which it still
works — in Boston, Massachusetts, or anywhere in México.

> HackMIT 2026 project. Not medical advice. If you are in doubt, go to an
> emergency room (US) or Urgencias (México) — they are open at all hours and
> cannot turn you away.

## Why two regions, two different apps

Both modules answer "where do I get PEP right now", but the two health systems
pose opposite problems, so the app does not force one solution on both:

- **México** — PEP is free and available at any CAPASITS, hospital SAIH, or
  IMSS hospital, regardless of insurance status. The hard part is *finding*
  a place nearby. This module is a location-ranked directory: pick your
  location, filter by whether you have IMSS coverage, and see the closest
  centers with directions, phone numbers, and the documents each type of
  center may ask for.

- **Boston, MA** — access is fragmented by insurance, opening hours, and who a
  given clinic will actually see. The hard part is *choosing* the right place
  before the clock runs out. This module asks four short questions and runs a
  router that weighs travel time, opening hours, cost, and the odds of
  actually walking out with medication in hand — then tells you exactly what
  to say when you arrive.

One shell, one visual language, two purpose-built flows.

## What it does

- **México**: detects your location (or you type it), asks whether you have
  IMSS coverage, and lists CAPASITS / SAIH / IMSS hospitals within 50 km,
  nearest first, with directions, phone, hours, and required documents. A
  WhatsApp shortcut connects to the IMSS *Atención VIHrtual* chatbot.
- **Boston**: asks when the exposure happened, what happened, your insurance
  situation, and your location (neighborhood picker, a pin you drop and drag
  on the map, or a typed address) — never your device's GPS. Returns up to
  five ranked options with estimated cost, wait, and a live 72-hour countdown,
  and a dedicated screen with the exact sentence to say on arrival.
- Both modules render an **unverified-data badge** on anything that has not
  been phone-confirmed, and always keep an always-open fallback (an ER in
  Boston, Urgencias in México) reachable even when other options rank higher.

## Project structure

```
app.py                  Flask app: serves both regions and the Boston routing API
router.py                Boston's routing logic (pure function, unit-tested)
store.py                 SQLite <-> router glue for the Boston region
load_sites.py             Builds pep.db from sites_demo.csv + neighborhoods_boston.csv
schema.sql                Database schema for the Boston region
geocode_sites.py          Standalone utility to geocode a sites CSV via Nominatim (not run at startup)

sites_demo.csv            24 Boston-area sites (synthetic operational data — see docs/)
neighborhoods_boston.csv  Boston neighborhoods for the location picker

test_router.py            Unit tests for the routing logic
test_store.py             Integration tests against a real pep.db

strings/
  boston_ma/en.json        Boston UI copy (English — reviewed, default)
  boston_ma/es.json        Boston UI copy (Spanish — reviewed)
  boston_ma/ht.json        Boston UI copy (Haitian Creole — MACHINE DRAFT, not served
                            until a native speaker reviews it; app.py falls back to
                            English if served anyway)
  mexico/es.json           México UI copy (Spanish)

templates/
  base.html, home.html      Shared shell and the region picker
  boston.html                Boston's four-question flow
  mexico.html                México's directory flow

static/
  css/style.css              Shared visual language for both regions
  js/boston.js, boston-map.js, clock.js    Boston's client-side flow
  js/mapa.js, mexico.js                    México's client-side flow (from the
                                            original standalone app)
  data/directorio.js         407 México sites: CAPASITS, SAIH, IMSS hospitals

docs/
  PROJECT_CONTEXT.md         Design decisions and project history, for anyone
                              (human or AI) picking this project up
  router_spec.md              Full specification of the Boston routing algorithm
  screens_spec.md              Wireframe-level spec of every screen
  *.xlsx                       Source spreadsheets used while designing the data
```

## Running it locally

Ubuntu/Debian blocks system-wide `pip install` (PEP 668), so use a virtual
environment:

```bash
git clone <this-repo-url>
cd <repo-folder>

python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python3 load_sites.py          # builds pep.db from sites_demo.csv
python3 app.py                 # -> http://127.0.0.1:5000
```

Open `http://127.0.0.1:5000` and pick a region. `/boston` and `/mexico` also
work directly.

### Running the tests

```bash
python3 test_router.py         # 39 assertions, hand-built fixtures, no DB needed
python3 test_store.py          # 17 assertions against a real pep.db — run
                                # load_sites.py first
```

### Showing it to someone on the same network

By default Flask only listens on your machine. To let another device on the
same Wi-Fi open it, run `app.run(host="0.0.0.0", port=5000)` in `app.py` and
share `http://<your-local-IP>:5000`. For access from outside the network
without deploying anywhere, a tunnel tool (e.g. ngrok) pointed at port 5000
works without touching the code.

## Data and its limits

**México** (`static/data/directorio.js`, 407 sites): 78 CAPASITS and 73 SAIH
from CENSIDA's official directories (March 2026), plus 256 IMSS hospitals from
the IMSS facilities directory, with real coordinates. CAPASITS/SAIH addresses
are approximated to their city center and refined live using each site's
address as the map loads (a dashed pin marks any that stay approximate). The
IMSS does not publish which hospitals run an HIV clinic — the app shows
2nd/3rd-level hospitals (where the IMSS reports having them) and asks the
user to confirm by WhatsApp or at their Unidad de Medicina Familiar.
IMSS-Bienestar facilities are not included: the source file had no addresses
to geocode.

**Boston** (`sites_demo.csv`, 24 sites): names, addresses, and published hours
are real as of September 2026. Everything operational — whether a site
dispenses PEP on the spot, wait times, and costs — is a **documented estimate**,
not phone-confirmed. Every site carries `is_demo_data = TRUE` and renders the
unverified badge accordingly. `docs/Sitios_PEP_Boston_DEMO.xlsx` documents the
reasoning and risk behind every estimated value; the weakest assumption is
that Fenway Health dispenses a full 28-day course same-day, inferred from its
same-day PrEP program and not yet confirmed by phone.

Neither dataset should be relied on for an actual medical emergency without
calling ahead.

## License

Code under the MIT license (see `LICENSE`). Data comes from official public
sources; check their own terms of use before reusing it elsewhere.
