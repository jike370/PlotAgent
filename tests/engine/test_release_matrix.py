from __future__ import annotations

import csv
import json
from hashlib import sha256
from pathlib import Path

from plotagent.engine import PlotDocumentRepository, PlotEngineAction, SetTitle
from plotagent.engine.profiles import ENGINE_PROFILES
from plotagent.storage.project import ProjectStore
from scripts.build_release_visual_signatures import build_visual_signatures
from scripts.release_matrix_actions import (
    action_parameter_names,
    document_for_actions,
    isolated_edit_cases,
    representative_edit_actions,
)
from scripts.release_matrix_cases import RELEASE_CASES
from scripts.run_release_edit_matrix import _failed_rows, _origin_request
from scripts.run_release_matrix import execute_offline_matrix
from scripts.run_release_origin_matrix import (
    _edited_history,
    _load_offline_rows,
    _request,
)


def test_release_cases_freeze_all_public_profiles_and_three_variants() -> None:
    public_ids = {str(profile.profile_id) for profile in ENGINE_PROFILES}

    assert len(RELEASE_CASES) == 102
    assert {case.profile_id for case in RELEASE_CASES} == public_ids
    for profile_id in public_ids:
        cases = [case for case in RELEASE_CASES if case.profile_id == profile_id]
        assert {case.variant for case in cases} == {
            "minimal",
            "representative",
            "edge_error",
        }
        for case in cases:
            assert len(case.view.row_ids) > 0
            assert all(len(column.values) == len(case.view.row_ids) for column in case.view.columns)
            assert tuple(binding.field_id for binding in case.create.bindings) == tuple(
                column.field.field_id for column in case.view.columns
            )


def test_offline_release_matrix_executes_306_unique_keys(tmp_path: Path) -> None:
    output = tmp_path / "offline-matrix"

    rows = execute_offline_matrix(output, repository=Path(__file__).resolve().parents[2])

    assert len(rows) == 306
    assert len({row.matrix_key for row in rows}) == 306
    assert sum(row.status == "PASS" for row in rows) == 272
    assert sum(row.status == "FAIL" for row in rows) == 0
    assert sum(row.status == "UNVERIFIED" for row in rows) == 34
    assert {row.profile_id for row in rows if row.status == "UNVERIFIED"} == {
        str(profile.profile_id) for profile in ENGINE_PROFILES
    }
    assert all(
        row.variant == "representative" and row.format == "opju"
        for row in rows
        if row.status == "UNVERIFIED"
    )

    metadata = json.loads((output / "run-metadata.json").read_text(encoding="utf-8"))
    assert metadata["matrix_key_count"] == 306
    assert metadata["phase"] == "offline"
    with (output / "matrix-results.csv").open(encoding="utf-8-sig", newline="") as stream:
        csv_rows = list(csv.DictReader(stream))
    assert len(csv_rows) == 306
    assert (output / "REPORT.md").is_file()
    assert len(tuple((output / "artifacts").glob("*/*/plot.png"))) == 68
    assert len(tuple((output / "artifacts").glob("*/*/plot.svg"))) == 68

    visual_output = tmp_path / "visual-signatures"
    manifest = build_visual_signatures(
        offline=output,
        output=visual_output,
        repository=Path(__file__).resolve().parents[2],
    )
    assert manifest["schema_version"] == "plotagent.release-visual-signatures.v1"
    assert manifest["chart_count"] == 34
    assert len(manifest["charts"]) == 34
    assert len({chart["profile_id"] for chart in manifest["charts"]}) == 34
    assert all(chart["chinese_name"] for chart in manifest["charts"])
    assert all(chart["official_name"] for chart in manifest["charts"])
    assert all(chart["template_or_process"] for chart in manifest["charts"])
    assert all(len(chart["sha256"]) == 64 for chart in manifest["charts"])
    assert len(tuple((visual_output / "images").glob("*.png"))) == 34
    assert (visual_output / "index.html").is_file()
    assert (visual_output / "visual-signatures.json").is_file()
    assert (visual_output / "visual-signatures.csv").is_file()


def test_representative_origin_history_uses_a_fresh_linear_edit_version(
    tmp_path: Path,
) -> None:
    case = next(
        item
        for item in RELEASE_CASES
        if item.profile_id == "K01" and item.variant == "representative"
    )
    title, document = _edited_history(case)
    default = _request(
        case,
        install_dir=tmp_path,
        output=tmp_path / "default.opju",
        previous=None,
    )
    edited = _request(
        case,
        install_dir=tmp_path,
        output=tmp_path / "edited.opju",
        previous=tmp_path / "default.opju",
        title=title,
        document=document,
    )

    assert default.document.plot_version == 1
    assert default.previous_opju is None
    assert document.plot_version == 2
    assert document.parent_version == 1
    assert title.expected_plot_version == 1
    assert edited.previous_opju == str(tmp_path / "default.opju")
    assert tuple(action.action_id for action in edited.actions) == document.applied_action_ids


def test_origin_matrix_rebases_offline_artifacts_to_merged_report(
    tmp_path: Path,
) -> None:
    offline = tmp_path / "offline"
    output = tmp_path / "origin"
    rows = execute_offline_matrix(
        offline,
        repository=Path(__file__).resolve().parents[2],
    )
    output.mkdir()

    rebased = _load_offline_rows(offline, output)

    source = next(row for row in rows if row.artifact is not None)
    merged = next(row for row in rebased if row.matrix_key == source.matrix_key)
    assert merged.artifact is not None
    assert (output / merged.artifact).resolve() == (offline / source.artifact).resolve()


def test_all_representative_profiles_apply_common_edits_in_matplotlib(
    tmp_path: Path,
) -> None:
    from plotagent.engine.backends.matplotlib import default_matplotlib_backend
    from plotagent.engine.ports import EngineRenderSource

    backend = default_matplotlib_backend(tmp_path / "matplotlib-edits")
    cases = tuple(case for case in RELEASE_CASES if case.variant == "representative")
    operation_profiles: dict[str, set[str]] = {}
    for case in cases:
        default = backend.stage(case.document, (), EngineRenderSource(data=case.view))
        default.publish()
        default.finalize()
        actions = representative_edit_actions(case, default.readback)
        assert [action.expected_plot_version for action in actions] == list(
            range(1, len(actions) + 1)
        )
        previous_hash = default.readback.style_hash
        baseline_export = backend.export(
            case.document,
            tmp_path / "incremental" / case.profile_id / "v1.png",
            "png",
        )
        previous_artifact_hash = baseline_export.artifact_hash
        for action in actions:
            operation_profiles.setdefault(action.operation, set()).add(case.profile_id)
        final_document = case.document
        for count in range(1, len(actions) + 1):
            history = actions[:count]
            current_action = history[-1]
            document = document_for_actions(case, history)
            final_document = document
            change = backend.stage(
                document,
                history,
                EngineRenderSource(data=case.view),
            )
            assert change.readback.style_hash != previous_hash
            previous_hash = change.readback.style_hash
            change.publish()
            change.finalize()
            artifact = backend.export(
                document,
                tmp_path
                / "incremental"
                / case.profile_id
                / f"v{document.plot_version}.png",
                "png",
            )
            assert artifact.artifact_hash != previous_artifact_hash, (
                f"{case.profile_id} {current_action.action_id} did not change the rendered PNG"
            )
            previous_artifact_hash = artifact.artifact_hash
        profile_output = tmp_path / "cross-format" / case.profile_id
        profile_output.mkdir(parents=True)
        for format in ("png", "svg"):
            destination = profile_output / f"v{final_document.plot_version}.{format}"
            backend.export(final_document, destination, format)
            assert destination.is_file()
            assert destination.stat().st_size > 0
        origin = _origin_request(
            case,
            actions,
            install_dir=tmp_path,
            output=profile_output / f"v{final_document.plot_version}.opju",
            previous=profile_output / "v1.opju",
        )
        assert origin.document.plot_version == final_document.plot_version
        assert origin.document.applied_action_ids == final_document.applied_action_ids
        assert tuple(action.action_id for action in origin.actions) == (
            case.create.action_id,
            *(action.action_id for action in actions),
        )

    for operation in ("set_title", "set_axis", "set_series_style", "set_legend"):
        expected_profiles = {
            str(profile.profile_id)
            for profile in ENGINE_PROFILES
            if any(capability.operation == operation for capability in profile.capabilities)
        }
        assert operation_profiles[operation] == expected_profiles


def test_all_34_profiles_enumerate_every_public_edit_parameter_in_isolation(
    tmp_path: Path,
) -> None:
    from plotagent.engine.backends.matplotlib import default_matplotlib_backend
    from plotagent.engine.ports import EngineRenderSource

    backend = default_matplotlib_backend(tmp_path / "isolated-contract-readbacks")
    focal_count = 0
    case_ids: set[str] = set()
    for case in (item for item in RELEASE_CASES if item.variant == "representative"):
        default = backend.stage(case.document, (), EngineRenderSource(data=case.view))
        isolated = isolated_edit_cases(case, default.readback)
        default.discard()
        expected = {
            capability.operation: set(capability.parameters)
            for profile in ENGINE_PROFILES
            if str(profile.profile_id) == case.profile_id
            for capability in profile.capabilities
            if capability.operation not in {"create_plot", "bind_fields", "export_plot"}
        }
        observed: dict[str, set[str]] = {}
        for item in isolated:
            assert item.case_id not in case_ids
            case_ids.add(item.case_id)
            assert set(item.focal_parameters).isdisjoint(item.dependency_parameters)
            assert action_parameter_names(item.action) == frozenset(
                (*item.focal_parameters, *item.dependency_parameters)
            )
            observed.setdefault(item.operation, set()).update(item.focal_parameters)
            focal_count += len(item.focal_parameters)
        assert observed == expected

    assert focal_count == sum(
        len(capability.parameters)
        for profile in ENGINE_PROFILES
        for capability in profile.capabilities
        if capability.operation not in {"create_plot", "bind_fields", "export_plot"}
    )


def test_every_profile_parameter_pair_has_an_isolated_matplotlib_execution(
    tmp_path: Path,
) -> None:
    from plotagent.engine.backends.matplotlib import default_matplotlib_backend
    from plotagent.engine.ports import EngineRenderSource

    artifact_root = tmp_path / "isolated-parameter-execution"
    backend = default_matplotlib_backend(artifact_root)
    covered: set[tuple[str, str, str]] = set()
    unchanged: list[str] = []
    shared_property_cases: set[str] = set()
    execution_count = 0
    for case in (item for item in RELEASE_CASES if item.variant == "representative"):
        default = backend.stage(case.document, (), EngineRenderSource(data=case.view))
        isolated_cases = isolated_edit_cases(case, default.readback)
        default.discard()
        plot_token = case.document.plot_id.removeprefix("plot:")
        for isolated in isolated_cases:
            for parameter in isolated.focal_parameters:
                covered.add((case.profile_id, isolated.operation, parameter))
            action_a = isolated.action
            document_a = document_for_actions(case, (action_a,))
            change_a = backend.stage(
                document_a,
                (action_a,),
                EngineRenderSource(data=case.view),
            )
            change_a.publish()
            edited_png = artifact_root / plot_token / "v2" / "preview.png"
            hash_a = sha256(edited_png.read_bytes()).hexdigest()
            change_a.revert()

            action_b = isolated.comparison_action
            document_b = document_for_actions(case, (action_b,))
            change_b = backend.stage(
                document_b,
                (action_b,),
                EngineRenderSource(data=case.view),
            )
            change_b.publish()
            hash_b = sha256(edited_png.read_bytes()).hexdigest()
            if isolated.comparison_mode == "shared_property":
                assert isolated.evidence_reason
                shared_property_cases.add(isolated.case_id)
            elif hash_a == hash_b:
                unchanged.append(isolated.case_id)
            change_b.revert()
            execution_count += 1

    expected = {
        (str(profile.profile_id), capability.operation, parameter)
        for profile in ENGINE_PROFILES
        for capability in profile.capabilities
        if capability.operation not in {"create_plot", "bind_fields", "export_plot"}
        for parameter in capability.parameters
    }
    assert covered == expected
    (tmp_path / "unchanged-rendered-parameters.json").write_text(
        json.dumps(unchanged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    assert unchanged == [], f"public edits did not change rendered PNG: {unchanged}"
    assert shared_property_cases == {
        "K01:set_legend:columns",
        "K04:set_legend:columns",
        "K04:set_colormap:missing_color",
        "K06:set_legend:columns",
        "K07:set_legend:columns",
        "K08:set_legend:columns",
        "K15:set_legend:columns",
        "K20:set_colormap:missing_color",
        "K21:set_colormap:missing_color",
        "K22:set_colormap:missing_color",
        "S34:set_legend:columns",
        "S61:set_colormap:missing_color",
        "X02:set_legend:columns",
        "X09:set_legend:columns",
    }
    paired_colormap_bounds = sum(
        1
        for profile in ENGINE_PROFILES
        for capability in profile.capabilities
        if capability.operation == "set_colormap"
        and {"minimum", "maximum"} <= set(capability.parameters)
    )
    assert execution_count == len(expected) - paired_colormap_bounds


def test_release_edit_origin_request_preserves_linear_action_history(
    tmp_path: Path,
) -> None:
    case = next(
        item
        for item in RELEASE_CASES
        if item.profile_id == "K01" and item.variant == "representative"
    )
    from plotagent.engine.backends.matplotlib import default_matplotlib_backend
    from plotagent.engine.ports import EngineRenderSource

    backend = default_matplotlib_backend(tmp_path / "matplotlib")
    default = backend.stage(case.document, (), EngineRenderSource(data=case.view))
    actions = representative_edit_actions(case, default.readback)

    request = _origin_request(
        case,
        actions[:2],
        install_dir=tmp_path,
        output=tmp_path / "v3.opju",
        previous=tmp_path / "v2.opju",
    )

    assert request.document.plot_version == 3
    assert request.document.parent_version == 2
    assert request.previous_opju == str(tmp_path / "v2.opju")
    assert tuple(action.action_id for action in request.actions) == (
        case.create.action_id,
        actions[0].action_id,
        actions[1].action_id,
    )


def test_release_edit_failures_are_recorded_per_backend(tmp_path: Path) -> None:
    case = next(
        item
        for item in RELEASE_CASES
        if item.profile_id == "K01" and item.variant == "representative"
    )
    from plotagent.engine.backends.matplotlib import default_matplotlib_backend
    from plotagent.engine.ports import EngineRenderSource

    backend = default_matplotlib_backend(tmp_path / "matplotlib")
    default = backend.stage(case.document, (), EngineRenderSource(data=case.view))
    actions = representative_edit_actions(case, default.readback)

    rows = _failed_rows(case, actions, backend="origin", error=RuntimeError("boom"))

    assert len(rows) == len(actions)
    assert {row.backend for row in rows} == {"origin"}
    assert {row.status for row in rows} == {"FAIL"}
    assert {row.error for row in rows} == {"RuntimeError: boom"}
    assert all(row.parameters for row in rows)


def test_all_formal_profile_documents_and_latest_versions_survive_project_reopen(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "release-recovery"
    representative = tuple(
        case for case in RELEASE_CASES if case.variant == "representative"
    )
    assert len(representative) == 34
    from plotagent.engine.backends.matplotlib import default_matplotlib_backend
    from plotagent.engine.ports import EngineRenderSource

    backend = default_matplotlib_backend(tmp_path / "recovery-readback")
    expected_histories: dict[str, tuple[PlotEngineAction, ...]] = {}

    with ProjectStore.create(workspace, project_id="project:release-recovery") as project:
        repository = PlotDocumentRepository(project)
        for case in representative:
            repository.commit(case.document, case.create)
            default = backend.stage(case.document, (), EngineRenderSource(data=case.view))
            default.publish()
            default.finalize()
            actions = representative_edit_actions(case, default.readback)
            history: tuple[PlotEngineAction, ...] = ()
            for action in actions:
                history = (*history, action)
                repository.commit(document_for_actions(case, history), action)
            edited_title = next(
                action.text for action in actions if isinstance(action, SetTitle)
            )
            assert edited_title is not None
            undo = SetTitle(
                action_id=f"action:release-recovery-{case.profile_id}-undo-title",
                target=case.document.plot_id,
                expected_plot_version=len(history) + 1,
                text="",
            )
            history = (*history, undo)
            repository.commit(document_for_actions(case, history), undo)
            redo = SetTitle(
                action_id=f"action:release-recovery-{case.profile_id}-redo-title",
                target=case.document.plot_id,
                expected_plot_version=len(history) + 1,
                text=edited_title,
            )
            history = (*history, redo)
            repository.commit(document_for_actions(case, history), redo)
            expected_histories[case.profile_id] = history

    with ProjectStore.open(workspace) as project:
        repository = PlotDocumentRepository(project)
        latest = repository.list_latest()
        assert len(latest) == 34
        assert {stored.document.profile_id for stored in latest} == {
            profile.profile_id for profile in ENGINE_PROFILES
        }
        for case in representative:
            history = expected_histories[case.profile_id]
            stored = repository.get(case.document.plot_id)
            assert stored.document.plot_version == len(history) + 1
            assert stored.document.parent_version == len(history)
            assert stored.document.profile_id == case.profile_id
            assert stored.document.data == case.document.data
            assert stored.document.bindings == case.document.bindings
            assert stored.document.applied_action_ids == (
                case.create.action_id,
                *(action.action_id for action in history),
            )
            assert [
                item.action.operation for item in repository.actions(case.document.plot_id)
            ] == ["create_plot", *(action.operation for action in history)]
