# data-export

A small Python module that exports lists of records (`list[dict]`) to **CSV or JSON**, with a **1-hour TTL cache** so repeated identical exports are served without re-serialising.

From the brief's three options, this implements **Option 1 (multi-format support)** and **Option 2 (caching support)**. The chosen edge case is **empty data**.

## Quick start

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/). uv will fetch Python 3.12+ automatically if needed.

```bash
# Install the package and dev tools into a local .venv
uv sync

# Run the test suite
uv run pytest

# Run the demo against the supplied sample dataset
uv run python examples/demo.py

# Optional: lint and type-check
uv run ruff check .
uv run mypy
```

## Usage

```python
from data_export import DataExporter, ExportFormat

exporter = DataExporter()  # creates its own 1-hour cache

csv_text = exporter.export(rows, ExportFormat.CSV)

# Plain strings work too (case-insensitive), and JSON is the default:
json_text = exporter.export(rows, "json")
json_text = exporter.export(rows)
```

Share one cache between exporters, or tune the TTL:

```python
from data_export import DataExporter, ExportCache

shared = ExportCache(ttl_seconds=600)
a, b = DataExporter(cache=shared), DataExporter(cache=shared)
```

Errors all derive from `data_export.ExportError`:

| Exception                | When                                                                             |
| ------------------------ | -------------------------------------------------------------------------------- |
| `UnsupportedFormatError` | The format isn't `csv` or `json`                                                 |
| `SerializationError`     | A value can't be represented (e.g. an arbitrary object, or a nested dict in CSV) |

## Project layout

```
src/data_export/
  errors.py     exception hierarchy
  formats.py    ExportFormat enum, CSV/JSON serialisers, serialiser registry
  cache.py      ExportCache: thread-safe in-memory TTL cache
  exporter.py   DataExporter: validates, checks cache, serialises, stores
examples/
  data.py       sample dataset supplied with the brief
  demo.py       runnable demo
tests/          pytest suite (critical paths)
```
