# Airport Investment Intelligence Agent

An AI agent that answers *"which U.S. airports most warrant infrastructure
investment?"* from free, public BTS flight-traffic data.

**Work in progress.** Ground rules for the build:

- The LLM routes questions to tools and narrates their results - it never
  invents or estimates a number.
- All KPIs and scoring are deterministic, unit-tested Python.
- Every proxy and assumption is disclosed alongside the result.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # add your OPENAI_API_KEY
pytest
```
