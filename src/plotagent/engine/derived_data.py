"""Explicit adapters for prepared and calculated plotting data."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from plotagent.contracts.calculations import PlotCalculationResult
from plotagent.engine.contracts import (
    EngineColumn,
    EngineDataRef,
    EngineDataView,
    EngineField,
)
from plotagent.engine.data import EngineDataError, _engine_field, _engine_values
from plotagent.preparation.artifacts import PreparedArtifact


def engine_view_from_prepared(artifact: PreparedArtifact) -> EngineDataView:
    """Expose included prepared rows without importing a plotting contract."""

    if len(artifact.rows) != len(artifact.row_mask) or len(artifact.rows) != len(
        artifact.coordinates
    ):
        raise EngineDataError("prepared artifact rows, mask, and coordinates must align")
    included = tuple(index for index, keep in enumerate(artifact.row_mask) if keep)
    if not included:
        raise EngineDataError("prepared artifact contains no included plotting rows")
    data = EngineDataRef(
        kind="prepared",
        dataset_id=artifact.prepared_dataset.prepared_dataset_id,
        version=artifact.prepared_dataset.prepared_version,
        content_hash=artifact.prepared_dataset.output_hash,
    )
    return EngineDataView(
        data=data,
        row_ids=tuple(artifact.coordinates[index].source_row_id for index in included),
        columns=tuple(
            EngineColumn(
                field=_engine_field(field),
                values=_engine_values(tuple(artifact.rows[index][column] for index in included)),
            )
            for column, field in enumerate(artifact.fields)
        ),
    )


def engine_view_from_calculation(result: PlotCalculationResult) -> EngineDataView:
    """Expose deterministic calculation geometry as one immutable data view."""

    rows = result.output_table.rows
    if not rows:
        raise EngineDataError("calculation result contains no plotting rows")
    token = result.calculation_id.removeprefix("plotcalc:")
    data = EngineDataRef(
        kind="calculated",
        dataset_id=result.calculation_id,
        version=result.result_version,
        content_hash=result.output_hash,
    )
    return EngineDataView(
        data=data,
        row_ids=tuple(
            f"row:{token}.{result.result_version}.{index + 1}" for index in range(len(rows))
        ),
        columns=tuple(
            EngineColumn(
                field=EngineField(
                    field_id=field_id,
                    name=_calculation_field_name(field_id),
                    logical_type=_logical_type(tuple(row[column] for row in rows)),
                ),
                values=_engine_values(tuple(row[column] for row in rows)),
            )
            for column, field_id in enumerate(result.output_table.field_ids)
        ),
    )


class DerivedEngineDataProvider:
    """Immutable provider over prepared/calculated views produced for a task."""

    def __init__(self, views: Iterable[EngineDataView]) -> None:
        items = tuple(views)
        keys = tuple(_key(view.data) for view in items)
        if len(keys) != len(set(keys)):
            raise ValueError("derived engine data revisions must be unique")
        if any(view.data.kind == "source" for view in items):
            raise ValueError("source data belongs to ProjectEngineDataProvider")
        self._views = dict(zip(keys, items, strict=True))

    def materialize(
        self,
        data: EngineDataRef,
        field_ids: tuple[str, ...],
    ) -> EngineDataView:
        try:
            view = self._views[_key(data)]
        except KeyError as exc:
            raise EngineDataError("derived engine data revision was not registered") from exc
        if not field_ids or len(field_ids) != len(set(field_ids)):
            raise EngineDataError("engine data materialization fields must be non-empty and unique")
        columns = {column.field.field_id: column for column in view.columns}
        missing = tuple(field_id for field_id in field_ids if field_id not in columns)
        if missing:
            raise EngineDataError(f"derived data does not contain requested fields: {missing!r}")
        return view.model_copy(update={"columns": tuple(columns[item] for item in field_ids)})


def _key(data: EngineDataRef) -> tuple[str, str, int, str]:
    return data.kind, data.dataset_id, data.version, data.content_hash


def _calculation_field_name(field_id: str) -> str:
    return field_id.rsplit(".", 1)[-1].replace("_", " ")


def _logical_type(
    values: tuple[object, ...],
) -> Literal["numeric", "categorical", "datetime", "boolean", "text"]:
    observed = tuple(value for value in values if value is not None)
    if observed and all(isinstance(value, bool) for value in observed):
        return "boolean"
    if observed and all(
        isinstance(value, (int, float)) and not isinstance(value, bool) for value in observed
    ):
        return "numeric"
    return "categorical"
