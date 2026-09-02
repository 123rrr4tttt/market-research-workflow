# MRW Functorial Successor Migration Development Contract

Status: `REVIEW_DRAFT · NOT_FROZEN · DOES_NOT_AUTHORIZE_IMPLEMENTATION`

Version: `0.1.0-draft`

Date: `2026-08-30`

Repository: `market-research-workflow`

Topic root: `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration`

Proposed laboratory root: `experiments/functorial-kernel`

## 1. Purpose

This contract defines a structure-preserving successor migration for MRW. The migration shall recover and reproduce existing capabilities before moving them into a small compositional program kernel. It shall not begin as a whole-repository rewrite, a blind merge of all worktrees, a new control plane, or a vocabulary-only conversion of existing modules into category-theory names.

The target is a successor architecture in which:

- domain programs are inspectable before execution where inspection, replay, approval, or audit is required;
- effects are interpreted at explicit runtime boundaries;
- provider, store, scheduler, and execution implementations may be substituted only under named observational contracts;
- canonical identity, provenance, authority, failure, recovery, and ordered composition survive migration;
- each legacy capability is first reproduced through a bounded specimen, then replayed, shadow-compared, migrated, and only later retired;
- the laboratory grows into the successor through verified capability adoption rather than through a terminal big-bang rewrite.

This draft is not implementation authority. A separate task must review and freeze an exact contract copy and a content-addressed freeze manifest before source migration begins.

## 2. Authority and document topology

### 2.1 Document roles

The topic uses the following document roles:

| Path | Role | Mutability |
| --- | --- | --- |
| `00_functorial-successor-migration-development-contract.draft.md` | Source proposal written by the supervising task | Immutable after freeze input selection |
| `01_functorial-successor-migration-development-contract.md` | Independently reviewed frozen contract | Frozen |
| `02_functorial-successor-migration-development-contract.freeze.json` | Content-addressed contract/input manifest | Frozen |
| `03_functorial-successor-migration-development-progress.md` | Sole current development and lifecycle record | Mutable, append/update at stage boundaries |
| `04_functorial-successor-capability-ledger.json` | Machine-readable capability/parity/migration registry | Mutable through validated transitions |
| `05_functorial-successor-final-review.md` | Exact-candidate independent review | Immutable review artifact |

The progress document is the only mutable human-readable current-state source for this development. README files, dashboards, test output, branch names, worktree names, laboratory fixtures, and runtime receipts are projections or evidence; they may not independently declare completion.

### 2.2 Authority exclusions

This contract does not authorize:

- merging every worktree without prior inventory and classification;
- deleting, resetting, cleaning, rebasing, or overwriting user-owned worktree changes;
- enabling live network, production provider, external publication, destructive cleanup, or irreversible migration;
- transferring canonical write authority to the laboratory;
- treating runtime success, test success, schema validity, or a clean tree as semantic or migration completion;
- creating a new universal manager, truth store, dashboard controller, or mandatory workflow layer;
- claiming strict functoriality, naturality, commutativity, or algebraic effects without the corresponding objects, transformations, observations, and tests.

## 3. Predecessor constraints to preserve

The successor must preserve the following existing constraints unless an explicit frozen correction declares a semantic break:

1. `agent_batch` owns supplementation, item selection, `query_terms`, and target count.
2. `agent_batch` dispatch does not force the final `source_mode`.
3. `source_library.ItemResolver` selects the final source mode; source-library runtime selects the handler/provider.
4. `generic_web.*` remains internal-adapter-only unless a separate contract changes that boundary.
5. Source collection success does not imply Document persistence, indexing, graph adoption, report completion, or research completion.
6. API, UI, dashboard, report, readback, and automation evidence remain bounded projections rather than independent truth sources.
7. Provider configuration, credentials, permission, live availability, and result quality remain distinct observations.
8. Cancellation, timeout, retry, resource cleanup, network, filesystem, database, process, external Agent, and model calls remain explicit effects with named owners.
9. Project/tenant isolation, authenticated actor identity, approvals, and irreversible-action authority are not supplied by program composition itself.
10. Existing adapters, callers, envelopes, error families, recovery paths, and compatibility behavior remain available until their ledger entries reach `LEGACY_RETIRED`.

## 4. Migration correction: inventory before convergence

### 4.1 Worktree census gate

No merge or capability migration may begin before producing a worktree census with, for every reachable worktree or relevant branch:

- absolute worktree path;
- branch, `HEAD`, base commit, and tree identity;
- dirty-state summary and ownership warning;
- changed files grouped by capability;
- implementation, test, document, fixture, automation, and evidence classification;
- current validation state and exact commands when known;
- overlap/conflict set with other worktrees;
- disposition: `CURRENT_CANDIDATE`, `CAPABILITY_DONOR`, `PARITY_ORACLE`, `EXPERIMENTAL`, `SUPERSEDED`, `USER_OWNED_UNRESOLVED`, or `OUT_OF_SCOPE`.

Uniform mtime, checkout creation time, branch naming, or the presence of closure prose is not evidence of a substantive change.

### 4.2 Capability packets

Convergence occurs by capability packet, not by indiscriminate whole-worktree merge. A packet contains:

- source worktree/commit references;
- owned files;
- semantic responsibility;
- preserved observations;
- declared loss or incompatibility;
- dependency and conflict list;
- focused test command;
- rollback/revert boundary;
- reviewer disposition.

Packets are integrated in dependency order. Independent packets may be prepared in parallel only when file ownership, effects, authority, resource use, and observations do not interfere. Integration, canonical status updates, final manifests, and completion claims remain serialized.

### 4.3 Dirty worktree rule

Uncommitted user changes must not be staged, committed, moved, merged, rewritten, or deleted merely to prepare the successor. If a required capability exists only inside unresolved dirty changes, the capability ledger records `USER_OWNED_UNRESOLVED`, and dependent migration remains open while independent work continues.

## 5. Minimum generative architecture

### 5.1 Primitive families

The laboratory starts with the following smallest useful families:

- `Program[A]`: inspectable description of a bounded domain computation when inspection is required;
- `ValidatedProgram[A]`: program whose structural and authority-independent invariants passed validation;
- `Interpreter[F]`: realization boundary for one capability/effect family;
- `EffectOutcome[A]`: typed execution disposition plus result or failure information;
- `StructuralObservation`: named observation used for parity and substitution checks;
- `AuthorityContext`: explicit permission, project/tenant scope, grants, expiry/epoch, and actor identity;
- `CanonicalRef`: stable identity, content digest, revision, and non-reusable incarnation/generation where recreation is possible;
- `Projection[A, B]`: bounded derivation from canonical facts to API/UI/report/readback forms;
- `CapabilitySpec`: semantic contract, effects, interpreters, observations, laws, fixtures, and migration status for one capability.

These names are internal design handles. Public APIs retain domain language unless the abstraction improves comprehension.

### 5.2 Core operations

The kernel may provide only operations justified by concrete use:

- `map_value`: transform a result inside a stable context while preserving context identity and failure;
- `then_ordered`: ordered composition where the second program depends on or follows the first;
- `combine_independent`: statically combine known programs without implying runtime parallel safety;
- `traverse_ordered`: apply an effectful operation across a stable shape with explicit visit order and error semantics;
- `validate`: produce `ValidatedProgram` or typed incompatibility;
- `interpret`: realize a validated program through a chosen interpreter;
- `observe`: project an execution/canonical result into a named structural observation;
- `project`: derive a bounded read model from canonical facts;
- `fold_events`: derive state from admitted ordered events when a capability adopts event folding;
- `reconcile`: resolve an `OUTCOME_UNKNOWN` or stale anchor without automatic redispatch.

No operation is assumed commutative. Parallel execution requires a separate proof of effect independence, resource safety, authority compatibility, failure isolation, and observation-order tolerance.

## 6. Architecture views

### 6.1 Semantic movement

```text
ResearchIntent
  --plans--> DomainProgram
  --interprets--> StagedOutcome
  --qualifies/verifies--> AdoptionCandidate
  --admits--> CanonicalArtifact

Failure / Counterevidence / Changed Requirement
  --reopens--> DomainProgram or ResearchIntent
```

The arrows describe different relations. Planning is not execution; execution is not qualification; qualification is not canonical admission; reverse return is not an inverse or automatic cancellation.

### 6.2 Canonical state and projections

```text
Canonical Facts
  --projects--> API
  --projects--> UI
  --projects--> Report
  --projects--> Readback
  --rebuilds--> Derived Index / Dashboard

Runtime Receipt / Journal
  --supports reconciliation--> Canonical Admission Boundary
```

Runtime receipts, journals, caches, dashboards, and progress files do not become a second canonical source. A projection may be rebuilt or deleted without deleting the underlying domain object.

### 6.3 Runtime realization

```text
ValidatedProgram
  --interpret by Memory--> EffectOutcome
  --interpret by Legacy--> EffectOutcome
  --interpret by Shadow--> EffectOutcome
  --interpret by Production Adapter--> EffectOutcome
```

Different interpreters may differ in trace, latency, resource consumption, backend-local identifiers, and timing. Substitution claims are limited to named observations and failure/authority semantics.

### 6.4 Authority and qualification

```text
Program description
  --does not authorize--> effect execution

AuthorityContext + ValidatedProgram
  --permits bounded dispatch--> Effect Interpreter

StagedOutcome + Verification + Exact Content Binding
  --permits bounded adoption--> Canonical Store
```

The kernel does not grant authority. A stale executor, expired lease, wrong project/tenant, missing grant, changed content digest, changed canonical incarnation, or incompatible base revision must fail closed.

## 7. Laboratory layout

The first implementation target is a development-only laboratory:

```text
experiments/functorial-kernel/
  README.md
  pyproject.toml or package-local test configuration
  core/
    program.py
    validation.py
    outcome.py
    observation.py
    authority.py
    canonical.py
    projection.py
    laws.py
  interpreters/
    memory.py
    legacy.py
    shadow.py
  capabilities/
    workflow_graph/
    source_library/
    collect_runtime/
    agent_batch/
    agent_session/
    agent_core/
    ingest_index/
    writing_report_graph/
    api_frontend_projection/
  fixtures/
  parity/
  migration/
  tests/
```

The laboratory must not import production settings at module import time, connect to network or production stores by default, or become a production scheduler. Stable components move into existing production modules or a separately reviewed production kernel only after capability-level adoption.

## 8. Capability-cell protocol

Every capability receives one `CapabilitySpec`/ledger cell containing:

- `capability_id` and owner;
- legacy source paths and donor worktrees;
- semantic inputs/outputs;
- admitted transformations and ordered compositions;
- effects and failure owner;
- authority and project/tenant scope;
- canonical identity and projection rules;
- selected structural observation;
- deliberately lost or backend-local information;
- micro specimen;
- legacy replay fixture;
- shadow parity scenario;
- law/property tests;
- migration adapter and rollback path;
- current state and evidence refs.

### 8.1 Capability states

Allowed states are:

```text
INVENTORIED
SPECIMEN_REPRODUCED
LEGACY_REPLAY_GREEN
DUAL_INTERPRETER_GREEN
SHADOW_PARITY
MIGRATED
LEGACY_RETIRED
BLOCKED_BOUNDED
INVALIDATED
```

A state change must name its evidence and exact code/tree identity. `BLOCKED_BOUNDED` records a known finite gap and does not block independent cells. `INVALIDATED` reopens a previously passing cell after a counterexample or drift finding.

### 8.2 Three mandatory reproduction levels

#### Level A: micro specimen

The smallest realistic example establishes domain objects, transformations, failures, and observations. A toy that omits the capability's defining authority, effect, or failure boundary is insufficient.

#### Level B: legacy trace replay

A deterministic legacy scenario is represented by the new program but interpreted through the legacy capability. It must preserve selected identities, parameters, event order, failure family, authority, provenance, and external envelope.

#### Level C: shadow parity

Legacy and successor interpretations run against the same bounded input. They are compared through the named `StructuralObservation`; byte equality is required only where the contract declares exact byte preservation.

Migration begins only after all three levels pass. Retirement begins only after production-facing callers, recovery, rollback, and observability have moved.

## 9. Capability migration order

### Foundation F0: census, ledger, kernel, and law harness

Deliver:

- worktree census;
- capability ledger schema and initial cells;
- laboratory scaffold;
- core program/outcome/observation/authority/canonical types;
- deterministic seed/replay support for property tests;
- no-live/no-canonical-write guard.

Gate:

- no production behavior change;
- all donor and user-owned unresolved states visible;
- kernel tests run without network, DB, Redis, Elasticsearch, Celery, or Docker.

### Capability C1: Workflow Graph

Problem shape: inspectable program before execution plus validated compilation.

Must reproduce:

- DSL parse/validate/compile;
- node type/config and ordered dependency identity;
- executor selection;
- node failure and run termination;
- memory and SQL store observations where safe;
- reload/replay of a compiled program.

Required correction:

- compiled identity binds normalized node type/config and all execution-semantic fields;
- runtime consumes `ValidatedProgram` or returns typed validation failure;
- invalid raw graphs cannot bypass validation into compilation/execution.

### Capability C2: Source Library

Problem shape: provider-neutral program with four bounded interpreters.

Must reproduce:

- item/channel merge and taxonomy normalization;
- `ExecutionRequest` construction;
- `protocol_search`, `provider_harvest`, `site_search`, and `url_execution`;
- terminal output and legacy compatibility projection;
- internal-only generic-web boundary;
- project-scoped credential and handler behavior.

Required correction:

- one normalization/taxonomy source;
- `source_mode -> interpreter` registry;
- `agent_batch` ownership boundary preserved;
- collection outcome remains distinct from downstream persistence/adoption.

### Capability C3: Collect Runtime

Problem shape: stable request shape, effectful traversal, and pure result fold.

Must reproduce:

- `CollectRequest`, adapter registry, and `CollectResult`;
- legacy/workflow route selection;
- auto-batch split/map/fold;
- links, counts, errors, provider receipts, and display metadata.

Required correction:

- pure `BatchPlan` creation;
- pure `ResultFold` with singleton identity and associative selected observations;
- serial/parallel compatibility tests without assuming effect commutativity.

### Capability C4: Agent Batch

Problem shape: inspectable tasks plus data-dependent bounded retry.

Must reproduce:

- plan normalization;
- source supplementation;
- bounded branching;
- dispatch receipt;
- critic and retry decisions;
- idempotency and round identity;
- existing API response shape.

Required correction:

- tagged `RetryAction` and pure reducer;
- retry budget monotonicity;
- explicit ordered rewrite composition;
- effectful submit separated from pure transition;
- final `source_mode` remains source-library-owned.

### Capability C5: Agent Session, Task, Event, and Readback

Problem shape: explicit state machine, durable events, recovery, and bounded projections.

Must reproduce:

- claim/heartbeat/release;
- dependency and approval behavior;
- retry/reopen identity;
- failure package provenance;
- workflow/agent-batch status mapping;
- Celery/DB readback projections.

Required correction:

- pure transition reducer;
- illegal transitions fail closed;
- final states absorb ordinary commands unless a typed retry/reopen creates a new epoch;
- observed events, derived events, and canonical completion facts are distinguishable;
- `OUTCOME_UNKNOWN` and reconciliation prohibit unsafe redispatch;
- event fold and snapshot selected observations agree.

### Capability C6: AgentCore and provider/tool interpretation

Problem shape: capability interface with multiple provider realizations.

Must reproduce:

- request/project/actor identity;
- permission and routing decision;
- tool schema, call, result, and ordered event trace;
- redaction projection;
- fake/repo-local/selected-live evidence classes without conflation.

Required correction:

- provider substitution claims remain observational compatibility unless stronger laws are established;
- credentials/network/timeout/cancellation/redaction remain interpreter effects;
- no historical live receipt is treated as current provider readiness.

### Capability C7: Ingest, persistence, indexing, and graph handoff

Problem shape: ordered effects with distinct adoption boundaries.

Must reproduce:

- submission/idempotency;
- fetch/normalize/candidate creation;
- persistence transaction;
- index/graph handoff;
- partial failure, retry, and rollback observations.

Required correction:

- staged collection does not imply downstream adoption;
- exact content digest and ordered event/payload identity bind admission;
- replay rebuilds state without repeating non-idempotent effects.

### Capability C8: Typed knowledge, writing, report, and graph consumers

Problem shape: bounded projections and composable consumers.

Must reproduce:

- stable read handles and provenance;
- demand-read before synthesis where required;
- writing/report artifacts and export boundaries;
- graph context adapter behavior;
- declared lossy compression/redaction.

Required correction:

- projections cannot manufacture source/adoption facts;
- semantic quality remains a reasoned/user/domain judgment, not a generic law score;
- compression preserves canonical identity and read handles even when content is lossy.

### Capability C9: API and frontend projections

Problem shape: multiple bounded views over canonical state.

Must reproduce:

- `status/data/error/meta` envelopes;
- project/trace identity;
- task/run/source/report/workflow read models;
- failure and unavailable states;
- frontend compatibility during migration.

Required correction:

- projections derive from canonical or explicitly labeled runtime observations;
- UI/readback does not feed inferred completion back into control;
- missing or ambiguous bindings render honestly.

### Integration I1: successor assembly

After C1-C9 reach at least `SHADOW_PARITY`, integrate the successor path through adapters while legacy remains available. Do not retire a legacy capability merely because its specimen passes.

### Closure I2: authority transfer and legacy retirement

Authority transfer requires a separate exact-candidate review. The closure may move a capability to `LEGACY_RETIRED` only when:

- all callers have migrated or have a reviewed compatibility adapter;
- recovery and rollback have been exercised;
- canonical identity and projection rebuild pass;
- no unresolved `USER_OWNED_UNRESOLVED`, P0, or dependent P1 remains;
- the capability ledger, progress record, Git commit/tree, and evidence digests agree.

## 10. Law and property-test matrix

Each law is opt-in by semantic claim. The kernel must not impose irrelevant laws.

| Law/check | Applies when | Minimum falsifier |
| --- | --- | --- |
| Identity | A neutral program/transform is defined | neutral mapping changes selected observation |
| Ordered composition | Sequential composition is defined | compiled/interpreted composite differs from ordered component composition |
| Associativity | Three compatible compositions are defined | parenthesization changes selected observation |
| Normalization idempotence | Normalizer is declared canonical | second normalization changes canonical form |
| Failure preservation | Adapter/interpreter substitution is claimed | failure family/owner disappears or becomes success |
| Authority preservation | Execution/adoption is mapped | weaker grant gains a stronger effect or claim ceiling |
| Projection rebuild | Incremental and full rebuild paths are claimed equivalent | canonical replay differs from current projection observation |
| Recovery equivalence | Restart continuation is supported | committed prefix duplicates or stale prefix is adopted |
| No duplicate effect | Retry/replay of external effects is supported | effect count increases without safe idempotency proof |
| Content binding | Verification/admission/commit is supported | payload/content mutation is admitted under unchanged identity |
| Backend compatibility | Two interpreters claim substitution | named structural observations diverge without declared loss |
| Traversal/fold shape | Stable batch shape is rebuilt | items reorder/disappear or errors vanish contrary to contract |
| Monotonic budget | Retry/qualification budget is defined | transition increases spent/remaining budget improperly |

Property tests must record reproducible seeds and make the smallest failing case inspectable. Example tests remain necessary for domain semantics and user-facing behavior.

## 11. Effect and recovery contract

Every effectful interpreter returns one of:

```text
NOT_STARTED
IN_FLIGHT
SUCCEEDED
FAILED
OUTCOME_UNKNOWN
```

Rules:

1. Missing receipt does not imply `NOT_STARTED`.
2. `OUTCOME_UNKNOWN` requires reconciliation or authoritative external readback.
3. Automatic retry requires an idempotency identity or proof that the effect did not start.
4. Replay/projector rebuild may not re-execute network, provider, process, filesystem, DB mutation, Agent, publication, or other non-idempotent effects.
5. Cancellation, timeout, cleanup, and lease loss have explicit owners and do not erase the effect outcome.
6. A stale executor cannot publish an admissible result.
7. Canonical recreation uses a non-reusable incarnation/generation so an old prefix cannot enter a new project through an ABA-equivalent revision/digest/fence image.

## 12. Compatibility and migration adapters

Adapters must declare:

- source and target representation;
- preserved identities and observations;
- intentionally changed or lost information;
- total, partial, or effectful behavior;
- failure and authority mapping;
- versioning and removal condition.

Compatibility adapters may not contain hidden business routing, silently elevate authority, or treat legacy read models as canonical facts. If existing semantics cannot be preserved, the adapter is labeled `LOSSY` or `SEMANTIC_BREAK`, and migration requires an explicit review.

## 13. Development workflow and progress discipline

### 13.1 Goal

The implementing task must create one durable Goal for the complete frozen contract family. It may not mark the Goal complete merely because the current capability or final edited file is green.

### 13.2 Progress record

The progress file must contain one top `Current claim identity` block with:

- Goal/task identity and status;
- repository branch/commit/tree and dirty-state boundary;
- frozen contract and manifest digests;
- current stage and capability-cell counts;
- accepted candidate/closure identities or explicit `null`;
- latest independent review disposition;
- live/canonical authority state;
- current blockers and next action.

Historical sections may retain earlier claims but must not conflict with the top block. Every invalidation updates the top block before adding history.

### 13.3 Stage-boundary updates

Update progress at:

- contract freeze;
- worktree census completion;
- Foundation F0 completion;
- each capability entering `LEGACY_REPLAY_GREEN`, `SHADOW_PARITY`, `MIGRATED`, or `INVALIDATED`;
- integration candidate creation;
- independent review;
- closure or renewed correction.

Do not rewrite progress after every small edit.

## 14. Validation levels

### Level 0: document and manifest

- paired fence and link checks;
- JSON parse/schema checks;
- SHA-256 freeze-input match;
- `git diff --check` for owned files.

### Level 1: laboratory

- pure kernel unit tests;
- law/property tests with seeds;
- no-network/no-production-store guard;
- micro specimen tests.

### Level 2: legacy replay

- focused legacy tests;
- exact fixture/readback provenance;
- no live service requirement unless explicitly authorized;
- old/new selected observations compared.

### Level 3: shadow integration

- dual interpretation on bounded inputs;
- failure, cancellation, timeout, and recovery injection;
- no duplicate external effects;
- projection rebuild and content mutation counterexamples.

### Level 4: repository integration

- module-focused suites;
- contract/integration suites;
- lint/typecheck/build as applicable;
- architecture-boundary and import checks;
- current tree/report binding;
- clean or explicitly bounded dirty-state review.

### Level 5: independent exact-candidate review

The reviewer reopens the exact candidate tree, freeze manifests, capability ledger, progress record, and generated evidence. It must replay named P0/P1 counterexamples rather than accepting aggregate green output.

## 15. Required acceptance scenarios

The frozen contract must retain at least these scenarios:

1. Add a new same-form source/provider without editing all previous providers.
2. Change a workflow node type/config and observe a changed compiled program identity.
3. Attempt to execute an invalid raw program and receive a typed failure before effects.
4. Run a source-library item through all four modes and preserve terminal identity/failure observations.
5. Compare serial and parallel collect realization without reordering or erasing failures.
6. Apply ordered retry rewrites and prove retry budget cannot increase.
7. Crash after external dispatch but before receipt publication and obtain `OUTCOME_UNKNOWN` without redispatch.
8. Delete and recreate canonical state with the same visible revision/digest/fence and reject the old prefix through incarnation mismatch.
9. Mutate any admitted content/event payload byte and reject commit under the old verification binding.
10. Delete a read model/dashboard and rebuild it from canonical facts without semantic loss beyond declared projection loss.
11. Replace memory/legacy/shadow interpreters and compare selected observations, failures, authority, and provenance.
12. Remove the manager/dashboard projection and show that the domain object and executable capability still exist.

## 16. Anti-pattern rejection gate

Reject or correct an implementation when:

- all worktrees were merged without a capability census;
- the laboratory becomes a second application or truth source;
- a `FunctorManager`, universal context, or central semantic router is introduced;
- every module is wrapped in one generic Program despite different problem shapes;
- a mapping is called natural merely because two adapters share a method name;
- parallel eligibility is treated as commutativity;
- a runtime receipt, progress row, fixture, or dashboard status becomes canonical completion;
- the successor silently removes legacy behavior, failure modes, or recovery paths;
- one micro specimen is used to authorize migration without legacy replay and shadow parity;
- property tests are weakened to make green evidence rather than retaining the counterexample;
- semantic quality or source quality is replaced by schema completeness, embedding similarity, or model consensus;
- completion is inferred from aggregate tests without exact tree/evidence binding.

## 17. Freeze protocol

The freezing task must:

1. read this draft and current repository evidence;
2. verify the current branch/HEAD/worktree boundary without modifying unrelated files;
3. perform an independent architecture review for identity, authority, effect, recovery, and capability preservation;
4. correct only bounded contract defects, recording changes from this draft;
5. write `01_functorial-successor-migration-development-contract.md` with `Status: FROZEN`;
6. write `02_functorial-successor-migration-development-contract.freeze.json` containing:
   - schema/version;
   - repository and topic identity;
   - source draft path/digest;
   - frozen contract path/digest;
   - normative input paths/digests;
   - baseline branch/commit/tree;
   - authority exclusions;
   - capability order and required scenarios;
   - reviewer task identity and disposition;
7. verify all manifest hashes;
8. create the progress and capability-ledger files;
9. only then create/start the implementation Goal.

If the review cannot establish a safe baseline because required dirty changes are unowned or conflicting, it records a bounded blocker and may still prepare the laboratory scaffold only if that work has no dependency on the blocked changes.

## 18. Completion contract

The implementing task may close its Goal only when:

- the frozen contract and manifest remain hash-valid;
- the worktree census is complete and no unresolved donor capability has been silently dropped;
- F0 and C1-C9 satisfy their required state, or an explicitly frozen scope reduction says otherwise;
- every migrated capability passed micro specimen, legacy replay, and shadow parity;
- current callers, recovery, rollback, and projections are covered;
- capability ledger IDs and evidence refs are unique and parseable;
- progress, ledger, Git commit/tree, and report identities agree;
- named content-mutation, recovery, ABA, validation-bypass, failure-preservation, and no-duplicate-effect counterexamples pass;
- a fresh independent exact-candidate review reports no open P0 or dependent P1;
- no live/canonical authority beyond the frozen scope was activated;
- the implementing task sends the supervising task a completion report containing result, changed files, verification status, risks, exact candidate identity, and review request.

Closure remains a code/migration statement. It does not imply market-research quality, source truth, production readiness, provider availability, human acceptance, or authorization for live cutover unless separately proven and authorized.

## 19. Supervising review and correction loop

After implementation Goal completion, the supervising task must independently audit:

- contract and freeze integrity;
- worktree census and capability-donor coverage;
- current source rather than progress prose alone;
- program identity and validation boundaries;
- effect ownership and `OUTCOME_UNKNOWN` handling;
- canonical single-truth and projection rebuild;
- capability-level parity and preserved failures;
- exact candidate/evidence attribution;
- completion wording and authority ceiling.

If findings exist:

- P0 or semantic-identity/recovery/authority failure invalidates completion;
- dependent P1 blocks affected migration/retirement while independent cells may remain accepted;
- P2 documentation/projection drift requires correction but does not erase unrelated verified code;
- a new correction task receives the exact findings, frozen inputs, ownership, tests, and completion criteria;
- historical failed candidates and counterexamples remain preserved as negative-development evidence.

## 20. Draft handoff

The next authorized action is an independent freezing task. Until its freeze manifest is created and verified, no implementation, worktree convergence, source migration, authority transfer, or legacy retirement is authorized by this document.
