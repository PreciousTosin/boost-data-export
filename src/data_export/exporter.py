"""The public entry point: ``DataExporter``.

This combines the two options chosen from the brief:
  * Option 1 (multi-format): ``export(data, format)`` with CSV/JSON output.
  * Option 2 (caching): results are cached in an ``ExportCache`` (1-hour TTL).

The two stubs in the brief have different signatures: Option 1's ``export``
takes a ``format``, Option 2's does not. They're reconciled by giving
``format`` a default of JSON, so both call styles work, and by including the
format in the cache key so CSV and JSON outputs of the same data never
collide.
"""

import csv
import hashlib
import json
import logging
from collections.abc import Sequence

from data_export.cache import ExportCache
from data_export.errors import SerializationError, UnsupportedFormatError
from data_export.formats import SERIALIZERS, ExportFormat, Row, to_primitive

logger = logging.getLogger(__name__)


def make_cache_key(data: Sequence[Row], fmt: ExportFormat) -> str:
    """Build a deterministic cache key from the export format and the data.

    The data is canonicalised to JSON with sorted keys and fixed separators,
    so two logically identical datasets produce the same key regardless of
    dict key order. Row *order* is preserved on purpose, because it changes
    the output.

    The canonical form is hashed with SHA-256 rather than used directly, so
    keys stay a fixed, small size however large the dataset is.

    Tradeoff, worth stating plainly: building this key is O(n), roughly the
    same cost as the export itself. A content-hash cache therefore saves
    little CPU for cheap formats like these. In a real system the key would
    be derived from the *request* (report id + filters + data version)
    *before* querying the database, which is where the real saving is. The
    brief's interface only gives us the data, so content-hashing is the
    correct choice within that contract.

    Note on collisions: ``to_primitive`` maps e.g. ``Decimal("1.5")`` and the
    string ``"1.5"`` to the same canonical value. That is harmless here,
    because both also produce identical CSV/JSON output.
    """
    canonical = json.dumps(
        data,
        default=to_primitive,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    # Namespaced, readable prefix. Useful if this ever moves to a shared
    # Redis instance where other features also store keys.
    return f"export:{fmt.value}:{digest}"


class DataExporter:
    """Export a list of records to CSV or JSON, caching results.

    Example:
        >>> exporter = DataExporter()
        >>> exporter.export([{"a": 1}], ExportFormat.CSV)
        'a\\r\\n1\\r\\n'
    """

    # The brief's stub declares ``cache = None`` at class level. That value
    # is always shadowed by the instance attribute set in __init__, so it is
    # dead code; a bare annotation documents the attribute's type without it.
    cache: ExportCache

    def __init__(self, cache: ExportCache | None = None) -> None:
        """Use the given cache, or create a private one.

        Deliberately ``is not None`` rather than the stub's
        ``cache or ExportCache()``: ``ExportCache`` defines ``__len__``, so
        an *empty* injected cache is falsy, and ``or`` would silently
        replace it with a new instance. Callers sharing a cache across
        exporters would then never share anything.
        """
        self.cache = cache if cache is not None else ExportCache()

    def export(
        self,
        data: Sequence[Row],
        format: ExportFormat | str = ExportFormat.JSON,  # noqa: A002 (name fixed by the brief)
    ) -> str:
        """Serialise ``data`` into ``format``, using the cache when possible.

        Args:
            data: Records as produced by the database layer, already mapped to
                Python types. The schema is not assumed to be fixed.
            format: An ``ExportFormat`` or its string value ("csv"/"json",
                case-insensitive). Defaults to JSON.

        Returns:
            The serialised export as a string.

        Raises:
            UnsupportedFormatError: ``format`` isn't a supported format.
            SerializationError: some value in ``data`` can't be represented
                in the requested format.
        """
        # 1. Validate the format first, so a bad format fails fast even for
        #    empty data, and before we do any O(n) work.
        fmt = self._resolve_format(format)
        serialize = SERIALIZERS[fmt]

        # 2. Edge case: empty data. Return the format's well-defined empty
        #    output ("[]" for JSON, "" for CSV) immediately. It is not cached:
        #    it's free to produce, and caching it would only waste an entry.
        if not data:
            logger.debug("Empty dataset; returning empty %s export", fmt.value)
            return serialize(data)

        # 3. Cache lookup. Key-building canonicalises every value, so it can
        #    hit an unsupported type before the serialiser does. Wrap that
        #    too, so callers only ever see our own exception types.
        try:
            key = make_cache_key(data, fmt)
        except (TypeError, ValueError) as exc:
            raise SerializationError(f"Cannot export data as {fmt.value}: {exc}") from exc

        cached = self.cache.get(key)
        if cached is not None:
            logger.debug("Cache hit for %s", key)
            return cached

        # 4. Cache miss: serialise, translating low-level errors.
        logger.debug("Cache miss for %s; serialising %d rows", key, len(data))
        try:
            output = serialize(data)
        except (TypeError, ValueError, csv.Error) as exc:
            raise SerializationError(
                f"Failed to export {len(data)} rows as {fmt.value}: {exc}"
            ) from exc

        # 5. Store and return. Only successful exports are cached; failures
        #    are never cached, so a fixed input is retried cleanly.
        self.cache.set(key, output)
        return output

    @staticmethod
    def _resolve_format(fmt: ExportFormat | str) -> ExportFormat:
        """Coerce ``fmt`` to an ``ExportFormat`` or raise ``UnsupportedFormatError``."""
        try:
            # ExportFormat("csv") works; an ExportFormat member passes through.
            # lower() makes "CSV" from a query string acceptable too.
            return ExportFormat(fmt.lower() if isinstance(fmt, str) else fmt)
        except ValueError:
            supported = ", ".join(f.value for f in ExportFormat)
            # "from None" hides the internal enum ValueError: our message
            # already says everything the caller needs.
            raise UnsupportedFormatError(
                f"Unsupported export format {fmt!r}. Supported formats: {supported}"
            ) from None
