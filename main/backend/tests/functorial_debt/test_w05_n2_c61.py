"""W05-N2 C6 common and C6.1 no-throw compatibility witnesses."""

from __future__ import annotations

import re
import typing
from pathlib import Path

from functorial_kit import Failure, ratchet, scan_project, violation_key

from mrw_functorial_kit.core.w05_capability_semantics import (
    successor_capability_contract_failures,
)


REPO_ROOT = Path(__file__).resolve().parents[4]
CAPABILITY_ROOT = (
    REPO_ROOT
    / "main"
    / "backend"
    / "app"
    / "successor_runtime"
    / "capabilities"
)
OWNED_FILES = (
    "agent_core_c6_common.py",
    "agent_core_c6_1.py",
    "agent_core_c6_1_interpreters.py",
    "agent_core_c6_1_program.py",
)
RETAINED_BOUNDARY_CONTEXT_KEYS = {
    "operation",
    "owner",
    "public_exception",
    "public_message",
    "site",
    "witness",
}


def test_w05_n2_c61_public_contract_lifts() -> None:
    failure = successor_capability_contract_failures.fail(
        "scope_contract_invalid",
        "canonical scope rejection",
        {
            "operation": "project_scope_digest.v1",
            "owner": "agent_core.c6.v1",
            "public_exception": "ValueError",
            "public_message": "project_key is required",
            "site": "project_scope_digest/project_key",
            "witness": "test:test_w05_n2_c61_public_contract_lifts",
        },
    )

    from app.successor_runtime.capabilities.agent_core_c6_common import (
        _raise_contract,
    )

    try:
        _raise_contract(failure, ValueError)
    except ValueError as error:
        assert str(error) == "project_key is required"
    else:
        raise AssertionError("public contract lift must retain its exception ABI")


def test_w05_n2_c61_programmer_defect_lift() -> None:
    incomplete = Failure(
        family=successor_capability_contract_failures.name,
        code="scope_contract_invalid",
        message="incomplete internal lift",
    )

    from app.successor_runtime.capabilities.agent_core_c6_common import (
        _raise_contract,
    )

    try:
        _raise_contract(incomplete, ValueError)
    except TypeError as error:
        assert str(error) == "contract lift context is incomplete"
    else:
        raise AssertionError("incomplete lift context must remain a programmer defect")

    inconsistent = successor_capability_contract_failures.fail(
        "scope_contract_invalid",
        "typed lift mismatch",
        {
            "operation": "project_scope_digest.v1",
            "owner": "agent_core.c6.v1",
            "public_exception": "TypeError",
            "public_message": "project_key is required",
            "site": "project_scope_digest/project_key",
            "witness": "test:test_w05_n2_c61_programmer_defect_lift",
        },
    )
    try:
        _raise_contract(inconsistent, ValueError)
    except TypeError as error:
        assert str(error) == "contract lift context is incomplete"
    else:
        raise AssertionError("inconsistent lift context must remain a programmer defect")


def test_w05_n2_c61_total_contract_validators_return_closed_failures() -> None:
    from app.successor_runtime.capabilities.agent_core_c6_common import (
        ProjectScope,
        _validate_project_scope,
        _validate_scope_digest_args,
    )
    from app.successor_runtime.capabilities.agent_core_c6_1 import (
        _tool_specimens_by_name,
    )
    from app.successor_runtime.capabilities.agent_core_c6_1_program import (
        validate_agent_core_c6_1_program_identity,
    )

    scope_failure = _validate_scope_digest_args("", "valid_schema", 0, "incarnation")
    project_failure = _validate_project_scope(
        project_key="project",
        registry_revision=0,
        resolved_schema="valid_schema",
        incarnation="incarnation",
        scope_digest="not-hex",
    )
    drifted_scope = ProjectScope(
        project_key="other-project",
        registry_revision=0,
        resolved_schema="valid_schema",
        incarnation="incarnation",
        scope_digest="",
    )
    drifted_payload = type("_Payload", (), {"project_scope": drifted_scope})()
    program_failure = validate_agent_core_c6_1_program_identity(
        drifted_payload,
        project_key="other-project",
        project_registry_revision=0,
        project_scope_digest="digest",
    )

    for failure in (scope_failure, project_failure):
        assert isinstance(failure, Failure)
        assert failure.family == "successor.capability.contract_failure"
        assert RETAINED_BOUNDARY_CONTEXT_KEYS <= set(failure.context or {})
    assert isinstance(program_failure, Failure)
    assert not isinstance(_tool_specimens_by_name(()), Failure)


def test_w05_n2_c61_tool_specimen_index_maps_loop_configuration() -> None:
    from app.successor_runtime.capabilities.agent_core_c6_1 import (
        AgentTurnFailure,
        _tool_specimens_by_name,
    )

    class _Specimen:
        tool_name = "duplicate"

    indexed = _tool_specimens_by_name((_Specimen(), _Specimen()))
    assert isinstance(indexed, Failure)
    assert indexed.context is not None
    assert indexed.context["public_message"] == (
        "duplicate tool specimen name 'duplicate'"
    )
    assert isinstance(AgentTurnFailure, type)


def test_w05_n2_c61_retained_raise_boundary_metadata_is_complete() -> None:
    common_path = CAPABILITY_ROOT / "agent_core_c6_common.py"
    lines = common_path.read_text(encoding="utf-8").splitlines()
    retained = [(index, line) for index, line in enumerate(lines) if "raise " in line]
    assert [line.strip() for _, line in retained] == [
        'raise TypeError("contract lift context is incomplete")',
        'raise exception_type(str(context["public_message"]))',
    ]
    for index, _ in retained:
        metadata = "\n".join(lines[max(0, index - 2) : index])
        assert "kit:boundary owner=agent_core_c6_common.py" in metadata
        assert re.search(r"class=(PROGRAMMER_DEFECT|LEGACY_COMPATIBILITY_EXCEPTION)", metadata)
        assert "failure_family=" in metadata
        expected_witness = (
            "test:test_w05_n2_c61_programmer_defect_lift"
            if "class=PROGRAMMER_DEFECT" in metadata
            else "test:test_w05_n2_c61_public_contract_lifts"
        )
        assert f"witness={expected_witness}" in metadata


def test_w05_n2_c61_latest_kit_owned_scan_removed_four_new_zero() -> None:
    scan = scan_project(REPO_ROOT)
    owned = [
        violation
        for violation in scan.violations
        if violation.severity == "fail"
        and violation.file.startswith(
            "main/backend/app/successor_runtime/capabilities/agent_core_c6"
        )
        and Path(violation.file).name in OWNED_FILES
    ]
    removed_keys = {
        f"no-throw-in-core|main/backend/app/successor_runtime/capabilities/{name}"
        "|raise in core path"
        for name in OWNED_FILES
    }
    assert len(removed_keys & set(scan.baseline)) == 4
    assert not [violation for violation in owned if violation.gate == "no-throw-in-core"]
    result = ratchet(scan.violations, scan.baseline)
    assert not [
        violation
        for violation in result.new_violations
        if violation.gate == "no-throw-in-core"
        if Path(violation.file).name in OWNED_FILES
    ]
    assert {violation_key(violation) for violation in owned}.isdisjoint(set())


def test_w05_agent_core_authority_metadata() -> None:
    from app.successor_runtime.capabilities.agent_core_c6_1 import (
        build_agent_core_c6_1_bundle,
        build_agent_core_c6_1_catalog,
        build_agent_core_c6_1_registry,
    )
    from app.successor_runtime.capabilities.agent_core_c6_1_program import (
        build_agent_core_c6_1_program,
    )
    from app.successor_runtime.capabilities.agent_core_c6_common import (
        build_p3_c6_fragment,
        build_payload_codec,
    )

    for function in (
        build_agent_core_c6_1_bundle,
        build_agent_core_c6_1_catalog,
        build_agent_core_c6_1_registry,
        build_agent_core_c6_1_program,
        build_p3_c6_fragment,
        build_payload_codec,
    ):
        hint = typing.get_type_hints(function, include_extras=True)["return"]
        metadata = typing.get_args(hint)[1]
        assert "witness=test:test_w05_agent_core_authority_metadata" in metadata
