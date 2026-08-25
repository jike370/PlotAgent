"""Strict MCP transport models and structured tool results."""

from __future__ import annotations

import json
from typing import Annotated, Literal, cast

from pydantic import Field, RootModel, model_validator

from plotagent.contracts.agent_data import DataViewOperation
from plotagent.contracts.base import FieldId, StrictModel
from plotagent.desktop_core.protocol import JsonValue
from plotagent.engine.contracts import EngineDataRef, ExportPlot, PlotEngineAction


class McpToolError(StrictModel):
    code: str
    message: str
    retryable: bool = False


class McpToolResponse(StrictModel):
    ok: bool
    data: dict[str, JsonValue] | None = None
    error: McpToolError | None = None

    @classmethod
    def success(cls, data: dict[str, JsonValue]) -> McpToolResponse:
        normalized = json.loads(json.dumps(data, allow_nan=False, ensure_ascii=True))
        return cls(ok=True, data=cast(dict[str, JsonValue], normalized))

    @classmethod
    def failure(cls, code: str, message: str) -> McpToolResponse:
        return cls(
            ok=False,
            error=McpToolError(
                code=code,
                message=message,
                retryable=code
                in {
                    "ENGINE_VERSION_CONFLICT",
                    "SOURCE_VERSION_CONFLICT",
                    "EXPORT_DESTINATION_EXISTS",
                },
            ),
        )


class McpImportOptions(StrictModel):
    encoding: str | None = None
    delimiter: str | None = None
    decimal_mark: str | None = None
    header_row: int | None = Field(default=None, ge=0)
    sheet: str | None = None


class McpStageSourceData(StrictModel):
    operation: Literal["stage_source"] = "stage_source"
    workspace_id: str
    source: EngineDataRef
    field_ids: tuple[FieldId, ...] = Field(min_length=1, max_length=128)


class McpApplyDataOperation(StrictModel):
    operation: Literal["apply_operation"] = "apply_operation"
    workspace_id: str
    data_operation: DataViewOperation


class McpInspectDataView(StrictModel):
    operation: Literal["inspect"] = "inspect"
    workspace_id: str
    handle_id: str


class McpPreviewDataView(StrictModel):
    operation: Literal["preview"] = "preview"
    workspace_id: str
    handle_id: str
    field_ids: tuple[FieldId, ...] = Field(min_length=1, max_length=24)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=5, ge=1, le=40)


class McpCommitDataView(StrictModel):
    operation: Literal["commit"] = "commit"
    workspace_id: str
    handle_id: str


McpDataViewCommand = Annotated[
    McpStageSourceData
    | McpApplyDataOperation
    | McpInspectDataView
    | McpPreviewDataView
    | McpCommitDataView,
    Field(discriminator="operation"),
]


class McpDataViewRequest(RootModel[McpDataViewCommand]):
    """One bounded external data-workspace command."""

    @model_validator(mode="before")
    @classmethod
    def json_lists_to_contract_tuples(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        adapted = dict(value)
        if isinstance(adapted.get("field_ids"), list):
            adapted["field_ids"] = tuple(adapted["field_ids"])
        operation = adapted.get("data_operation")
        if isinstance(operation, dict):
            operation = dict(operation)
            for key in (
                "field_ids",
                "input_handle_ids",
                "source_labels",
                "key_field_ids",
                "input_field_ids",
                "id_field_ids",
                "value_field_ids",
                "index_field_ids",
                "group_field_ids",
                "keys",
                "metrics",
                "outputs",
                "predicates",
            ):
                if isinstance(operation.get(key), list):
                    operation[key] = tuple(operation[key])
            adapted["data_operation"] = operation
        return adapted


class McpPlotAction(RootModel[PlotEngineAction]):
    """Transport wrapper for the engine's discriminated public action union."""

    @model_validator(mode="before")
    @classmethod
    def json_collections_to_contract_collections(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        adapted = dict(value)
        for key in ("bindings", "components"):
            collection = adapted.get(key)
            if isinstance(collection, list):
                adapted[key] = tuple(collection)
        return adapted


class McpExportAction(RootModel[ExportPlot]):
    pass
