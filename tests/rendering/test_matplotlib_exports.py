from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

from plotagent.charts.registry import CHARTS
from plotagent.contracts.canonical import JsonValue, canonical_hash
from plotagent.exports import export_png, export_svg, validate_svg
from plotagent.exports import png_svg as export_module
from plotagent.rendering import PlotResolver, RenderDataStore, RenderTable
from tests.contracts.helpers import HASH_A, minimal_plot
from tests.rendering.fixture_factory import resolve_chart

CHART_IDS = tuple(entry.chart_type_id for entry in CHARTS)
FIXTURE_MANIFEST = Path(__file__).parents[1] / "fixtures" / "rendering" / "chart-fixtures.json"
TEST_ARTIFACT_PREFIX = f".w4-test-output-{os.getpid()}-"
PLAN_GOLDENS = {
    "K01": "b72978a36cdc2fba261bfd0919824cb1bdbe17f3ceed81bc1e4fad9fdbc39db5",
    "K08": "39cbac068ecdb24e97fe300937d4dce8e3b6eb286b123d1da0f71c20d6213ced",
    "K15": "9726a6ddb344202e8c161407959be1d8c4b200e8f5d71398f488864d7718140a",
    "K20": "9a1972fd248af123a8c57702e93f6800a3f12fe8a3dfc4251ee9312f5ac1a029",
    "S21": "a23abd19a21a47592f515ee545d536b5619399ac6594519a21d3d9f9a4f9f653",
    "K24": "a14777d5eadd041afcf15c3f20c3a4fef9c0ec8cfde2876d843de12718ce3a31",
    "K25": "9a4621bc546b5ea82b4b875495f9f9868dc881fc48d55940b2aeeb99d70a68b2",
}
PRECOMPUTED_FIXTURE_IDS = {"K05", "K21", "K22", "S01", "S05", "S21", "S25", "S31", "S34"}
FIXED_FIXTURE_IDS = {
    "K06",
    "K07",
    "K08",
    "K09",
    "K11",
    "K13",
    "K14",
    "K15",
    "K16",
    "K17",
    "K20",
    "S61",
}


@pytest.fixture(scope="module")
def artifact_dir() -> Iterator[Path]:
    directory = FIXTURE_MANIFEST.parent
    yield directory
    for artifact in directory.glob(f"{TEST_ARTIFACT_PREFIX}*"):
        artifact.unlink(missing_ok=True)


def test_fixture_manifest_has_three_explicit_cases_for_exactly_52_charts() -> None:
    payload = json.loads(FIXTURE_MANIFEST.read_text(encoding="utf-8"))
    charts = payload["charts"]
    assert payload["schema_version"] == "1.0"
    assert payload["fixture_factory"] == "tests.rendering.fixture_factory.resolve_chart"
    assert len(charts) == 52
    assert {entry["chart_type_id"] for entry in charts} == set(CHART_IDS)
    case_ids: list[str] = []
    for entry in charts:
        chart_id = entry["chart_type_id"]
        cases = entry["cases"]
        assert [case["kind"] for case in cases] == ["minimal", "representative", "edge"]
        assert [case["case_id"] for case in cases] == [
            f"{chart_id}.minimal",
            f"{chart_id}.representative",
            f"{chart_id}.edge",
        ]
        case_ids.extend(case["case_id"] for case in cases)
    assert len(case_ids) == len(set(case_ids)) == 156


@pytest.mark.parametrize("chart_id", CHART_IDS)
def test_every_chart_exports_valid_full_data_png_and_svg(chart_id: str, artifact_dir: Path) -> None:
    resolved = resolve_chart(chart_id)
    png_path = artifact_dir / f"{TEST_ARTIFACT_PREFIX}{chart_id}.png"
    svg_path = artifact_dir / f"{TEST_ARTIFACT_PREFIX}{chart_id}.svg"

    png = export_png(png_path, resolved)
    svg = export_svg(svg_path, resolved)

    assert png.format == "png"
    assert (png.width, png.height) == (1051.0, 709.0)
    assert svg.format == "svg"
    assert (svg.width, svg.height) == (89.0, 60.0)
    assert svg.element_counts["path"] > 0
    assert svg.element_counts["g"] > 0
    assert svg.element_counts.get("image", 0) == 0
    assert png.render_plan_hash == svg.render_plan_hash == resolved.render_plan_hash
    assert all(layer.full_row_count == layer.displayed_row_count for layer in resolved.plan.layers)
    assert resolved.plan.data_integrity.simplification_applied is False


@pytest.mark.parametrize("chart_id,expected_hash", PLAN_GOLDENS.items())
def test_key_adapter_family_plan_matches_portable_golden(chart_id: str, expected_hash: str) -> None:
    payload = resolve_chart(chart_id).plan.model_dump(mode="json")
    fonts = cast(list[dict[str, object]], payload["fonts"])
    fonts[0]["family"] = "<resolved-font>"
    fonts[0]["file_hash"] = "0" * 64
    assert canonical_hash(cast(JsonValue, payload)) == expected_hash


def test_precomputed_and_fixed_geometry_sources_remain_explicit() -> None:
    for chart_id in PRECOMPUTED_FIXTURE_IDS:
        assert {layer.data_source_kind for layer in resolve_chart(chart_id).plan.layers} == {
            "user_precomputed"
        }
    for chart_id in FIXED_FIXTURE_IDS:
        assert {layer.data_source_kind for layer in resolve_chart(chart_id).plan.layers} == {
            "fixed"
        }
    assert {layer.data_source_kind for layer in resolve_chart("K25").plan.layers} == {"panel_plan"}


def test_formal_k01_keeps_all_100000_rows() -> None:
    count = 100_000
    table = RenderTable.from_columns(
        {
            "field:x": tuple(float(index) for index in range(count)),
            "field:y": tuple(float(index % 101) for index in range(count)),
        }
    )
    resolved = PlotResolver().resolve(minimal_plot(), RenderDataStore({HASH_A: table}))
    layer = resolved.plan.layers[0]
    assert layer.full_row_count == layer.displayed_row_count == count
    assert resolved.table_for(layer).row_count == count
    assert resolved.plan.data_integrity.total_rows == count
    assert resolved.plan.data_integrity.simplification_applied is False


def test_editable_svg_keeps_text_and_declares_font_portability(artifact_dir: Path) -> None:
    resolved = resolve_chart("K01", svg_text_mode="editable_text")
    validation = export_svg(artifact_dir / f"{TEST_ARTIFACT_PREFIX}editable.svg", resolved)
    assert validation.element_counts["text"] > 0
    assert {warning.warning_id for warning in resolved.plan.warnings} == {
        "svg.editable_text_font_portability"
    }


def test_svg_validator_rejects_embedded_or_external_content(artifact_dir: Path) -> None:
    resolved = resolve_chart("K01")
    path = artifact_dir / f"{TEST_ARTIFACT_PREFIX}unsafe.svg"
    export_svg(path, resolved)
    content = path.read_text(encoding="utf-8")
    path.write_text(
        content.replace(
            '<metadata id="plotagent-metadata">',
            '<image href="https://example.invalid/tracker.png"/><metadata id="plotagent-metadata">',
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="SVG_FORBIDDEN_ELEMENT"):
        validate_svg(path, resolved)


def test_atomic_export_preserves_existing_target_on_validation_failure(
    artifact_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = artifact_dir / f"{TEST_ARTIFACT_PREFIX}existing.png"
    target.write_bytes(b"existing artifact")

    def reject_validation(_path: Path, _resolved: object) -> None:
        raise ValueError("forced validation failure")

    monkeypatch.setattr(export_module, "validate_png", reject_validation)
    with pytest.raises(ValueError, match="forced validation failure"):
        export_png(target, resolve_chart("K01"))
    assert target.read_bytes() == b"existing artifact"
    assert list(artifact_dir.glob(f".{target.name}.*")) == []
