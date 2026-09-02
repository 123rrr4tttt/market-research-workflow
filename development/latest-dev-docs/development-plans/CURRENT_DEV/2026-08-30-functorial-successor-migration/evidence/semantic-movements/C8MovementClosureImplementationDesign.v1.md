# C8 Movement Closure Implementation Design v1

Status: `MAINLINE_IO_FIXED · IMPLEMENTATION_NOT_COMPLETE · MOVEMENTS_REMAIN_BLOCKED · NO_PROMOTION`

This non-normative design fixes implementation IO for `C8-M001..M005`. Frozen
`06/20/21` and the current P1–P3 movement matrix remain authoritative. No
production canonical write, live provider, external delivery, cutover,
authority transfer or movement re-disposition is authorized by this file.

## Upstream exact-value seam

C7 admission must consume both the exact `StructuredMaterialCandidate` and its
`VerifiedMaterialCandidate`. In the same nested transaction/savepoint that
prepares the CommitIntent and writes the disposable canonical head, it writes
the candidate's canonical `structured_payload` bytes to the existing project
`successor_values` table:

- `value_id = c7:structured:<candidate_id>`;
- object type `StructuredMaterialCandidatePayload.v1`;
- codec `mrw.successor.c7.structured-payload.canonical-json.v1`;
- content digest exactly `payload_content_digest`;
- provenance digest exactly `provenance_closure_digest`;
- immutable revision `1` and non-reusable scope/candidate incarnation;
- source ref equal to the full C7 snapshot ref.

The C7 head binds value ref, revision, incarnation and digest. Exact duplicate
admission reads the same value. Candidate/value/head mutation, stale revision,
incarnation ABA or half-commit fails closed. A finalize fault rolls back value,
head and intent together. No new table or root schema is introduced.

## C8.1 canonical material and knowledge handle

`CanonicalMaterialRead` is issued only by a PostgreSQL port that reads the
admitted C7 head and exact project value in one transaction. It binds project,
candidate/document identity, head revision/incarnation/closure, value
revision/incarnation/digest, snapshot/provenance and decoded structured payload.

`TypedKnowledgeCandidate` is a staged interpretation of that material under a
named formation profile. Formation is deterministic and grants no knowledge
adoption authority. `KnowledgeReadHandle` is issued by an exact registry only
after canonical readback; registry resolution requires the handle to be present
and byte-for-byte equal to the issued entry. Callers cannot derive a handle from
an arbitrary DTO. Reads are field-bounded, read-only and reject stale project,
revision, incarnation, provenance or content.

## C8.2 writing composition

Inputs are one or more issued knowledge reads, an ordered `CitationClosure` and
a `WritingCompositionSpec` with base revision/incarnation and byte/citation
ceilings. Output is canonical Markdown bytes for a staged
`ResearchArtifact(DRAFT)` plus exact provenance/citation closure and an artifact
digest. Citation identity, order, duplicate policy and removal are explicit.
Composition/staging never implies report admission, export or delivery.

Legacy card cache, scores, wall-clock retrieval metadata and UI convenience
fields are declared local projection loss. Citation/source/provenance closure is
not lossy.

## C8.3 report, admission and delivery separation

The operation family is split into four distinct contracts:

1. report composition/stage;
2. structural and citation verification plus canonical admission/readback;
3. export preparation producing an internal `DeliveryIntent` only;
4. separately approved internal delivery attempt and authoritative receipt.

The stage operation has no admission authority. Admission uses exact
VerificationBinding/CommitIntent/readback. Delivery requires an independent
approval/authority epoch and never accepts staged-only bytes. Outcome unknown is
readback-first and never repeats a non-idempotent attempt. External delivery is
explicitly rejected in this local milestone. Legacy inline HTML/CSV, broad model
fallback and synthetic source sentences are declared loss.

## C8.4 graph projection and C8.5 consumer

Graph projection consumes canonical knowledge/relation handles and a registered
loss profile. Each edge occurrence keeps a stable occurrence identity. Every
filter, truncation, redaction, casefold, duplicate collapse and omitted field is
enumerated. A content-addressed generation and PostgreSQL offset CAS make the
projection delete/rebuildable without control authority; failed generations do
not replace the active generation.

`GraphConsumerResult` is read-only and preserves source/projection provenance
and inherited loss. Relevance/reachability never creates EvidenceQualification,
claim support, source/adoption facts or synthetic evidence text. Missing
provenance returns a typed unavailable/empty result.

## File ownership

C7 handoff package may write only:

- `substrate/postgres/ingest_c7_candidate_values.py` (new);
- `substrate/postgres/ingest_c7_movement_admission.py`;
- `test_c7_movement_admission_postgres.py`.

C8 pure package may write only:

- `capabilities/c8_common.py`;
- `capabilities/c8_typed_knowledge.py`;
- `capabilities/c8_writing.py`;
- `capabilities/c8_report.py`;
- `capabilities/c8_graph.py`;
- `capabilities/c8_consumer.py` (new);
- C8 pure tests and legacy C8 oracle tests.

C8 effect package may add family-local PostgreSQL handlers/tests and may reuse
`ValueRepository`, `StagedArtifactRepository`, `AdmissionCoordinator`, delivery
gate/receipt stores and `ProjectionOffsetRepository`. It must not modify shared
AST/compiler/plan/reducer/RuntimeAssignment/work-item root schemas or frozen
files.

## Required acceptance

- C7 value/head/intent same-transaction exact commit, duplicate, crash, stale,
  ABA and readback tests;
- material read and issued-handle forgery/stale/project/no-write tests;
- knowledge formation plus citation/order/base/provenance writing tests;
- stage/admission/export/delivery type and authority separation, rejection and
  readback-first recovery tests;
- occurrence-preserving graph loss, offset CAS, generation rebuild and rollback;
- consumer no-evidence-synthesis and stale projection tests;
- legacy named observational compatibility with all intentional loss explicit;
- dependency/locality, exact source/test hashes and independent movement double
  review.

Movement dispositions remain blocked until these acceptance traces exist and
the regenerated matrix passes both independent completeness gates.
