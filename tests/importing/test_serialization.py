from __future__ import annotations

import io
import math
from pathlib import Path

import pyarrow.parquet as pq  # type: ignore[import-untyped]

from plotagent.importing import Imported, inspect_source
from plotagent.importing.serialization import source_artifact_to_parquet_bytes

FILES_ROOT = Path(__file__).parents[1] / "fixtures" / "import" / "files"


def test_parquet_preserves_nonfinite_values_and_source_coordinates() -> None:
    result = inspect_source(FILES_ROOT / "csv_nonfinite.csv")
    assert isinstance(result, Imported)
    source = result.sources[0]

    first = source_artifact_to_parquet_bytes(source)
    second = source_artifact_to_parquet_bytes(source)
    table = pq.read_table(io.BytesIO(first))

    assert first == second
    assert table.schema.metadata[b"plotagent.schema_version"] == b"source-dataset-v1"
    assert table.column("__source_row_id").to_pylist() == [
        coordinate.source_row_id for coordinate in source.coordinates
    ]
    values = table.column(source.source_dataset.field_schema[1].field_id).to_pylist()
    assert math.isnan(values[0])
    assert values[1:] == [float("inf"), float("-inf"), None]
