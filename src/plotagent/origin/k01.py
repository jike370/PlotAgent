"""Frozen K01 line-plot plan used by the native Origin spike."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from .constants import (
    DECLARED_ORIGIN_DISPLAY_VERSION,
    DECLARED_ORIGIN_RUNTIME_VERSION,
    DECLARED_ORIGINPRO_VERSION,
    GRAPH_LAYER_NAME,
    GRAPH_PAGE_LONG_NAME,
    GRAPH_PAGE_NAME,
    K01_ADAPTER_ID,
    K01_ADAPTER_VERSION,
    K01_CAPABILITY,
    K01_CHART_TYPE_ID,
    K01_PAGE_HEIGHT_MM,
    K01_PAGE_WIDTH_MM,
    MANIFEST_SHEET_NAME,
    METADATA_BOOK_NAME,
    ORIGIN_EXPORT_SCHEMA_VERSION,
    ORIGIN_TEMPLATE_ID,
    ORIGIN_TEMPLATE_SHA256,
    RAW_BOOK_NAME,
    RAW_SHEET_NAME,
)
from .models import JsonValue, OriginEnvironment


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class K01Data:
    x: tuple[float, ...]
    y: tuple[float, ...]
    x_long_name: str = "Time"
    y_long_name: str = "Signal"
    x_unit: str = "s"
    y_unit: str = "mV"
    x_comments: str = "plotagent_field_id=field:x;role=X"
    y_comments: str = "plotagent_field_id=field:y;role=Y"

    def __post_init__(self) -> None:
        if len(self.x) < 2 or len(self.x) != len(self.y):
            raise ValueError("K01 requires equal X/Y arrays with at least two rows")
        if not all(math.isfinite(value) for value in (*self.x, *self.y)):
            raise ValueError("The M0 K01 spike accepts finite numeric data only")
        for value in (
            self.x_long_name,
            self.y_long_name,
            self.x_unit,
            self.y_unit,
            self.x_comments,
            self.y_comments,
        ):
            if not value or "\x00" in value:
                raise ValueError("K01 labels, units, and comments must be non-empty safe text")

    @classmethod
    def minimal_fixture(cls) -> K01Data:
        return cls(
            x=(0.0, 1.0, 2.0, 3.0, 4.0, 5.0),
            y=(0.0, 1.2, 1.9, 1.4, 2.6, 3.1),
        )

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "x": list(self.x),
            "y": list(self.y),
            "x_long_name": self.x_long_name,
            "y_long_name": self.y_long_name,
            "x_unit": self.x_unit,
            "y_unit": self.y_unit,
            "x_comments": self.x_comments,
            "y_comments": self.y_comments,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> K01Data:
        expected = {
            "x",
            "y",
            "x_long_name",
            "y_long_name",
            "x_unit",
            "y_unit",
            "x_comments",
            "y_comments",
        }
        if set(payload) != expected:
            raise ValueError("K01 data contains missing or unknown fields")
        return cls(
            x=tuple(float(value) for value in payload["x"]),
            y=tuple(float(value) for value in payload["y"]),
            x_long_name=str(payload["x_long_name"]),
            y_long_name=str(payload["y_long_name"]),
            x_unit=str(payload["x_unit"]),
            y_unit=str(payload["y_unit"]),
            x_comments=str(payload["x_comments"]),
            y_comments=str(payload["y_comments"]),
        )


@dataclass(frozen=True, slots=True)
class K01OriginPlan:
    schema_version: str
    chart_type_id: str
    capability: str
    plot_id: str
    plot_version: int
    target_scope: str
    data: K01Data
    x_axis: tuple[float, float, float]
    y_axis: tuple[float, float, float]
    x_axis_title: str
    y_axis_title: str
    legend_text: str
    page_width_mm: float
    page_height_mm: float
    object_map: dict[str, str]
    export_time_utc: str
    adapter_id: str
    adapter_version: str
    origin_display_version: str
    origin_runtime_version: float
    originpro_version: str
    template_id: str
    template_sha256: str
    raw_data_sha256: str
    render_plan_sha256: str
    validation_report_sha256: str
    manifest: dict[str, JsonValue]

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "schema_version": self.schema_version,
            "chart_type_id": self.chart_type_id,
            "capability": self.capability,
            "plot_id": self.plot_id,
            "plot_version": self.plot_version,
            "target_scope": self.target_scope,
            "data": self.data.to_dict(),
            "x_axis": list(self.x_axis),
            "y_axis": list(self.y_axis),
            "x_axis_title": self.x_axis_title,
            "y_axis_title": self.y_axis_title,
            "legend_text": self.legend_text,
            "page_width_mm": self.page_width_mm,
            "page_height_mm": self.page_height_mm,
            "object_map": cast(dict[str, JsonValue], self.object_map),
            "export_time_utc": self.export_time_utc,
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "origin_display_version": self.origin_display_version,
            "origin_runtime_version": self.origin_runtime_version,
            "originpro_version": self.originpro_version,
            "template_id": self.template_id,
            "template_sha256": self.template_sha256,
            "raw_data_sha256": self.raw_data_sha256,
            "render_plan_sha256": self.render_plan_sha256,
            "validation_report_sha256": self.validation_report_sha256,
            "manifest": self.manifest,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> K01OriginPlan:
        expected = {
            "schema_version",
            "chart_type_id",
            "capability",
            "plot_id",
            "plot_version",
            "target_scope",
            "data",
            "x_axis",
            "y_axis",
            "x_axis_title",
            "y_axis_title",
            "legend_text",
            "page_width_mm",
            "page_height_mm",
            "object_map",
            "export_time_utc",
            "adapter_id",
            "adapter_version",
            "origin_display_version",
            "origin_runtime_version",
            "originpro_version",
            "template_id",
            "template_sha256",
            "raw_data_sha256",
            "render_plan_sha256",
            "validation_report_sha256",
            "manifest",
        }
        if set(payload) != expected:
            raise ValueError("K01 Origin plan contains missing or unknown fields")
        x_axis_values = payload["x_axis"]
        y_axis_values = payload["y_axis"]
        if len(x_axis_values) != 3 or len(y_axis_values) != 3:
            raise ValueError("K01 Origin axes must contain from, to, and increment")
        plan = cls(
            schema_version=str(payload["schema_version"]),
            chart_type_id=str(payload["chart_type_id"]),
            capability=str(payload["capability"]),
            plot_id=str(payload["plot_id"]),
            plot_version=int(payload["plot_version"]),
            target_scope=str(payload["target_scope"]),
            data=K01Data.from_dict(cast(dict[str, Any], payload["data"])),
            x_axis=(
                float(x_axis_values[0]),
                float(x_axis_values[1]),
                float(x_axis_values[2]),
            ),
            y_axis=(
                float(y_axis_values[0]),
                float(y_axis_values[1]),
                float(y_axis_values[2]),
            ),
            x_axis_title=str(payload["x_axis_title"]),
            y_axis_title=str(payload["y_axis_title"]),
            legend_text=str(payload["legend_text"]),
            page_width_mm=float(payload["page_width_mm"]),
            page_height_mm=float(payload["page_height_mm"]),
            object_map={str(key): str(value) for key, value in payload["object_map"].items()},
            export_time_utc=str(payload["export_time_utc"]),
            adapter_id=str(payload["adapter_id"]),
            adapter_version=str(payload["adapter_version"]),
            origin_display_version=str(payload["origin_display_version"]),
            origin_runtime_version=float(payload["origin_runtime_version"]),
            originpro_version=str(payload["originpro_version"]),
            template_id=str(payload["template_id"]),
            template_sha256=str(payload["template_sha256"]),
            raw_data_sha256=str(payload["raw_data_sha256"]),
            render_plan_sha256=str(payload["render_plan_sha256"]),
            validation_report_sha256=str(payload["validation_report_sha256"]),
            manifest=cast(dict[str, JsonValue], payload["manifest"]),
        )
        if plan.to_dict() != payload:
            raise ValueError("K01 Origin plan failed canonical round-trip validation")
        return plan


def _object_map() -> dict[str, str]:
    return {
        "source:dataset-k01": f"Data/{RAW_BOOK_NAME}/{RAW_SHEET_NAME}",
        "field:x": f"Data/{RAW_BOOK_NAME}/{RAW_SHEET_NAME}!A",
        "field:y": f"Data/{RAW_BOOK_NAME}/{RAW_SHEET_NAME}!B",
        "plot:k01@1": f"Graphs/{GRAPH_PAGE_NAME}",
        "series:signal": f"Graphs/{GRAPH_PAGE_NAME}/{GRAPH_LAYER_NAME}/Plot1",
        "manifest:k01": f"Metadata/{METADATA_BOOK_NAME}/{MANIFEST_SHEET_NAME}",
    }


def validation_report_for_plan(plan_fields: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {
        "schema_version": ORIGIN_EXPORT_SCHEMA_VERSION,
        "chart_type_id": K01_CHART_TYPE_ID,
        "capability": K01_CAPABILITY,
        "folders": ["Data", "Analysis", "Graphs", "Metadata"],
        "raw_data": {
            "book": RAW_BOOK_NAME,
            "sheet": RAW_SHEET_NAME,
            "rows": plan_fields["rows"],
            "columns": 2,
            "x_designation": 3,
            "y_designation": 0,
            "raw_data_sha256": plan_fields["raw_data_sha256"],
        },
        "graph": {
            "page": GRAPH_PAGE_NAME,
            "page_long_name": GRAPH_PAGE_LONG_NAME,
            "layers": 1,
            "plots": 1,
            "linked_y_dataset": f"{RAW_BOOK_NAME}_B",
            "x_axis": plan_fields["x_axis"],
            "y_axis": plan_fields["y_axis"],
            "x_axis_title": plan_fields["x_axis_title"],
            "y_axis_title": plan_fields["y_axis_title"],
            "legend_text": plan_fields["legend_text"],
            "page_width_mm": plan_fields["page_width_mm"],
            "page_height_mm": plan_fields["page_height_mm"],
        },
        "object_map": cast(dict[str, JsonValue], plan_fields["object_map"]),
        "external_links": False,
    }


def compile_k01_plan(
    environment: OriginEnvironment,
    data: K01Data | None = None,
    *,
    export_time_utc: str | None = None,
) -> K01OriginPlan:
    data = data or K01Data.minimal_fixture()
    export_time_utc = export_time_utc or datetime.now(UTC).isoformat(timespec="seconds")
    object_map = _object_map()
    raw_data_sha256 = sha256_json({"x": list(data.x), "y": list(data.y)})
    render_fields: dict[str, JsonValue] = {
        "schema_version": ORIGIN_EXPORT_SCHEMA_VERSION,
        "chart_type_id": K01_CHART_TYPE_ID,
        "plot_id": "plot:k01",
        "plot_version": 1,
        "data": data.to_dict(),
        "x_axis": [-0.25, 5.25, 1.0],
        "y_axis": [-0.2, 3.4, 0.5],
        "x_axis_title": f"{data.x_long_name} ({data.x_unit})",
        "y_axis_title": f"{data.y_long_name} ({data.y_unit})",
        "legend_text": data.y_long_name,
        "page_width_mm": K01_PAGE_WIDTH_MM,
        "page_height_mm": K01_PAGE_HEIGHT_MM,
        "object_map": cast(dict[str, JsonValue], object_map),
        "raw_data_sha256": raw_data_sha256,
    }
    render_plan_sha256 = sha256_json(render_fields)
    validation_fields = dict(render_fields)
    validation_fields["rows"] = len(data.x)
    validation_report = validation_report_for_plan(validation_fields)
    validation_report_sha256 = sha256_json(validation_report)
    manifest: dict[str, JsonValue] = {
        "schema_version": ORIGIN_EXPORT_SCHEMA_VERSION,
        "chart_type_id": K01_CHART_TYPE_ID,
        "capability": K01_CAPABILITY,
        "target_scope": "current_chart",
        "object_map": cast(dict[str, JsonValue], object_map),
        "data_chain": {
            "kind": "direct",
            "raw_data_edit_updates_graph": True,
            "raw_data_triggers_plotagent_recalculation": False,
        },
        "versions": {
            "adapter_id": K01_ADAPTER_ID,
            "adapter_version": K01_ADAPTER_VERSION,
            "origin_display_version": environment.display_version,
            "origin_runtime_version": environment.runtime_version,
            "originpro_version": environment.originpro_version,
            "template_id": ORIGIN_TEMPLATE_ID,
            "template_sha256": environment.template_sha256,
        },
        "hashes": {
            "raw_data_sha256": raw_data_sha256,
            "render_plan_sha256": render_plan_sha256,
            "validation_report_sha256": validation_report_sha256,
        },
        "validation_required": ["live", "fresh_reopen"],
        "export_time_utc": export_time_utc,
        "known_differences": [],
    }
    return K01OriginPlan(
        schema_version=ORIGIN_EXPORT_SCHEMA_VERSION,
        chart_type_id=K01_CHART_TYPE_ID,
        capability=K01_CAPABILITY,
        plot_id="plot:k01",
        plot_version=1,
        target_scope="current_chart",
        data=data,
        x_axis=(-0.25, 5.25, 1.0),
        y_axis=(-0.2, 3.4, 0.5),
        x_axis_title=f"{data.x_long_name} ({data.x_unit})",
        y_axis_title=f"{data.y_long_name} ({data.y_unit})",
        legend_text=data.y_long_name,
        page_width_mm=K01_PAGE_WIDTH_MM,
        page_height_mm=K01_PAGE_HEIGHT_MM,
        object_map=object_map,
        export_time_utc=export_time_utc,
        adapter_id=K01_ADAPTER_ID,
        adapter_version=K01_ADAPTER_VERSION,
        origin_display_version=environment.display_version,
        origin_runtime_version=environment.runtime_version,
        originpro_version=environment.originpro_version,
        template_id=ORIGIN_TEMPLATE_ID,
        template_sha256=environment.template_sha256,
        raw_data_sha256=raw_data_sha256,
        render_plan_sha256=render_plan_sha256,
        validation_report_sha256=validation_report_sha256,
        manifest=manifest,
    )


def qualification_constants_are_consistent() -> bool:
    return (
        DECLARED_ORIGIN_DISPLAY_VERSION == "10.10.178"
        and math.isclose(DECLARED_ORIGIN_RUNTIME_VERSION, 10.100178, abs_tol=1e-12)
        and DECLARED_ORIGINPRO_VERSION == "1.1.15"
        and ORIGIN_TEMPLATE_SHA256
        == "588d94a13eee1140e55ff3edf04bc84e955b9c2c1dc3a40fc7b4a3932572d254"
    )
