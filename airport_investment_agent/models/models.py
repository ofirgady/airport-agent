from pydantic import BaseModel, Field


class AirportTraffic(BaseModel):
    """Traffic statistics for a single airport over a given period."""

    iata_code: str
    passengers: int
    departures: int
    seats: int
    load_factor: float
    passengers_per_departure: float
    growth_rate: float
    completion_rate: float | None
    caveats: list[str]


class AirportScore(BaseModel):
    """Normalized 0-1 scores for a single airport within a comparison set.

    demand_pressure_proxy deliberately blends only volume_score and
    efficiency_score (current capacity utilization), not growth_score
    (trajectory) -- growth already gets its own explicit weight in
    compare_airports's top-level investment_score, so including it here
    too would double-count it.
    """

    iata_code: str
    volume_score: float
    efficiency_score: float
    growth_score: float
    demand_pressure_proxy: float


class UnmetDemandScore(BaseModel):
    """Normalized 0-1 unmet-demand proxy components for a single airport.

    growth_vs_fixed_band is normalized against a fixed reference band (see
    scoring.GROWTH_SCORE_FLOOR_RATE/GROWTH_SCORE_CEILING_RATE), unlike
    AirportScore.growth_score, which is comparison-set-relative (see
    scoring.compute_demand_pressure). Different normalization spaces,
    reaching the same LLM context - named apart on purpose.
    """

    iata_code: str
    volume_score: float
    load_pressure_score: float
    growth_vs_fixed_band: float
    congestion_score: float
    unmet_demand_score: float
    drivers: list[str]


class RankedAirport(BaseModel):
    """One airport's full result within a completed comparison."""

    traffic: AirportTraffic
    score: AirportScore
    investment_score: float
    rank: int


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    message: str = Field(min_length=1, max_length=4000)


class ToolInfo(BaseModel):
    """One entry in the live /tools registry introspection response."""

    name: str
    description: str | None


class RunLogEntry(BaseModel):
    """One line of runs.jsonl. Tolerant of every shape the log has had over
    the project's lifetime -- unsupported_numbers predates the number
    guardrail and input_tokens/output_tokens/total_tokens/
    latency_seconds predate usage/latency logging, so both default rather
    than require every historical entry to be backfilled."""

    timestamp: str
    session_id: str
    query: str
    tool_calls: list[str]
    response: str
    unsupported_numbers: list[float] = Field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    latency_seconds: float | None = None


class LongHaulPercentage(BaseModel):
    """Percentage of an airport's scheduled flights this month that are
    long-haul, with raw counts and the source month/year."""

    iata_code: str
    threshold_miles: int
    long_haul_percentage: float
    long_haul_flight_count: int
    scheduled_flight_count: int
    data_period: dict[str, int]
    summary: str
    caveats: list[str]
