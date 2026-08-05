"""Deterministic JSON Schema and TypeScript contract generation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, TypeAdapter
from pydantic.json_schema import models_json_schema

from plotagent.contracts.base import SCHEMA_VERSION
from plotagent.contracts.datasets import FieldMapping, PreparedDataset, SourceDataset
from plotagent.contracts.errors import STABLE_ERROR_REGISTRY, ErrorRegistry, ErrorResponse
from plotagent.contracts.plots import BatchSpec, FigureSpec, PatchTransaction, PlotSpec
from plotagent.contracts.registry import ChartRegistry
from plotagent.contracts.rendering import ExportSpec, OriginExportPlan, ResolvedRenderPlan
from plotagent.contracts.schema_roots import (
    AgentDecisionContract,
    ContextEnvelopeContract,
    PlotCalculationResultContract,
    PlotCalculationSpecContract,
    PlotPatchContract,
    PreparationSpecContract,
)

type JsonObject = dict[str, Any]
SchemaModel = type[BaseModel]
SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_ID_BASE = "https://schemas.plotagent.local/v1"

SCHEMA_EXPORTS: tuple[tuple[str, SchemaModel], ...] = (
    ("source-dataset", SourceDataset),
    ("field-mapping", FieldMapping),
    ("preparation-spec", PreparationSpecContract),
    ("prepared-dataset", PreparedDataset),
    ("plot-calculation-spec", PlotCalculationSpecContract),
    ("plot-calculation-result", PlotCalculationResultContract),
    ("chart-registry", ChartRegistry),
    ("plot-spec", PlotSpec),
    ("plot-patch", PlotPatchContract),
    ("patch-transaction", PatchTransaction),
    ("batch-spec", BatchSpec),
    ("figure-spec", FigureSpec),
    ("export-spec", ExportSpec),
    ("resolved-render-plan", ResolvedRenderPlan),
    ("origin-export-plan", OriginExportPlan),
    ("agent-decision", AgentDecisionContract),
    ("context-envelope", ContextEnvelopeContract),
    ("error-registry", ErrorRegistry),
    ("error-response", ErrorResponse),
)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _schema_id(slug: str) -> str:
    return f"{SCHEMA_ID_BASE}/{slug}.schema.json"


def _with_schema_metadata(schema: JsonObject, slug: str) -> JsonObject:
    return {"$id": _schema_id(slug), "$schema": SCHEMA_DRAFT, **schema}


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_schemas() -> tuple[dict[str, str], JsonObject]:
    outputs: dict[str, str] = {}
    for slug, model in SCHEMA_EXPORTS:
        schema = TypeAdapter(model).json_schema(mode="validation")
        outputs[f"schemas/{slug}.schema.json"] = _json_text(_with_schema_metadata(schema, slug))

    model_schemas, definitions = models_json_schema(
        [(model, "validation") for _, model in SCHEMA_EXPORTS],
        title="PlotAgent v1 contract bundle",
    )
    definitions["roots"] = {
        slug: model_schemas[(model, "validation")] for slug, model in SCHEMA_EXPORTS
    }
    bundle = _with_schema_metadata(definitions, "contracts-bundle")
    outputs["schemas/contracts-bundle.schema.json"] = _json_text(bundle)
    return outputs, bundle


def _literal(value: object) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _ref_name(ref: str) -> str:
    return ref.rsplit("/", maxsplit=1)[-1]


def _property_name(name: str) -> str:
    if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", name):
        return name
    return json.dumps(name, ensure_ascii=False)


def _ts_type(schema: JsonObject, indent: int = 0) -> str:
    if "$ref" in schema:
        return _ref_name(str(schema["$ref"]))
    if "const" in schema:
        return _literal(schema["const"])
    if "enum" in schema:
        return " | ".join(_literal(value) for value in schema["enum"])
    for union_key in ("anyOf", "oneOf"):
        if union_key in schema:
            variants = [_ts_type(variant, indent) for variant in schema[union_key]]
            return " | ".join(dict.fromkeys(variants))
    if "allOf" in schema:
        variants = [_ts_type(variant, indent) for variant in schema["allOf"]]
        return " & ".join(dict.fromkeys(variants))

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return " | ".join(_ts_type({**schema, "type": item}, indent) for item in schema_type)
    if schema_type == "string":
        return "string"
    if schema_type in {"number", "integer"}:
        return "number"
    if schema_type == "boolean":
        return "boolean"
    if schema_type == "null":
        return "null"
    if schema_type == "array" or "items" in schema or "prefixItems" in schema:
        if "prefixItems" in schema:
            members = ", ".join(_ts_type(item, indent) for item in schema["prefixItems"])
            return f"readonly [{members}]"
        item_type = _ts_type(schema.get("items", {}), indent)
        return f"ReadonlyArray<{item_type}>"
    if schema_type == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        if properties:
            prefix = " " * indent
            child_prefix = " " * (indent + 2)
            lines = ["{"]
            for name, child in properties.items():
                optional = "" if name in required else "?"
                lines.append(
                    f"{child_prefix}readonly {_property_name(name)}{optional}: "
                    f"{_ts_type(child, indent + 2)};"
                )
            lines.append(f"{prefix}}}")
            return "\n".join(lines)
        additional = schema.get("additionalProperties")
        if isinstance(additional, dict):
            return f"Readonly<Record<string, {_ts_type(additional, indent)}>>"
        return "Readonly<Record<string, never>>"
    return "unknown"


def generate_typescript(bundle: JsonObject) -> str:
    definitions = bundle.get("$defs", {})
    lines = [
        "// Generated from schemas/contracts-bundle.schema.json. Do not edit.",
        "",
        f"export const CONTRACT_SCHEMA_VERSION = {json.dumps(SCHEMA_VERSION)} as const",
        "",
    ]
    for name, schema in sorted(definitions.items()):
        lines.append(f"export type {name} = {_ts_type(schema)}")
        lines.append("")
    return "\n".join(lines)


def desired_outputs() -> dict[str, str]:
    outputs, bundle = build_schemas()
    outputs["schemas/error-registry.json"] = _json_text(
        STABLE_ERROR_REGISTRY.model_dump(mode="json")
    )
    outputs["src/shared/generated/contracts.ts"] = generate_typescript(bundle)

    manifest_entries = [
        {
            "path": path,
            "sha256": _sha256_text(content),
        }
        for path, content in sorted(outputs.items())
    ]
    outputs["schemas/manifest.json"] = _json_text(
        {
            "schema_version": SCHEMA_VERSION,
            "json_schema_draft": SCHEMA_DRAFT,
            "generator": "plotagent.contracts.codegen",
            "files": manifest_entries,
        }
    )
    return outputs


def write_outputs(root: Path) -> None:
    for relative_path, content in desired_outputs().items():
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")


def check_outputs(root: Path) -> list[str]:
    stale: list[str] = []
    for relative_path, content in desired_outputs().items():
        target = root / relative_path
        if not target.exists() or target.read_text(encoding="utf-8") != content:
            stale.append(relative_path)
    return stale


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if generated files differ")
    args = parser.parse_args()
    root = repository_root()
    if args.check:
        stale = check_outputs(root)
        if stale:
            print("Generated contract files are out of sync:")
            for path in stale:
                print(f"- {path}")
            return 1
        return 0
    write_outputs(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
