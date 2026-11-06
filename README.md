# Shipping Company Flight Booking

A NanoAgent plugin (`nanoagent.plugin/v0001`): a traveller describes a trip in plain words, an agent books
one one-way flight for it under a shipping company's air-travel policy, as of today, and a deterministic
verifier checks the booking against every rule.

The policy is based on Pitney Bowes' public **Travel and Expense Policy**
(<https://www.pitneybowes.com/us/license-terms-of-use/travel-and-expense-policy-external.html>), its air
travel rules only. This plugin is **unofficial**: it is not made, endorsed or used by Pitney Bowes, and
it restates the policy as exact rules of its own (below).

**Simulated fares and schedules.** Airports and airline names are real; every flight, fare, schedule and
bag fee is synthetic, made by the plugin (see *The simulated flights* below). Airline names are used for
realism only: nothing here is a real fare or a real timetable.

## Tools

| Tool | Does | Code |
|---|---|---|
| `booking_requirements` | What a booking request must give, field by field with examples (read from the contract), the date rules, the airports to choose from, and an example request, as of today. Nothing about the policy: applying it is the agent's job | `src/plugin/requirements.py`, `src/plugin/guide.py` |
| `get_trip` | Begins a booking run for a trip request: the trip as booked today (traveller, airports with country and continent, booking date, fixed or flexible dates, business and checked-bag wishes) and its `run_id` | `src/plugin/trip.py` |
| `search_flights` | The one-way offers on a route departing on the searched days (at most 14 days apart, today or later): airline, flight numbers, operator, cabin, fare, minutes in the air and bag fees | `src/plugin/search.py` |
| `solve_booking` | The answer key: the trip as booked today, its offers and the booking the rules require. NanoAgent runs it before the agent, out of its sight; it is never one of the agent's tools | `src/plugin/solve.py` |

### Tasks

| Task | Does | Runner |
|---|---|---|
| `booking-requirements` | Shows what to tell us to book a flight (topic `ALL`, `FIELDS` or `AIRPORTS`) | `tool`, with `booking_requirements` |
| `search-flights` | Shows the offers on a route and days | `tool`, with `search_flights` |
| `shipping-company-flight-booking` | Books a flight for a trip request under the policy | `agent`, with `get_trip` and `search_flights`; reference `solve_booking` |

The booking task's input is the trip request, which the chat fills from plain words such as "book Maya
Chen, an employee, Boston to London Heathrow any day from Dec 3 to Dec 5, business class and a checked
bag": `traveller_name`, `traveller_type` (`EMPLOYEE`, `NON_EMPLOYEE` or `CONSULTANT`), `origin` and
`destination` (airport codes from the list), `date_from` and `date_to` (the same day for a fixed date, a
range of up to 14 days for flexible dates), `wants_business` and `wants_checked_bag`. The booking date is
today (UTC), read when the answer key is pinned; requests leaving before today or more than 330 days
ahead are refused.

The agent's path is three tool calls: `get_trip` with the request, `search_flights` with the trip's route
and dates, then `submit` (a consultant's trip needs no search). It submits `run_id`, `booked`, `refusal`
(`NONE`, `CONSULTANT` or `NO_COMPLIANT_FLIGHT`), `offer_id` and `traveller_out_of_pocket_cents`.

### The rules (the task's instructions state them exactly)

| Rule | Policy text it formalises | Exact rule |
|---|---|---|
| R1 | "Travel expenses for authorized consultants should not be directly billed to the Company" | A `CONSULTANT` is never booked: refusal `CONSULTANT` |
| R2 | Non-employee travel "should be arranged through the PB designated travel agencies" | `EMPLOYEE` and `NON_EMPLOYEE` follow the same rules; the agent acts as the agency |
| R3 | "All air travel is by commercial airlines" | Never a `CHARTER` offer |
| R4 | "Tickets should be booked at least seven days in advance, if possible" | Depart in the trip's dates; on a `FLEXIBLE` trip, 7 or more days after booking when any allowed offer in the window does (exactly 7 is fine) |
| R5 | Coach within the U.S.; business "only on international flights greater than six hours… or transatlantic flights (of any duration)"; "First class travel will not be reimbursed" | Never `FIRST`. `BUSINESS` only when wanted and the trip is transatlantic (NA and EU), or international with an offer flying more than 360 minutes; then business whenever such an offer exists |
| R6 | "Contractors must book the lowest cost fare, within $100 USD per trip" | Fare at most the lowest allowed fare in the booked cabin + 10000 cents |
| R7 | "One checked-bag fee (up to a maximum of $30) per flight segment is reimbursable" | Out-of-pocket = Σ max(0, bag fee − 3000) per segment when a bag is wanted; then the lowest out-of-pocket among fares within $100 must be booked |
| R8 | — | No offer allowed by R3–R5: refusal `NO_COMPLIANT_FLIGHT` |

Out of scope: the policy's non-air rules, Saturday-night stays, personal travel, fare type and
cancellation, the $40 fee for using an agent instead of the online tool (this agent books directly), upgrades
at no charge, and round trips (the policy states its rules per trip or per flight and adds nothing for a
return flight).

### The simulated flights

`src/plugin/world.py` (the same file as `verifier/world.py`) makes the offers on a route and day from a
SHA-256 stream keyed by the route and the day only, so a search gives the same offers on every machine and
on any booking date, and the verifier rebuilds every search the agent made. Its model, every constant of
which is a modelling choice, not data:

- **Airports:** 68 large airports from OurAirports (public domain), fetched 2026-11-02, with their
  standard-time UTC offsets. Times are UTC; departures leave between 06:00 and 22:00 local time.
- **Airlines:** 29 real airlines, each with its country, hubs among the 68 airports, longest nonstop and
  cabins sold. An airline sells a nonstop when one end is its hub, and connections through its own hubs that
  add at most 35% distance; a domestic trip is sold only by that country's airlines, and no airline flies a
  leg inside another country. Up to three itineraries fly a route each day; flight numbers (e.g. `DL 1482`)
  are stable per airline and leg.
- **Charters:** NetJets, Wheels Up and VistaJet (private jets) offer a flight on about 30% of days on routes
  up to 9000 km: usually at many times an airline fare, sometimes an empty-leg seat that undercuts it.
- **Times:** minutes in the air are 20 + the great-circle distance at 870 km/h; connections take 45 to 240
  minutes (60 at least between countries).
- **Fares:** economy is $50 + 30 x km^0.85 cents, times 0.80-1.35 by day, connections 78-95% of that, and
  low-cost airlines 88%; business is 3-5x economy on long haul (sometimes a 1.4-1.9x sale) and 1.8-3x on
  short flights; U.S. airlines sell domestic first at 1.8-2.6x; some long-haul airlines sell first at 6-9x.
- **Bag fees:** charged once per ticket, on its first flight, economy only: $35-$45 on U.S. airlines in
  North America, included or a $75 basic-economy fee on their long haul; other airlines mostly include a
  bag, or charge $25-$60 on lighter fares.

Exact boundaries (exactly 360 minutes, a fare exactly $100.00 above the lowest, a $30.00 bag fee, a flight
exactly 7 days ahead) rarely occur in realistic data, so the tests and scripted cases check them with
hand-built offers, which replace the world in the tools and the verifier alike.

## Layout

It has the standard plugin layout, which NanoAgent requires:

```text
.
├── nanoagent.yaml   # manifest: id, runtime, permissions (no network), tools, tasks and their instructions
├── contract.py      # each tool's and task's typed input and output: slimconfig Output classes
├── README.md
├── LICENSE
├── pyproject.toml
├── uv.lock
├── .gitignore
├── .env             # needed environment variable names (none)
├── src/plugin/      # the MCP server (__main__.py, IMPLEMENTATIONS) and the tools
│   ├── world.py     # airports, airlines and the simulated offers; the same file as verifier/world.py
│   ├── rules.py     # requests, dates and rules R1-R8 as exact integer code; the same file as verifier/rules.py
│   ├── guide.py     # what a booking request must give; the same file as verifier/guide.py
│   └── receipts.py  # each run's receipts in the workspace: runs/<run id>/trip.json, search-<n>.json
├── tests/           # rules, world, requirements, verifier, scripted cases (tests/cases/*.json), MCP server
├── ui/              # renderers.js / renderers.css: the requirements, the offers table, the booking
├── product/         # product.yaml and icon.svg
└── verifier/        # the deterministic verifier: one module per tool and booking.py for the task
```

The verdict of the booking task is a list of named checks, each with `ok`, `expected`, `actual` and a
message naming the offer and the rule:

- integrity gates: `answer-key` (the pinned key is this request's, booked on the day it was pinned, with
  the route's offers, and follows the rules), `this-run` (the submitted run was begun by `get_trip` for
  this request, on the same booking date, after the key was pinned), `searched`, `receipts-match` (every
  search receipt equals the route's offers for its query, rebuilt by the verifier), `offer-seen` (the
  booked offer was in this run's search results, on the trip's route);
- policy: `refusal`, `commercial`, `dates`, `cabin`, `fare`, `bag`, `out-of-pocket`.

The verdict is valid, scoring 1, only when every check holds; any failed check scores 0, since a
booking either follows the policy or it does not. Checks after a failed one they depend on are
"not checked". Expected values come from the verifier's own copy of the rules applied to the pinned trip
and offers.

## Develop and run

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
```

The tests freeze today at 2026-11-05, so they pass on any day. `uv run pytest` replays the scripted cases
in `tests/cases/` (gold, wrong, missing, malformed, tampered and boundary runs) through the real tools and
verifier, checks the answer key against an independent reading of the rules for 400 varied requests, and
checks the simulated world's plausibility, determinism and size.

NanoAgent passes the folder the plugin may write to as `NANOAGENT_WORKSPACE`; the tools write only
their receipts there, under `runs/`. To check the plugin with NanoAgent from its checkout:

```bash
uv run nanoagent plugin inspect <path to this plugin>
```
