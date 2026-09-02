# C8 Semantic Movement Design v2

Status: `MAINLINE_REDISPOSITION_PROPOSAL · FIVE_REIMPLEMENTED_AS · DOUBLE_REVIEW_REQUIRED · NO_PROMOTION`

This design records the current local C8 material, knowledge, writing, report,
delivery, graph and consumer movement evidence. Frozen `01/02/06/20/21` remain
authoritative, and the generated P1-P3 matrix remains the machine-readable
state. This file grants no live provider, external delivery, production
cutover, authority transfer, candidate or P4 promotion.

## Dispositions

| Movement | Proposed disposition | Successor realization |
| --- | --- | --- |
| `C8-M001` | `REIMPLEMENTED_AS` | exact C7 head/value read, deterministic knowledge formation and opaque bounded read witness |
| `C8-M002` | `REIMPLEMENTED_AS` | exact issued reads and citations to deterministic staged Markdown draft |
| `C8-M003` | `REIMPLEMENTED_AS` | verified draft to canonical `ResearchArtifact.v1`, separate approved RuntimeNode internal delivery, receipt and relation |
| `C8-M004` | `REIMPLEMENTED_AS` | occurrence-preserving content-addressed graph generation with fixed loss catalog and offset CAS |
| `C8-M005` | `REIMPLEMENTED_AS` | active-handle read consumer that preserves provenance/loss and rejects evidence synthesis |

No movement is `MOVED_TO`: legacy canonical identity or owner is not migrated.
Intentional metadata, convenience output, model fallback, graph compression and
synthetic-evidence rejection are recorded as projection loss inside the
corresponding movement, not as a second disposition.

## Owner and authority invariants

- C7 canonical head/value own source bytes; C8 knowledge handles are bounded
  read authority only.
- C8 writing/report draft values are staged evidence, not canonical artifacts.
- Research Ledger plus project artifact store own the admitted
  `ResearchArtifact.v1`; Research Ledger owns `DeliveryIntent`; Execution
  Journal owns `DeliveryAttempt`; internal blob store owns effect bytes/marker;
  receipt store owns `DeliveryReceiptRef`; Research Ledger owns `delivered_as`.
- Report admission never grants delivery. Delivery requires independent human
  approval, authority epoch, exact artifact revision, assignment, lease and
  attempt.
- Graph values and offsets remain rebuildable read projections and cannot
  become canonical source, evidence qualification, claim or runtime authority.

## Runtime and recovery evidence

The delivery bridge compiles five distinct operations into seven ordered Plan
steps, including report and delivery-receipt admission barriers. A real
disposable PostgreSQL RuntimeNode trace proves missing approval rejection,
single claimed attempt, one internal blob effect, effect-before-receipt
`OUTCOME_UNKNOWN`, readback-only recovery through a facade with no `execute`,
one receipt, one `delivered_as`, terminal completion and retained receipt after
authority rollback. External/network calls remain zero.

Material, writing and graph recovery exact-read durable locators and reissue
process-local opaque witnesses. Stale/cross-root/test-only witnesses, raw
content/provenance drift, generation/ref mismatch, wrong graph identity and
failed CAS residue fail closed.

## Named legacy observations and loss

- `legacy.typed_knowledge.downstream_contract.v1`: compare exact object/source
  identity and bounded read fields; legacy governance mutation is excluded.
- `legacy.writing.keyword_card_from_typed_knowledge.v1`: compare ordered source
  and citation closure; card cache/score/wall-clock/UI convenience fields are
  declared loss.
- `legacy.report.admission_delivery.v1`: named locator absence remains an
  observation, while actual generator/gate/export behavior is compared against
  the new owner-separated path. Inline HTML/CSV convenience, broad fallback,
  synthetic source sentences and transient job/UI metadata are loss.
- `legacy.graph.project_by_node_types.v1`: compare occurrence identity, edge
  endpoints/types and declared loss.
- graph-consumer legacy synthetic evidence fallbacks are explicitly rejected,
  not silently replaced.

## Current evidence ceiling

The independent current-byte review `/root/c8_postgres_exact_review` returned
`PASS_CURRENT_EXACT_BYTES_BOUNDED_LOCAL_ONLY`, with no open P0/P1 and all five
movements eligible for redisposition. Current evidence proves only local
disposable canonical artifact admission, internal content-addressed effect and
authoritative local receipt/readback. Production canonical mutation, live
provider, external delivery, cutover, authority transfer, promotion, candidate
adoption and legacy retirement remain unauthorized.

Formal acceptance still requires regenerated artifacts plus independent
declared-scope and predecessor-completeness review records on the same bytes.

