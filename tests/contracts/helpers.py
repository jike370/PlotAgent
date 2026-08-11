from __future__ import annotations

from plotagent.contracts.base import PreparedDatasetRef

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def prepared_ref() -> PreparedDatasetRef:
    return PreparedDatasetRef(
        prepared_dataset_id="prepared:test",
        prepared_version=1,
        content_hash=HASH_A,
    )
