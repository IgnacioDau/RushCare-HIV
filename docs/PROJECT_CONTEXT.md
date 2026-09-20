# PEP Boston — project context

Handoff document. Written so that a teammate (or an AI assistant they are working with)
can pick up the project without having seen the conversations that produced it.

**Status:** design complete, no code written yet.
**Event:** HackMIT 2026.
**Last updated:** 19 September 2026.

---

## 1. What the project is

A web app that helps someone in Boston who may have been exposed to HIV get **PEP**
(post-exposure prophylaxis) inside the **72-hour window** in which it still works.

It is not a directory and not a medical advisor. It is a **router**: given the hour of
exposure, a location and an insurance situation, it returns the fastest and cheapest
realistic way to have the medication in hand, plus the exact words to say on arrival.

### The insight the whole product rests on

Eligibility barely varies by state. In all 50 states, nobody is asked for immigration
papers, minors can consent to STI treatment, and any emergency room must evaluate
anyone regardless of ability to pay (EMTALA). What varies is **speed and cost**. So the
app should route people through the system, not check whether they qualify for it.

### MVP scope — one route, one profile

Deliberately narrow, so one path works end to end rather than five paths working
halfway:

- **Geography:** Boston only.
- **Route:** consensual sexual exposure only. Sexual assault and occupational exposure
  are acknowledged with a referral message but not built. (Assault triggers a different
  protocol — SANE exams, victim compensation. Occupational exposure is the employer's
  responsibility under OSHA and is usually free.)
- **Insurance profile:** uninsured / MassHealth. Private insurance is not modelled.
- **Language:** English first. Spanish and Haitian Creole are part of the intended
  MVP, built last — see Conventions.

---

## 2. Domain facts that drive the design

| Fact | Consequence for the product |
|---|---|
| PEP must start within 72h; sooner is better, efficacy decays continuously | A visible countdown; a "sooner is better" notice on any recommendation that involves waiting |
| Treatment is 28 days, then follow-up HIV tests | Post-visit reminder screen |
| Any licensed prescriber can prescribe it; in ~20 states a trained pharmacist can too | The path always ends at a prescriber; the variable is which one is fastest |
| **Massachusetts, Aug 2026:** pharmacists may independently prescribe PEP (M.G.L. c. 94C § 19F) — but it is optional per pharmacist | Cannot assume any given pharmacy participates; must be confirmed branch by branch |
| **EMTALA:** ERs must evaluate anyone, no papers, no ability to pay | ERs are the only always-available option. This is why they are the algorithm's fallback |
| **Health Safety Net (MA):** pays hospitals and community health centers for uninsured residents | An ER visit in Boston can end up free — unusual, and a strong pitch point. But it is not instant: a bill may arrive first |
| HSN does **not** cover community pharmacies | For an uninsured person, the pharmacy route means paying ~$600+ out of pocket today. Counterintuitive, and it is why pharmacies rarely win |
| Minors may consent to STI treatment in all 50 states; MA has no minimum age | Age is informational, not a gate. But billing a parent's insurance can expose the visit via the EOB |

---

## 3. Product flow

Four intake questions, roughly 30 seconds:

1. **When was the exposure?** Over 72h → different flow (testing + PrEP), not PEP.
2. **What happened?** (unprotected sex / condom failure / not sure)
3. **Do you have insurance?** (MassHealth / none / prefer not to say → treated as none)
4. **Where are you?** Neighborhood picker or map pin. **Not** browser GPS — see below.

Optional toggle: "I am under 18." Not a gate; it surfaces the Massachusetts consent
note and the EOB confidentiality warning, and nudges the ranking toward sites that see
minors without a parent.

Then: **1–3 results** (expandable to 5), each with directions, a call button, an
expected cost sentence, and the reason it was chosen. Then a screen with **the exact
sentence to say on arrival** — "I had a possible HIV exposure X hours ago and I need
PEP" — what to bring, and the assistance programs to ask about if billed.

That last screen is the part no existing locator offers, and it is where the project's
value concentrates.

---

## 4. The router algorithm

Full spec in `router_spec.md`. Summary:

- Compute hours remaining in the 72h window. Pick a **mode**:
  margin (>30h) · normal (20–30h) · emergency (<20h).
- Filter sites: open when the user would *arrive* (not "open now"), still accepting
  walk-ins at that hour, and reachable with a **2-hour safety buffer** before the
  deadline.
- Score each: `effective_time + cost_weight[mode] * cost`, where
  `effective_time = time + (1 - certainty) * nearest_ER_time`. Cost weights are
  0 / 0.5 / 1.0 by mode — in a hurry, money stops mattering.
- **`certainty`** is the probability of walking out with medication in hand. A site
  that only writes a prescription costs real minutes, because the person may still end
  up at an ER.
- **The ER is always the plan B**, because it is the only site type that is always
  open, always stocked, and cannot turn anyone away.
- **Safety floor:** an ER always appears in the results, even when clinics outrank it.
  Synthetic or stale data must never be able to hide the guaranteed option.

---

## 5. Data situation — read this before trusting any number

Site data is **synthetic**. Phone verification was planned but could not be carried
out in time. Names, addresses, coordinates and published hours are real; everything
operational (whether PEP is dispensed, costs, waits, certainty) is estimated.

- Every row carries `data_origin = synthetic_demo` and `is_demo_data = TRUE`.
- The UI must show an **"unverified data"** badge while that flag is set.
- Assumptions and their justifications are documented in `Sitios_PEP_Boston_DEMO.xlsx`,
  sheet `Supuestos_DEMO`. The weakest one: **Fenway Health is assumed to dispense a
  full 28-day course same-day**, inferred from its same-day PrEP program. Fenway wins
  most daytime scenarios because of it. Verify first.
- Real data collection is ready to run: `Sitios_PEP_Boston_plantilla.xlsx` has the
  empty template, an English call script, and per-site follow-up questions.

### Keeping data fresh — the three layers

1. **Phone verification** — manual, does not scale, highest quality.
2. **Staleness decay** — every row has `last_verified`; past N months the app stops
   presenting it as fact and says "verified X months ago, call ahead." ~10 lines of
   code, and it is what makes the app honest from day one.
3. **Claimed profiles** — sites verify themselves and edit their own entry. The only
   layer that scales, and the only one that can fail for reasons outside our code
   (institutions have little incentive to maintain a student project's profile).

Identity verification options for layer 3, if asked: call/SMS a code to the already
public phone number (the Google Business Profile model); institutional email domain;
cross-check against the Massachusetts license registry; endorsement by BPHC or DPH;
or two-tier review where low-risk edits (hours) apply instantly and high-risk ones
("we no longer offer PEP") go to a human.

---

## 6. Tech stack

- **Backend:** Flask + SQLite. Router as a single pure module, no I/O, `now` passed in
  as an argument so tests and the demo are reproducible.
- **Frontend:** HTML/CSS/plain JS. React was considered and dropped — nobody on the
  team knows it well enough to learn it under hackathon pressure.
- **Map:** Leaflet + OpenStreetMap tiles. Free, no API key, ~40 KB, no React needed.
- **Travel times:** OpenRouteService `/matrix` (free key, ~2,000–2,500 req/day; one
  request per user query, not one per site). **Precompute** a matrix from ~30
  neighborhood centroids to the 24 sites and store it — then live calls are rare, the
  quota question disappears, and the app works without network.
- **Fallback:** if routing fails, haversine distance × 1.3 ÷ 20 km/h. The demo must
  never die because an external API timed out.
- **Not in the MVP:** MBTA V3 API for transit times (free, relevant because the T stops
  at night), user accounts, notifications, any state outside Massachusetts.

These are complementary pieces, not alternatives: Leaflet draws, ORS times, Nominatim
geocodes.

### A privacy decision worth keeping

No browser GPS prompt. On a page about HIV exposure, "share my location" is a bad ask.
Intake uses a neighborhood picker (coordinates hardcoded locally, nothing leaves the
server) or a manually dropped map pin. A typed address needs geocoding, which does send
data to Nominatim — disclose it or leave it out of the MVP.

---

## 7. Conventions

- Conversation and planning happen in Spanish; **everything that ships — code, variable
  names, comments, column headers, UI copy — is in English**, because the realistic end
  user is English-speaking.
- All times in minutes, money in USD, coordinates in decimal degrees.
- Enum values are lowercase snake_case (`full_28_day_course`, `walk_in_ok`).
- **No user-facing string is hardcoded.** All copy lives in `strings/<lang>.json` and is
  looked up by key from the very first template. English ships first; Spanish and
  Haitian Creole follow within the MVP. This costs almost nothing if done from line
  one and is expensive to retrofit.

---

## 8. Open items

| Item | State |
|---|---|
| Wireframes | Not started. Constraint: a frightened person, on a phone, at night. Max 4 questions, first result under 60 seconds, huge call and directions buttons. |
| Task split | Not decided. Suggested tracks: data · router logic · frontend · pitch. |
| Phone verification | Blocked (could not make calls from campus). Template and script are ready. |
| `OUT_OF_WINDOW` screen | MVP ships a static page (get tested now, again at 4–6 weeks and 3 months, consider PrEP). Expanding it into a testing-site finder is a pitch talking point. |
| Out-of-area users | Out of scope. Router still returns the nearest Massachusetts site. Optional cheap guard: if the nearest site is >50 km away, show a coverage banner. |
| Spanish / Haitian Creole UI | Part of the intended MVP, sequenced last. Requires that no user-facing string is ever hardcoded — see Conventions. |
| Legal/privacy notice | Not written. Needed before the demo: not medical advice, no exposure data stored, no accounts. |

---

## 9. What to say about the synthetic data in the pitch

Declare it first, before anyone asks. A judge who discovers it alone stops trusting
everything else; a judge told upfront reads it as rigor.

> "The site data you see is synthetic and labelled as such in the interface. Names,
> addresses and hours are real; PEP availability and costs are estimates. We have the
> verification protocol ready — template, call script, per-site questions — and we
> could not execute it in time."

And on liability: the app is never the only source. It always shows an ER as a
guaranteed alternative and tells people to call before setting out. It provides
logistics, not medical advice.

---

## 10. Files

| File | What it is | Who needs it |
|---|---|---|
| `router_spec.md` | The algorithm in pseudocode, with constants, helpers, output contract, 8 test cases, limitations and open items | Whoever writes the backend |
| `schema.sql` | `CREATE TABLE sites`, with every enum value documented | Backend |
| `sites_demo.csv` | The 24 Boston sites, synthetic, English schema. Loads straight into SQLite | Backend |
| `Sitios_PEP_Boston_DEMO.xlsx` | The same data plus `Supuestos_DEMO`, documenting where every invented number came from and the risk if it is wrong | Pitch, and anyone questioning the data |
| `Sitios_PEP_Boston_plantilla.xlsx` | Empty collection template with validations, English call script, per-site questions | Whoever ends up making the calls |
| `PEP_requisitos_por_estado_EEUU.xlsx` | Legal requirements across all 51 US jurisdictions. Background, does not feed the app | Pitch ("here is how it scales") |
