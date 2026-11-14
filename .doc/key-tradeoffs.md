# Key Tradeoffs

Part of this project's design documentation (see [README](../README.md#documentation) for the full set): [Design Notes](design.md) (data sources, KPIs, assumptions) · [Scoring Methodology](scoring-methodology.md) · **Key Tradeoffs** · [Where/How AI Is Used](where-how-ai-is-used.md).

Each tradeoff below is framed against the quality attribute it actually trades off, not just "what we picked" - the biggest one (session storage) is the one most likely to matter if this project ever needed to run at real scale.

## The biggest one: session storage

| Decision | Instead of | Quality attributes traded | Why |
|---|---|---|---|
| **SQLite file-based sessions** (`SQLiteSession`, one local `.db` file) | A managed, multi-writer database (Postgres, DynamoDB, etc.) | **Scalability & availability** traded for **operational simplicity & cost** | Zero infrastructure to provision, secure, or pay for - the SDK ships `SQLiteSession` as a first-class primitive, so persistence works out of the box with no external service. The real cost: SQLite is single-writer and file-local. It can't be shared across multiple API processes or machines, has no built-in replication/backup, and concurrent write throughput is limited. Correct for a single-process demo; the first thing that would need replacing before any real multi-instance deployment. |

## Everything else

| Decision | Instead of | Quality attributes traded | Why |
|---|---|---|---|
| Deterministic scoring over LLM judgment, everywhere feasible | LLM blending qualitative factors into a "holistic" score | **Correctness & auditability** over **flexibility** | Reproducibility and auditability are non-negotiable for an investment-decision tool |
| Fixed, hand-picked composite weights | Data-derived weights | **Transparency** over **statistical optimality** | No public labeled-outcome data exists (which airports got funded, and whether it worked) |
| Calendar-year-over-calendar-year growth | Trailing-12-month growth | **Correctness** constrained by **data availability** | BTS T-100 has no month-level field at all (verified live) - the honest ceiling of the data, not a chosen simplification |
| Single agent + one narrowly-scoped sub-agent | A multi-agent pipeline (planner/critic/router) | **Latency & reliability** over **architectural flexibility** | Would add coordination latency and non-determinism, with nowhere new for the already-deterministic scoring logic to live |
| `gpt-5.4-mini` at the SDK's default reasoning effort | A higher reasoning-effort tier | **Cost & latency** over **theoretical headroom** | Live-compared on the three behaviors the system prompt depends on most - no correctness difference found |
| No offline/mock data path | Keeping the original mock-first MVP skeleton | **Maintainability** over **offline availability** | Real BTS integration became the only meaningfully-used path; a second, increasingly-stale branch wasn't worth maintaining |
| A detected unsupported number is logged, not retried or blocked | An automatic retry-with-correction fix (built and verified working) | **Simplicity** over **defense-in-depth** | Reverted after the run log showed the guardrail had never actually fired - the added complexity wasn't justified by a zero-occurrence failure mode |
| Tool-routing correctness verified live only | A scripted fake `Model` test double | **Delivery speed** over **test coverage** | More engineering than a lean MVP warrants |
| Off-topic guardrail and comparison-honesty are prompt rules, not tool-enforced | Hard-coding every edge case as deterministic logic | **Delivery speed** over **reliability guarantees** | A probabilistic LLM behavior, same caveat as the web-search disclosure rule - cheap to add, but not a hard guarantee the way a tool-level check would be |
| "Nationwide" ranking reuses the curated regions' union (~46 airports) | Sourcing a separate full U.S. airport list | **Maintainability** over **completeness** | Reuses the already-tested peer-set engine and needs no new data source; disclosed as curated, not exhaustive |
| An uncurated-but-named U.S. scope (state, metro area, informal region) is answered via an LLM-selected airport list | A second hand-curated region list | **Coverage** over **verifiability** | Avoids maintaining a 50-state reference table; the airport list (never any number) is model-selected and disclosed as such |
| BTS's own published fields used directly wherever one exists | Re-deriving the same figures ourselves | **Correctness** over **self-sufficiency** | `total_load_factor`/`total_passengers_flight` and `DepDel15` were found by checking BTS's live field list; official load factor (RPM/ASM) can genuinely diverge from a self-derived flat ratio |
| DDI kept as this project's own composite | Replacing it with a "real" industry metric | **Transparency** over **borrowed authority** | No FAA/DOT/BTS/industry-standard "Departure Delay Index" exists to adopt; its DOT-standard ingredient is exposed separately so it stays independently checkable |
