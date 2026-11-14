# Design Notes - Data Sources, KPIs & Assumptions

Part of this project's design documentation (see [README](../README.md#documentation) for the full set): **Design Notes** · [Scoring Methodology](scoring-methodology.md) · [Key Tradeoffs](key-tradeoffs.md) · [Where/How AI Is Used](where-how-ai-is-used.md).

## Data Sources

| Source | Provides | Why this shape |
|---|---|---|
| **BTS T-100** (`data.bts.gov/resource/r495-tyji.json`, Socrata JSON API, free, no key) | Passengers, departures, seats, per calendar year - plus BTS's own precomputed `total_load_factor` and `total_passengers_flight` fields, used directly (see KPI table) | No month-level field exists at all (verified live) - the current year is one collapsed year-to-date row, not 12 monthly rows. Calendar-year-over-calendar-year is the honest ceiling of what this data supports |
| **BTS On-Time Performance** (`transtats.bts.gov/PREZIP/...zip`, free, no key, large throttled flat file) | Flight-level records for one month - powers completion rate, congestion, taxi-out, and long-haul share | One shared download/parse pass, since fetching this file four times per query would be needlessly slow. Delayed-departure classification uses BTS's own `DepDel15` field rather than re-deriving the threshold |
| **Region membership** | A small hardcoded dict of five curated U.S. regions | No free dataset encodes informal regions like "New England" - verified live against OurAirports and FAA data, both of which resolve only to state/administrative codes. The nationwide ranking reuses this same dict's union (~46 airports) as its peer set |

Every KPI below was checked against BTS's own live field list before deciding whether to compute it ourselves or use a published field directly - `total_load_factor`, `total_passengers_flight`, and `DepDel15` were all found and adopted this way.

## KPI Definitions

| KPI | Formula | Source |
|---|---|---|
| Load factor | BTS's own `total_load_factor` field¹ | T-100 |
| Passengers per departure | BTS's own `total_passengers_flight` field | T-100 |
| Growth rate | (current year - prior year) / prior year | T-100, 2 most recent complete years |
| Completion rate | 1 - cancelled / scheduled (the industry-standard "completion factor") | On-Time Performance, latest month |
| Delayed-departure rate | % of non-cancelled departures BTS's own `DepDel15` field flags ≥15min late² | On-Time Performance, latest month |
| Departure Delay Index (DDI, 0-100) | `delay_rate_pct·0.6 + severity_pct·0.4`³ | On-Time Performance, latest month |
| Congestion score (0-1) | This airport's DDI, clipped and rescaled against the nationwide 5th-95th percentile DDI band (airports with ≥100 non-cancelled departures) | On-Time Performance, latest month |
| Average taxi-out minutes | Mean `TaxiOut` across non-cancelled departures | On-Time Performance, latest month |
| Long-haul share | % of flights with Distance ≥2300mi⁴ | On-Time Performance, latest month |
| Unmet-demand score (0-1) | Equal-weighted (25/25/25/25) blend of volume, load pressure, growth, congestion | Derived |

¹ Not a flat `passengers/seats` ratio - official load factor is RPM/ASM (revenue passenger-miles ÷ available seat-miles), which only equals a flat ratio for a single nonstop segment. Aggregated across a whole airport-year of mixed-distance routes, the two can genuinely diverge, so BTS's own distance-weighted figure is used instead of approximating it.
² DOT's own on-time standard (14 CFR Part 234) - exposed as its own field so DDI can be cross-checked against the official definition.
³ `delay_rate_pct` is the delayed-departure rate above; `severity_pct` is the average delay among those, capped at 60min, as a %. This composite (the weights and the cap) is this project's own proxy, not an industry-standard metric - no FAA/DOT/BTS metric by this name exists; only the ≥15min rate ingredient is DOT's official definition.
⁴ A disclosed, round-number judgment call, not a BTS-defined category. Published airline thresholds for where "long-haul" starts range from ~700mi to 3,000mi depending on carrier; the EU's own short/medium/long-haul boundary sits at roughly 1,180-2,175mi.

See [Scoring Methodology](scoring-methodology.md) for how these KPIs combine into the three composite scores.

## Assumptions, Limitations, Proxies

- **Congestion is a proxy for delay, not physical runway/airspace capacity, and DDI is this project's own formula, not an industry-standard one.** A high score can reflect weather, staffing, or hub connection-bank scheduling rather than genuine throughput saturation. `delayed_departure_rate_pct` is exposed alongside DDI so the DOT-standard portion can be checked independently of the custom blend.
- **Unmet demand is an inferred proxy, not a measurement.** No public data source counts passengers who wanted to fly but couldn't get a seat.
- **Long-haul share reflects one month's schedule**, not an annual average - seasonal route changes aren't captured.
- **On-Time Performance data can go stale between snapshot rebuilds.** `traffic.py` checks the snapshot's age on every lookup and appends a caveat suggesting a rebuild (`scripts/build_otp_snapshots.py`) once it's more than `STALE_DATA_WARNING_MONTHS` old - a disclosed staleness check, not an automatic refresh.
- **Region membership is a fixed, manually curated list**, not an authoritative or exhaustive boundary; the nationwide ranking's peer set (their union) inherits the same limitation.
- **A named U.S. scope outside the five curated regions** (a state, metro area, or informal area) is answered by having the LLM identify a plausible airport list from its own knowledge, then running that list through the same deterministic `compare_airports_tool` scoring. The airport *list* is model-selected and disclosed as such - every number computed from it is still real, tool-computed data.
- **Model choice is a stated assumption, not an unexamined default.** `airport_agent` is pinned to `gpt-5.4-mini` at the SDK's own default reasoning effort (`"none"`), made explicit and live-compared against a bumped `reasoning.effort="low"` on the three behaviors the system prompt most depends on: routing across near-duplicate tools, relaying a tool's own validation-error text instead of self-refusing, and not conflating `growth_score` with `growth_vs_fixed_band`. Both tiers got all three right, so the cheaper/faster default was kept.
- **Tool-routing correctness has no default-run test coverage.** The default `pytest` run (no `OPENAI_API_KEY` required) verifies tool schemas, scoring math, and static agent config, but not whether the LLM actually picks the right tool for a given question - that's only exercised by a handful of `@pytest.mark.live` tests. Closing this without a live call would mean building a scripted fake `Model` test double, judged not worth the effort and the ongoing coupling risk to the SDK's internal response format for a lean MVP. Accepted, disclosed gap rather than an oversight.
