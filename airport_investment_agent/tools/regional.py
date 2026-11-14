"""Region-based and nationwide airport ranking via one shared peer-set
workflow: build the peer set -> compute KPIs per airport -> normalize
within the peer set -> weight and rank. Normalization is always relative
to the other airports in the same peer set (one region, or the nationwide
union of all regions), never against an outside reference - a different
contract than compare_congestion's nationwide-normalized congestion_score.

Region membership is a fixed, curated list of major commercial airports
per region (no free dataset encodes informal regions like "New England";
only US state/FAA codes exist), not a live geographic query. The
"nationwide" ranking is the union of these same curated lists (~46
airports), not every U.S. commercial airport - see rank_airports_nationwide.
"""

from collections.abc import Sequence

from airport_investment_agent.models import AirportDataError, UnknownRegionError
from airport_investment_agent.tools.otp_kpis import (
    get_average_taxi_out_minutes,
    get_completion_data_period,
    get_delayed_departure_rate_pct,
    get_departure_delay_index,
    get_long_haul_percentage,
)
from airport_investment_agent.tools.traffic import get_airport_traffic
from airport_investment_agent.utils import merge_unique

# Regional composite weights: volume 20%, growth 25%,
# DDI 25%, taxi-out 15%, long-haul share 15%.
VOLUME_WEIGHT = 0.20
GROWTH_WEIGHT = 0.25
DDI_WEIGHT = 0.25
TAXI_OUT_WEIGHT = 0.15
LONG_HAUL_WEIGHT = 0.15

REGION_AIRPORTS: dict[str, list[str]] = {
    "New England": ["BOS", "PVD", "BDL", "MHT", "PWM", "BTV", "BGR"],
    "Pacific Northwest": ["SEA", "PDX", "GEG", "BOI", "EUG", "PAE", "BLI"],
    "Texas": ["DFW", "IAH", "AUS", "SAT", "DAL", "HOU", "ELP", "LBB", "MAF", "CRP"],
    "Southeast": [
        "ATL",
        "CLT",
        "MCO",
        "MIA",
        "FLL",
        "TPA",
        "BNA",
        "MEM",
        "RDU",
        "SAV",
        "CHS",
        "JAX",
    ],
    "Mid-Atlantic": [
        "JFK",
        "LGA",
        "EWR",
        "PHL",
        "BWI",
        "DCA",
        "IAD",
        "PIT",
        "RIC",
        "ORF",
    ],
}

_REGION_LOOKUP = {name.strip().lower(): name for name in REGION_AIRPORTS}


def _resolve_region(region_name: str) -> str:
    canonical_name = _REGION_LOOKUP.get(region_name.strip().lower())
    if canonical_name is None:
        recognized = ", ".join(sorted(REGION_AIRPORTS))
        raise UnknownRegionError(
            f"Unknown region: '{region_name}'. Recognized regions: {recognized}."
        )
    return canonical_name


def _percentile_rank(values: Sequence[float], value: float) -> float:
    """rank/(N-1), 0 for the minimum. Used for volume, which is typically
    right-skewed (a few mega-hubs, several mid-size airports) - spaces the
    mid-size airports out instead of compressing them near the bottom the
    way min-max would."""
    if len(values) <= 1:
        return 0.5
    ordered = sorted(values)
    return ordered.index(value) / (len(ordered) - 1)


def _min_max_normalize(values: Sequence[float], value: float) -> float:
    lo, hi = min(values), max(values)
    if hi == lo:
        return 0.5
    return (value - lo) / (hi - lo)


def _rank_airports(
    codes: list[str], scope_label: str, scope_caveats: list[str]
) -> list[dict]:
    """Shared engine behind rank_airports_by_region and
    rank_airports_nationwide: build the peer set from `codes` (excluding
    any airport whose data can't be fetched, rather than failing the whole
    request), compute volume/growth/DDI/taxi-out/long-haul per airport,
    normalize each metric within this peer set only, then apply the
    composite weights. `scope_label` and `scope_caveats` are the only
    things that differ between a regional and a nationwide call.
    """
    peer_set = []
    excluded: list[str] = []
    for code in codes:
        try:
            peer_set.append(
                {
                    "traffic": get_airport_traffic(code),
                    "ddi": get_departure_delay_index(code),
                    "delayed_departure_rate_pct": get_delayed_departure_rate_pct(code),
                    "taxi_out": get_average_taxi_out_minutes(code),
                    "long_haul_pct": get_long_haul_percentage(code),
                }
            )
        except AirportDataError as error:
            # A known data-coverage gap (no traffic/DDI/taxi-out/long-haul
            # data for this airport) must not take down the whole region's
            # ranking; it's excluded and disclosed instead. Anything that
            # isn't an AirportDataError is a real bug, not a coverage gap,
            # and should propagate rather than be silently swallowed here.
            excluded.append(f"{code}: {error}")

    if not peer_set:
        raise UnknownRegionError(
            f"Could not build a peer set for {scope_label}: {'; '.join(excluded)}"
        )

    volumes = [p["traffic"].passengers for p in peer_set]
    growths = [p["traffic"].growth_rate for p in peer_set]
    ddis = [p["ddi"] for p in peer_set]
    taxi_outs = [p["taxi_out"] for p in peer_set]
    long_hauls = [p["long_haul_pct"] for p in peer_set]
    period_year, period_month = get_completion_data_period()

    scored = []
    for p in peer_set:
        volume_score = _percentile_rank(volumes, p["traffic"].passengers)
        growth_score = _min_max_normalize(growths, p["traffic"].growth_rate)
        ddi_score = _min_max_normalize(ddis, p["ddi"])
        taxi_out_score = _min_max_normalize(taxi_outs, p["taxi_out"])
        long_haul_score = _min_max_normalize(long_hauls, p["long_haul_pct"])

        investment_score = (
            VOLUME_WEIGHT * volume_score
            + GROWTH_WEIGHT * growth_score
            + DDI_WEIGHT * ddi_score
            + TAXI_OUT_WEIGHT * taxi_out_score
            + LONG_HAUL_WEIGHT * long_haul_score
        )
        scored.append(
            (
                p,
                volume_score,
                growth_score,
                ddi_score,
                taxi_out_score,
                long_haul_score,
                investment_score,
            )
        )

    scored.sort(key=lambda item: item[-1], reverse=True)

    caveats = list(scope_caveats) + [
        f"DDI, taxi-out, and long-haul share reflect one month's data ({period_year}-{period_month:02d}).",
        "departure_delay_index (DDI) is this project's own composite of departure "
        "delay rate and severity, not an industry-standard metric; "
        "delayed_departure_rate_pct (in each airport's raw block) is DOT's own "
        "standard on-time definition (14 CFR Part 234) and can be cross-checked "
        "against BTS's published figures directly.",
    ]
    if excluded:
        caveats.append(
            f"Excluded from ranking (data unavailable): {'; '.join(excluded)}"
        )

    results = []
    for rank, (
        p,
        volume_score,
        growth_score,
        ddi_score,
        taxi_out_score,
        long_haul_score,
        investment_score,
    ) in enumerate(scored, start=1):
        diagnostic = (
            "both DDI and taxi-out are high in this peer set - airside "
            "(runway/taxiway) capacity is the stronger hypothesis"
            if ddi_score >= 0.6 and taxi_out_score >= 0.6
            else (
                "DDI is high but taxi-out is not - delays here may be more "
                "gate/schedule-driven than airside capacity"
                if ddi_score >= 0.6
                else None
            )
        )
        results.append(
            {
                "rank": rank,
                "region": scope_label,
                "iata_code": p["traffic"].iata_code,
                "investment_score": round(investment_score, 4),
                "volume_score": round(volume_score, 4),
                "growth_score": round(growth_score, 4),
                "ddi_score": round(ddi_score, 4),
                "taxi_out_score": round(taxi_out_score, 4),
                "long_haul_score": round(long_haul_score, 4),
                "raw": {
                    "passengers": p["traffic"].passengers,
                    "growth_rate": round(p["traffic"].growth_rate, 4),
                    "departure_delay_index": round(p["ddi"], 2),
                    "delayed_departure_rate_pct": round(
                        p["delayed_departure_rate_pct"], 2
                    ),
                    "average_taxi_out_minutes": round(p["taxi_out"], 2),
                    "long_haul_percentage": round(p["long_haul_pct"], 2),
                },
                "diagnostic": diagnostic,
                "caveats": merge_unique(p["traffic"].caveats, caveats),
            }
        )
    return results


def rank_airports_by_region(region_name: str) -> list[dict]:
    """Rank airports in a named region by investment potential -- see
    _rank_airports for the shared peer-set/normalize/rank workflow.
    """
    canonical_region = _resolve_region(region_name)
    codes = REGION_AIRPORTS[canonical_region]
    scope_caveats = [
        f"All scores are relative to the other airports in {canonical_region} "
        "in this peer set only, not a nationwide comparison.",
        "Region membership is a fixed, manually curated list, not authoritative or exhaustive.",
    ]
    return _rank_airports(codes, canonical_region, scope_caveats)


def rank_airports_nationwide() -> list[dict]:
    """Rank airports nationally by investment potential, using the same
    peer-set workflow as rank_airports_by_region but over the union of all
    curated regions' airports as one combined peer set -- so scores are
    normalized against one consistent nationwide universe, instead of the
    five separate, incompatible per-region normalizations you'd get from
    calling rank_airports_by_region for every region and comparing the
    results (those aren't directly comparable).
    """
    codes = sorted({code for airports in REGION_AIRPORTS.values() for code in airports})
    scope_caveats = [
        "All scores are relative to the other airports in this nationwide "
        "peer set only.",
        f"This 'nationwide' set is the union of the {len(REGION_AIRPORTS)} curated "
        f"regions' airport lists ({len(codes)} airports total) -- a fixed, manually "
        "curated list, not every U.S. commercial airport.",
    ]
    return _rank_airports(codes, "Nationwide", scope_caveats)
