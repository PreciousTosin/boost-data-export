"""Critical-path tests for ExportCache (Option 2).

Still to test:
  * Overwriting a key resets its TTL.
  * Lazy eviction actually removes the entry (len() drops after expiry).
  * ttl_seconds <= 0 raises ValueError.
  * Concurrency: many threads doing get/set simultaneously don't corrupt
    state (a stress test with ThreadPoolExecutor).
"""

from conftest import FakeClock

from data_export.cache import DEFAULT_TTL_SECONDS, ExportCache


def test_get_returns_none_for_missing_key() -> None:
    assert ExportCache().get("nope") is None


def test_entry_is_served_until_ttl_then_expires(clock: FakeClock) -> None:
    cache = ExportCache(clock=clock)  # default TTL: 1 hour
    cache.set("k", "payload")

    # Just inside the TTL: still a hit.
    clock.advance(DEFAULT_TTL_SECONDS - 1)
    assert cache.get("k") == "payload"

    # At exactly the TTL: expired (boundary is inclusive, see cache.get).
    clock.advance(1)
    assert cache.get("k") is None
