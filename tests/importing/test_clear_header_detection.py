from pathlib import Path

from openpyxl import Workbook

from plotagent.importing import Imported, inspect_source


def test_clear_categorical_csv_header_does_not_require_confirmation(tmp_path: Path) -> None:
    source = tmp_path / "confusion.csv"
    source.write_text("Actual,Predicted\nCat,Cat\nDog,Cat\n", encoding="utf-8")

    result = inspect_source(source)

    assert isinstance(result, Imported)
    assert tuple(field.name for field in result.sources[0].source_dataset.field_schema) == (
        "Actual",
        "Predicted",
    )


def test_clear_categorical_excel_sheet_does_not_block_other_sheets(tmp_path: Path) -> None:
    source = tmp_path / "workbook.xlsx"
    workbook = Workbook()
    first = workbook.active
    first.title = "Numeric"
    first.append(("X", "Y"))
    first.append((1, 2))
    second = workbook.create_sheet("S61_raw")
    second.append(("Actual", "Predicted"))
    second.append(("Cat", "Cat"))
    second.append(("Dog", "Cat"))
    workbook.save(source)

    result = inspect_source(source)

    assert isinstance(result, Imported)
    assert tuple(item.recipe.sheet for item in result.sources) == ("Numeric", "S61_raw")


def test_bracketed_excel_unit_row_is_metadata_not_sample_data(tmp_path: Path) -> None:
    source = tmp_path / "units.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Data"
    sheet.append(("X", "Response_mV"))
    sheet.append(("[mm]", "[mV]"))
    sheet.append((1, 4.28))
    sheet.append((2, 5.31))
    workbook.save(source)

    result = inspect_source(source)

    assert isinstance(result, Imported)
    artifact = result.sources[0]
    assert artifact.rows == ((1, 4.28), (2, 5.31))
    assert artifact.recipe.data_start_row == 3
    assert tuple(field.name for field in artifact.source_dataset.field_schema) == (
        "X",
        "Response_mV",
    )
    assert tuple(field.logical_type for field in artifact.source_dataset.field_schema) == (
        "numeric",
        "numeric",
    )
    assert tuple(field.unit.source_text for field in artifact.source_dataset.field_schema) == (
        "mm",
        "mV",
    )
