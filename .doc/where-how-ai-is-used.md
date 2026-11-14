# Where/How AI Is Used

Part of this project's design documentation (see [README](../README.md#documentation) for the full set): [Design Notes](design.md) (data sources, KPIs, assumptions) · [Scoring Methodology](scoring-methodology.md) · [Key Tradeoffs](key-tradeoffs.md) · **Where/How AI Is Used**.

The LLM's job is routing and narration only - never arithmetic.

| The LLM does | The LLM never does |
|---|---|
| Routes a natural-language question to the correct deterministic tool | Performs the underlying arithmetic itself |
| Narrates that tool's already-computed result | Invents or estimates a number |
| Surfaces every `caveats` entry a tool returns (proxy vs. measured, time period) | Presents an approximation as fact |
| Declines and redirects a question with no airport/aviation/investment connection | Answers an off-topic question from its own general knowledge |
| States plainly which airport(s) couldn't be analyzed when part of a comparison fails | Builds a comparative conclusion ("X is higher than Y") from one real result plus one failure |

The last two rows are prompt-level rules, not tool-enforced - a probabilistic LLM behavior, not a hard guarantee (see [Key Tradeoffs](key-tradeoffs.md)). `compare_unmet_demand_tool` closes the second gap structurally for that one case: it fails atomically on either airport rather than letting the LLM improvise a comparison from two independent single-airport calls.

The agent is pinned to `gpt-5.4-mini` (see [Design Notes](design.md#assumptions-limitations-proxies)) rather than left to the SDK's own default, so this behavior is reproducible rather than dependent on whatever `openai-agents` currently defaults to.

## Single agent, not a multi-agent pipeline

`airport_agent` is one `Agent` with eight deterministic tools plus one sub-agent (`web_search_fallback`) exposed via `Agent.as_tool()` - not a multi-agent system with separate planner/critic/router agents coordinating with each other.

- **Why not multi-agent:** the actual "intelligence" this problem calls for is the scoring logic, which is already fully deterministic and lives entirely outside the LLM (see [Scoring Methodology](scoring-methodology.md)). A multi-agent pipeline would add coordination latency and a second layer of non-determinism (agent-to-agent handoffs), without giving that scoring logic anywhere new to live.
- **The one sub-agent that does exist** (`web_search_fallback`) is scoped narrowly to a single job - live web lookups for airport/aviation questions outside the deterministic tools' coverage - not a second decision-maker with its own scoring authority.
- **Both its own instructions and the main agent's** explicitly forbid it from influencing a stated score or ranking.
