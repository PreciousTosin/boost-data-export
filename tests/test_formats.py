"""Critical-path tests for the serialisers (Option 1).

Still to test (deliberately left out of this minimal pass):
  * Decimal, UUID, date, time and Enum conversion in to_primitive.
  * None values -> empty CSV cells; bool values in CSV.
  * Nested list/dict values in CSV raise TypeError.
  * Fieldname ordering: first-seen order across heterogeneous rows.
  * Property-based tests (e.g. hypothesis): CSV round-trips through
    csv.DictReader for arbitrary string content (quotes, newlines, unicode).
  * CSV formula-injection handling, if we decide to add it (see README).
"""

import csv
import io
import json
from datetime import datetime

from data_export.formats import to_csv, to_json


def test_json_serialises_datetimes_as_iso8601() -> None:
    # json.dumps raises TypeError on datetime by default; our hook must handle it.
    rows = [{"created_at": datetime(2023, 12, 5, 17, 4, 16), "qty": 5.5}]

    assert json.loads(to_json(rows)) == [{"created_at": "2023-12-05T17:04:16", "qty": 5.5}]


def test_csv_quotes_values_containing_commas() -> None:
    # Real case from the sample data: SKU names contain commas.
    rows = [{"sku_name": "KEY BAR ELEPHANT 16× 1,000g box", "quantity": 5}]

    parsed = list(csv.DictReader(io.StringIO(to_csv(rows))))

    # Parsing it back proves the comma didn't split the field.
    assert parsed == [{"sku_name": "KEY BAR ELEPHANT 16× 1,000g box", "quantity": "5"}]


def test_csv_handles_rows_with_different_columns() -> None:
    # The schema "is liable to change": a later row may add a column.
    rows = [{"a": 1}, {"a": 2, "b": "new"}]

    parsed = list(csv.DictReader(io.StringIO(to_csv(rows))))

    assert parsed == [{"a": "1", "b": ""}, {"a": "2", "b": "new"}]
