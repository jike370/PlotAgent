from __future__ import annotations

from plotagent.contracts.errors import ERRORS_BY_CODE
from plotagent.importing.errors import ImportErrorCode
from plotagent.preparation.errors import PreparationErrorCode
from plotagent.storage.errors import StorageErrorCode


def test_all_w2_data_codes_are_in_the_w0_registry() -> None:
    emitted = (
        {code.value for code in ImportErrorCode}
        | {code.value for code in PreparationErrorCode}
        | {code.value for code in StorageErrorCode}
    )

    assert emitted <= ERRORS_BY_CODE.keys()
    w2_codes = emitted - {"SCHEMA_VERSION_UNSUPPORTED"}
    assert all(ERRORS_BY_CODE[code].owner == "W2_DATA" for code in w2_codes)
