"""In-memory export cache with timestamp-based (TTL) expiration."""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

#: One hour, as required by the brief.
DEFAULT_TTL_SECONDS: float = 60 * 60


@dataclass
class ExportCache:
    """A thread-safe, in-process key/value cache with a fixed TTL.

    Each entry stores the timestamp at which it was written. Expiry is *lazy*:
    an entry older than ``ttl_seconds`` is treated as missing (and evicted)
    the next time it is read. There is no background sweeper thread, which
    keeps the class simple and deterministic to test.

    Attributes:
        ttl_seconds: How long an entry stays valid after ``set``.
        clock: Zero-argument callable returning the current time in seconds.
            Defaults to ``time.monotonic``, which never jumps backwards or
            forwards with wall-clock changes (NTP sync, DST, manual changes),
            so TTLs are measured reliably. Injecting it means tests can
            advance time instantly instead of calling ``sleep``.

    Known limitations (deliberate for this exercise):
        * Per-process only. With several workers or Lambda instances, each
          has its own cache. A shared deployment would back this interface
          with Redis (``SET key value EX 3600``), which gives TTL natively.
        * Unbounded size. Entries that are never read again are never
          evicted. A production version would add a max size with LRU
          eviction, or rely on Redis' eviction policy.
    """

    ttl_seconds: float = DEFAULT_TTL_SECONDS
    clock: Callable[[], float] = time.monotonic

    # Internal state, excluded from __init__ and __repr__.
    # Maps key -> (stored_at timestamp, cached export string).
    _entries: dict[str, tuple[float, str]] = field(default_factory=dict, init=False, repr=False)
    # Guards _entries so concurrent threads (e.g. a threaded web server)
    # can't interleave a read-check-delete with a write.
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be positive, got {self.ttl_seconds}")

    def get(self, key: str) -> str | None:
        """Return the cached export for ``key``, or ``None`` if missing or expired."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None

            stored_at, data = entry
            # ">=" means an entry is expired at exactly ttl_seconds old.
            if self.clock() - stored_at >= self.ttl_seconds:
                # Lazy eviction: clean up the stale entry on the way out.
                del self._entries[key]
                return None
            return data

    def set(self, key: str, data: str) -> None:
        """Store ``data`` under ``key``, stamped with the current time.

        Overwriting an existing key resets its TTL.
        """
        with self._lock:
            self._entries[key] = (self.clock(), data)

    def __len__(self) -> int:
        """Number of stored entries, including expired ones not yet evicted."""
        with self._lock:
            return len(self._entries)
