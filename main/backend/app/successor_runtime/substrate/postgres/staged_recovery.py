"""PostgreSQL readback adapter for exact CW08 staged-artifact recovery."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Connection

from app.successor_runtime.runtime.assignments import RuntimeAssignment
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.runtime.staged_recovery import (
    ExactStagedArtifact,
    RecoverableStagedState,
    StagedArtifactRecoveryError,
    StagedRecoveryRequest,
)

from .runtime_journal import _one_mapping, _scope_key, _table
from .staged_artifacts import StagedArtifactRepository
from .values import ValueRepository


class PostgresStagedArtifactRecoveryAdapter:
    """Join public metadata to exact project-owned bytes without re-execution."""

    def __init__(
        self,
        *,
        connection: Connection,
        scope: RuntimeScope,
        project_tables: Any,
    ) -> None:
        self.connection = connection
        self.scope = scope
        self.project_tables = project_tables
        self.staged = StagedArtifactRepository(connection, scope)
        self.values = ValueRepository(connection, project_tables)

    def load_exact(
        self,
        *,
        request: StagedRecoveryRequest,
        assignment: RuntimeAssignment,
        expected_content_digest: str,
    ) -> ExactStagedArtifact:
        compiled = assignment.compiled_admission_binding
        if compiled is None:
            raise StagedArtifactRecoveryError(
                "staged recovery assignment lacks compiled admission binding"
            )
        row = self.staged.load(request.artifact_id, for_update=True)
        self._require_staged_row(
            row,
            request=request,
            assignment=assignment,
            effect_step_id=compiled.effect_step_id,
        )
        value_table = _table("runtime_values")
        value = _one_mapping(
            self.connection.execute(
                select(value_table).where(
                    value_table.c.project_key == _scope_key(self.scope),
                    value_table.c.value_id == request.value_id,
                )
            )
        )
        if value is None:
            raise StagedArtifactRecoveryError(
                "staged artifact public value binding is absent"
            )
        expected_value = {
            "object_type": request.object_type,
            "codec_id": request.codec_id,
            "content_digest": expected_content_digest,
            "state": "AVAILABLE",
        }
        drift = tuple(
            name
            for name, expected in expected_value.items()
            if value[name] != expected
        )
        if drift:
            raise StagedArtifactRecoveryError(
                "staged public value drift: " + ", ".join(drift)
            )
        if value["project_value_ref"] is None or any(
            value[name] is not None
            for name in ("runtime_blob_ref", "canonical_ref")
        ):
            raise StagedArtifactRecoveryError(
                "first-specimen staged artifact is not project-value owned"
            )
        exact = self.values.get_exact(
            self.scope,
            request.value_id,
            expected_revision=request.value_revision,
            expected_incarnation=request.value_incarnation,
            expected_digest=expected_content_digest,
        )
        return ExactStagedArtifact(
            artifact_id=str(row["artifact_id"]),
            project_key=str(row["project_key"]),
            run_id=str(row["run_id"]),
            effect_step_id=str(row["step_id"]),
            effect_attempt_id=str(row["attempt_id"]),
            effect_receipt_ref=str(row["receipt_ref"]),
            value_id=str(row["value_id"]),
            object_type=str(value["object_type"]),
            codec_id=str(value["codec_id"]),
            content_digest=str(value["content_digest"]),
            byte_size=int(value["byte_size"]),
            value_revision=request.value_revision,
            value_incarnation=request.value_incarnation,
            qualifier_ref=str(row["qualifier_ref"]),
            loss_profile_ref=(
                str(row["loss_profile_ref"])
                if row["loss_profile_ref"] is not None
                else None
            ),
            state=RecoverableStagedState(str(row["state"])),
            staged_revision=int(row["revision"]),
            exact_bytes=exact,
        )

    def mark_verified(
        self, staged: ExactStagedArtifact
    ) -> ExactStagedArtifact:
        if staged.state is not RecoverableStagedState.STAGED:
            if staged.state is RecoverableStagedState.VERIFIED:
                return staged
            raise StagedArtifactRecoveryError(
                "only an exact STAGED artifact may enter verification"
            )
        updated = self.staged.transition(
            staged.artifact_id,
            expected_revision=staged.staged_revision,
            expected_state="STAGED",
            target_state="VERIFIED",
        )
        return ExactStagedArtifact(
            artifact_id=staged.artifact_id,
            project_key=staged.project_key,
            run_id=staged.run_id,
            effect_step_id=staged.effect_step_id,
            effect_attempt_id=staged.effect_attempt_id,
            effect_receipt_ref=staged.effect_receipt_ref,
            value_id=staged.value_id,
            object_type=staged.object_type,
            codec_id=staged.codec_id,
            content_digest=staged.content_digest,
            byte_size=staged.byte_size,
            value_revision=staged.value_revision,
            value_incarnation=staged.value_incarnation,
            qualifier_ref=staged.qualifier_ref,
            loss_profile_ref=staged.loss_profile_ref,
            state=RecoverableStagedState.VERIFIED,
            staged_revision=int(updated["revision"]),
            exact_bytes=staged.exact_bytes,
        )

    @staticmethod
    def _require_staged_row(
        row: Mapping[str, object],
        *,
        request: StagedRecoveryRequest,
        assignment: RuntimeAssignment,
        effect_step_id: str,
    ) -> None:
        expected = {
            "artifact_id": request.artifact_id,
            "project_key": assignment.project_key,
            "run_id": assignment.run_id,
            "step_id": effect_step_id,
            "attempt_id": request.effect_attempt_id,
            "receipt_ref": request.effect_receipt_ref,
            "value_id": request.value_id,
            "qualifier_ref": request.qualifier_ref,
            "loss_profile_ref": request.loss_profile_ref,
        }
        drift = tuple(
            name for name, value in expected.items() if row[name] != value
        )
        if drift:
            raise StagedArtifactRecoveryError(
                "staged artifact row drift: " + ", ".join(drift)
            )
        if row["state"] not in {"STAGED", "VERIFIED"}:
            raise StagedArtifactRecoveryError(
                "staged artifact is already terminal or orphaned"
            )


__all__ = ["PostgresStagedArtifactRecoveryAdapter"]
