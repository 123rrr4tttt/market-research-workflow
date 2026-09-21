# MRW Functorial Debt Zero-Baseline Task Specification (v1)

- Status: `FROZEN_TASK_SPEC_AFTER_MANIFEST`
- Date: `2026-09-05`
- Scope root: `/Users/wangyiliang/market-research-workflow`
- Input classification: `docs/governance/functorial-structural-debt-remediation-completion5-classification.v1.json`
- Mutable execution ledger: `docs/governance/functorial-debt-zero-baseline-progress.v1.md`
- Authority: `IMPLEMENTATION_ONLY · NOT_PROMOTION · NOT_PRODUCTION`

## 1. Objective

Resolve the remaining 727 architecture baseline keys without hiding them. Completion requires:

```text
baseline_fail_keys=0
new_fail_keys=0
stale_fail_keys=0 after the reviewed baseline is regenerated from an empty fail set
import-direction=0
derived-marked=0
no-throw-in-core=0
```

The starting set is exact and closed:

```text
SCHEDULED_SEMANTIC_REPAIR=528
  derived-marked=317
  no-throw-in-core=211
CLI_OR_REPORT=173
LEGACY_COMPATIBILITY=25
SHELL_BOUNDARY=1
TOTAL=727
```

A key is resolved only by a semantic code repair, a proved lawful boundary representation, or an evidenced compatibility retirement. Classification alone is not resolution.

## 2. Frozen Inputs And Prohibitions

The following are read-only inputs:

- the 2026-09-04 frozen review and remediation plan;
- `docs/governance/functorial-structural-debt-remediation.freeze.v1.json`;
- predecessor migration evidence and exact-byte candidates;
- `scripts/formal_release/**` and `tests/formal_release/**`;
- production authority, promotion, cutover, delivery, and canonical-write controls.

Forbidden ways to reduce the count:

- deleting or bulk-rewriting `arch-baseline.json` before the underlying keys are absent;
- broadening `shell_paths` or narrowing `core_paths` to conceal real core code;
- adding blanket `kit:boundary` comments without a named owner and failure family;
- deleting tests, evidence, error branches, or compatibility paths to satisfy the scanner;
- converting every builder to a projection without determining its domain meaning;
- changing public exceptions, JSON envelopes, ordering, retries, persistence, or authority as an incidental cleanup;
- editing frozen exact-byte artifacts instead of creating an authorized additive successor candidate.

## 3. Semantic Resolution Rules

### 3.1 Derived values

For every `derived-marked` key, the packet must first classify the function as exactly one of:

```text
VIEW
PREFLIGHT
SIMULATION
EXTERNAL_CLAIM
GENERATED_EVIDENCE
PREPARED_COMMAND
CANONICAL_READ
AUTHORITATIVE_WRITE
```

Only the first five are derived. They must use the existing project/kit non-authoritative representation, preserve the current runtime and wire ABI, declare `derived_as`, deny reverse write, and identify their fact source. `PREPARED_COMMAND`, `CANONICAL_READ`, and `AUTHORITATIVE_WRITE` must not be falsely marked derived; a scanner false positive requires a narrow tested gate refinement or an explicit registered semantic classification.

When three or more functions share the same output shape, use one shared type/constructor and one shared test template. Do not create per-module wrappers.

### 3.2 Core failures

For every `no-throw-in-core` key, classify each observed raise site as:

```text
DOMAIN_REJECTION
PURE_CONTRACT_FAILURE
EFFECT_OR_PROVIDER_FAILURE
PROGRAMMER_DEFECT
SHELL_BOUNDARY_EXCEPTION
LEGACY_COMPATIBILITY_EXCEPTION
```

Domain and contract failures require a closed owned failure family and a typed result or existing project result representation. Effect failures belong to a port/interpreter boundary with preserved retry, timeout, cleanup, and observation semantics. Programmer defects remain defects but must not be represented as ordinary domain outcomes. Shell and legacy exceptions require narrow registered ownership and focused negative witnesses.

Do not replace `raise` with `None`, free-form dictionaries, generic `Result[Any, str]`, or message parsing. Preserve ordered composition and failure provenance.

### 3.3 CLI and report builders

The 173 script findings are not exempt from the zero-baseline target. Resolve them through one shared CLI/report result representation that is non-authoritative in type while preserving existing stdout, JSON bytes, exit codes, dry-run behavior, and direct/module entry points. A packet may prove a builder is a prepared command or canonical read instead, but must provide a narrow witness.

### 3.4 Legacy compatibility

The 25 compatibility keys may be removed only after one of these outcomes:

- the legacy path is retained behind an explicit compatibility adapter whose classification is accepted by a focused architecture test; or
- all live callers are migrated, parity and rollback are witnessed, and the legacy implementation is retired additively.

No packet may delete a legacy surface solely because no local unit test imports it.

### 3.5 Shell boundary

The single typed-knowledge persistence boundary remains an effect shell. Resolve its scanner key with a narrow boundary declaration tied to its registered failure family and existing negative tests; do not move persistence semantics into pure core.

## 4. Work Package Contract

Every delegated package is atomic and must contain:

```text
id
goal
input classification rows and exact baseline keys
owned files
read-only context files
domain object and transformations
canonical representation and authority direction
failure owner, when applicable
change class: extension | refinement | loss
allowed edits
forbidden edits
focused verification command
expected removed keys
rollback route
```

Worker output is fixed:

```text
result
changed files
verification status
removed keys observed by pure scan
remaining risks
```

Workers must not edit the frozen specification, mutable progress ledger, baseline, kit configuration, registries shared by another active package, or files outside their ownership. Workers must not spawn sub-agents. The root agent owns semantic decisions, shared registries, baseline updates, exact-byte successor staging, integration tests, and the progress ledger.

## 5. Execution Batches

### Z0: Partition and shared-kernel recognition

- Generate a deterministic packet registry from the 727 classification rows.
- Group by semantic owner and non-overlapping file set, not by arbitrary equal-sized chunks.
- Identify repeated derived and failure shapes before any bulk edit.
- Establish shared constructors/types/tests first when a third same-form implementation exists.

### D1-D4: Derived authority

- D1: shared derived representation and architecture witnesses.
- D2: successor runtime capabilities/assembly/substrate/specification.
- D3: backend services for ingest, source library, agent, graph, workflow, search, documents, and typed knowledge.
- D4: remaining API/model/service builders and prepared-command/canonical-read exceptions.

### F1-F4: Failure semantics

- F1: shared typed failure/result patterns and registry discipline.
- F2: successor runtime capabilities/language/research/runtime.
- F3: ingest/source-library/resource-pool/crawler/provider effects.
- F4: remaining service contract failures and narrow shell exceptions.

### C1: CLI/report convergence

- Parameterize root and backend scripts over one shared non-authoritative result representation.
- Migrate in low-coupling file batches; preserve all entry behavior.

### L1: Legacy convergence

- Inventory callers and select adapter retention or evidenced retirement per surface.

### E1: Final structural closure

- Resolve the typed-knowledge shell key.
- Run architecture gates, root suite, exact-byte candidate checks, frontend gates, and an isolated backend aggregate.
- Regenerate the baseline only after the pure scan has zero fail keys.

## 6. Batch And Review Cadence

GLM 5.3 Flash-en workers may run in large parallel batches only after Z0 emits packets with disjoint owned files. A normal batch contains 6-16 packets. Each worker runs only focused verification. The root integrates one semantic family at a time and then runs:

```text
packet schema/path precheck
focused family tests
pure architecture scan
new_fail_keys == 0
git diff --check
```

Do not run the repository full suite for each packet. Run full gates only at family, milestone, and final boundaries.

## 7. Baseline Ratchet

For each integrated batch:

1. scan without writing the baseline;
2. compute removed, new, and unchanged exact keys;
3. reject the batch if any new key is unexplained;
4. record semantic evidence for every removed key;
5. update `arch-baseline.json` only to the exact remaining current key set;
6. verify `new=0` and `stale=0` against the updated baseline.

Baseline reduction is evidence of scanner closure only. The progress ledger must also record focused semantic witnesses and authority ceilings.

## 8. Acceptance

The Goal is complete only when:

- all 727 starting keys have an accepted resolution record;
- the live architecture scan contains zero fail keys and no hidden import-direction findings;
- shared derived/failure representations are registered and witnessed;
- every affected public ABI has focused compatibility coverage;
- exact-byte-bound changes use additive successors and keep predecessors unchanged;
- root tests and relevant frontend/backend gates pass within stated environment boundaries;
- remaining failures are outside this Goal and explicitly enumerated;
- no promotion, production, live-provider, or cutover authority is inferred.

