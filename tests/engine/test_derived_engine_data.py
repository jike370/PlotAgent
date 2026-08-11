from __future__ import annotations

from pathlib import Path

from plotagent.contracts import FieldMapping, canonical_hash
from plotagent.contracts.base import FieldMappingRef, PreparedDatasetRef, SourceDatasetRef
from plotagent.contracts.calculations import HistogramBinningSpec
from plotagent.contracts.datasets import (
    FieldRoleBinding,
    FieldSnapshot,
    FilterRowsSpec,
)
from plotagent.engine import (
    DerivedEngineDataProvider,
    engine_view_from_calculation,
    engine_view_from_prepared,
)
from plotagent.importing import Imported, inspect_source
from plotagent.plot_calculations import ALGORITHM_VERSION, PlotCalculationInput, calculate_plot
from plotagent.preparation import ImportedSourceResolver, prepare

FILES_ROOT = Path(__file__).parents[1] / "fixtures" / "import" / "files"


def _prepared_artifact(tmp_path: Path):
    source_path = tmp_path / "partially-missing.csv"
    source_path.write_text("x,y\n0,1\n1,NA\n2,3\n", encoding="utf-8")
    imported = inspect_source(source_path)
    assert isinstance(imported, Imported)
    artifact = imported.sources[0]
    source = artifact.source_dataset
    source_ref = SourceDatasetRef(
        source_dataset_id=source.source_dataset_id,
        source_version=source.source_version,
        content_hash=source.content_hash,
    )
    fields = source.field_schema
    mapping_hash = canonical_hash({"source": source_ref.model_dump(mode="json")})
    mapping = FieldMapping(
        field_mapping_id="mapping:engine-derived",
        mapping_version=1,
        chart_type_id="K01",
        source_dataset_refs=(source_ref,),
        bindings=tuple(
            FieldRoleBinding(
                role=role,
                field=FieldSnapshot(
                    field_id=field.field_id,
                    name=field.name,
                    logical_type=field.logical_type,
                    unit=field.unit,
                    source_dataset_ref=source_ref,
                ),
            )
            for role, field in zip(("x", "y"), fields, strict=False)
        ),
        content_hash=mapping_hash,
    )
    spec = FilterRowsSpec(
        preparation_spec_id="preparation:engine-derived",
        preparation_version=1,
        input_refs=(source_ref,),
        field_mapping_ref=FieldMappingRef(
            field_mapping_id=mapping.field_mapping_id,
            mapping_version=1,
            content_hash=mapping.content_hash,
        ),
        compiler_version="preparation.compiler.v1",
        field_ids=(fields[1].field_id,),
        missing_policy="exclude_with_report",
    )
    return prepare((source,), mapping, spec, ImportedSourceResolver((artifact,)))


def test_prepared_adapter_filters_excluded_rows_and_preserves_source_identity(
    tmp_path: Path,
) -> None:
    artifact = _prepared_artifact(tmp_path)
    view = engine_view_from_prepared(artifact)

    assert view.data.kind == "prepared"
    assert view.data.content_hash == artifact.prepared_dataset.output_hash
    assert len(view.row_ids) == artifact.prepared_dataset.included_row_count
    assert len(view.row_ids) < len(artifact.rows)
    assert all(len(column.values) == len(view.row_ids) for column in view.columns)


def test_calculation_adapter_and_provider_keep_geometry_order_and_projection() -> None:
    spec = HistogramBinningSpec(
        calculation_id="plotcalc:engine-hist",
        calculation_version=1,
        prepared_dataset_ref=PreparedDatasetRef(
            prepared_dataset_id="prepared:engine",
            prepared_version=1,
            content_hash="a" * 64,
        ),
        algorithm_version=ALGORITHM_VERSION,
        missing_policy="fail",
        value_field="field:value",
    )
    result = calculate_plot(
        spec,
        PlotCalculationInput(
            row_ids=tuple(f"row:{index}" for index in range(8)),
            columns={"field:value": tuple(range(8))},
        ),
        producer_build_hash="f" * 64,
    )
    view = engine_view_from_calculation(result)
    requested = (view.columns[4].field.field_id, view.columns[2].field.field_id)
    projected = DerivedEngineDataProvider((view,)).materialize(view.data, requested)

    assert view.data.kind == "calculated"
    assert view.data.content_hash == result.output_hash
    assert view.row_ids == ("row:engine-hist.1.1", "row:engine-hist.1.2")
    assert tuple(column.field.field_id for column in projected.columns) == requested
    assert projected.columns[0].values == (4, 4)
