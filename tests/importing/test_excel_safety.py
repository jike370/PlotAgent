from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import xlrd  # type: ignore[import-untyped]

import plotagent.importing.excel as excel_module
from plotagent.importing import Imported, inspect_source

FILES_ROOT = Path(__file__).parents[1] / "fixtures" / "import" / "files"


def test_openxml_is_read_only_and_never_refreshes_links(monkeypatch: Any) -> None:
    calls: list[dict[str, object]] = []
    original = excel_module.load_workbook

    def recording_load_workbook(*args: object, **kwargs: object) -> object:
        calls.append(dict(kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(excel_module, "load_workbook", recording_load_workbook)
    result = inspect_source(FILES_ROOT / "excel_formula.xlsx")

    assert isinstance(result, Imported)
    assert len(calls) == 2
    assert all(call["read_only"] is True for call in calls)
    assert all(call["keep_links"] is False for call in calls)
    assert all(call["keep_vba"] is False for call in calls)
    assert {call["data_only"] for call in calls} == {True, False}
    assert result.sources[0].rows == ((2, 4), (3, 6))
    assert all(marker.kind == "cached_formula_value" for marker in result.sources[0].provenance)


@dataclass
class _FakeCell:
    value: object
    data_type: str
    coordinate: str


@dataclass
class _FakeEmptyCell:
    """Match openpyxl's read-only EmptyCell surface: no coordinate attribute."""

    value: object = None
    data_type: str = "n"


class _FakeSheet:
    def __init__(self, title: str, rows: tuple[tuple[_FakeCell, ...], ...]) -> None:
        self.title = title
        self._rows = rows

    def iter_rows(self) -> Any:
        return iter(self._rows)


class _FakeBook:
    def __init__(self, sheet: _FakeSheet) -> None:
        self.worksheets = [sheet]
        self._sheet = sheet

    def __getitem__(self, name: str) -> _FakeSheet:
        assert name == self._sheet.title
        return self._sheet

    def close(self) -> None:
        return None


def test_uncached_formula_becomes_missing_without_execution(monkeypatch: Any) -> None:
    formula_sheet = _FakeSheet(
        "Data",
        (
            (_FakeCell("x", "s", "A1"), _FakeCell("derived", "s", "B1")),
            (_FakeCell(2, "n", "A2"), _FakeCell("=A2*2", "f", "B2")),
        ),
    )
    cached_sheet = _FakeSheet(
        "Data",
        (
            (_FakeCell("x", "s", "A1"), _FakeCell("derived", "s", "B1")),
            (_FakeCell(2, "n", "A2"), _FakeCell(None, "n", "B2")),
        ),
    )
    books = iter((_FakeBook(formula_sheet), _FakeBook(cached_sheet)))
    monkeypatch.setattr(excel_module, "load_workbook", lambda *args, **kwargs: next(books))

    sheets = excel_module._read_openpyxl(Path("uncached.xlsx"))

    region = excel_module._regions(sheets[0])[0]
    candidate = excel_module._candidate(
        path=Path("uncached.xlsx"),
        sheet=sheets[0],
        region=region,
        source_hash="a" * 64,
        parser_name="openpyxl",
        parser_version="test",
        header_row=None,
    )
    assert candidate.rows == ((2, None),)
    assert candidate.source_dataset.quality.missing_values == 1
    assert sheets[0].provenance[0][2].kind == "formula_uncached"


def test_sparse_read_only_empty_cell_does_not_require_coordinate(monkeypatch: Any) -> None:
    formula_sheet = _FakeSheet(
        "Data",
        (
            (_FakeCell("x", "s", "A1"), _FakeEmptyCell(), _FakeCell("y", "s", "C1")),
            (_FakeCell(1, "n", "A2"), _FakeEmptyCell(), _FakeCell(2, "n", "C2")),
        ),
    )
    cached_sheet = _FakeSheet(
        "Data",
        (
            (_FakeCell("x", "s", "A1"), _FakeEmptyCell(), _FakeCell("y", "s", "C1")),
            (_FakeCell(1, "n", "A2"), _FakeEmptyCell(), _FakeCell(2, "n", "C2")),
        ),
    )
    books = iter((_FakeBook(formula_sheet), _FakeBook(cached_sheet)))
    monkeypatch.setattr(excel_module, "load_workbook", lambda *args, **kwargs: next(books))

    sheets = excel_module._read_openpyxl(Path("sparse.xlsx"))

    assert sheets[0].rows == (("x", None, "y"), (1, None, 2))
    assert sheets[0].provenance == ()


class _FakeXlsSheet:
    name = "Data"
    nrows = 3
    ncols = 2
    _rows = (
        ((xlrd.XL_CELL_TEXT, "x"), (xlrd.XL_CELL_TEXT, "y")),
        ((xlrd.XL_CELL_NUMBER, 0.0), (xlrd.XL_CELL_NUMBER, 1.0)),
        ((xlrd.XL_CELL_NUMBER, 1.0), (xlrd.XL_CELL_NUMBER, 2.5)),
    )

    def cell(self, row: int, column: int) -> Any:
        cell_type, value = self._rows[row][column]
        return type("Cell", (), {"ctype": cell_type, "value": value})()

    def unload(self) -> None:
        return None


class _FakeXlsBook:
    datemode = 0

    def sheets(self) -> list[_FakeXlsSheet]:
        return [_FakeXlsSheet()]

    def release_resources(self) -> None:
        return None


def test_xls_uses_the_small_read_only_xlrd_adapter(monkeypatch: Any) -> None:
    source = FILES_ROOT / "virtual_legacy.xls"
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda self: b"frozen fake signature; parser entry is mocked",
    )
    monkeypatch.setattr(xlrd, "open_workbook", lambda *args, **kwargs: _FakeXlsBook())

    result = inspect_source(source)

    assert isinstance(result, Imported)
    assert result.sources[0].recipe.parser_name == "xlrd"
    assert result.sources[0].rows == ((0, 1), (1, 2.5))
