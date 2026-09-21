"""Narrow semantic classification for the W08-D C2.2/C2.3 canary shard."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import get_args, get_type_hints

from functorial_kit.arch.gates import scan_project
from functorial_kit.arch.scan import ratchet, violation_key

from app.successor_runtime.capabilities import source_library_c2_3 as c23
from app.successor_runtime.capabilities.checksum import (
    canonical_json,
    sha256_hex,
)
from app.successor_runtime.language.catalog import (
    OperationContractCatalogSnapshot,
)
from app.successor_runtime.language.program import ProgramSpec
from app.successor_runtime.runtime.assignments import (
    InterpreterBinding,
    RecoveryBinding,
)
from app.successor_runtime.substrate.postgres.source_library_c2_23_canary import (
    build_c2_3_fixture_program,
    build_c2_3_payload_value_ref,
    build_legacy_c2_2_binding,
    build_legacy_c2_3_binding,
    build_recovery_c2_3_binding,
    build_successor_c2_2_binding,
    build_successor_c2_3_binding,
)
from successor_runtime.test_p3_c2_3_contracts import _effect_request


_CANARY_PATH = (
    "main/backend/app/successor_runtime/substrate/postgres/"
    "source_library_c2_23_canary.py"
)
_EXACT_BASELINE_KEYS = {
    f"derived-marked|{_CANARY_PATH}|build_c2_3_fixture_program returns an unmarked derived value",
    f"derived-marked|{_CANARY_PATH}|build_c2_3_payload_value_ref returns an unmarked derived value",
    f"derived-marked|{_CANARY_PATH}|build_legacy_c2_2_binding returns an unmarked derived value",
    f"derived-marked|{_CANARY_PATH}|build_legacy_c2_3_binding returns an unmarked derived value",
    f"derived-marked|{_CANARY_PATH}|build_recovery_c2_3_binding returns an unmarked derived value",
    f"derived-marked|{_CANARY_PATH}|build_successor_c2_2_binding returns an unmarked derived value",
    f"derived-marked|{_CANARY_PATH}|build_successor_c2_3_binding returns an unmarked derived value",
}
_CONTRACT_DIGEST = "a" * 64
_DEPLOYMENT_DIGEST = "b" * 64
_SCOPE_DIGEST = "c" * 64
_INTERPRETER_DIGEST = "d" * 64


def _prepared_metadata(function: object) -> str:
    metadata_args = get_args(get_type_hints(function, include_extras=True)["return"])[1:]
    metadata = next(arg for arg in metadata_args if isinstance(arg, str) and arg.startswith("kit:"))
    return metadata


def test_w08d_binding_metadata_preserves_prepared_command_abi() -> None:
    successor_c2_2 = build_successor_c2_2_binding(
        contract_digest=_CONTRACT_DIGEST,
        deployment_catalog_digest=_DEPLOYMENT_DIGEST,
        project_scope_digest=_SCOPE_DIGEST,
    )
    successor_c2_2_repeat = build_successor_c2_2_binding(
        contract_digest=_CONTRACT_DIGEST,
        deployment_catalog_digest=_DEPLOYMENT_DIGEST,
        project_scope_digest=_SCOPE_DIGEST,
    )
    successor_c2_3 = build_successor_c2_3_binding(
        contract_digest=_CONTRACT_DIGEST,
        deployment_catalog_digest=_DEPLOYMENT_DIGEST,
        project_scope_digest=_SCOPE_DIGEST,
    )
    recovery = build_recovery_c2_3_binding(
        interpreter_profile_digest=_INTERPRETER_DIGEST
    )
    legacy_c2_2 = build_legacy_c2_2_binding(
        contract_digest=_CONTRACT_DIGEST,
        deployment_catalog_digest=_DEPLOYMENT_DIGEST,
        project_scope_digest=_SCOPE_DIGEST,
    )
    legacy_c2_3 = build_legacy_c2_3_binding(
        contract_digest=_CONTRACT_DIGEST,
        deployment_catalog_digest=_DEPLOYMENT_DIGEST,
        project_scope_digest=_SCOPE_DIGEST,
    )

    assert isinstance(successor_c2_2, InterpreterBinding)
    assert successor_c2_2 == successor_c2_2_repeat
    assert successor_c2_2.binding_digest == successor_c2_2_repeat.binding_digest
    assert all(
        isinstance(value, (InterpreterBinding, RecoveryBinding))
        for value in (
            successor_c2_2,
            successor_c2_3,
            recovery,
            legacy_c2_2,
            legacy_c2_3,
        )
    )
    assert successor_c2_2.binding_digest != legacy_c2_2.binding_digest
    assert successor_c2_3.binding_digest != legacy_c2_3.binding_digest
    assert len(
        {
            successor_c2_2.binding_digest,
            successor_c2_3.binding_digest,
            recovery.binding_digest,
            legacy_c2_2.binding_digest,
            legacy_c2_3.binding_digest,
        }
    ) == 5

    metadata_by_name = {
        "build_successor_c2_2_binding": "kit:prepared-command",
        "build_successor_c2_3_binding": "kit:prepared-command",
        "build_recovery_c2_3_binding": "kit:prepared-command",
        "build_legacy_c2_2_binding": "kit:prepared-command",
        "build_legacy_c2_3_binding": "kit:prepared-command",
    }
    for name, marker in metadata_by_name.items():
        metadata = _prepared_metadata(globals()[name])
        assert metadata.startswith(marker)
        assert "effect_boundary=" in metadata
        assert metadata.endswith(
            "witness=test:test_w08d_binding_metadata_preserves_prepared_command_abi"
        )


def test_w08d_payload_projection_is_nonauthoritative() -> None:
    request = dataclasses.replace(
        _effect_request(),
        request_id="request:w08d-payload",
        request_digest="",
    )
    value = build_c2_3_payload_value_ref(
        request,
        program_id="program:w08d",
        project_key="project:w08d",
    )
    metadata = _prepared_metadata(build_c2_3_payload_value_ref)

    assert metadata.startswith("kit:non-authoritative")
    assert "derived_as=view" in metadata
    assert "fact_source=request.to_plain" in metadata
    assert "witness=test:test_w08d_payload_projection_is_nonauthoritative" in metadata
    assert value.content_digest == sha256_hex(
        canonical_json(request.to_plain()).encode("utf-8")
    )


def test_w08d_program_spec_preserves_prepared_command_abi() -> None:
    request = dataclasses.replace(
        _effect_request(),
        request_id="request:w08d-program",
        request_digest="",
    )
    bundle = c23.build_source_library_c2_3_bundle()
    catalog = c23.build_source_library_c2_3_catalog(bundle)
    assert isinstance(catalog, OperationContractCatalogSnapshot)
    program = build_c2_3_fixture_program(
        request=request,
        catalog=catalog,
        program_id="program:w08d",
        project_key="project:w08d",
        project_registry_revision=1,
        project_scope_digest=_SCOPE_DIGEST,
    )
    metadata = _prepared_metadata(build_c2_3_fixture_program)

    assert isinstance(program, ProgramSpec)
    assert program.program_digest
    assert metadata.startswith("kit:prepared-command")
    assert "effect_boundary=successor_runtime.language.compile_program" in metadata
    assert metadata.endswith(
        "witness=test:test_w08d_program_spec_preserves_prepared_command_abi"
    )


def test_w08d_exact_keys_have_registered_non_derived_classification() -> None:
    scan = scan_project(Path(__file__).resolve().parents[4])
    result = ratchet(scan.violations, scan.baseline)
    raw_owned_derived = {
        violation_key(violation)
        for violation in scan.violations
        if violation.file == _CANARY_PATH and violation.gate == "derived-marked"
    }
    owned_new = {
        violation_key(violation)
        for violation in result.new_violations
        if violation.file == _CANARY_PATH and violation.gate == "derived-marked"
    }

    assert raw_owned_derived == set()
    assert owned_new == set()
    assert _EXACT_BASELINE_KEYS.isdisjoint(scan.baseline)
