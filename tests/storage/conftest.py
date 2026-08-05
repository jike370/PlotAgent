from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def storage_root() -> Iterator[Path]:
    root = Path(__file__).parents[2] / "build" / "storage-tests" / uuid.uuid4().hex
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)
