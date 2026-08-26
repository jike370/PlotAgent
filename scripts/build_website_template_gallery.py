"""Build the landing-page gallery from Origin 2024 sample data.

The chart contracts and renderers are the same ones used by PlotAgent.  Each
gallery case records the Origin-shipped sample that supplied its values and the
small deterministic reshaping needed to satisfy the renderer-neutral contract.
Raw Origin templates and sample files are never copied into the website.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from collections import Counter
from collections.abc import Iterable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from plotagent.engine import SetTitle  # noqa: E402
from plotagent.engine.backends.matplotlib import default_matplotlib_backend  # noqa: E402
from plotagent.engine.backends.origin import (  # noqa: E402
    SubprocessOriginWorker,
    preflight_origin,
)
from plotagent.engine.backends.origin.messages import OriginWorkerRequest  # noqa: E402
from plotagent.engine.backends.origin.recipe import ORIGIN_RECIPES  # noqa: E402
from plotagent.engine.ports import EngineRenderSource  # noqa: E402
from scripts.release_matrix_cases import ColumnCase, _release_case  # noqa: E402
from scripts.run_release_origin_matrix import _fresh_verify  # noqa: E402

SAMPLES = Path(os.environ.get("PLOTAGENT_ORIGIN_SAMPLES", r"D:\origin\Samples"))

TEMPLATE = SAMPLES / "Graphing" / "Template.dat"
GROUP_BAR = SAMPLES / "Graphing" / "GroupBar1.txt"
BOX = SAMPLES / "Graphing" / "Box Chart.dat"
HISTOGRAM = SAMPLES / "Graphing" / "Histogram2.dat"
AFRICA = SAMPLES / "Graphing" / "African_population.dat"
VERTICAL = SAMPLES / "Graphing" / "Vertical_2_Panel_Line.txt"
CONTOUR = SAMPLES / "Graphing" / "Contour.dat"
CORRELATION = SAMPLES / "Signal Processing" / "Correlation.dat"
IRIS = SAMPLES / "Statistics" / "Fisher's Iris Data.dat"


def _rows(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as stream:
        return [row for row in csv.reader(stream, delimiter="\t") if row]


def _numeric(value: str) -> float | None:
    value = value.strip()
    if not value or value == "--":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _even(values: list[Any], count: int) -> list[Any]:
    if len(values) < count:
        raise ValueError(f"need {count} values, only found {len(values)}")
    if count == 1:
        return [values[0]]
    return [values[round(index * (len(values) - 1) / (count - 1))] for index in range(count)]


def _column(
    role: str,
    name: str,
    logical_type: str,
    values: Iterable[Any],
    unit: str | None = None,
) -> ColumnCase:
    return ColumnCase(role, name, logical_type, tuple(values), unit)  # type: ignore[arg-type]


def _template_data() -> list[tuple[float, float, float]]:
    return [
        (float(row[0]), float(row[1]), float(row[2]))
        for row in _rows(TEMPLATE)[1:]
        if len(row) >= 3 and all(_numeric(cell) is not None for cell in row[:3])
    ]


def _group_bar_data() -> list[tuple[str, str, float, float]]:
    return [
        (row[0], row[1], float(row[2]), float(row[3]))
        for row in _rows(GROUP_BAR)[1:]
        if len(row) >= 4 and _numeric(row[2]) is not None and _numeric(row[3]) is not None
    ]


def _box_data() -> dict[str, list[float]]:
    rows = _rows(BOX)
    result = {header: [] for header in rows[0][1:]}
    for row in rows[1:]:
        for name, raw in zip(rows[0][1:], row[1:], strict=False):
            value = _numeric(raw)
            if value is not None:
                result[name].append(value)
    return result


def _histogram_data() -> list[float]:
    values: list[float] = []
    for row in _rows(HISTOGRAM):
        value = _numeric(row[-1])
        if value is not None:
            values.append(value)
    return values


def _africa_data() -> list[tuple[str, float, float, float, float]]:
    result: list[tuple[str, float, float, float, float]] = []
    for row in _rows(AFRICA)[3:]:
        if len(row) < 5:
            continue
        values = [_numeric(value) for value in row[1:5]]
        if all(value is not None for value in values):
            result.append((row[0], *(float(value) for value in values)))
    return result


def _vertical_data() -> tuple[list[str], list[tuple[float, ...]]]:
    rows = _rows(VERTICAL)
    headers = rows[0]
    values = [
        tuple(float(value) for value in row[: len(headers)])
        for row in rows[1:]
        if len(row) >= len(headers)
        and all(_numeric(value) is not None for value in row[: len(headers)])
    ]
    return headers, values


def _contour_data() -> list[list[float]]:
    return [[float(value) for value in row] for row in _rows(CONTOUR)]


def _correlation_data() -> list[tuple[float, float]]:
    return [
        (float(row[0]), float(row[1]))
        for row in _rows(CORRELATION)
        if len(row) >= 2 and _numeric(row[0]) is not None and _numeric(row[1]) is not None
    ]


def _iris_data() -> list[tuple[float, float, float, float, str]]:
    result: list[tuple[float, float, float, float, str]] = []
    for raw in IRIS.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw or raw.startswith("//"):
            continue
        row = raw.split("\t")
        if len(row) == 5 and all(_numeric(value) is not None for value in row[:4]):
            result.append((*(float(value) for value in row[:4]), row[4]))
    return result


def _pearson(left: list[float], right: list[float]) -> float:
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right, strict=True))
    denominator = math.sqrt(
        sum((a - left_mean) ** 2 for a in left) * sum((b - right_mean) ** 2 for b in right)
    )
    return 0.0 if denominator == 0 else numerator / denominator


def _case_columns(profile_id: str) -> tuple[tuple[ColumnCase, ...], Path, str]:
    template = _template_data()
    group_bar = _group_bar_data()
    box = _box_data()
    africa = _africa_data()
    vertical_headers, vertical = _vertical_data()

    if profile_id in {"K01", "K02", "K03", "K04", "K18", "K19", "X02"}:
        sampled = _even(template, 10)
        x = [row[0] for row in sampled]
        first = [row[1] for row in sampled]
        second = [row[2] for row in sampled]
        if profile_id == "K01":
            columns = (
                _column("x", "Time", "numeric", x, "s"),
                _column("y", "SVep", "numeric", first),
            )
        elif profile_id in {"K02", "K03"}:
            columns = (
                _column("x", "Time", "numeric", x, "s"),
                _column("y", "SVep", "numeric", first),
                _column(
                    "group",
                    "SVpr sign",
                    "categorical",
                    ["SVpr ≥ 0" if value >= 0 else "SVpr < 0" for value in second],
                ),
            )
        elif profile_id == "K04":
            color_min = min(second)
            color_span = max(second) - color_min or 1.0
            columns = (
                _column("x", "Time", "numeric", x, "s"),
                _column("y", "SVep", "numeric", first),
                _column("size", "|SVpr|", "numeric", [6 + abs(value) * 600 for value in second]),
                _column(
                    "color",
                    "Normalized SVpr",
                    "numeric",
                    [round((value - color_min) / color_span, 2) for value in second],
                ),
            )
        elif profile_id == "K18":
            columns = (
                _column("x", "Time", "numeric", x, "s"),
                _column("series_1", "SVep", "numeric", first),
                _column(
                    "series_2",
                    "SVep + |SVpr|",
                    "numeric",
                    [a + abs(b) * 10 for a, b in zip(first, second, strict=True)],
                ),
            )
        elif profile_id == "K19":
            origin = datetime(2024, 1, 1)
            columns = (
                _column(
                    "time", "Time", "datetime", [origin + timedelta(days=value) for value in x]
                ),
                _column("series_1", "SVep", "numeric", first),
                _column("series_2", "SVpr", "numeric", second),
            )
        else:
            columns = (
                _column("x", "Time", "numeric", x, "s"),
                _column("y", "SVep", "numeric", first),
                _column(
                    "label", "Point", "categorical", [f"P{index + 1}" for index in range(len(x))]
                ),
            )
        return (
            columns,
            TEMPLATE,
            "selected evenly spaced rows; derived only required grouping/modifier roles",
        )

    if profile_id == "K06":
        response = [row[2] for row in group_bar]
        error = [row[3] for row in group_bar]
        return (
            (
                _column("x", "Observation", "numeric", range(1, len(group_bar) + 1)),
                _column("center", "Response", "numeric", response),
                _column("x_err_minus", "X error -", "numeric", [value * 0.08 for value in error]),
                _column("x_err_plus", "X error +", "numeric", [value * 0.08 for value in error]),
                _column("y_err_minus", "Error", "numeric", error),
                _column("y_err_plus", "Error", "numeric", error),
            ),
            GROUP_BAR,
            (
                "used Response/Error directly; row index and symmetric X error "
                "are deterministic adaptations"
            ),
        )

    if profile_id == "K07":
        sampled = _even(vertical, 9)
        return (
            (
                _column("x", vertical_headers[0], "numeric", [row[0] for row in sampled]),
                _column("center", vertical_headers[1], "numeric", [row[1] for row in sampled]),
                _column("lower", vertical_headers[3], "numeric", [row[3] for row in sampled]),
                _column("upper", vertical_headers[4], "numeric", [row[4] for row in sampled]),
            ),
            VERTICAL,
            "selected Year and three official series as center/lower/upper",
        )

    if profile_id in {"K08", "K09", "X09", "X24", "X35", "X40"}:
        labels = [f"{treatment} · {sex}" for treatment, sex, _, _ in group_bar]
        response = [row[2] for row in group_bar]
        error = [row[3] for row in group_bar]
        if profile_id == "K08":
            columns = (
                _column("category", "Treatment · Sex", "categorical", labels),
                _column("value", "Response", "numeric", response),
            )
        elif profile_id == "K09":
            columns = (
                _column("category", "Treatment", "categorical", [row[0] for row in group_bar]),
                _column("group", "Sex", "categorical", [row[1] for row in group_bar]),
                _column("value", "Response", "numeric", response),
            )
        elif profile_id == "X09":
            columns = (
                _column("category", "Treatment · Sex", "categorical", labels),
                _column(
                    "start",
                    "Response - Error",
                    "numeric",
                    [
                        value - error_value
                        for value, error_value in zip(response, error, strict=True)
                    ],
                ),
                _column("middle", "Response", "numeric", response),
                _column(
                    "end",
                    "Response + Error",
                    "numeric",
                    [
                        value + error_value
                        for value, error_value in zip(response, error, strict=True)
                    ],
                ),
            )
        elif profile_id == "X24":
            ordered = sorted(
                zip(labels, response, strict=True), key=lambda item: item[1], reverse=True
            )
            columns = (
                _column(
                    "category", "Treatment · Sex", "categorical", [item[0] for item in ordered]
                ),
                _column("value", "Response", "numeric", [item[1] for item in ordered]),
            )
        elif profile_id == "X35":
            columns = (
                _column("category", "Treatment · Sex", "categorical", labels),
                _column("left", "Response", "numeric", response),
                _column("right", "Error", "numeric", error),
            )
        else:
            columns = (
                _column("label", "Treatment · Sex", "categorical", labels),
                _column("series_1", "Response", "numeric", response),
                _column(
                    "series_2",
                    "Response + Error",
                    "numeric",
                    [
                        value + error_value
                        for value, error_value in zip(response, error, strict=True)
                    ],
                ),
                _column("group", "Sex", "categorical", [row[1] for row in group_bar]),
            )
        return (
            columns,
            GROUP_BAR,
            (
                "used official Treatment/Sex/Response/Error values; interval and "
                "paired endpoints are deterministic derivations"
            ),
        )

    if profile_id in {"K10", "K11"}:
        records = africa[:4]
        component_indices = (("Male 2010", 1), ("Female 2010", 2), ("Male 2050", 3))
        categories: list[str] = []
        components: list[str] = []
        values: list[float] = []
        for record in records:
            for component, index in component_indices:
                categories.append(record[0])
                components.append(component)
                values.append(record[index])
        return (
            (
                _column("category", "Age Group", "categorical", categories),
                _column("component", "Population series", "categorical", components),
                _column("value", "Population", "numeric", values, "million"),
            ),
            AFRICA,
            "melted the first four age groups and three population series into indexed long form",
        )

    if profile_id in {"K12", "K13", "K14", "X05"}:
        groups = ("OCT", "NOV", "DEC")
        values: list[float] = []
        labels: list[str] = []
        for group in groups:
            selected = box[group][:12]
            values.extend(selected)
            labels.extend([group] * len(selected))
        return (
            (
                _column("value", "Daily value", "numeric", values),
                _column("group", "Month", "categorical", labels),
            ),
            BOX,
            "unpivoted OCT/NOV/DEC columns; missing markers were omitted",
        )

    if profile_id == "K15":
        return (
            (_column("value", "Weight", "numeric", _histogram_data()[:48], "Kg"),),
            HISTOGRAM,
            "used the first 48 official Weight observations",
        )

    if profile_id in {"K20", "K22"}:
        matrix = _contour_data()
        size = 7
        x = [column for _row in range(size) for column in range(size)]
        y = [row for row in range(size) for _column_index in range(size)]
        z = [matrix[row][column] for row in range(size) for column in range(size)]
        if profile_id == "K20":
            columns = (
                _column("row", "Matrix row", "categorical", [f"R{value + 1}" for value in y]),
                _column("column", "Matrix column", "categorical", [f"C{value + 1}" for value in x]),
                _column("value", "Z", "numeric", z),
            )
        else:
            columns = (
                _column("x", "Grid X", "numeric", x),
                _column("y", "Grid Y", "numeric", y),
                _column("z", "Z", "numeric", z),
            )
        return (
            columns,
            CONTOUR,
            "selected the upper-left 7×7 block and converted the official matrix to long form",
        )

    if profile_id == "K21":
        names = vertical_headers[1:5]
        series = [[row[index] for row in vertical] for index in range(1, 5)]
        rows: list[str] = []
        columns_: list[str] = []
        values: list[float] = []
        for left_index, left in enumerate(names):
            for right_index, right in enumerate(names):
                rows.append(left)
                columns_.append(right)
                values.append(_pearson(series[left_index], series[right_index]))
        return (
            (
                _column("row_label", "Series", "categorical", rows),
                _column("column_label", "Series", "categorical", columns_),
                _column("value", "Pearson r", "numeric", values),
            ),
            VERTICAL,
            "computed a Pearson correlation matrix from four official time-series columns",
        )

    if profile_id == "K24":
        sampled = _even(vertical, 7)
        facets = ((vertical_headers[1], 1), (vertical_headers[3], 3), (vertical_headers[5], 5))
        labels: list[str] = []
        x: list[float] = []
        y: list[float] = []
        for label, index in facets:
            labels.extend([label] * len(sampled))
            x.extend(row[0] for row in sampled)
            y.extend(row[index] for row in sampled)
        return (
            (
                _column("facet", "Population series", "categorical", labels),
                _column("base_x", "Year", "numeric", x),
                _column("base_y", "Value", "numeric", y),
            ),
            VERTICAL,
            "melted three official series into facet/x/y long form",
        )

    if profile_id == "S34":
        sampled = _even(_correlation_data(), 18)
        positions = [index / (len(sampled) - 1) for index in range(len(sampled))]
        signal = [abs(first) + abs(second) * 0.02 for first, second in sampled]
        signal_max = max(signal) or 1.0
        real = [10 + 30 * position for position in positions]
        imaginary = [
            15 * math.sin(math.pi * position) * (0.92 + 0.12 * value / signal_max)
            for position, value in zip(positions, signal, strict=True)
        ]
        frequency = [100000 / (1.8**index) for index in range(len(sampled))]
        return (
            (
                _column("z_real", "Z real", "numeric", real),
                _column("z_imaginary", "-Z imaginary", "numeric", imaginary),
                _column("frequency", "Frequency", "numeric", frequency, "Hz"),
            ),
            CORRELATION,
            (
                "adapted two official numeric signal columns into monotone "
                "real/imaginary coordinates; frequency is a deterministic index scale"
            ),
        )

    if profile_id == "S61":
        iris = _iris_data()
        classes = ("setosa", "versicolor", "virginica")
        pairs: list[tuple[str, str]] = []
        for _sepal_length, _sepal_width, petal_length, _petal_width, actual in iris:
            predicted = (
                "setosa"
                if petal_length < 2.5
                else "versicolor"
                if petal_length < 5.0
                else "virginica"
            )
            pairs.append((actual, predicted))
        counts = Counter(pairs)
        actual_values = [actual for actual in classes for _predicted in classes]
        predicted_values = [predicted for _actual in classes for predicted in classes]
        return (
            (
                _column("actual", "Actual species", "categorical", actual_values),
                _column("predicted", "Predicted species", "categorical", predicted_values),
                _column(
                    "count",
                    "Count",
                    "numeric",
                    [counts[(actual, predicted)] for actual in classes for predicted in classes],
                ),
            ),
            IRIS,
            "derived a 3×3 confusion matrix using a fixed petal-length threshold classifier",
        )

    if profile_id == "X03":
        labels = [f"{row[0]} · {row[1]}" for row in group_bar]
        response = [row[2] for row in group_bar]
        error = [row[3] for row in group_bar]
        return (
            (
                _column("category", "Treatment · Sex", "categorical", labels),
                _column("series_1", "Response", "numeric", response),
                _column(
                    "series_2",
                    "Response + Error",
                    "numeric",
                    [a + b for a, b in zip(response, error, strict=True)],
                ),
                _column(
                    "series_3",
                    "Response - Error",
                    "numeric",
                    [a - b for a, b in zip(response, error, strict=True)],
                ),
            ),
            GROUP_BAR,
            "used Response and deterministic ±Error series",
        )

    if profile_id == "X13":
        selected = africa[:10]
        return (
            (
                _column("category", "Age Group", "categorical", [row[0] for row in selected]),
                _column("left", "Male 2010", "numeric", [row[1] for row in selected], "million"),
                _column("right", "Female 2010", "numeric", [row[2] for row in selected], "million"),
            ),
            AFRICA,
            "used the official age group, male-2010 and female-2010 columns directly",
        )

    if profile_id in {"X23", "X36", "X38", "X39"}:
        sampled = _even(vertical, 9)
        if profile_id == "X23":
            columns = (
                _column("x", "Year", "numeric", [row[0] for row in sampled]),
                _column("left", vertical_headers[1], "numeric", [row[1] for row in sampled]),
                _column("right", vertical_headers[3], "numeric", [row[3] for row in sampled]),
            )
        elif profile_id == "X36":
            columns = (
                _column("category", "Year", "categorical", [str(int(row[0])) for row in sampled]),
                _column("left", vertical_headers[1], "numeric", [row[1] for row in sampled]),
                _column("right", vertical_headers[3], "numeric", [row[3] for row in sampled]),
            )
        elif profile_id == "X38":
            columns = (
                _column("x", "Year", "numeric", [row[0] for row in sampled]),
                _column("series_1", vertical_headers[1], "numeric", [row[1] for row in sampled]),
                _column("series_2", vertical_headers[3], "numeric", [row[3] for row in sampled]),
                _column("series_3", vertical_headers[5], "numeric", [row[5] for row in sampled]),
            )
        else:
            columns = tuple(
                _column(
                    f"series_{index}",
                    vertical_headers[index],
                    "numeric",
                    [row[index] for row in sampled],
                )
                for index in range(1, 5)
            )
        return (
            columns,
            VERTICAL,
            "selected evenly spaced official years and the chart-required series columns",
        )

    raise KeyError(profile_id)


def build(output: Path, *, skip_origin: bool = False) -> None:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    matplotlib_root = output / "matplotlib"
    origin_root = output / "origin"
    backend = default_matplotlib_backend(output / "matplotlib-cache")

    install_dir: Path | None = None
    worker: SubprocessOriginWorker | None = None
    if not skip_origin:
        probe = preflight_origin(output / "origin-preflight.opju")
        if probe.status != "ready":
            raise RuntimeError(probe.error.message)
        install_dir = Path(probe.environment.install_dir)
        worker = SubprocessOriginWorker(timeout_seconds=900)

    manifest: list[dict[str, Any]] = []
    for index, recipe in enumerate(ORIGIN_RECIPES.values(), start=1):
        profile_id = str(recipe.profile_id)
        print(f"[{index:02d}/34] {profile_id} {recipe.chinese_name}", flush=True)
        columns, source, adaptation = _case_columns(profile_id)
        case = _release_case(profile_id, "representative", columns)

        matplotlib_dir = matplotlib_root / profile_id
        matplotlib_dir.mkdir(parents=True)
        change = backend.stage(case.document, (), EngineRenderSource(data=case.view))
        try:
            change.publish()
            change.finalize()
        except Exception:
            change.revert()
            raise
        matplotlib_png = matplotlib_dir / "plot.png"
        backend.export(case.document, matplotlib_png, "png")

        origin_png: Path | None = None
        origin_opju: Path | None = None
        origin_error: str | None = None
        if worker is not None and install_dir is not None:
            origin_dir = origin_root / profile_id
            origin_dir.mkdir(parents=True)
            default_opju = origin_dir / "default.opju"
            origin_opju = origin_dir / "plot.opju"
            try:
                default_request = OriginWorkerRequest(
                    install_dir=str(install_dir),
                    output_opju=str(default_opju),
                    previous_opju=None,
                    document=case.document,
                    actions=(case.create,),
                    source=EngineRenderSource(data=case.view),
                )
                worker.run(default_request)
                title = SetTitle(
                    action_id=f"action:website-{profile_id.lower()}-title",
                    target=case.document.plot_id,
                    expected_plot_version=1,
                    text=recipe.official_name,
                )
                edited_document = case.document.model_copy(
                    update={
                        "plot_version": 2,
                        "parent_version": 1,
                        "applied_action_ids": (
                            *case.document.applied_action_ids,
                            title.action_id,
                        ),
                    }
                )
                request = OriginWorkerRequest(
                    install_dir=str(install_dir),
                    output_opju=str(origin_opju),
                    previous_opju=str(default_opju),
                    document=edited_document,
                    actions=(case.create, title),
                    source=EngineRenderSource(data=case.view),
                )
                response = worker.run(request)
                if not response.readback.objects:
                    raise RuntimeError(f"{profile_id} Origin readback exposed no native objects")
                origin_png = origin_dir / "plot.png"
                _fresh_verify(
                    origin_opju.with_suffix(".request.json"),
                    origin_opju,
                    origin_png,
                    origin_dir / "fresh-readback.json",
                )
            except Exception as error:  # Keep the diagnostic batch complete.
                origin_error = f"{type(error).__name__}: {error}"
                origin_png = None
                origin_opju = None
                print(f"  Origin FAIL: {origin_error}", flush=True)

        manifest.append(
            {
                "profile_id": profile_id,
                "chinese_name": recipe.chinese_name,
                "official_name": recipe.official_name,
                "official_help_url": recipe.official_help_url,
                "official_entry": recipe.official_entry,
                "origin_templates": [
                    {"filename": item.filename, "sha256": item.sha256, "role": item.role}
                    for item in recipe.templates
                ],
                "origin_sample": str(source),
                "sample_adaptation": adaptation,
                "matplotlib_png": str(matplotlib_png.relative_to(output)).replace("\\", "/"),
                "origin_png": None
                if origin_png is None
                else str(origin_png.relative_to(output)).replace("\\", "/"),
                "origin_opju": None
                if origin_opju is None
                else str(origin_opju.relative_to(output)).replace("\\", "/"),
                "origin_error": origin_error,
            }
        )

    (output / "gallery-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--skip-origin", action="store_true")
    args = parser.parse_args()
    build(args.output, skip_origin=args.skip_origin)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
