from __future__ import annotations

from dataclasses import fields
from typing import get_args

import pytest
from functorial_kit import Failure, FailureFamily

from mrw_functorial_kit.core.agent_service_semantics import (
    AgentBatchFailureCode,
    AgentFunctorialProjectionFailureCode,
    AgentRuntimeFailureCode,
    AgentSessionFailureCode,
    AgentSkillRuntimeFailureCode,
    CodexOauthFailureCode,
    agent_batch_failures,
    agent_functorial_projection_failures,
    agent_runtime_failures,
    agent_session_failures,
    agent_skill_runtime_failures,
    codex_oauth_failures,
)


W02_FAMILIES: tuple[tuple[FailureFamily, str, tuple[str, ...]], ...] = (
    (
        agent_batch_failures,
        "agent.batch.failure",
        (
            "approval_expired",
            "approval_not_found",
            "approval_token_required",
            "channel_unknown",
            "command_required",
            "lane_invalid",
            "planner_no_executable_tasks",
        ),
    ),
    (
        agent_functorial_projection_failures,
        "agent.functorial_projection.failure",
        (
            "catalog_record_malformed",
            "composition_step_invalid",
            "motif_id_required",
            "ref_cycle",
            "ref_empty",
            "ref_id_missing",
            "ref_invalid_format",
            "ref_kind_unsupported",
            "ref_unresolved",
            "workflow_id_required",
            "workflow_no_operator",
            "workflow_order_incompatible",
            "workflow_step_invalid",
            "workflow_steps_empty",
            "workflow_steps_invalid_type",
            "workflow_steps_required",
        ),
    ),
    (
        agent_runtime_failures,
        "agent.runtime.failure",
        (
            "approval_binding_incomplete",
            "approval_id_required",
            "approval_not_approved",
            "approval_type_invalid",
            "capability_input_missing",
            "conversation_empty_answer",
            "long_task_stage_invalid",
            "long_task_stage_status_invalid",
            "message_required",
            "session_project_mismatch",
            "write_set_conflict",
            "writing_anchor_not_found",
            "writing_anchor_required",
            "writing_cursor_offset_required",
            "writing_operation_unsupported",
            "writing_range_invalid",
            "tool_name_required",
            "tool_status_unsupported",
        ),
    ),
    (
        agent_session_failures,
        "agent.session.failure",
        (
            "approval_id_required",
            "approval_not_found",
            "artifact_identity_required",
            "backend_unavailable",
            "execution_mode_invalid",
            "phase_invalid",
            "session_already_exists",
            "session_id_required",
            "session_not_found",
            "status_invalid",
            "task_dependencies_incomplete",
            "task_identity_required",
            "task_not_claimable",
            "task_not_found",
        ),
    ),
    (
        codex_oauth_failures,
        "codex.oauth.failure",
        (
            "codex_oauth_authorize_url_missing",
            "codex_oauth_client_id_missing",
            "codex_oauth_disabled",
            "codex_oauth_redirect_uri_missing",
            "codex_oauth_token_url_missing",
            "invalid_or_expired_state",
            "state_expired",
            "state_missing_verifier",
            "state_required",
            "token_exchange_failed",
            "token_sink_owner_mismatch",
            "token_sink_parent_missing",
            "token_sink_parent_must_be_directory",
            "token_sink_parent_must_not_be_group_or_world_writable",
            "token_sink_parent_must_not_be_symlink",
            "token_sink_path_contains_control_character",
            "token_sink_path_must_be_absolute",
            "token_sink_path_must_be_file",
            "token_sink_path_must_not_be_symlink",
        ),
    ),
    (
        agent_skill_runtime_failures,
        "agent.skill_runtime.failure",
        (
            "actor_role_invalid",
            "approval_context_required",
            "approval_required",
            "invoke_denied",
            "loop_detected",
            "skill_id_required",
            "skill_not_found",
            "write_set_conflict",
        ),
    ),
)


def test_INVARIANT__w02_literal_aliases_match_exact_families() -> None:
    aliases: dict[str, tuple[str, ...]] = {
        "agent.batch.failure": get_args(AgentBatchFailureCode),
        "agent.functorial_projection.failure": get_args(
            AgentFunctorialProjectionFailureCode
        ),
        "agent.runtime.failure": get_args(AgentRuntimeFailureCode),
        "agent.session.failure": get_args(AgentSessionFailureCode),
        "codex.oauth.failure": get_args(CodexOauthFailureCode),
        "agent.skill_runtime.failure": get_args(AgentSkillRuntimeFailureCode),
    }

    assert aliases == {
        family.name: codes
        for family, _name, codes in W02_FAMILIES
    }


@pytest.mark.parametrize(("family", "name", "codes"), W02_FAMILIES)
def test_INVARIANT__w02_failure_family_names_and_codes_are_exact(
    family: FailureFamily,
    name: str,
    codes: tuple[str, ...],
) -> None:
    assert family.name == name
    assert family.codes == codes
    assert len(set(family.codes)) == len(family.codes)


@pytest.mark.parametrize(("family", "name", "_codes"), W02_FAMILIES)
def test_INVARIANT__w02_failure_family_rejects_unknown_codes(
    family: FailureFamily,
    name: str,
    _codes: tuple[str, ...],
) -> None:
    with pytest.raises(
        ValueError,
        match=f"failure family {name}: unknown code 'w02_not_registered'",
    ):
        family.fail("w02_not_registered", "outside the closed family")


@pytest.mark.parametrize(("family", "_name", "_codes"), W02_FAMILIES)
def test_FAILURE_PRESERVED__w02_fail_returns_kit_failure_values(
    family: FailureFamily,
    _name: str,
    _codes: tuple[str, ...],
) -> None:
    context = {"source": "w02-test"}
    for code in family.codes:
        failure = family.fail(code, "closed W02 member", context)

        assert type(failure) is Failure
        assert isinstance(failure, Failure)
        assert (failure.family, failure.code, failure.message) == (
            family.name,
            code,
            "closed W02 member",
        )
        assert failure.context == context
        assert family.matches(failure)


def test_INVARIANT__w02_uses_the_kit_failure_primitive_without_replacement() -> None:
    assert {field.name for field in fields(Failure)} == {
        "family",
        "code",
        "message",
        "context",
    }
