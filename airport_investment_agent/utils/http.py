"""Shared bounded-retry wrapper for external HTTP calls.

Retries only transport-level failures (a dropped connection, a timeout) --
the project's error-handling rule is "retry only transient infrastructure
errors, with bounded retries and backoff." A 4xx/5xx from
raise_for_status() is deliberately left to the caller, unretried: BTS
doesn't return HTTP errors for the failure modes this codebase actually
hits (an unknown airport code comes back as an empty JSON array, not a
4xx), so keeping the retry surface to connection/timeout only avoids
wasting attempts on errors a retry can't fix.

Backoff is intentionally short (tens to hundreds of ms, not seconds) so
tests that exercise this through a mocked-and-failing `requests.get`
don't sit through multi-second real sleeps.
"""

import requests
import tenacity

_RETRYABLE_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
)


@tenacity.retry(
    retry=tenacity.retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=0.05, max=0.5),
    reraise=True,
)
def get_with_retry(url: str, **kwargs) -> requests.Response:
    return requests.get(url, **kwargs)
