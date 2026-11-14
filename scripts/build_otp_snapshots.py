"""One-time/offline snapshot builder for BTS On-Time Performance data.

Downloads and aggregates the latest published monthly OTP file and writes
the result to data/otp_snapshots.json. Trades a one-time, ~7-10 minute
batch job (run here, offline, ahead of time) for an instant, no-network
runtime lookup in clients/bts_otp.py -- BTS throttles this file to
~60-90 KB/s, so a live per-question fetch is incompatible with a
conversational response time.

Safe to re-run: if the latest available month is already in the snapshot
file, this is a no-op. Re-run it whenever you want to pick up a newly
published month.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from airport_investment_agent.clients.bts_otp import (
    OTP_SNAPSHOT_PATH,
    download_and_aggregate,
    resolve_latest_available_month,
)
from airport_investment_agent.tools.otp_kpis import (
    DDI_HIGH_PERCENTILE,
    DDI_LOW_PERCENTILE,
    MIN_DEPARTURES_FOR_DDI_REFERENCE,
    compute_ddi,
    percentile,
)

# Imported from clients/bts_otp.py rather than recomputed here -- the two
# files sit at different depths under the repo root (scripts/ vs
# airport_investment_agent/clients/), so independently computing "parent.parent"
# in both places previously pointed at two different directories and the
# snapshot silently went unused.
SNAPSHOT_PATH = OTP_SNAPSHOT_PATH


def _month_key(year: int, month: int) -> str:
    return f"{year}-{month:02d}"


def _load_existing_snapshots() -> dict:
    if SNAPSHOT_PATH.exists():
        with SNAPSHOT_PATH.open() as snapshot_file:
            return json.load(snapshot_file)
    return {}


def _save_snapshots(snapshots: dict) -> None:
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SNAPSHOT_PATH.open("w") as snapshot_file:
        json.dump(snapshots, snapshot_file, indent=2, sort_keys=True)


def _build_month_snapshot(year: int, month: int) -> dict:
    print(
        f"Downloading {year}-{month:02d} (this can take several minutes)...", flush=True
    )
    aggregate = download_and_aggregate(year, month)

    reference_ddis = sorted(
        compute_ddi(entry)
        for entry in aggregate.values()
        if entry["non_cancelled_departures"] >= MIN_DEPARTURES_FOR_DDI_REFERENCE
    )
    ddi_reference = None
    if len(reference_ddis) >= 2:
        ddi_reference = {
            "low_percentile": percentile(reference_ddis, DDI_LOW_PERCENTILE),
            "high_percentile": percentile(reference_ddis, DDI_HIGH_PERCENTILE),
        }

    airports = {}
    for origin, entry in aggregate.items():
        if entry["scheduled"] == 0:
            continue
        airports[origin] = {
            **entry,
            "completion_rate": 1 - (entry["cancelled"] / entry["scheduled"]),
            "departure_delay_index": (
                compute_ddi(entry) if entry["non_cancelled_departures"] else None
            ),
            "average_taxi_out_minutes": (
                entry["taxi_out_minutes_sum"] / entry["taxi_out_sample_count"]
                if entry["taxi_out_sample_count"]
                else None
            ),
            "long_haul_percentage": 100
            * (entry["long_haul_count"] / entry["scheduled"]),
        }

    return {
        "year": year,
        "month": month,
        "ddi_reference": ddi_reference,
        "airports": airports,
    }


def main() -> int:
    year, month = resolve_latest_available_month()
    key = _month_key(year, month)

    snapshots = _load_existing_snapshots()
    if key in snapshots:
        print(
            f"{key}: already snapshotted, nothing to do. Snapshot file: {SNAPSHOT_PATH}"
        )
        return 0

    snapshots[key] = _build_month_snapshot(year, month)
    _save_snapshots(snapshots)
    print(
        f"{key}: done ({len(snapshots[key]['airports'])} airports). Snapshot file: {SNAPSHOT_PATH}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
