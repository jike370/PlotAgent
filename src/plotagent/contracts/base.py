"""Strict primitives shared by PlotAgent domain contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

SchemaVersion = Literal["1.0"]
SCHEMA_VERSION: SchemaVersion = "1.0"
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$", strict=True)]
ObjectId = Annotated[
    str,
    StringConstraints(
        pattern=(
            r"^(source|mapping|preparation|prepared|plotcalc|plot|batch|figure|export|"
            r"renderplan|originplan|plan|project):[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
        ),
        strict=True,
    ),
]
FieldId = Annotated[
    str,
    StringConstraints(pattern=r"^field:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
]
RowId = Annotated[
    str,
    StringConstraints(pattern=r"^row:[A-Za-z0-9][A-Za-z0-9._-]{0,191}$", strict=True),
]
SemanticTargetId = Annotated[
    str,
    StringConstraints(
        pattern=r"^(series|axis|legend|annotation|panel):[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
        strict=True,
    ),
]
SemanticAlias = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$", strict=True),
]
VersionId = Annotated[int, Field(ge=1)]
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(ge=1)]
FiniteNumber = Annotated[float, Field(allow_inf_nan=False)]
NonEmptyText = Annotated[str, StringConstraints(min_length=1, max_length=512, strict=True)]
Token = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:+-]{0,127}$", strict=True),
]
SafeOutputName = Annotated[
    str,
    StringConstraints(
        pattern=r"^[^\\/:*?\"<>|\r\n]{1,120}$",
        strip_whitespace=True,
        strict=True,
    ),
]

ChartTypeId = Literal[
    "K01",
    "K02",
    "K03",
    "K04",
    "K05",
    "K06",
    "K07",
    "K08",
    "K09",
    "K10",
    "K11",
    "K12",
    "K13",
    "K14",
    "K15",
    "K16",
    "K17",
    "K18",
    "K19",
    "K20",
    "K21",
    "K22",
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
]
CalculationKind = Literal[
    "histogram_binning",
    "tukey_box",
    "violin_kde",
    "density_kde",
    "ecdf",
    "summary_error",
    "percent_stack",
    "matrix_projection",
    "confusion_count",
]
MissingPolicy = Literal["fail", "exclude_with_report"]
FamilyKind = Literal[
    "xy",
    "categorical",
    "distribution",
    "matrix",
    "survival",
    "dose_response",
    "forest",
    "facet",
    "special",
]
OriginCapability = Literal["O0", "O1", "O2", "O3"]
PrecomputedKind = Literal[
    "curve",
    "band",
    "matrix",
    "matrix_grid",
    "step_curve",
    "risk_table",
    "parameter_table",
    "spectrum",
    "peak_labels",
    "complex_curve",
    "effect_interval",
]


class StrictModel(BaseModel):
    """Base class for immutable, strict, unknown-field-rejecting contracts."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        validate_default=True,
    )


class SourceDatasetRef(StrictModel):
    source_dataset_id: Annotated[
        str,
        StringConstraints(pattern=r"^source:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    source_version: VersionId
    content_hash: Sha256


class FieldMappingRef(StrictModel):
    field_mapping_id: Annotated[
        str,
        StringConstraints(pattern=r"^mapping:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    mapping_version: VersionId
    content_hash: Sha256


class PreparationSpecRef(StrictModel):
    preparation_spec_id: Annotated[
        str,
        StringConstraints(pattern=r"^preparation:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    preparation_version: VersionId
    content_hash: Sha256


class PreparedDatasetRef(StrictModel):
    prepared_dataset_id: Annotated[
        str,
        StringConstraints(pattern=r"^prepared:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    prepared_version: VersionId
    content_hash: Sha256


class PlotCalculationSpecRef(StrictModel):
    calculation_id: Annotated[
        str,
        StringConstraints(pattern=r"^plotcalc:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    calculation_version: VersionId
    calculation_kind: CalculationKind
    content_hash: Sha256


class PlotCalculationResultRef(StrictModel):
    calculation_id: Annotated[
        str,
        StringConstraints(pattern=r"^plotcalc:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    result_version: VersionId
    calculation_kind: CalculationKind
    content_hash: Sha256


class PlotSpecRef(StrictModel):
    plot_id: Annotated[
        str,
        StringConstraints(pattern=r"^plot:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    plot_version: VersionId
    content_hash: Sha256


class ExportSpecRef(StrictModel):
    export_id: Annotated[
        str,
        StringConstraints(pattern=r"^export:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    export_version: VersionId
    content_hash: Sha256


class ObjectVersionRef(StrictModel):
    object_id: ObjectId
    expected_version: VersionId


class ResourceRef(StrictModel):
    """An Electron-authorized resource reference, never a filesystem path."""

    resource_id: Annotated[
        str,
        StringConstraints(pattern=r"^resource:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", strict=True),
    ]
    resource_kind: Literal["authorized_file", "authorized_directory", "temporary_output"]


class ContentTableRef(StrictModel):
    object_hash: Sha256
    row_count: NonNegativeInt
    field_ids: Annotated[tuple[FieldId, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def unique_fields(self) -> ContentTableRef:
        if len(set(self.field_ids)) != len(self.field_ids):
            raise ValueError("field_ids must be unique")
        return self


class Quantity(StrictModel):
    value: FiniteNumber
    unit: Token


class PhysicalLength(StrictModel):
    value: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    unit: Literal["mm", "pt"]


class PhysicalSize(StrictModel):
    width: PhysicalLength
    height: PhysicalLength


class ColorValue(StrictModel):
    value: Annotated[
        str,
        StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$", strict=True),
    ]


class WarningRecord(StrictModel):
    warning_id: Token
    message: NonEmptyText


class RowExclusion(StrictModel):
    row_id: RowId
    field_id: FieldId | None = None
    reason: Literal["missing", "nan", "positive_inf", "negative_inf"]


class NonFiniteCounts(StrictModel):
    missing: NonNegativeInt = 0
    nan: NonNegativeInt = 0
    positive_inf: NonNegativeInt = 0
    negative_inf: NonNegativeInt = 0
