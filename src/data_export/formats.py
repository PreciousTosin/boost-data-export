"""Output formats and the serialisers that produce them.

Design: a small *strategy registry*. Each ``ExportFormat`` maps to a plain
function ``(rows) -> str``. Adding a new format (e.g. XLSX, NDJSON) means
writing one function and adding one entry to ``SERIALIZERS``; the exporter
itself does not change (open/closed principle).

Schema-agnostic by design: the brief says the columns and types "are liable
to change", so nothing here hardcodes column names or per-column types.
"""

import csv
import io
import json
from collections.abc import Callable, Sequence
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum, StrEnum
from typing import Any
from uuid import UUID

# PEP 695 type aliases (Python 3.12+).
# A row is one record as it comes out of the database layer.
type Row = dict[str, Any]
# A serialiser turns a sequence of rows into the final string output.
type Serializer = Callable[[Sequence[Row]], str]


class ExportFormat(StrEnum):
    """Supported export formats.

    ``StrEnum`` members *are* strings, so ``ExportFormat.CSV == "csv"`` is True.
    That lets callers pass either the enum or a plain string (handy for values
    arriving from an HTTP query parameter) while we still validate centrally.
    """

    CSV = "csv"
    JSON = "json"


def to_primitive(value: Any) -> Any:
    """Convert a non-JSON-native Python value into a JSON-safe primitive.

    Used as the ``default=`` hook for ``json.dumps`` (which calls it only for
    types it can't handle itself) and for CSV cell conversion.

    Choices:
      * datetime/date/time -> ISO 8601 string: unambiguous, sortable, and
        parseable by every mainstream language and spreadsheet.
      * Decimal -> string, NOT float: converting money to float silently loses
        precision. A string keeps the exact value; the consumer decides how
        to parse it.
      * UUID -> canonical string form.
      * Enum -> its underlying value.

    Raises:
        TypeError: for anything else. This mirrors ``json``'s own contract, and
            the exporter wraps it in a ``SerializationError``.
    """
    # Note: datetime is a subclass of date, so the order of this tuple doesn't
    # matter here: both expose .isoformat().
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"Object of type {type(value).__name__} is not serializable")


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


def to_json(rows: Sequence[Row]) -> str:
    """Serialise rows as a JSON array of objects.

    ``ensure_ascii=False`` keeps characters such as the ``×`` in the sample
    SKU names readable instead of escaping them to ``\\u00d7``. The output is
    a ``str``; encoding (UTF-8) is the caller's concern when writing bytes.

    An empty input produces ``"[]"``, which is still valid JSON.
    """
    return json.dumps(rows, default=to_primitive, ensure_ascii=False)


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def collect_fieldnames(rows: Sequence[Row]) -> list[str]:
    """Return the ordered union of keys across all rows.

    Why not just ``rows[0].keys()``? Because the schema can change: if a later
    row has an extra column, taking only the first row's keys would make
    ``DictWriter`` raise (or silently drop data). A dict is used as an
    insertion-ordered set, so columns appear in first-seen order.

    Cost: one extra O(rows x columns) pass. Acceptable at this scale; for a
    streaming exporter you would need a known schema up front instead.
    """
    seen: dict[str, None] = {}
    for row in rows:
        for key in row:
            seen.setdefault(key, None)
    return list(seen)


def _to_csv_cell(value: Any) -> Any:
    """Normalise a single value for a CSV cell.

    * ``None`` -> empty cell (CSV has no null; empty is the convention).
    * str/int/float/bool pass through unchanged; ``csv`` stringifies them.
    * Everything else goes through ``to_primitive``. This matters for
      datetimes: ``str(datetime)`` gives "2023-12-05 17:04:16" (space
      separator), whereas we want the same ISO 8601 form as JSON output.
    * Nested lists/dicts raise ``TypeError`` via ``to_primitive``: CSV is
      flat, and silently writing a Python repr into a cell would be worse
      than failing loudly.
    """
    if value is None:
        return ""
    if isinstance(value, str | int | float | bool):
        return value
    return to_primitive(value)


def to_csv(rows: Sequence[Row]) -> str:
    """Serialise rows as RFC 4180-style CSV with a header row.

    The ``csv`` module handles quoting for us. That is essential with this
    dataset, because SKU names contain commas (e.g. "16× 1,000g box"); naive
    ``",".join(...)`` would corrupt those rows.

    Edge case: empty input returns ``""``. With no rows we cannot infer any
    column names, so there is no meaningful header to write. (Without this
    guard, ``DictWriter`` would emit a lone line terminator.)
    """
    if not rows:
        return ""

    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=collect_fieldnames(rows),
        # Rows missing a column (heterogeneous schema) get an empty cell.
        restval="",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _to_csv_cell(value) for key, value in row.items()})
    return buffer.getvalue()


# Strategy registry: the single place where formats are wired to serialisers.
SERIALIZERS: dict[ExportFormat, Serializer] = {
    ExportFormat.CSV: to_csv,
    ExportFormat.JSON: to_json,
}
