# MRW Functorial Structural Debt Remediation Plan (v1)

- Status: `FROZEN_FOR_IMPLEMENTATION_V1 · NOT_NORMATIVE · DOES_NOT_AMEND_EXISTING_FREEZE`
- Date: `2026-09-04`
- Basis: `functorial-project-review-2026-09-04.v1.md`
- Mechanical gate: `functorial-kit.json` + `arch-baseline.json`
- Current baseline: 1,191 fail keys + 260 report notices
- Authority ceiling: no production write, live provider, external delivery, cutover, authority transfer, or promotion is authorized by this plan.
- Mutable execution state is tracked only in `functorial-structural-debt-remediation-progress.v1.md`; do not edit this frozen plan to record progress.

## 1. Prioritization principle

Priority is not raw violation count. A debt ranks higher when it can:

1. create a second canonical representation;
2. hide the boundary between fact, projection, plan, and authority;
3. make failure or recovery semantics disappear;
4. allow backend/provider substitution without a shared law witness;
5. force every new capability to modify old subjects or copy a full stack.

The large `raise` count is therefore not first. Many existing exceptions are legitimate shell or validation behavior. They become harmful only when they sit in a declared pure core, lack a closed failure family, or obscure recovery ownership.

## 2. Current debt composition

Observed full Python scan:

```text
source_files=994
test_files=519
fail_baseline_keys=1191
report_notices=260
```

Fail composition:

| Gate | Raw findings | Baseline keys | Meaning |
| --- | ---: | ---: | --- |
| `no-throw-in-core` | 5,270 | 568 | Core paths directly raise exceptions. |
| `derived-marked` | 521 | 521 | `build*` / `plan*` / `preflight*` / `simulate*` outputs are not marked non-authoritative. |
| `import-direction` | 105 | 102 | Core imports concrete adapter/shell implementations. |

Report composition:

- 260 duplicate-helper notices;
- highest-signal names include `parse_args`, `build_check`, `_read_text`, `utc_now`, `_repo_root`, `_require`, `build_report`, `_canonical_json`, and `load_json`;
- `main` is mostly CLI noise and is not a priority.

Existing zero findings do not imply semantic completeness:

- `registry-complete = 0` because real MRW codecs/vocabularies/failures/ports are not registered yet;
- `fakes-run-laws = 0` because only the generated `Counter` example is registered;
- `sketch-valid = 0` because only the generated example sketch exists.

## 3. Repair priorities

| Priority | Debt family | Why it ranks here | Primary scope |
| --- | --- | --- | --- |
| P0 | Representation and semantic registration gap | Without canonical object registration, later repairs can add another representation instead of converging F. | C7 chain first, then C8/C9. |
| P0 | Lightweight projection authority ambiguity | A named `functorial` surface can be mistaken for successor authority. | `agent_core/functorial` + `/api/functorial`. |
| P1 | Adapter/core direction debt | Blocks lawful backend/provider replacement and port law suites. | `ingest.adapters`, `source_library.adapters`. |
| P1 | Derived projection authority | Reports/plans/preflights can be consumed as facts or completion authority. | successor generators, checkers, dashboard/readiness builders. |
| P2 | Core exception/failure discipline | Most numerous, but repair requires closed failure families and core/shell classification first. | active typed successor slices. |
| P2 | Duplicate helper mechanics | Increases drift and copy cost, but usually does not by itself create authority ambiguity. | shared script/checker utilities. |
| P3 | Broad semantic registration beyond C7-C9 | Valuable only after the first slices prove the template. | remaining services and automation. |

## 4. P0-A: Representation census and C7 semantic registration

### Goal

Make the kit operate on real MRW semantic objects rather than only the generated Counter example.

### Required work

1. Create `docs/governance/functorial-representation-census.v1.json`.
2. Classify current surfaces as:
   - `CANONICAL`;
   - `PROJECTION`;
   - `KNOWN_COPY`;
   - `COMPATIBILITY_SURFACE`;
   - `SHELL`;
   - `CLI_OR_REPORT`.
3. Register the C7 minimum semantic chain first:
   - `RawSnapshot`;
   - `NormalizedIngestEnvelope`;
   - `DigestionDecision`;
   - `Extract | Chunk | Summarize | PassThrough`;
   - `StructuredMaterialCandidate`;
   - admission/projection/recovery outcomes.
4. Register the C7 codec discriminants, dispositions, outcome kinds, and failure families.
5. Replace free-string failure codes where they cross interface boundaries with closed vocabulary members. Existing `C7Rejected` and `C7Deferred` outcome unions are closed, but their `failure_code: str` fields are not.
6. Add kit sketches for:
   - ordered prefix;
   - `one_of` alternatives;
   - candidate closure;
   - admission;
   - projection;
   - recovery.
7. Bind every testable sketch equation to an existing test ID or add a focused test.

### Non-goals

- Do not register the entire repository in one pass.
- Do not rewrite frozen movement artifacts.
- Do not turn historical review artifacts into runtime authority.

### Acceptance

- Real C7 objects appear in `registries/`.
- Every registered `testable` equation has a test witness.
- Fakes or deterministic ports execute the same law suite as real implementations where a registered port exists.
- `architecture_gate_tests` passes.
- A documented baseline delta shows no new violation.
- C7 authority ceiling remains all false for production/live/cutover claims.

## 5. P0-B: Lightweight functorial projection correction

### Goal

Prevent `services/agent_core/functorial` from becoming a second successor authority.

### Required work

1. Mark the public surface `PROJECTION_ONLY` in API documentation and route metadata.
2. Choose one executable program representation:
   - interpret the stored `WorkflowSpec.program`; or
   - stop storing the private program projection and make refs the only source.
3. Repair dependent data flow:
   - pass the prior step output to the next step for dependent sequences;
   - declare independent execution as a separate shape with explicit resource/effect checks.
4. Derive operator schemas from the existing AgentCore tool contract. Any static fallback requires a typed deviation record.
5. Close the risk and failure vocabularies.
6. Preserve AgentCore `status`, structured error, retry/readback disposition, and authority ceiling instead of collapsing them to `ok`.
7. Replace generic catalog writes with one domain writer per record family and an explicit version policy.
8. Remove import-time filesystem creation/seeding; use an explicit lifecycle entry point.
9. Add focused tests for:
   - ordered composition;
   - unresolved refs;
   - schema mismatch;
   - runtime failure propagation;
   - catalog version conflicts;
   - idempotent seed lifecycle.

### Acceptance

- No hidden second program interpreter.
- No silent schema replacement.
- No free-string risk/failure family at this interface.
- Lightweight surface cannot emit production authority language.
- All focused tests pass and the full kit ratchet remains green.

## 6. P1-A: Adapter/core boundary repair

### Goal

Make adapter replacement a port/law question rather than a source-import rewrite.

### Observed clusters

```text
ingest.adapters          66 raw findings
source_library.adapters  20
collect_runtime.adapters  8
graph.adapters            5
local_index.adapters      3
llm.adapters              2
discovery.adapters        1
```

### Required work

1. First classify scanner topology:
   - adapter packages and composition roots belong to shell unless they own pure domain contracts;
   - do not move violations out of baseline merely by renaming directories.
2. For each real core-to-adapter dependency:
   - name the required capability port;
   - define operations, types, laws, and closed failure family;
   - make composition root inject the concrete adapter;
   - keep pure domain independent of HTTP, DB, provider, crawler, and filesystem.
3. Start with `ingest.adapters` and `source_library.adapters` because they dominate the debt and are active in C7/source-library flows.
4. Reuse an existing port when it already has the needed semantics; do not create a manager layer.
5. Add one shared law suite per real port. Fakes and deterministic implementations run the same suite.

### Acceptance

- Remaining import-direction findings are shell composition roots or documented compatibility boundaries.
- Core modules no longer import concrete adapters for the repaired families.
- Each repaired port has a closed failure family and law suite.
- Baseline import-direction keys for repaired files become stale and are removed.
- No broad `backend naturality` claim is made; provider/backend comparisons are named observational compatibility unless full components and squares are witnessed.

## 7. P1-B: Derived projection authority repair

### Goal

Prevent plans, reports, preflights, simulations, and generated evidence from being consumed as canonical facts.

### Required work

1. Repair authority-adjacent builders first:
   - successor semantic movement generators;
   - capability-spec generators;
   - readiness/dashboard/report builders;
   - promotion/cutover preflight builders;
   - automation artifact checkers.
2. Use the kit marker:

   ```python
   derived(kind, value)
   ```

   with `kind` restricted to `view | plan | preflight | simulation | external_claim`.
3. Preserve compatibility carefully:
   - internal builders may wrap outputs directly;
   - stable API payloads require a C3 transport compatibility decision before changing their response shape;
   - a builder that already returns an authoritative persisted record must be renamed or classified, not falsely marked as derived.
4. Add explicit fact-source and writer metadata to generated governance artifacts.
5. Scripts that merely print diagnostics can remain CLI/report surfaces if represented that way in the census; they do not all need the same runtime wrapper.

### Acceptance

- Authority-adjacent derived outputs cannot be mistaken for canonical facts.
- Focused baseline keys for repaired builders are removed.
- Existing report/checker contracts remain backward compatible or carry an explicit extension/refinement/loss classification.
- No historical artifact is mutated to make a checker green.

## 8. P2-A: Exception and failure-family repair

### Goal

Make core partiality explicit and preserve failure ownership. This is not a campaign to delete every `raise`.

### Classification before repair

Each baseline file is classified as one of:

1. `PURE_CORE`: convert raises to closed failure values or move the operation behind a port.
2. `SHELL_BOUNDARY`: exception is legitimate; move code to shell or mark a narrow `kit:boundary`.
3. `CLI`: `SystemExit` and argument parsing belong to shell/CLI, not core.
4. `TYPED_INTERFACE_EXCEPTION`: preserve the exception but register its closed failure family and owner.
5. `LEGACY_COMPATIBILITY`: freeze behavior until the corresponding movement record is repaired.

### Priority files

Start with high-impact active semantic surfaces, not alphabetical order:

```text
main/backend/app/successor_runtime/capabilities/source_library_c2_shared.py
main/backend/app/successor_runtime/substrate/postgres/first_specimen_handlers.py
main/backend/app/successor_runtime/capabilities/ingest_c7_movements.py
main/backend/app/services/typed_knowledge/persistence_boundary.py
main/backend/app/successor_runtime/substrate/postgres/ingest_c7_movement_admission.py
```

These are high-density, but each requires semantic review; file count alone does not authorize mechanical rewrite.

### Required work

1. Register real failure families before converting calls.
2. Convert pure-core `ValueError` / `TypeError` partiality into closed failure values where the operation is claimed pure or replayable.
3. Keep shell exceptions at the boundary; do not scatter `kit:boundary` markers to suppress findings.
4. Ensure `OUTCOME_UNKNOWN`, retry authorization, readback failure, stale revision, and ABA remain distinct typed outcomes.
5. Add failure-preservation tests when implementations of one port are substituted.

### Acceptance

- A reduced baseline key is accompanied by a registered failure family or justified shell classification.
- No failure class is silently merged into generic `INTERNAL_ERROR`.
- Recovery/retry/readback behavior remains testable.

## 9. P2-B: Shared helper consolidation

### Goal

Reduce mechanical drift without hiding domain differences.

### First candidates

```text
_read_text
_canonical_json
load_json
write_json
repo_root / _repo_root
utc_now / _utc_now
_as_bool
parse_args
build_check
build_report
run_git
changed_files_in_worktree
```

### Rules

1. Extract only generic mechanics; do not merge semantic predicates.
2. Shared helpers live in one owned module and have focused tests.
3. Do not consolidate `main` CLI entry functions.
4. A helper used by checker scripts must preserve exit codes and artifact bytes unless a byte-bound artifact is additively rebound.

### Acceptance

- Duplicate-helper report count decreases for targeted names.
- Existing checker outputs and exit codes remain stable.
- Relevant focused checker tests pass.

## 10. P3: Expand registration family by family

Only after P0 proves the C7 pattern:

1. register C8 typed knowledge and delivery chain;
2. register C9 projection/source evolution chain;
3. register shared generator codecs and authority profiles;
4. register automation artifact codecs;
5. register provider/crawler ports that truly have multiple interpreters;
6. register frontend/API read models only after their Python fact sources are stable.

Each family contributes only:

- mapping data;
- port/profile differences;
- focused tests;
- declared losses;
- no copied runtime/fixture/law stack.

## 11. Execution sequence

```text
S0  Freeze current ratchet and publish debt report
      already complete

S1  Representation census + C7 semantic registration
S2  Lightweight functorial projection correction
S3  ingest/source-library adapter boundary repair
S4  Derived authority markers for generators/readiness/report builders
S5  C7/C2 failure-family repair and targeted no-throw reduction
S6  Shared helper consolidation
S7  C8/C9 registration
S8  Remaining service/automation families
```

S1 and S2 may proceed in parallel because their write boundaries do not overlap. S3 can begin after S1 fixes the vocabulary owner. S4 can begin in parallel with S3 but must not rewrite the same files. S5 depends on the relevant failure families from S1/S3.

## 12. Baseline governance

Every repair package must report:

```text
changed files
baseline keys removed
baseline keys added, expected zero
classification of each removed key
focused test commands and results
full kit ratchet result
remaining authority ceiling
rollback route
```

Allowed baseline removal reasons:

- code repaired;
- file moved to correct shell classification after ownership review;
- duplicate scanner finding eliminated without semantic change;
- stale key no longer present.

Forbidden:

- broad baseline rewrite;
- hiding a path by narrowing `functorial-kit.json`;
- adding `kit:boundary` without naming the boundary owner and failure family;
- deleting tests or evidence;
- treating a green scanner as semantic completion.

## 13. Completion definition

This remediation program is complete only when:

1. active C7-C9 semantic objects and real failure families are registered;
2. lightweight functorial projection has one representation, one interpreter, closed failures, and focused law witnesses;
3. active adapter substitution boundaries use shared port law suites;
4. authority-adjacent derived outputs are marked non-authoritative;
5. remaining fail baseline is explicitly classified as shell, CLI, compatibility, or scheduled semantic repair;
6. no new violation is allowed by the ratchet;
7. promotion/live/cutover claims remain under their separate authority gates.

A green kit run is necessary, not sufficient.
