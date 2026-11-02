# Shipping Company Flight Booking

A NanoAgent plugin (`nanoagent.plugin/v0001`): an agent books one one-way flight for a shipping
company's traveller under the company's air-travel policy, and a deterministic verifier checks the
booking against every rule.

The policy is based on Pitney Bowes' public **Travel and Expense Policy**
(<https://www.pitneybowes.com/us/license-terms-of-use/travel-and-expense-policy-external.html>), its air
travel rules only. This plugin is **unofficial**: it is not made, endorsed or used by Pitney Bowes, and
it restates the policy as exact rules of its own (below).

## Tools

| Tool | Does | Code |
|---|---|---|
| `get_trip` | The trip a seed makes: traveller and type, origin and destination airports (country and continent), booking date, fixed or flexible dates, whether business class and a checked bag are wanted; it begins a booking run and returns its `run_id` | `src/plugin/trip.py` |
| `search_flights` | The seed's one-way offers on a route departing on the searched days (at most 14 days): operator, cabin, fare, minutes in the air and each segment's bag fee | `src/plugin/search.py` |
| `solve_booking` | The answer key: the booking the rules require. NanoAgent runs it before the agent, out of its sight; it is never one of the agent's tools | `src/plugin/solve.py` |

### Tasks

| Task | Does | Runner |
|---|---|---|
| `show-trip` | Shows a seed's trip | `tool`, with `get_trip` |
| `search-flights` | Shows a seed's offers on a route and days | `tool`, with `search_flights` |
| `shipping-company-flight-booking` | Books a flight for a seed's trip under the policy | `agent`, with `get_trip` and `search_flights`; reference `solve_booking` |

The task input is a seed from 0 to 9999. The agent's path is three tool calls: `get_trip`,
`search_flights` with the trip's route and dates, then `submit` (a consultant's trip needs no search).
It submits `run_id`, `booked`, `refusal` (`NONE`, `CONSULTANT` or `NO_COMPLIANT_FLIGHT`), `offer_id`
and `traveller_out_of_pocket_cents`.

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

Out of scope: the policy's non-air rules, Saturday-night stays, personal travel, the $40 fee for using
an agent instead of the online tool (this agent books directly), and upgrades at no charge.

### Seeds and scenarios

The seed's last digit picks the kind of case, so every rule and boundary can be asked for:

| Last digit | Scenario |
|---|---|
| 0 | `domestic-economy`: coach in the U.S.; traps: first class, a cheaper charter, fares at exactly +$100.00 and +$100.01 |
| 1 | `long-haul-business`: international, over 6 h in the air, business wanted |
| 2 | `short-transatlantic`: transatlantic under 6 h, business wanted: allowed anyway |
| 3 | `exactly-360-minutes`: business flying exactly 360 min (not allowed), sometimes a 361-min connection (allowed) |
| 4 | `consultant`: never booked |
| 5 | `flexible-later-possible`: cheaper flights under 7 days ahead are out; one flight leaves exactly 7 days ahead |
| 6 | `flexible-all-soon`: the whole window is under 7 days ahead, so any day in it |
| 7 | `checked-bag-trade-off`: the cheapest fare's bag costs more than a fare within $100 that includes it (bag fees of $30.00 and $30.01 occur) |
| 8 | `charter-only`: only charters and first class fly in the window: no compliant flight |
| 9 | `business-cheaper`: a business fare below economy that is still not allowed |

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
│   ├── data/airports.json  # 68 airports from OurAirports (public domain), fetched 2026-11-02
│   ├── generator.py # seed -> trip and offers (prng.py: a SHA-256 stream, the same on every machine)
│   ├── rules.py     # R1-R8 as exact integer code, the same file as verifier/rules.py
│   └── receipts.py  # each run's receipts in the workspace: runs/<run id>/trip.json, search-<n>.json
├── tests/           # rules, generator, verifier, scripted cases (tests/cases/*.json), MCP server
├── ui/              # renderers.js / renderers.css: the trip card, the offers table, the booking
├── product/         # product.yaml and icon.svg
└── verifier/        # the deterministic verifier: one module per tool and booking.py for the task
```

Airports are real (code, city, country, continent, coordinates); minutes in the air come from the
great-circle distance. Carriers, fares, schedules and bag fees are synthetic, generated from the seed,
so every boundary case can be planted and the same seed always gives the same answer.

The verdict of the booking task is a list of named checks, each with `ok`, `expected`, `actual` and a
message naming the offer and the rule:

- integrity gates: `answer-key` (the pinned key is this seed's and follows
  the rules), `this-run` (the submitted run was begun by `get_trip` for this seed after the key was
  pinned), `searched`, `receipts-match` (every search receipt equals the pinned offers for its query),
  `offer-seen` (the booked offer was in this run's search results);
- policy: `refusal`, `commercial`, `dates`, `cabin`, `fare`, `bag`, `out-of-pocket`.

The verdict is valid, scoring 1, only when every check holds; any failed check scores 0, since a
booking either follows the policy or it does not. Checks after a failed one they depend on are
"not checked". Expected values come from the
verifier's own copy of the rules applied to the pinned trip and offers.

## Develop and run

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
```

`uv run pytest` replays the scripted cases in `tests/cases/` (gold, wrong, missing, malformed,
tampered and boundary runs) through the real tools and verifier, checks the answer key against an
independent reading of the rules for 1000 seeds, and builds all 10000 seeds.

NanoAgent passes the folder the plugin may write to as `NANOAGENT_WORKSPACE`; the tools write only
their receipts there, under `runs/`. To run a task with NanoAgent from its checkout:

```bash
uv run nanoagent plugin inspect <path to this plugin>
```
