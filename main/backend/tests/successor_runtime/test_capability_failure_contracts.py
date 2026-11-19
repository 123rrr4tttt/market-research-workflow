"""Capability failure contracts."""

from __future__ import annotations

import pytest

from functorial_kit import Failure


def test_capability_failure_preserves_public_errors() -> None:
    from app.successor_runtime.capabilities import batch_task
    from app.successor_runtime.capabilities import failure as capability_failure_module
    from app.successor_runtime.capabilities import first_specimen
    from app.successor_runtime.capabilities import quality_promotion_port
    from app.successor_runtime.capabilities import request_identity_port
    from app.successor_runtime.capabilities.checksum import (
        primitive_failure,
        raise_primitive_failure,
    )

    malformed = Failure(
        family="not.a.registered.family",
        code="INVALID",
        message="malformed lift context",
    )

    batch_failure = batch_task.agent_batch_contract_failure(
        "schema_contract_invalid",
        "batch public message",
    )
    assert batch_failure.context is not None
    assert batch_failure.context["witness"] == (
        "test:test_capability_failure_preserves_public_errors"
    )
    with pytest.raises(ValueError, match="^batch public message$"):
        batch_task.raise_agent_batch_contract_failure(batch_failure)
    with pytest.raises(TypeError, match="^contract lift context is incomplete or inconsistent$"):
        batch_task.raise_agent_batch_contract_failure(malformed)

    checksum_failure = primitive_failure(
        "digest_contract_invalid",
        "digest public message",
        exception_type=ValueError,
        field_name="digest",
    )
    with pytest.raises(ValueError, match="^digest public message$"):
        raise_primitive_failure(checksum_failure, ValueError)
    with pytest.raises(TypeError, match="^primitive contract lift context is incomplete$"):
        raise_primitive_failure(malformed, ValueError)

    first_failure = capability_failure_module.capability_failure(
        "LOOKUP_NOT_FOUND",
        "missing capability",
    )
    with pytest.raises(KeyError) as helper_error:
        capability_failure_module.raise_capability_failure(
            first_failure,
            KeyError,
            "missing-helper",
        )
    assert helper_error.value.args == ("missing-helper",)
    with pytest.raises(KeyError) as local_error:
        first_specimen._raise_capability_failure(
            first_specimen._capability_failure(
                "LOOKUP_NOT_FOUND",
                "missing local capability",
            ),
            KeyError,
            "missing-local",
        )
    assert local_error.value.args == ("missing-local",)

    quality_failure = quality_promotion_port._failure(
        "evidence_type_invalid",
        "quality public message",
    )
    with pytest.raises(ValueError, match="^quality public message$"):
        quality_promotion_port._raise_contract_failure(quality_failure)
    with pytest.raises(TypeError, match="^quality-promotion contract lift context is incomplete$"):
        quality_promotion_port._raise_contract_failure(malformed)

    identity_failure = request_identity_port._failure(
        "actor_context_invalid",
        "identity public message",
    )
    with pytest.raises(ValueError, match="^identity public message$"):
        request_identity_port._raise_contract_failure(identity_failure)
    with pytest.raises(TypeError, match="^request identity contract lift context is incomplete$"):
        request_identity_port._raise_contract_failure(malformed)


def test_worker_readback_rejects_unknown_plan_mode() -> None:
    from app.successor_runtime.capabilities.source_library_worker_readback import (
        SourceLibraryWorkerObservation,
    )

    try:
        SourceLibraryWorkerObservation(
            item_key="item-1",
            plan_mode="invalid",  # type: ignore[arg-type]
            phase="planned",
            guard_decision="missing",
            observed_at="2026-09-05T00:00:00Z",
        )
    except ValueError as error:
        assert "unknown plan_mode" in str(error)
    else:
        raise AssertionError("worker readback must lift its typed projection failure")
