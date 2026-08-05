import os
from pathlib import Path

import pytest

from plotagent.origin import OriginExportSuccess, export_k01

pytestmark = pytest.mark.origin_live


@pytest.mark.skipif(
    os.environ.get("PLOTAGENT_RUN_ORIGIN_LIVE") != "1",
    reason="set PLOTAGENT_RUN_ORIGIN_LIVE=1 to run the exact-version Origin spike",
)
def test_real_k01_build_and_fresh_reopen(tmp_path: Path) -> None:
    target = tmp_path / "k01-origin-10.10.178.opju"

    result = export_k01(target)

    assert isinstance(result, OriginExportSuccess), result.to_dict()
    assert result.environment.display_version == "10.10.178"
    assert result.environment.origin_bitness == 64
    assert result.build_validation == result.reopen_validation
    assert target.is_file()
    assert target.stat().st_size == result.file_size
