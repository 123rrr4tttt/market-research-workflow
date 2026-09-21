# MRW Functorial Project Review (v1)

- Status: `FROZEN_EVIDENCE_V1 · NOT_NORMATIVE · NOT_A_PROMOTION_GATE`
- Date: `2026-09-04`
- Project root: `/Users/wangyiliang/market-research-workflow`
- Review basis: current checkout files plus the latest local functorial kit checkout
- Remediation plan: `docs/governance/functorial-structural-debt-remediation-plan.v1.md`
- Kit checkout: `/Users/wangyiliang/Desktop/functorial-kit`
- Kit observed commit: `785ff25e201c9eae84c862e68e786bc975e7a800`
- Kit version observed by file: `Functorial Kit — cross-language conventions (v0)`

## 1. Evidence boundary

This is a source-grounded review, not a current test run and not an authority claim.

Observed checkout state:

```text
cwd: /Users/wangyiliang/market-research-workflow
branch: codex/all-lines-donor-cutover
worktree: heavily dirty with existing user/migration-owned changes
```

Evidence classes used here:

- `OBSERVED`: directly read from the current checkout in this review.
- `HISTORICAL`: recorded by an existing artifact; current bytes were not rerun.
- `UNEXECUTED`: no current execution was performed.
- `NON_CLAIM`: no production, live-provider, cutover, authority-transfer, or canonical-write completion is claimed.

Current review executions:

- MRW pytest: `UNEXECUTED`
- MRW Playwright: `UNEXECUTED`
- MRW PostgreSQL fixtures: `UNEXECUTED`
- MRW movement generator/checker commands: `UNEXECUTED`
- MRW functorial-kit full Python architecture ratchet: `VERIFIED`
- Latest kit self-test: `VERIFIED`

Kit self-test command:

```text
uv run --no-sync --with pytest --with hypothesis --project /Users/wangyiliang/Desktop/functorial-kit/python python -m pytest -q /Users/wangyiliang/Desktop/functorial-kit/python/tests
```

Observed result:

```text
40 passed in 4.23s
```

This verifies the independent Python kit implementation. It does not verify MRW business surfaces.

MRW kit bootstrap tests were also run after initialization:

```text
PYTHONPATH=/Users/wangyiliang/market-research-workflow/src \
uv run --no-sync \
  --with /Users/wangyiliang/Desktop/functorial-kit/python \
  --with pytest --with hypothesis \
  python -m pytest -q -p no:cacheprovider \
  tests/test_architecture.py \
  tests/test_counter_laws.py \
  tests/test_example_codec_laws.py
```

Observed result:

```text
14 passed in 2.22s
```

The initial bootstrap run verified the generated kit config, registries, sketch, example port, law suite, and seven architecture gates.

A full Python-surface run was then added. The current `functorial-kit.json` covers:

- backend app source except the API shell directory, which is declared as shell;
- backend scripts;
- root `scripts/`;
- generated kit core/shell;
- backend tests and root tests.

Observed full-scan input:

```text
source_files=994
test_files=519
```

Observed raw architecture findings before the ratchet:

```text
import-direction=106
no-throw-in-core=5278
registry-complete=0
one-representation=260 reports
fakes-run-laws=0
derived-marked=521
sketch-valid=0
```

The `one-representation` findings are report-level duplicate-helper notices, not fail-level duplicate vocabularies/codecs. The first three fail-level counts were reconciled to the exact configured path set and recorded in `arch-baseline.json` as 1,191 unique fail keys.

Full kit validation command:

```text
PYTHONPATH=/Users/wangyiliang/market-research-workflow/src \
uv run --no-sync \
  --with /Users/wangyiliang/Desktop/functorial-kit/python \
  --with pytest --with hypothesis \
  python -m pytest -q -p no:cacheprovider \
  tests/test_architecture.py \
  tests/test_counter_laws.py \
  tests/test_example_codec_laws.py
```

Observed result:

```text
274 passed in 1.10s
```

This result means the ratchet passes: existing fail-level debt is recorded, no new architecture violation is introduced, and no baseline entry is stale. It does not mean the 1,191 recorded violations are fixed. It also does not run MRW backend business tests, PostgreSQL fixtures, frontend tests, or provider/live paths.

Historical test records were observed in
`development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence/P4PgEvidenceRerun.2026-09-02.md`,
including local/disposable C7/C8/C9 suites and teardown evidence. Those records are `HISTORICAL`, not current `VERIFIED` results.

## 2. Review method

The review applies the latest functorial kernel and kit:

```text
recognize -> sketch -> realize -> witness -> register
```

The kernel treats the implementation as a structure-preserving map:

```text
F : Domain Movements -> Implementation Contracts / Programs / Runtime Effects
```

The project now has a root `functorial-kit.json` initialized from the Python kit and expanded to the full MRW Python source/test surfaces described above. The independent Python kit implementation was separately self-tested as recorded above.

The latest kit v0 was nevertheless used as the mechanical review standard:

- closed vocabulary/failure family;
- codec and discriminant registry;
- non-authoritative derived marker;
- anchor and drift;
- ordered fold;
- shared port law suites;
- seven architecture gates.

Kit conventions observed at `/Users/wangyiliang/Desktop/functorial-kit/CONVENTIONS.md`.

## 3. Recognized surfaces

### 3.1 Typed successor runtime

`OBSERVED`: MRW has a substantial typed successor surface under:

```text
main/backend/app/successor_runtime/**
main/backend/app/successor_migration/**
main/backend/tests/successor_runtime/**
```

Its controlling semantic object for C7 is:

```text
RawSnapshot
  -> NormalizedIngestEnvelope
  -> DigestionDecision
  -> one_of { Extract, Chunk, Summarize, PassThrough }
  -> StructuredMaterialCandidate
  -> C7.2 Verify | Admit
  -> C7.3 Index | Graph Projection
  -> C7.4 Recovery
```

Source:
`development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/20_functorial-successor-semantic-movement-completeness-amendment.v1.md`.

This surface is the semantic authority for the migration family. It must not be represented by the lightweight agent-core projection merely because both use the word `functorial`.

### 3.2 Lightweight agent-core functorial projection

`OBSERVED`: the separate surface under:

```text
main/backend/app/services/agent_core/functorial/**
main/backend/app/api/functorial.py
```

is a development catalog/projection surface, not a canonical successor authority.

Observed implementation includes:

- `OperatorSpec`;
- `MotifSpec`;
- `WorkflowSpec`;
- JSONL-backed `FunctorialCatalog`;
- HTTP projection routes;
- direct AgentCore tool execution in `run_workflow`.

It should remain labeled `PROJECTION_ONLY` until its representation, writer, failure family, and execution semantics pass a C3 gate.

### 3.3 Governance surfaces

`OBSERVED`: active and proposal-level governance coexist:

- Active movement standard:
  `docs/governance/semantic-movement-completeness-standard.md`
- Candidate global governance proposal:
  `docs/governance/project-development-and-governance-standard.proposal.v1.md`
- Frozen migration authority:
  `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/02_functorial-successor-migration-development-contract.freeze.json`

The proposal is `PROPOSAL_ONLY`; it does not amend the frozen v2.3 family.

## 4. Kit review matrix

| Kit concern | MRW observed state | Review result |
| --- | --- | --- |
| `functorial-kit.json` | Root manifest initialized and expanded to MRW Python source/test surfaces with an architecture baseline. | Full Python ratchet adopted; frontend and non-Python surfaces remain outside kit scope. |
| Registries | Kit-format `codecs.json`, `vocabularies.json`, `failures.json`, and `ports.json` exist with one example Counter port. | Registries are valid; real MRW codecs/vocabularies/failures are not yet registered. |
| `sketches.json` | Root kit sketch registry initialized with the Counter capability-interface example. | Existing semantic movement designs are not yet kit-validated sketches. |
| One representation | Typed successor language and lightweight agent-core projection both express operator/workflow semantics. | Potential second representation; explicit adapter or bounded projection declaration required. |
| Closed vocabulary | Movement dispositions are closed. Operator `risk` is a free string in `OperatorSpec`; HTTP and lightweight services use multiple exception/string mappings. | Strong in movement layer; weak in lightweight projection. |
| Closed failure family | C7 has extensive typed failure/reverse/recovery tests. `run_workflow` collapses failures to `ok: bool` and ad hoc text. | Strong in successor C7; unacceptable for a lawful lightweight interface. |
| Equation witness | C7 parity/one-of/digest tests are named and traceable. Motif identity/associativity implementation exists, but no direct focused test for the lightweight surface was observed. | Testable claims without current test IDs remain heuristic for that surface. |
| Derived projection marker | Typed migration authority ceilings are explicit. `FunctorialCatalog` calls itself a single truth source despite being a mutable JSONL projection. | Derived surfaces must be explicitly non-authoritative. |
| Single writer | Migration authority exclusions are explicit. The lightweight JSONL catalog has generic open `upsert` calls and import-time seeding. | Lightweight surface lacks a domain-specific single writer. |
| Shared law suites | C7 family has shared generator/checker/evidence patterns. Lightweight operator/motif/workflow surface does not observe a shared port-law suite. | Kit adoption should start with bounded successor slices, not broad repository rewrite. |
| Architecture gates | The seven kit gates pass as a full Python ratchet with 1,191 recorded fail keys and 260 report notices. | New violations are blocked; recorded debt requires staged reduction. |

## 5. Findings

### F1. C7 semantic movement is strong but remains local-scoped

`OBSERVED`: the current capability ledger records:

- C7 movement rows: 20;
- `UNASSIGNED_BLOCKER = 0`;
- C7 double review pass;
- legacy four-mode decision parity present with declared provider loss;
- production canonical write, live provider, external delivery, cutover, and authority transfer all false.

Source:
`development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/04_functorial-successor-capability-ledger.json`.

This supports local movement closure only. It is not live-provider parity, production authority, cutover, or candidate authority.

Disposition: `OBSERVED_LOCAL_BOUNDARY`.

### F2. Lightweight execution does not preserve declared data movement

`OBSERVED`: `run_workflow` iterates operators in order but passes the same original `inputs` to every step. It does not route the prior step output into the next step.

Source:
`main/backend/app/services/agent_core/functorial/run.py`.

Operational consequence: it preserves scheduling order, not the ordered composition semantics implied by Motif/Workflow.

Law status:

```text
[ORDERED_COMPOSITION]: NOT_WITNESSED_FOR_RUNTIME_DATA_FLOW
```

Disposition: `BLOCKING_FOR_LAWFUL_COMPOSITION_CLAIM`.

### F3. Workflow has two executable interpretations

`OBSERVED`: `WorkflowSpec` stores an embedded program projection, while `run_workflow` reparses workflow refs and motif composition instead of interpreting that stored program.

Sources:

- `main/backend/app/services/agent_core/functorial/workflow.py`
- `main/backend/app/services/agent_core/functorial/run.py`

Operational consequence: the validated program and executed program can drift.

Disposition: `SECOND_REPRESENTATION_RISK`.

### F4. Operator schema projection can override the existing schema authority

`OBSERVED`: the lightweight projection derives `OperatorSpec` from existing tool definitions but replaces output schemas with a static map or fallback rather than deriving from the existing `CoreToolSpec` schema authority.

Source:
`main/backend/app/services/agent_core/functorial/operator.py`.

Disposition: `KNOWN_COPY_REQUIRED`; converge to one schema source or record a typed deviation.

### F5. Catalog authority is not a production-grade writer

`OBSERVED`:

- import creates `.data/functorial`;
- import seeds operators;
- API and services write through generic catalog `upsert`;
- every upsert appends JSONL and later reads use last-line-wins;
- locking is process-local.

Sources:

- `main/backend/app/services/agent_core/functorial/registry.py`
- `main/backend/app/services/agent_core/functorial/catalog.py`

This is not a cross-process canonical authority and should not be described as a single truth source without a version policy and durable readback contract.

Disposition: `PROJECTION_ONLY`.

### F6. Lightweight failure family is not closed

`OBSERVED`: lightweight services use `TypeError`, `ValueError`, `KeyError`, and strings such as `workflow not found` / `not registered`. HTTP error mapping also performs substring matching on exception text.

Sources:

- `main/backend/app/services/agent_core/functorial/run.py`
- `main/backend/app/api/functorial.py`
- `main/backend/app/services/agent_core/functorial/motif.py`
- `main/backend/app/services/agent_core/functorial/workflow.py`

Underlying AgentCore results can carry structured status/error/retry information, but the workflow wrapper collapses this to `ok`.

Disposition: `INTERFACE_QUARTET_INCOMPLETE`.

### F7. Kit full Python ratchet is initialized; registered semantic coverage remains partial

`OBSERVED`: root `functorial-kit.json`, registries, `sketches.json`, generated source, architecture baseline, and focused tests were initialized from the Python kit. The full Python ratchet passes, but registries contain only the scaffold Counter port; real MRW codecs, vocabularies, failure families, and ports remain unregistered.

Recommended expansion boundary:

1. Start with a narrow typed successor slice, not the whole repository.
2. Add kit-format registries only for that slice.
3. Seed `sketches.json` from already witnessed C7 shapes.
4. Add an architecture baseline for existing violations.
5. Wire the seven gates into the ordinary focused test command.
6. Require each new violation class to decrease or be explicitly owned.
7. Do not copy kit primitives into MRW.

Disposition: `KIT_FULL_PYTHON_RATCHET_VERIFIED_SEMANTIC_REGISTRATION_PENDING`.

## 6. Witness inventory

### Current observed witnesses

These are source/test declarations observed during review, not current executions.

- `test_four_mode_legacy_and_target_decision_parity`
  - claim: legacy and target digestion decisions agree on four modes;
  - source: `main/backend/tests/successor_runtime/test_c7_movement_decision_parity.py`.

- `test_exactly_one_target_branch_executes_per_trace`
  - claim: C7 alternatives execute exactly one selected branch;
  - source: same file.

- `test_candidate_digests_bind_snapshot_decision_and_branch`
  - claim: candidate identity binds snapshot, envelope, decision, payload, provenance, and branch;
  - source: same file.

- `test_design_has_twenty_unique_rows_and_zero_blockers`
  - claim: C7 design has twenty unique movements and zero unassigned blockers;
  - source: `main/backend/tests/successor_runtime/test_c7_semantic_movement_completeness.py`.

- `test_matrix_contract_topology_and_authority_ceiling`
  - claim: one-of topology is declared, commutativity is not claimed, promotion/candidate false, and authority ceiling false;
  - source: same file.

### Missing or unbound witnesses

- Lightweight workflow data handoff.
- Lightweight stored-program interpreter equivalence.
- Lightweight closed failure-family mapping.
- Lightweight catalog cross-process/version policy.
- Lightweight operator schema deviation policy.
- Kit validation of real MRW semantic movement sketches and production paths.

Any corresponding claim remains heuristic until those witnesses exist.

## 7. Required next actions

### A. Immediate representation correction

Classify the lightweight surface explicitly as `PROJECTION_ONLY`. Do not use it for promotion, candidate, canonical-write, cutover, or semantic-completeness claims.

### B. C3 repair package

Before expanding the lightweight surface:

1. choose one program representation and one interpreter;
2. pass prior output into dependent steps or declare independent inputs as a separate shape;
3. preserve typed AgentCore failure/status/retry information;
4. close risk and failure vocabularies;
5. derive operator schemas from the existing authority or record deviations;
6. replace generic catalog writes with domain-specific writers and version policy;
7. add direct focused tests for all changed laws.

### C. Registered semantic expansion

The Python kit is initialized as a full Python ratchet. In a dedicated implementation task, register one real successor slice's codecs, vocabularies, failure families, ports, and sketches, then reduce its baseline entries. Do not attempt semantic registration for the entire repository in one pass.

### D. Governance linkage

Use `docs/governance/semantic-movement-completeness-standard.md` as the active movement baseline. Treat the proposal v1.1 as candidate governance until accepted. Do not create a third competing standard.

## 8. Review verdict

The typed successor migration has a credible semantic spine: named objects, ordered movement, one-of decision structure, declared loss, typed failure/recovery evidence, explicit authority ceilings, and independent review artifacts.

The lightweight agent-core functorial surface is not yet a lawful implementation of the same structure. It is useful as a development projection but currently has duplicate representations, incomplete failure ownership, no shared law suite for its exposed composition semantics, and no kit-controlled architecture gate.

Therefore:

```text
successor migration: OBSERVED_STRONG_LOCAL_SEMANTIC_BOUNDARY
lightweight projection: PROJECTION_ONLY_REQUIRES_C3_REPAIR
functorial-kit adoption: FULL_PYTHON_RATCHET_VERIFIED_SEMANTIC_REGISTRATION_PENDING
promotion/cutover/production authority: NON_CLAIM
```
