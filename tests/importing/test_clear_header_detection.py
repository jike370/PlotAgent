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


def test_explicit_scientific_header_suffixes_are_imported_as_unit_suggestions(
    tmp_path: Path,
) -> None:
    source = tmp_path / "signals.csv"
    source.write_text("Time_s,Signal_mV\n0,1.5\n1,2.5\n", encoding="utf-8")

    result = inspect_source(source)

    assert isinstance(result, Imported)
    fields = result.sources[0].source_dataset.field_schema
    assert tuple(field.name for field in fields) == ("Time_s", "Signal_mV")
    assert tuple(field.unit.source_text for field in fields) == ("s", "mV")
    assert tuple(field.unit.kind for field in fields) == ("opaque", "opaque")


def test_arbitrary_header_suffix_is_not_invented_as_a_unit(tmp_path: Path) -> None:
    source = tmp_path / "identities.csv"
    source.write_text("sample_id,value\nA,1\nB,2\n", encoding="utf-8")

    result = inspect_source(source)

    assert isinstance(result, Imported)
    fields = result.sources[0].source_dataset.field_schema
    assert tuple(field.unit.kind for field in fields) == ("dimensionless", "dimensionless")


def test_unit_registry_preserves_scientific_prefix_case(tmp_path: Path) -> None:
    source = tmp_path / "resistance.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(("Value (MΩ)", "Signal (mΩ)"))
    sheet.append((2, 3))
    sheet.append((4, 5))
    workbook.save(source)

    result = inspect_source(source)

    assert isinstance(result, Imported)
    fields = result.sources[0].source_dataset.field_schema
    assert tuple(field.unit.source_text for field in fields) == ("MΩ", "mΩ")
    assert tuple(field.unit.canonical_unit for field in fields) == ("Mohm", "mohm")


def test_ambiguous_single_letter_suffixes_are_not_asserted_as_units(tmp_path: Path) -> None:
    source = tmp_path / "ambiguous_suffixes.csv"
    source.write_text(
        "distance_m,mass_g,duration_h,pressure_kPa\n1,2,3,4\n",
        encoding="utf-8",
    )

    result = inspect_source(source)

    assert isinstance(result, Imported)
    fields = result.sources[0].source_dataset.field_schema
    assert tuple(field.unit.source_text for field in fields) == ("", "", "", "kPa")
    assert tuple(field.unit.kind for field in fields) == (
        "dimensionless",
        "dimensionless",
        "dimensionless",
        "opaque",
    )
