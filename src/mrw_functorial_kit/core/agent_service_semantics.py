"""Kit projection for agent service and OAuth failure families.

Each family is a closed registration over existing service failure codes.
This module does not execute agent, session, skill, or OAuth operations and
does not introduce a second ``Failure`` primitive.
"""

from __future__ import annotations

from typing import Literal, get_args

from functorial_kit import define_failure_family


AgentBatchFailureCode = Literal[
    "approval_expired",
    "approval_not_found",
    "approval_token_required",
    "channel_unknown",
    "command_required",
    "lane_invalid",
    "planner_no_executable_tasks",
]

AgentFunctorialProjectionFailureCode = Literal[
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
]

AgentRuntimeFailureCode = Literal[
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
]

AgentSessionFailureCode = Literal[
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
]

CodexOauthFailureCode = Literal[
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
]

AgentSkillRuntimeFailureCode = Literal[
    "actor_role_invalid",
    "approval_context_required",
    "approval_required",
    "invoke_denied",
    "loop_detected",
    "skill_id_required",
    "skill_not_found",
    "write_set_conflict",
]


agent_batch_failures = define_failure_family(
    "agent.batch.failure",
    get_args(AgentBatchFailureCode),
)
agent_functorial_projection_failures = define_failure_family(
    "agent.functorial_projection.failure",
    get_args(AgentFunctorialProjectionFailureCode),
)
agent_runtime_failures = define_failure_family(
    "agent.runtime.failure",
    get_args(AgentRuntimeFailureCode),
)
agent_session_failures = define_failure_family(
    "agent.session.failure",
    get_args(AgentSessionFailureCode),
)
codex_oauth_failures = define_failure_family(
    "codex.oauth.failure",
    get_args(CodexOauthFailureCode),
)
agent_skill_runtime_failures = define_failure_family(
    "agent.skill_runtime.failure",
    get_args(AgentSkillRuntimeFailureCode),
)


__all__ = [
    "AgentBatchFailureCode",
    "AgentFunctorialProjectionFailureCode",
    "AgentRuntimeFailureCode",
    "AgentSessionFailureCode",
    "CodexOauthFailureCode",
    "AgentSkillRuntimeFailureCode",
    "agent_batch_failures",
    "agent_functorial_projection_failures",
    "agent_runtime_failures",
    "agent_session_failures",
    "codex_oauth_failures",
    "agent_skill_runtime_failures",
]
