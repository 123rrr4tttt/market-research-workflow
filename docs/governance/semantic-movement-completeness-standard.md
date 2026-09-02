# Semantic Movement Completeness Standard

- Status: ACTIVE
- Version: 1.0.0
- Date: 2026-09-01
- Owner: repository architecture/quality governance
- Scope: market-research-workflow and any successor workspace that migrates or
  regenerates code, contracts, data flows, or capabilities from this repository.

## Purpose

This standard makes "semantic movement completeness" a hard requirement for
migration, refactor, successor, backend replacement, and code-generation work.
The project must account for every semantic movement between the legacy/donor
system and the target system, not just prove that the new system compiles,
passes tests, or produces byte-identical artifacts.

Locator evidence (files, modules, cells, test counts, line ranges) describes
where things are. It is not evidence that a capability moved losslessly.
Promotion, capability-family acceptance, phase completion, and legacy
retirement require a completed semantic movement inventory with explicit
dispositions and acceptance traces.

## Scope

Applies to any change that:

- migrates, renames, or deletes an existing implementation, contract, data
  path, or workflow;
- refactors a module, service, or domain boundary;
- replaces a backend, provider, adapter, or runtime;
- generates new code from a spec, prompt, or donor implementation;
- retires or freezes a legacy system, route, or capability;
- promotes a candidate, capability family, phase, or feature to a higher
  qualification state.

## Definitions

### Semantic capability inventory

The ordered set of semantic movements that a legacy/donor system must preserve,
reimplement, or explicitly reject in the target. It answers "what must still be
true or still be done". Counts of locators or tests are not entries in this
inventory.

### Runtime authority inventory

The set of live wiring points that execute a semantic capability: routes,
workers, adapters, providers, permissions, storage, retry/recovery paths, and
their owners. A capability may be absent from this inventory and still belong
in the semantic capability inventory with an explicit disposition.

### Locator evidence

Pointers such as file paths, module names, line/cell ranges, and test IDs.
Locator evidence is necessary for traceability but is never a completeness
proof.

### Movement record

One atomic row of the semantic movement inventory. Each record must carry:

- source object: the legacy/donor object, contract, data shape, or behavior;
- target object: the successor object, contract, data shape, or behavior;
- named transformation: the explicit function, adapter, mapping, or manual
  procedure that converts source to target;
- owner: the accountable person or team;
- effect: side effects and observable behavior of the movement;
- failure: failure modes and their propagation;
- resource: compute, storage, network, memory, or cost impact;
- authority: permissions, roles, and authorization boundary;
- recovery: retry, rollback, compensation, and restart behavior;
- projection-loss: anything lost or weakened by the movement;
- source evidence: a reproducible pointer to the source behavior;
- target realization: a reproducible pointer to the target behavior;
- acceptance trace: the test or review trace proving the transformation and
  its loss account are correct.

## Required Artifacts

Any in-scope change must produce, in the change itself or a referenced
governance artifact:

1. `legacy/donor semantic movement inventory`: at least one movement record per
   identifiable semantic capability; locator/file/module/cell/test counts are
   not entries.
2. `movement matrix`: a table mapping every inventory entry to
   `source object -> target object -> named transformation -> disposition ->
   acceptance trace`.
3. `legacy trace`: a reproducible end-to-end trace from the legacy system.
4. `target trace`: a reproducible end-to-end trace from the target system.
5. `loss account`: one declared-loss statement or an explicit zero-loss
   declaration, plus any projection-loss notes per record.
6. `gate result`: a pass/fail result for every phase gate defined below.

## Dispositions

Every movement record must have exactly one disposition:

- `PRESERVED_AS`: source semantics are preserved by the named target object
  with an acceptance trace.
- `MOVED_TO`: source semantics moved to a different target location or owner
  with an acceptance trace.
- `REIMPLEMENTED_AS`: source semantics are intentionally rebuilt in a new
  implementation with an acceptance trace.
- `DECLARED_LOSS`: the loss is intentional, documented in the loss account, and
  reviewed.
- `EXPLICITLY_REJECTED`: the capability was considered and intentionally
  rejected; the rejection must name the decision owner and reason.
- `UNASSIGNED_BLOCKER`: the capability has no valid disposition yet; this is a
  blocker, not a placeholder.

## Phase Gates

`UNASSIGNED_BLOCKER > 0` forbids:

- capability or capability-family promotion;
- phase or milestone completion;
- candidate acceptance into the canonical target;
- legacy retirement or freeze;
- generator/parallel-worker output being treated as promotion.

Every phase gate must also check:

- the movement inventory exists and is complete for the declared scope;
- every record has all required fields and a valid disposition;
- runtime authority inventory and locator evidence are kept separate from
  semantic capability inventory;
- unwired or contract-only capabilities are explicitly placed or rejected, not
  deleted for lacking a live owner;
- declared-scope correctness and predecessor-to-successor completeness are both
  reviewed.

## Generator and Worker Rules

- Generators and parallel workers may only consume a spec that has already
  passed the completeness gate.
- Worker completion is evidence that a bounded job finished, not that a
  capability moved or that promotion is authorized.
- Worker output that adds, removes, or rewrites semantic capabilities must be
  folded back into the movement inventory before any promotion gate.

## Mechanical Implementation Routing

Once the IO contract is fixed, mechanical development defaults to DeepSeek:

- Mainline/high-reasoning models own architecture, the semantic movement
  inventory and matrix, normative/frozen authority, risk acceptance,
  promotion, integration, and final review.
- DeepSeek owns mechanical work with fixed boundaries: bulk code
  implementation, mechanical refactor, boilerplate/fixture/test generation,
  doc synchronization, formatting, deterministic serialization/hash scripts,
  and similar bounded tasks.
- Every DeepSeek package must declare target, input, output, allowed read/write
  scope, and acceptance criteria, and must know it is not the only executor.
- A DeepSeek package must not expand semantics, must not revert other
  executors' changes, and must return result, changed files, verification, and
  risk in a fixed envelope.
- DeepSeek must not modify frozen semantics, decide authority/cutover/
  promotion, or treat a green test as completion.
- Mechanical generation must pass the semantic movement completeness gate
  before its output can be consumed as canonical input.

## Review Checklist

Reviewers must verify both sides of every in-scope change:

### Declared-scope correctness

- [ ] Every movement record has source object, target object, named
      transformation, owner, effect, failure, resource, authority, recovery,
      projection-loss, source evidence, target realization, and acceptance
      trace.
- [ ] Every disposition is one of the six allowed values.
- [ ] Movement matrix rows are unique and traceable to tests or review notes.
- [ ] Locator counts are labeled as locator evidence, not completeness.

### Predecessor-to-successor completeness

- [ ] Every semantic capability in the legacy/donor scope has a movement record
      or an explicit rejection record.
- [ ] No capability is dropped because it lacks a live owner.
- [ ] At least one legacy end-to-end trace maps to a target trace with a
      structure-preservation verification.
- [ ] At least one failure or reverse-return case is traced end to end.
- [ ] There is at least one declared loss or an explicit zero-loss declaration.
- [ ] `UNASSIGNED_BLOCKER` count is reported; when greater than zero, no
      promotion or retirement is claimed.
- [ ] Green tests and exact hashes are not presented as proof of capability
      preservation; they prove the declared scope only.

## Machine-Readable Example

The canonical inventory is a JSON array. The record below is the structural
template; real inventories must fill every required field and use only the
allowed dispositions.

```json
{
  "schema_version": "1.0.0",
  "scope": "single-url ingest -> source_library frontdoor replacement",
  "movements": [
    {
      "movement_id": "M-INGEST-0001",
      "source_object": "legacy POST /api/v1/ingest/url/single behavior",
      "target_object": "source_library frontdoor url_routing behavior",
      "named_transformation": "url_routing/source_library -> postprocess_frontdoor",
      "owner": "backend-core",
      "effect": "same normalized document write contract",
      "failure": "fetch/parse/write failures mapped to task FAILURE",
      "resource": "unchanged pool/crawler budget",
      "authority": "same project-scoped write authority",
      "recovery": "idempotent uri dedupe retained",
      "projection_loss": "none declared",
      "source_evidence": "legacy trace T-SRC-0001",
      "target_realization": "target trace T-DST-0001",
      "acceptance_trace": "trace comparison T-COMPARE-0001",
      "disposition": "MOVED_TO"
    }
  ],
  "unassigned_blockers": 0,
  "declared_losses": [],
  "zero_loss_declared": true
}
```

## C7 Example Chain

The standard capability boundary for ingest and admission is:

```text
RawSnapshot
  -> NormalizedIngestEnvelope
  -> DigestionDecision
  -> Extract | Chunk | Summarize | PassThrough
  -> StructuredMaterialCandidate
  -> Verify | Admit
  -> Index | Graph Projection
```

- C7 owns format/structure processing: snapshot capture, envelope
  normalization, digestion routing, extraction/chunking/summarization, and
  structural candidate formation through admission.
- C8 owns post-admission typed knowledge, argumentation, and writing:
  typed knowledge, writing composition, report/export admission, and graph
  consumers.
- The chain is lossless only when every edge has a movement record with source
  evidence and a target acceptance trace; a missing edge is an
  `UNASSIGNED_BLOCKER`, even if every cell has a locator.
- `Verify/Admit` is a semantic gate, not a file existence check.

## Anti-Patterns

- Reporting locator counts or test counts as capability completeness.
- Claiming promotion while `UNASSIGNED_BLOCKER > 0`.
- Deleting an unwired or contract-only capability because it has no live owner.
- Treating green tests or exact hashes as proof of lossless capability
  movement.
- Letting generator or worker completion replace the completeness gate.
- Reviewing only declared scope and never the predecessor-to-successor
  inventory.
- Filling disposition with free text instead of the six allowed values.
- Declaring "migration complete" without a legacy trace, a target trace, a
  failure case, and a declared-loss or zero-loss statement.
- Routing architectural or authority decisions to a mechanical worker, or
  letting a worker's green test replace mainline risk acceptance and final
  review.
