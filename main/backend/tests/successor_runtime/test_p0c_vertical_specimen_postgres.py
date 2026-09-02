"""Real PostgreSQL semantic/admission slice after immutable submission capture."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Any

import pytest
import sqlalchemy as sa

from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.first_specimen import (
    CanonicalReadInput,
    ClaimOrGapInput,
    EvidenceQualificationInput,
    MarkdownComposeInput,
)
from app.successor_runtime.capabilities.first_specimen_interpreters import (
    CapturedDocumentValue,
    FirstSpecimenInterpreters,
    InterpreterSuccess,
)
from app.successor_runtime.research import Claim
from app.successor_runtime.research.codec import canonical_bytes, dataclass_to_json
from app.successor_runtime.research.evidence import Validity
from app.successor_runtime.research.identities import ResearchObjectRef
from app.successor_runtime.research.object_types import (
    CLAIM_TYPE,
    RESEARCH_ARTIFACT_TYPE,
)
from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES
from app.successor_runtime.substrate.postgres.research_ledger import (
    ResearchLedgerRepository,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    RuntimeJournalRepository,
)
from app.successor_runtime.substrate.postgres.values import ValueRepository

from .p0c_postgres_fixture import (
    NOW,
    PROJECT_KEY,
    SEED_CONTENT_SHA256,
    LiveP0CDatabase,
    live_p0c_database,
    p0c_database,
    submission_command,
)

pytestmark = pytest.mark.integration

PROVENANCE_DIGEST = hashlib.sha256(b"p0c-vertical-provenance").hexdigest()


def _payload(cls: type, **values: object) -> Any:
    return cls(**values, payload_digest=content_digest(values))


def _captured(receipt: Any) -> CapturedDocumentValue:
    return CapturedDocumentValue(
        exact_bytes=receipt.observation.exact_bytes,
        snapshot=receipt.snapshot,
        exact_bytes_digest=receipt.snapshot_value_ref.content_digest,
    )


def _runtime_material(
    interpreters: FirstSpecimenInterpreters,
    capture: Any,
) -> Any:
    result = interpreters.read_canonical_ref(
        _payload(
            CanonicalReadInput,
            source_ref=capture.source_ref.source_ref_id,
            locator=capture.source_ref.locator,
            owner_id=capture.source_ref.owner_id,
            observed_at=capture.source_ref.observed_at.isoformat(),
        ),
        _captured(capture),
    )
    assert isinstance(result, InterpreterSuccess)
    return result.value


def _qualify(
    interpreters: FirstSpecimenInterpreters,
    *,
    material: Any,
    inquiry_ref: str,
    label: str,
    direction: str,
) -> Any:
    result = interpreters.qualify_evidence(
        _payload(
            EvidenceQualificationInput,
            qualification_id=f"qualification:p0c:{label}",
            material_ref=material.material_ref_id,
            inquiry_ref=inquiry_ref,
            direction=direction,
            scope_statement_ref="scope:p0c:two-frozen-documents",
            uncertainty_profile_ref="uncertainty:p0c:explicit",
            verifier_profile_ref="verifier:p0c:deterministic-specimen",
        ),
        project_key=PROJECT_KEY,
        provenance_closure_digest=PROVENANCE_DIGEST,
        validity=Validity(valid_from=NOW, valid_to=None),
        observed_at=NOW,
    )
    assert isinstance(result, InterpreterSuccess)
    return result.value


def _put_payload_object(
    database: LiveP0CDatabase,
    *,
    payload: Any,
    object_id: str,
    object_type: Any,
    owner: str,
    incarnation: str,
) -> ResearchObjectRef:
    digest = payload.content_digest
    assert isinstance(digest, str)
    exact = canonical_bytes(dataclass_to_json(payload, ("content_digest",)))
    assert hashlib.sha256(exact).hexdigest() == digest
    provenance = hashlib.sha256(
        f"p0c:{object_id}:provenance".encode("utf-8")
    ).hexdigest()
    ref = ResearchObjectRef(
        object_id=object_id,
        object_type=object_type,
        project_key=PROJECT_KEY,
        revision=1,
        incarnation=incarnation,
        owner_binding_ref=owner,
        content_ref=f"project-value:{object_id}",
        content_digest=digest,
        provenance_closure_digest=provenance,
        lifecycle_state="ADMITTED",
    )
    with database.engine.begin() as connection:
        ValueRepository(connection, database.project_tables).put_exact(
            database.scope,
            value_id=object_id,
            object_type=object_type.type_id,
            codec_id=object_type.codec_id,
            content=exact,
            expected_digest=digest,
            provenance_digest=provenance,
            expected_revision=0,
            expected_incarnation=incarnation,
            provenance={"first_specimen": True, "object_id": object_id},
        )
        ResearchLedgerRepository(
            connection, database.project_tables
        ).put_object(
            database.scope,
            ref,
            expected_revision=0,
            expected_incarnation=incarnation,
        )
    return ref


def test_runtime_material_identity_matches_the_exact_submission_program_output(
    p0c_database: LiveP0CDatabase,
) -> None:
    submitted = p0c_database.submission_service().submit(submission_command())
    interpreters = FirstSpecimenInterpreters()
    runtime_materials = tuple(
        _runtime_material(interpreters, capture) for capture in submitted.captures
    )

    assert runtime_materials == tuple(
        capture.material for capture in submitted.captures
    )
    assert tuple(
        hashlib.sha256(capture.observation.exact_bytes).hexdigest()
        for capture in submitted.captures
    ) == (SEED_CONTENT_SHA256[101], SEED_CONTENT_SHA256[102])


def test_a04_a05_a06_relation_only_claim_and_markdown_closure_are_durable(
    p0c_database: LiveP0CDatabase,
) -> None:
    submitted = p0c_database.submission_service().submit(submission_command())
    interpreters = FirstSpecimenInterpreters()
    materials = tuple(
        _runtime_material(interpreters, capture) for capture in submitted.captures
    )
    assert materials == tuple(capture.material for capture in submitted.captures)

    qualifications = (
        _qualify(
            interpreters,
            material=materials[0],
            inquiry_ref=submitted.inquiry_ref.object_id,
            label="support",
            direction="SUPPORTS",
        ),
        _qualify(
            interpreters,
            material=materials[1],
            inquiry_ref=submitted.inquiry_ref.object_id,
            label="contradiction",
            direction="CONTRADICTS",
        ),
    )
    with p0c_database.engine.begin() as connection:
        ledger = ResearchLedgerRepository(connection, p0c_database.project_tables)
        for qualification, capture in zip(
            qualifications, submitted.captures, strict=True
        ):
            ledger.put_evidence_qualification(
                p0c_database.scope,
                qualification,
                source_ref=capture.material_object_ref,
                target_ref=submitted.inquiry_ref,
                expected_revision=0,
                expected_incarnation=qualification.incarnation,
            )

    claim_result = interpreters.form_claim_or_open_gap(
        _payload(
            ClaimOrGapInput,
            claim_or_gap_id="claim:p0c:two-documents",
            statement_ref="statement:p0c:bounded-comparison",
            inquiry_ref=submitted.inquiry_ref.object_id,
            support_relation_refs=(qualifications[0].qualification_id,),
            contradiction_relation_refs=(qualifications[1].qualification_id,),
            uncertainty_profile_ref="uncertainty:p0c:explicit",
            requirement="",
            reason="",
            missing_evidence_or_decision="",
            reopen_policy={},
            closure_condition="",
        ),
        provenance_closure_digest=PROVENANCE_DIGEST,
    )
    assert isinstance(claim_result, InterpreterSuccess)
    assert isinstance(claim_result.value.value, Claim)
    claim = claim_result.value.value
    assert claim.support_relation_refs == (qualifications[0].qualification_id,)
    assert claim.contradiction_relation_refs == (
        qualifications[1].qualification_id,
    )
    assert claim.scope["provenance_closure_digest"] == PROVENANCE_DIGEST
    _put_payload_object(
        p0c_database,
        payload=claim,
        object_id=claim.claim_id,
        object_type=CLAIM_TYPE,
        owner="ResearchLedger",
        incarnation="claim-inc:p0c",
    )

    composed_result = interpreters.compose_markdown(
        _payload(
            MarkdownComposeInput,
            artifact_id="artifact:p0c:two-documents",
            claim_closure=(claim.claim_id,),
            evidence_relation_closure=tuple(
                qualification.qualification_id for qualification in qualifications
            ),
            citation_closure=tuple(
                material.material_ref_id for material in materials
            ),
        ),
        claim_result.value,
        qualifications=qualifications,
        materials=materials,
    )
    assert isinstance(composed_result, InterpreterSuccess)
    composed = composed_result.value
    artifact = replace(
        composed.artifact,
        lifecycle_state="ADMITTED",
        content_digest=None,
    )
    artifact_ref = _put_payload_object(
        p0c_database,
        payload=artifact,
        object_id=artifact.artifact_id,
        object_type=RESEARCH_ARTIFACT_TYPE,
        owner="ResearchLedger_plus_project_artifact_store",
        incarnation="artifact-inc:p0c",
    )

    assert artifact.citation_closure == tuple(
        material.material_ref_id for material in materials
    )
    assert artifact.evidence_relation_closure == tuple(
        qualification.qualification_id for qualification in qualifications
    )
    assert all(ref.encode() in composed.exact_bytes for ref in artifact.citation_closure)
    with p0c_database.engine.connect() as connection:
        relation_types = connection.scalars(
            sa.select(p0c_database.project_tables.research_relations.c.relation_type)
        ).all()
        object_types = connection.scalars(
            sa.select(p0c_database.project_tables.research_objects.c.object_type)
        ).all()
        assert sorted(relation_types) == ["contradicts", "supports"]
        assert "EvidenceQualification.v1" not in object_types
        assert artifact_ref.object_type == RESEARCH_ARTIFACT_TYPE


def test_cw07_relation_and_runtime_event_share_one_real_postgres_transaction(
    p0c_database: LiveP0CDatabase,
) -> None:
    submitted = p0c_database.submission_service().submit(submission_command())
    interpreters = FirstSpecimenInterpreters()
    qualification = _qualify(
        interpreters,
        material=submitted.captures[0].material,
        inquiry_ref=submitted.inquiry_ref.object_id,
        label="cw07",
        direction="SUPPORTS",
    )

    connection = p0c_database.engine.connect()
    transaction = connection.begin()
    try:
        ResearchLedgerRepository(
            connection, p0c_database.project_tables
        ).put_evidence_qualification(
            p0c_database.scope,
            qualification,
            source_ref=submitted.captures[0].material_object_ref,
            target_ref=submitted.inquiry_ref,
            expected_revision=0,
            expected_incarnation=qualification.incarnation,
        )
        RuntimeJournalRepository(
            connection, p0c_database.scope
        ).append_transition(
            run_id=submission_command().run_id,
            expected_revision=0,
            snapshot_values={"state": "COMPILING"},
            events=(
                {
                    "event_type": "EvidenceQualificationAdmitted",
                    "schema_version": "mrw.runtime.event.evidence-admitted.v1",
                    "event_metadata_json": {
                        "relation_id": qualification.qualification_id
                    },
                        "payload_ref": (
                            f"canonical:research-relation:"
                            f"{qualification.qualification_id}"
                        ),
                    "payload_digest": qualification.qualification_digest,
                    "authority_digest": submission_command().submission_authority_digest,
                },
            ),
        )
        raise RuntimeError("CW07 injected after relation/event before commit")
    except RuntimeError:
        transaction.rollback()
    finally:
        connection.close()

    with p0c_database.engine.connect() as check:
        assert check.scalar(
            sa.select(sa.func.count()).select_from(
                p0c_database.project_tables.research_relations
            )
        ) == 0
        events = check.execute(
            sa.select(PUBLIC_TABLES["runtime_events"]).order_by(
                PUBLIC_TABLES["runtime_events"].c.seq
            )
        ).mappings().all()
        run = check.execute(
            sa.select(PUBLIC_TABLES["runtime_runs"])
        ).mappings().one()
        assert [event["event_type"] for event in events] == ["ProgramAccepted"]
        assert (run["state"], run["revision"], run["next_event_seq"]) == (
            "SUBMITTED",
            0,
            2,
        )

    with p0c_database.engine.begin() as connection:
        ResearchLedgerRepository(
            connection, p0c_database.project_tables
        ).put_evidence_qualification(
            p0c_database.scope,
            qualification,
            source_ref=submitted.captures[0].material_object_ref,
            target_ref=submitted.inquiry_ref,
            expected_revision=0,
            expected_incarnation=qualification.incarnation,
        )
        RuntimeJournalRepository(
            connection, p0c_database.scope
        ).append_transition(
            run_id=submission_command().run_id,
            expected_revision=0,
            snapshot_values={"state": "COMPILING"},
            events=(
                {
                    "event_type": "EvidenceQualificationAdmitted",
                    "schema_version": "mrw.runtime.event.evidence-admitted.v1",
                    "event_metadata_json": {
                        "relation_id": qualification.qualification_id
                    },
                        "payload_ref": (
                            f"canonical:research-relation:"
                            f"{qualification.qualification_id}"
                        ),
                    "payload_digest": qualification.qualification_digest,
                    "authority_digest": submission_command().submission_authority_digest,
                },
            ),
        )

    with p0c_database.engine.connect() as check:
        assert check.scalar(
            sa.select(sa.func.count()).select_from(
                p0c_database.project_tables.research_relations
            )
        ) == 1
        assert check.scalar(
            sa.select(sa.func.count()).select_from(PUBLIC_TABLES["runtime_events"])
        ) == 2
