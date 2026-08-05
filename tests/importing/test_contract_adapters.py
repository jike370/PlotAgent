from __future__ import annotations

from plotagent.contracts.errors import ERRORS_BY_CODE
from plotagent.importing.errors import ImportErrorCode
from plotagent.preparation.errors import PreparationErrorCode


def test_all_import_and_preparation_codes_are_in_the_w0_registry() -> None:
    emitted = {code.value for code in ImportErrorCode} | {
        code.value for code in PreparationErrorCode
    }

    assert emitted <= ERRORS_BY_CODE.keys()
    assert all(ERRORS_BY_CODE[code].owner == "W2_DATA" for code in emitted)
