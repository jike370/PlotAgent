from plotagent.origin.constants import (
    DECLARED_ORIGIN_DISPLAY_VERSION,
    DECLARED_ORIGINPRO_VERSION,
    ORIGIN_TEMPLATE_SHA256,
)
from plotagent.origin.k01 import (
    K01OriginPlan,
    compile_k01_plan,
    qualification_constants_are_consistent,
)
from plotagent.origin.models import OriginEnvironment


def _environment() -> OriginEnvironment:
    return OriginEnvironment(
        display_name="Origin2024 SR1",
        display_version=DECLARED_ORIGIN_DISPLAY_VERSION,
        install_dir=r"D:\origin",
        executable_path=r"D:\origin\Origin64.exe",
        origin_bitness=64,
        python_bitness=64,
        originpro_version=DECLARED_ORIGINPRO_VERSION,
        runtime_version=10.100178,
        template_sha256=ORIGIN_TEMPLATE_SHA256,
        license_available=True,
    )


def test_k01_plan_is_canonical_and_contains_no_local_path() -> None:
    plan = compile_k01_plan(_environment(), export_time_utc="2026-08-05T00:00:00+00:00")

    assert qualification_constants_are_consistent()
    assert K01OriginPlan.from_dict(plan.to_dict()) == plan
    assert plan.capability == "O1"
    assert plan.manifest["object_map"] == plan.object_map
    assert plan.manifest["hashes"]["validation_report_sha256"] == (
        plan.validation_report_sha256
    )
    manifest_text = str(plan.manifest).lower()
    assert "d:\\" not in manifest_text
    assert "secret" not in manifest_text
    assert "raster" not in manifest_text


def test_k01_plan_rejects_unknown_worker_fields() -> None:
    payload = compile_k01_plan(
        _environment(), export_time_utc="2026-08-05T00:00:00+00:00"
    ).to_dict()
    payload["arbitrary_property_path"] = "plot1.anything"

    try:
        K01OriginPlan.from_dict(payload)
    except ValueError as exc:
        assert "unknown fields" in str(exc)
    else:
        raise AssertionError("unknown plan fields must be rejected")
