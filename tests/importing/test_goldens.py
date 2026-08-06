from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from plotagent.importing import Imported, inspect_source

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "import"
FILES_ROOT = FIXTURE_ROOT / "files"


def _manifest() -> dict[str, Any]:
    return json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("fixture", _manifest()["fixtures"], ids=lambda item: item["id"])
def test_frozen_import_golden(fixture: dict[str, Any]) -> None:
    source = FILES_ROOT / fixture["file"]
    expected = fixture["expected"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == fixture["sha256"]

    result = inspect_source(source)

    assert result.kind == expected["kind"]
    if result.kind != "imported":
        assert result.code == expected["code"]
        if result.kind == "clarification":
            assert 1 <= len(result.options) <= 3
            assert result.question
        else:
            assert result.remediation
        return

    assert isinstance(result, Imported)
    assert len(result.sources) == expected["candidates"]
    assert [source.source_dataset.quality.total_rows for source in result.sources] == expected[
        "rows"
    ]
    assert all(
        source.source_dataset.source_object_hash == fixture["sha256"] for source in result.sources
    )
    assert all(source.coordinates for source in result.sources)
    assert all(
        coordinate.source_row_id.startswith("row:") and coordinate.kind in {"text", "excel"}
        for source in result.sources
        for coordinate in source.coordinates
    )
    if "encoding" in expected:
        assert result.sources[0].recipe.encoding == expected["encoding"]
    if "decimal_mark" in expected:
        assert result.sources[0].recipe.decimal_mark == expected["decimal_mark"]
    if "delimiter" in expected:
        assert result.sources[0].recipe.delimiter == expected["delimiter"]
    if "header_row" in expected:
        assert result.sources[0].recipe.header_row == expected["header_row"]
    if "first_header" in expected:
        assert result.sources[0].source_dataset.field_schema[0].name == expected["first_header"]
    if "quality" in expected:
        quality = result.sources[0].source_dataset.quality
        assert quality.missing_values == expected["quality"]["missing"]
        assert quality.nan_values == expected["quality"]["nan"]
        assert quality.positive_inf_values == expected["quality"]["positive_inf"]
        assert quality.negative_inf_values == expected["quality"]["negative_inf"]
    if "provenance" in expected:
        assert any(
            marker.kind == expected["provenance"]
            for source in result.sources
            for marker in source.provenance
        )
    if "first_value" in expected:
        assert result.sources[0].rows[0][0] == expected["first_value"]
    if "first_boolean" in expected:
        assert result.sources[0].rows[0][-1] is expected["first_boolean"]
    if "channel" in expected:
        coordinate = result.sources[0].coordinates[0]
        assert coordinate.kind == "text" and coordinate.channel == expected["channel"]
    if "sweep" in expected:
        coordinate = result.sources[0].coordinates[0]
        assert coordinate.kind == "text" and coordinate.sweep == expected["sweep"]
    if "metadata_key" in expected:
        assert expected["metadata_key"] in result.sources[0].instrument_metadata
    if "postamble" in expected:
        assert len(result.sources[0].postamble) == expected["postamble"]


def test_manifest_has_approximately_thirty_fixed_oracles() -> None:
    manifest = _manifest()
    assert manifest["schema_version"] == "import-golden-manifest-v1"
    assert 30 <= len(manifest["fixtures"]) <= 36
    assert len({fixture["id"] for fixture in manifest["fixtures"]}) == len(manifest["fixtures"])
