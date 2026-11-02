"""Critical-path tests for DataExporter: Options 1 + 2 working together.

Still to test:
  * Case-insensitive string formats ("CSV", "Json").
  * A shared cache injected into two exporters is actually shared.
  * Cached entries expire end-to-end (exporter + FakeClock).
  * Failed exports are not cached.
  * Logging output on hit/miss (caplog).
  * Performance/large-input behaviour (e.g. 1M rows): memory and timing.
"""

import csv
import io
import json
from typing import Any

import pytest

from data_export import (
    DataExporter,
    ExportCache,
    ExportFormat,
    SerializationError,
    UnsupportedFormatError,
    formats,
)


@pytest.mark.parametrize("fmt", list(ExportFormat))
def test_exports_full_sample_dataset(sample_data: list[dict[str, Any]], fmt: ExportFormat) -> None:
    output = DataExporter().export(sample_data, fmt)

    # Parse the output back and check that every row survived.
    if fmt is ExportFormat.JSON:
        parsed = json.loads(output)
    else:
        parsed = list(csv.DictReader(io.StringIO(output)))
    assert len(parsed) == len(sample_data)


def test_second_identical_export_is_served_from_cache(
    sample_data: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    exporter = DataExporter()
    first = exporter.export(sample_data, ExportFormat.CSV)

    # If the cache is used, the serialiser must not run again. Replace it
    # with one that fails loudly, which proves the second call is a cache hit.
    def boom(rows: Any) -> str:
        raise AssertionError("serialiser called despite cache hit")

    # The exporter reads from this same dict object, so patching it here works.
    monkeypatch.setitem(formats.SERIALIZERS, ExportFormat.CSV, boom)

    assert exporter.export(sample_data, ExportFormat.CSV) == first


def test_same_data_in_different_formats_does_not_collide(
    sample_data: list[dict[str, Any]],
) -> None:
    cache = ExportCache()
    exporter = DataExporter(cache=cache)

    csv_out = exporter.export(sample_data, ExportFormat.CSV)
    json_out = exporter.export(sample_data, ExportFormat.JSON)

    assert csv_out != json_out
    assert len(cache) == 2  # one entry per format


def test_injected_empty_cache_is_used() -> None:
    # Regression guard for the stub's `cache or ExportCache()` pattern:
    # an empty ExportCache is falsy (it has __len__) and must not be replaced.
    cache = ExportCache()
    assert DataExporter(cache=cache).cache is cache


@pytest.mark.parametrize(("fmt", "expected"), [(ExportFormat.JSON, "[]"), (ExportFormat.CSV, "")])
def test_empty_data_returns_empty_output_and_is_not_cached(
    fmt: ExportFormat, expected: str
) -> None:
    # The edge case chosen from the brief.
    cache = ExportCache()

    assert DataExporter(cache=cache).export([], fmt) == expected
    assert len(cache) == 0


def test_unsupported_format_raises() -> None:
    with pytest.raises(UnsupportedFormatError, match="xml"):
        DataExporter().export([{"a": 1}], "xml")


def test_unserialisable_value_raises_serialization_error() -> None:
    # Callers should see our exception type, with the original cause chained.
    with pytest.raises(SerializationError) as exc_info:
        DataExporter().export([{"a": object()}], ExportFormat.JSON)

    assert isinstance(exc_info.value.__cause__, TypeError)
