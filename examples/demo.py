"""Demo: export the sample dataset and show the cache at work.

Run from the repo root with:
    uv run python examples/demo.py
"""

from time import perf_counter

# examples/ is on sys.path when this script runs, so the brief's data.py imports directly.
from data import data

from data_export import DataExporter, ExportFormat


def timed_export(exporter: DataExporter, fmt: ExportFormat) -> tuple[str, float]:
    start = perf_counter()
    output = exporter.export(data, fmt)
    return output, (perf_counter() - start) * 1000


def main() -> None:
    exporter = DataExporter()
    print(f"Loaded {len(data)} rows\n")

    for fmt in ExportFormat:
        output, cold_ms = timed_export(exporter, fmt)
        _, warm_ms = timed_export(exporter, fmt)
        print(f"== {fmt.value.upper()} ==  {len(output):,} chars")
        print(f"first call {cold_ms:.2f} ms, cached call {warm_ms:.2f} ms")
        print("preview:", output[:400].replace("\r\n", "\n"), "...\n")

    print("Empty data (the chosen edge case):")
    print(f"  JSON -> {exporter.export([], ExportFormat.JSON)!r}")
    print(f"  CSV  -> {exporter.export([], ExportFormat.CSV)!r}")


if __name__ == "__main__":
    main()
