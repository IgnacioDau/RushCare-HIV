# Screen specification

Five screens. Designed for one person: frightened, on a phone, possibly at night,
possibly on a borrowed device. Every decision below follows from that.

**Global rules**

- First useful result in under 60 seconds from landing.
- Maximum four questions before something useful appears.
- Nothing is stored. No accounts, no history, no cookies beyond the session.
- Every string comes from `strings/<region>/<lang>.json`. Nothing hardcoded.
- The countdown is persistent from screen 2 onward, but small and calm — a fact, not
  an alarm. No red flashing, no ticking sound. Panic slows people down.
- Tap targets for call and directions are at least 48px and sit within thumb reach at
  the bottom of the screen, not the top.
- Works with no JavaScript for the core path where possible, and on a slow connection.

---

## Screen 1 — Landing / first question

```
┌──────────────────────────────┐
│  Get PEP in Boston           │
│  HIV prevention medication   │
│  that works within 72 hours  │
│                              │
│  When was the possible       │
│  exposure?                   │
│                              │
│  ┌──────────────────────┐    │
│  │ Less than an hour ago│    │
│  ├──────────────────────┤    │
│  │ Earlier today        │    │
│  ├──────────────────────┤    │
│  │ Yesterday            │    │
│  ├──────────────────────┤    │
│  │ Two days ago         │    │
│  ├──────────────────────┤    │
│  │ Three or more days   │    │
│  └──────────────────────┘    │
│                              │
│  Enter an exact time instead │
│                              │
│  ─────────────────────────   │
│  In an emergency, any        │
│  hospital emergency room     │
│  can see you right now.      │
└──────────────────────────────┘
```

No splash, no explainer, no cookie banner. The question *is* the landing page.

The emergency-room line at the bottom is the escape hatch: someone who does not want
to answer four questions gets a correct answer immediately. This line appears on every
screen of the flow.

"Three or more days" branches straight to screen 5.

---

## Screen 2 — What happened

```
┌──────────────────────────────┐
│  ← back        68 hours left │
│                              │
│  What happened?              │
│                              │
│  ┌──────────────────────┐    │
│  │ Sex without a condom │    │
│  ├──────────────────────┤    │
│  │ A condom broke or    │    │
│  │ came off             │    │
│  ├──────────────────────┤    │
│  │ I'm not sure         │    │
│  └──────────────────────┘    │
│                              │
│  Something else:             │
│  · This was an assault       │
│  · This happened at work     │
│  · Shared needles            │
└──────────────────────────────┘
```

The three MVP options are buttons; the other three are quieter text links that open the
referral screens. That hierarchy reflects what the router actually handles, without
hiding the paths it does not.

Assault and occupational referral screens both end with "Continue to the PEP finder
anyway" — the person decides, not the app.

---

## Screen 3 — Insurance

```
┌──────────────────────────────┐
│  ← back        68 hours left │
│                              │
│  Do you have health          │
│  insurance?                  │
│                              │
│  This only changes what we   │
│  estimate it will cost. It   │
│  never changes whether you   │
│  can get PEP.                │
│                              │
│  ┌──────────────────────┐    │
│  │ MassHealth           │    │
│  ├──────────────────────┤    │
│  │ I don't have any     │    │
│  ├──────────────────────┤    │
│  │ I'd rather not say   │    │
│  └──────────────────────┘    │
│                              │
│  ☐ I'm under 18              │
└──────────────────────────────┘
```

The explanatory line above the options is doing real work: people skip or lie on
insurance questions because they expect to be turned away. Saying it changes only the
cost estimate is both true and disarming.

"I'd rather not say" is treated as uninsured — the option that never under-promises.

The under-18 checkbox is optional and filters nothing. Ticking it reveals the
Massachusetts consent note and the insurance-EOB warning inline, and nudges ranking
toward sites that see minors unaccompanied.

---

## Screen 4 — Location

```
┌──────────────────────────────┐
│  ← back        68 hours left │
│                              │
│  Where are you?              │
│                              │
│  ┌──────────────────────┐    │
│  │ Pick a neighborhood ▾│    │
│  └──────────────────────┘    │
│                              │
│  or  drop a pin on the map   │
│  or  type an address         │
│                              │
│  ┌──────────────────────┐    │
│  │                      │    │
│  │   [Leaflet map]      │    │
│  │                      │    │
│  └──────────────────────┘    │
│                              │
│  We don't ask your device    │
│  for your location and we    │
│  don't save what you pick.   │
└──────────────────────────────┘
```

No browser geolocation prompt. The neighborhood picker is the default because its
coordinates are local — nothing leaves the server. Typing an address triggers a
Nominatim lookup, and the privacy line says so when that option is selected.

---

## Screen 5a — Results

```
┌──────────────────────────────┐
│  68 hours left               │
│                              │
│  Fenway Health               │
│  1340 Boylston St · 12 min   │
│  Open until 7:00 PM          │
│  Likely $0 with Health       │
│  Safety Net                  │
│  ⚠ Unverified — call ahead   │
│  ┌────────┐  ┌────────────┐  │
│  │  Call  │  │ Directions │  │
│  └────────┘  └────────────┘  │
│  What to say when you get    │
│  there →                     │
│  ─────────────────────────   │
│  Boston Medical Center ER    │
│  ...                         │
│  ─────────────────────────   │
│  Whittier Street Health Ctr  │
│  ...                         │
│                              │
│  See 2 more options          │
└──────────────────────────────┘
```

Three cards, expandable to five, filtered by the score cutoff. Each card leads with
*why it was chosen* (open, distance, cost) rather than with a description of the place.

An emergency room always appears among the results, even when clinics outrank it.

Warnings render inline on the card they apply to — unverified data, Health Safety Net,
pharmacy out-of-pocket, sooner-is-better — never as a wall of disclaimers at the top.

---

## Screen 5b — Nothing open

```
┌──────────────────────────────┐
│  68 hours left               │
│                              │
│  Nothing is open right now   │
│                              │
│  The first to open is        │
│  Fenway Health, at 8:00 AM   │
│  — in 6 hours.               │
│                              │
│  You have 68 hours left in   │
│  the window, so waiting is   │
│  safe.                       │
│                              │
│  ┌──────────────────────┐    │
│  │ Remind me at 8:00 AM │    │
│  └──────────────────────┘    │
│                              │
│  PEP works better the sooner │
│  you take it. If you'd       │
│  rather not wait:            │
│  ┌──────────────────────┐    │
│  │ Emergency rooms open │    │
│  │ now                  │    │
│  └──────────────────────┘    │
└──────────────────────────────┘
```

Not an error state. It answers the question the person actually has at 3 AM: what time
do I set my alarm for? The reminder is a local notification or a calendar file — no
account, nothing stored server-side.

This screen will be common in the Mexico region, where most units are weekday-only.

---

## Screen 6 — What to say

Reached from any result card, and the screen the whole product exists to deliver.

```
┌──────────────────────────────┐
│  ← back                      │
│  What to say when you get    │
│  there                       │
│                              │
│  ┌──────────────────────┐    │
│  │ "I had a possible    │    │
│  │  HIV exposure about  │    │
│  │  6 hours ago and I   │    │
│  │  need PEP."          │    │
│  │            [ copy ]  │    │
│  └──────────────────────┘    │
│                              │
│  What to bring               │
│  What to expect              │
│  What they cannot do         │
│  After the visit             │
│  (accordions, closed by      │
│   default)                   │
└──────────────────────────────┘
```

The sentence is large, quotable and copyable, with the hour count filled in. Everything
else is collapsed: someone standing outside a hospital door needs one sentence, not an
article. The copy button matters — people rehearse by reading it off the screen.

---

## Screen 7 — Past 72 hours

Not a dead end and not a failure message. It states plainly that PEP will not work now,
then gives the three things that do matter: test now and again at 4–6 weeks and 3
months, what symptoms to mention, and PrEP for the future. Copy lives under
`out_of_window`.

---

## What is deliberately absent

- No account creation, no saved history, no "welcome back".
- No chatbot or symptom checker — neither belongs in a 72-hour decision.
- No risk calculator. Telling someone their exposure was "low risk" discourages a
  medication with almost no downside.
- No ratings or reviews of clinics.
- No imagery of people. Stock photos of worried faces make this harder to look at.
