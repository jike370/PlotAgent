from __future__ import annotations

import json

import pytest
from pydantic import TypeAdapter, ValidationError

from plotagent.contracts.base import (
    ContentTableRef,
    ExportSpecRef,
    ObjectVersionRef,
    PhysicalLength,
    PreparationSpecRef,
    ResourceRef,
)
from plotagent.contracts.canonical import canonical_hash
from plotagent.contracts.plots import (
    BatchExecutionSignature,
    BatchItemState,
    BatchSpec,
    DatasetFieldSignature,
    DatasetSignature,
    FigurePanel,
    FigureSpec,
    PlotPatch,
    PlotSpec,
)
from plotagent.contracts.registry import CHARTS_BY_ID, V1_CHART_REGISTRY
from plotagent.contracts.rendering import (
    DataIntegritySnapshot,
    ExportSpec,
    ExportValidationRequirements,
    OriginAxisPlan,
    OriginColumnPlan,
    OriginDataObject,
    OriginExactVersion,
    OriginExportPlan,
    OriginGraphObject,
    OriginLayerPlan,
    OriginManifestPlan,
    OriginObjectMapEntry,
    OriginPlotPlan,
    OriginRoleColumn,
    OriginTemplateRef,
    OriginTickPlan,
    ResolvedAxis,
    ResolvedFont,
    ResolvedLayer,
    ResolvedPanel,
    ResolvedRenderPlan,
)

from .helpers import (
    HASH_A,
    HASH_B,
    HASH_C,
    minimal_plot,
    physical_size,
    prepared_ref,
    profile,
    rich_text,
    style,
    table_ref,
)


def test_chart_registry_is_exactly_the_frozen_52_and_all_opju_o1() -> None:
    expected = {
        *(f"K{index:02d}" for index in range(1, 23)),
        "K24",
        "K25",
        "S01",
        "S05",
        "S21",
        "S25",
        "S31",
        "S34",
        "S61",
        "X01",
        "X02",
        "X03",
        "X05",
        "X07",
        "X09",
        "X11",
        "X12",
        "X13",
        "X15",
        "X16",
        "X17",
        "X18",
        "X19",
        "X23",
        "X24",
        "X35",
        "X36",
        "X37",
        "X38",
        "S07",
    }
    assert set(CHARTS_BY_ID) == expected
    assert len(V1_CHART_REGISTRY.charts) == 52
    assert all(chart.exports.opju == "O1" for chart in V1_CHART_REGISTRY.charts)


def test_plot_spec_round_trip_rejects_unknowns_and_registry_mismatch() -> None:
    plot = minimal_plot()
    assert PlotSpec.model_validate_json(plot.model_dump_json()) == plot
    with pytest.raises(ValidationError):
        PlotSpec.model_validate({**plot.model_dump(), "renderer": "matplotlib"})
    with pytest.raises(ValidationError, match="chart family"):
        PlotSpec.model_validate(
            {
                **plot.model_dump(),
                "chart_type_id": "K08",
                "family": plot.family.model_dump(),
            }
        )


def test_plot_patch_is_discriminated_and_unknown_fields_fail() -> None:
    adapter = TypeAdapter(PlotPatch)
    payload = {
        "schema_version": "1.0",
        "operation": "set_axis_range",
        "target_id": "axis:y",
        "expected_plot_version": 1,
        "minimum": 0.0,
        "maximum": 10.0,
    }
    assert adapter.validate_json(json.dumps(payload)).operation == "set_axis_range"
    with pytest.raises(ValidationError):
        adapter.validate_json(json.dumps({**payload, "path": "/axes/0"}))
    with pytest.raises(ValidationError):
        adapter.validate_json(json.dumps({**payload, "minimum": 10.0, "maximum": 0.0}))


def test_general_edit_contracts_are_closed_and_validate_shape() -> None:
    adapter = TypeAdapter(PlotPatch)
    common = {"schema_version": "1.0", "expected_plot_version": 1}
    assert (
        adapter.validate_python(
            {
                **common,
                "operation": "set_axis_range",
                "target_id": "axis:y",
                "minimum": None,
                "maximum": None,
            }
        ).minimum
        is None
    )
    assert (
        adapter.validate_python(
            {
                **common,
                "operation": "set_axis_ticks",
                "target_id": "axis:y",
                "ticks": {
                    "major_interval": 2.5,
                    "number_format": "scientific",
                    "decimal_places": 2,
                },
            }
        ).ticks.major_interval
        == 2.5
    )
    assert (
        adapter.validate_python(
            {
                **common,
                "operation": "add_annotation",
                "target_id": "plot:test",
                "annotation": {
                    "annotation_id": "annotation:band",
                    "kind": "reference_band",
                    "x": 2.0,
                    "x2": 4.0,
                },
            }
        ).annotation.x2
        == 4.0
    )

    with pytest.raises(ValidationError, match="both be fixed or both be automatic"):
        adapter.validate_python(
            {
                **common,
                "operation": "set_axis_range",
                "target_id": "axis:y",
                "minimum": None,
                "maximum": 10.0,
            }
        )
    with pytest.raises(ValidationError, match="start must be lower"):
        adapter.validate_python(
            {
                **common,
                "operation": "add_annotation",
                "target_id": "plot:test",
                "annotation": {
                    "annotation_id": "annotation:bad-band",
                    "kind": "reference_band",
                    "y": 4.0,
                    "y2": 2.0,
                },
            }
        )


def test_batch_and_figure_pin_exact_versions() -> None:
    plot = minimal_plot()
    plot_ref = {
        "plot_id": plot.plot_id,
        "plot_version": plot.plot_version,
        "content_hash": HASH_C,
    }
    dataset_signature = DatasetSignature(
        fields=(
            DatasetFieldSignature(
                field_id="field:x",
                logical_type="numeric",
                unit_hash=HASH_A,
                semantic_role="x",
            ),
        ),
        semantic_hash=HASH_B,
    )
    signature_payload = {
        "dataset_signature": dataset_signature.model_dump(mode="json"),
        "field_mapping_hash": HASH_A,
        "preparation_spec_hash": HASH_B,
        "plot_calculation_spec_hash": None,
        "chart_type_id": "K01",
        "plot_template_hash": HASH_C,
        "style_hash": canonical_hash(style()),
    }
    batch = BatchSpec(
        batch_id="batch:test",
        batch_version=1,
        dataset_signature=dataset_signature,
        execution_signature=BatchExecutionSignature(
            dataset_signature=dataset_signature,
            field_mapping_hash=HASH_A,
            preparation_spec_hash=HASH_B,
            plot_calculation_spec_hash=None,
            chart_type_id="K01",
            plot_template_hash=HASH_C,
            style_hash=canonical_hash(style()),
            content_hash=canonical_hash(signature_payload),
        ),
        dataset_version_refs=(prepared_ref(),),
        shared_field_mapping={
            "field_mapping_id": "mapping:test",
            "mapping_version": 1,
            "content_hash": HASH_A,
        },
        shared_preparation=PreparationSpecRef(
            preparation_spec_id="preparation:test",
            preparation_version=1,
            content_hash=HASH_B,
        ),
        plot_template_ref=plot_ref,
        shared_style=style(),
        item_states=(BatchItemState(item_id="item.one", state="pending"),),
    )
    assert batch.axis_policy == "per_plot"

    figure = FigureSpec(
        figure_id="figure:test",
        figure_version=1,
        layout="1x2",
        panels=(
            FigurePanel(panel_id="panel:a", plot_version_ref=plot_ref, panel_label=rich_text("A")),
            FigurePanel(panel_id="panel:b", plot_version_ref=plot_ref, panel_label=rich_text("B")),
        ),
        common_legend=True,
        physical_size=physical_size(),
        publication_profile=profile(),
    )
    assert all(panel.plot_version_ref.plot_version == 1 for panel in figure.panels)


def resolved_plan() -> ResolvedRenderPlan:
    data_ref = table_ref("field:x", "field:y")
    return ResolvedRenderPlan(
        render_plan_id="renderplan:test",
        render_plan_version=1,
        resolver_version="resolver.v1",
        source_refs=(ObjectVersionRef(object_id="plot:test", expected_version=1),),
        source_content_hashes=(HASH_A,),
        quality_tier="formal",
        canvas=physical_size(),
        panels=(
            ResolvedPanel(
                panel_id="panel:main",
                left=PhysicalLength(value=10.0, unit="mm"),
                top=PhysicalLength(value=5.0, unit="mm"),
                width=PhysicalLength(value=70.0, unit="mm"),
                height=PhysicalLength(value=45.0, unit="mm"),
            ),
        ),
        axes=(
            ResolvedAxis(
                axis_id="axis:x",
                scale="linear",
                minimum=0.0,
                maximum=1.0,
                label=rich_text("X"),
            ),
        ),
        layers=(
            ResolvedLayer(
                layer_id="layer.main",
                target_id="series:main",
                geometry="line",
                data_ref=data_ref,
                field_ids=("field:x", "field:y"),
                z_order=1,
            ),
        ),
        fonts=(
            ResolvedFont(
                family="Arial",
                file_hash=HASH_B,
                size=PhysicalLength(value=8.0, unit="pt"),
            ),
        ),
        data_integrity=DataIntegritySnapshot(
            total_rows=4,
            visible_rows=4,
            excluded_rows=0,
            nonfinite_values=0,
            simplification_applied=False,
            full_data_hash=HASH_C,
        ),
    )


def test_export_and_origin_plans_never_carry_paths_or_arbitrary_properties() -> None:
    export = ExportSpec(
        export_id="export:test",
        export_version=1,
        format="opju",
        target_scope="current_plot",
        target_refs=(ObjectVersionRef(object_id="plot:test", expected_version=1),),
        target_resource=ResourceRef(
            resource_id="resource:chosen_directory",
            resource_kind="authorized_directory",
        ),
        output_name="figure.opju",
        render_plan_hash=HASH_A,
        validation=ExportValidationRequirements(require_fresh_reopen=True),
    )
    origin = OriginExportPlan(
        origin_plan_id="originplan:test",
        origin_plan_version=1,
        export_spec_ref=ExportSpecRef(
            export_id=export.export_id,
            export_version=export.export_version,
            content_hash=HASH_B,
        ),
        render_plan_hash=export.render_plan_hash,
        adapter_id="origin.adapter.k01",
        adapter_version="adapter.v1",
        origin_version=OriginExactVersion(version="2026", build="10.0.0"),
        template=OriginTemplateRef(
            template_resource=ResourceRef(
                resource_id="resource:signed_template",
                resource_kind="authorized_file",
            ),
            template_hash=HASH_A,
            signature_hash=HASH_B,
        ),
        data_objects=(
            OriginDataObject(
                object_id="data.main",
                object_kind="worksheet",
                folder="Data",
                internal_name="DataMain",
                long_name="Data Main",
                data_chain="direct",
                data_ref=ContentTableRef(
                    object_hash=HASH_C,
                    row_count=4,
                    field_ids=("field:x", "field:y"),
                ),
                columns=(
                    OriginColumnPlan(
                        field_id="field:x",
                        role="x",
                        designation="X",
                        logical_type="numeric",
                        long_name="X",
                        values=(0.0, 1.0, 2.0, 3.0),
                    ),
                    OriginColumnPlan(
                        field_id="field:y",
                        role="y",
                        designation="Y",
                        logical_type="numeric",
                        long_name="Y",
                        values=(1.0, 2.0, 3.0, 4.0),
                    ),
                ),
            ),
        ),
        graph_objects=(
            OriginGraphObject(
                graph_id="graph.main",
                internal_name="GraphMain",
                long_name="Graph Main",
                page_width_mm=89.0,
                page_height_mm=60.0,
                font_family="Arial",
                font_size_pt=8.0,
                legend_visible=False,
                layers=(
                    OriginLayerPlan(
                        layer_id="originlayer.main",
                        panel_id="panel:main",
                        left_mm=10.0,
                        top_mm=5.0,
                        width_mm=70.0,
                        height_mm=45.0,
                        axes=(
                            OriginAxisPlan(
                                axis_id="axis:x",
                                orientation="x",
                                scale="linear",
                                minimum=0.0,
                                maximum=3.0,
                                ticks=(
                                    OriginTickPlan(value=0.0, label="0"),
                                    OriginTickPlan(value=3.0, label="3"),
                                ),
                            ),
                            OriginAxisPlan(
                                axis_id="axis:y",
                                orientation="y",
                                scale="linear",
                                minimum=1.0,
                                maximum=4.0,
                                ticks=(
                                    OriginTickPlan(value=1.0, label="1"),
                                    OriginTickPlan(value=4.0, label="4"),
                                ),
                            ),
                        ),
                        plots=(
                            OriginPlotPlan(
                                plot_id="plot.main",
                                source_layer_id="layer.main",
                                native_kind="line",
                                data_object_id="data.main",
                                role_columns=(
                                    OriginRoleColumn(role="x", field_id="field:x"),
                                    OriginRoleColumn(role="y", field_id="field:y"),
                                ),
                                z_order=1,
                            ),
                        ),
                    ),
                ),
                data_object_ids=("data.main",),
            ),
        ),
        manifest=OriginManifestPlan(
            chart_type_ids=("K01",),
            target_scope="current_plot",
            object_map=(
                OriginObjectMapEntry(
                    plotagent_object_id="data.main", origin_object_ref="Data/DataMain"
                ),
                OriginObjectMapEntry(
                    plotagent_object_id="graph.main", origin_object_ref="Graphs/GraphMain"
                ),
                OriginObjectMapEntry(
                    plotagent_object_id="plot.main",
                    origin_object_ref="Graphs/GraphMain/L00/P00",
                ),
            ),
            render_plan_hashes=(HASH_A,),
            data_chains=("direct",),
            resolver_versions=("resolver.v1",),
        ),
    )
    assert origin.capability == "O1"
    assert "path" not in json.dumps(origin.model_dump(mode="json"), sort_keys=True)

    with pytest.raises(ValidationError):
        OriginExportPlan.model_validate(
            {**origin.model_dump(), "property_assignments": [{"property_name": "formula"}]}
        )


def test_formal_render_plan_rejects_simplification() -> None:
    plan = resolved_plan()
    with pytest.raises(ValidationError, match="formal render plans"):
        ResolvedRenderPlan.model_validate(
            {
                **plan.model_dump(),
                "data_integrity": {
                    **plan.data_integrity.model_dump(),
                    "simplification_applied": True,
                },
            }
        )
