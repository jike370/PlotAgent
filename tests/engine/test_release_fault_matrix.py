from __future__ import annotations

import inspect

from scripts import run_release_fault_matrix, run_release_operational_matrix
from scripts.run_release_fault_matrix import FAULT_CASES


def test_release_fault_matrix_is_complete_and_stable() -> None:
    assert len(FAULT_CASES) == 13
    assert len({case.case_id for case in FAULT_CASES}) == len(FAULT_CASES)
    required = {
        "FAULT-TIMEOUT",
        "FAULT-RATE-LIMIT",
        "FAULT-OFFLINE",
        "FAULT-PROXY",
        "FAULT-BAD-PROVIDER-JSON",
        "FAULT-BAD-CORE-JSON",
        "FAULT-CANCEL",
        "FAULT-PARTIAL",
        "FAULT-TRANSIENT-RETRY",
        "FAULT-EXPLICIT-SAFE-RETRY",
        "FAULT-UNRECOVERABLE",
        "FAULT-UNSAFE-RETRY-REJECTED",
        "FAULT-ATOMIC-DISK-WRITE",
    }
    assert {case.case_id for case in FAULT_CASES} == required
    assert {case.runner for case in FAULT_CASES} == {"pytest", "vitest"}
    assert all("::" in case.target for case in FAULT_CASES)
    assert all(case.expected for case in FAULT_CASES)


def test_release_runners_do_not_force_utf8_on_windows_subprocesses() -> None:
    for module in (run_release_fault_matrix, run_release_operational_matrix):
        assert '"PYTHONUTF8"' not in inspect.getsource(module)
