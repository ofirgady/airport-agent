# Scoring Methodology

Part of this project's design documentation (see [README](../README.md#documentation) for the full set): [Design Notes](design.md) (data sources, KPIs, assumptions) · **Scoring Methodology** · [Key Tradeoffs](key-tradeoffs.md) · [Where/How AI Is Used](where-how-ai-is-used.md).

Three distinct formulas exist, each with its own normalization contract:

| Formula | Applies to | Composite | Normalized against |
|---|---|---|---|
| Multi-airport comparison | `compare_airports` | `investment_score = 0.35·volume + 0.25·efficiency + 0.25·growth + 0.15·demand_pressure` | The comparison set's own max (volume/efficiency) or min-max range (growth) |
| Region / nationwide ranking | `rank_airports_by_region`, `rank_airports_nationwide` | `investment_score = 0.20·volume + 0.25·growth + 0.25·ddi + 0.15·taxi_out + 0.15·long_haul` | One peer set - a curated region, or the union of all five (~46 airports) for "nationwide" |
| Single-airport unmet-demand | `estimate_unmet_demand`, `compare_unmet_demand` | Equal-weighted (25/25/25/25) blend of volume, load pressure, growth, congestion | A fixed reference band for growth - no natural comparison set for one airport |

**Notes:**
- `demand_pressure = 0.5·volume + 0.5·efficiency`, feeding into the first formula's `demand_pressure` term.
- Region and nationwide ranking share one engine (`regional._rank_airports`) - only the peer set and a disclosed scope caveat differ.
- `compare_unmet_demand` computes the same score for two named airports atomically (both or neither), not a distinct formula.
- All composite weights are a disclosed judgment call, not derived from data.

Conflating these three contracts is a documented pitfall - see `models/models.py`'s `UnmetDemandScore` docstring for why its `growth_vs_fixed_band` field is deliberately not named `growth_score`, despite measuring a conceptually similar thing to `AirportScore.growth_score`.
