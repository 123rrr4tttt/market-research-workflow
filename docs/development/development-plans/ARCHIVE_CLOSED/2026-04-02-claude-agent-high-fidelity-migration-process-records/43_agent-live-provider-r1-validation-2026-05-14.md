<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/43_agent-live-provider-r1-validation-2026-05-14.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-04-02-claude-agent-high-fidelity-migration-process-records/43_agent-live-provider-r1-validation-2026-05-14.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# Agent Live Provider R1 Validation

Date: 2026-05-14
Status: R1 live-provider validation evidence
Mainline: Claude Code level AgentCore reconstruction

## Purpose

This document closes the live-provider part of R1 from `41_agent-high-fidelity-migration-closure-audit-2026-05-14.md`.

The earlier closure audit had code and deterministic E2E coverage for the external source chain, but it had not proven that a stable real provider was configured in this runtime. This note validates the live provider through the actual AgentCore tool registry, not by bypassing the AgentCore loop.

2026-05-14 sync: the updated 41 document adds R3 Matrix Capability Execution. This note still closes R1 live-provider availability, but it does not close R3. A successful `provider=auto` live query proves one configured branch can return candidates; broad research and material workflows still need query/provider/evidence matrices, candidate merge/rank, and branch-level diagnostics.

## Validation Boundary

The probe intentionally stops before `ingest.url_pool.submit` dispatches an external URL into the project ingest pipeline. That write path is already covered by deterministic URL-pool, source-history, task-event, and writing-workbench E2E gates. Re-running it against a real external URL would mutate project/source-library state without a user-selected target source.

This note therefore validates:

- AgentCore can call `source.web.search` through the real project tool registry;
- the live provider is configured and selected;
- the provider returns concrete candidates;
- a returned live candidate can be reviewed by `source.candidate.review`;
- the review returns a `url_pool` ingest payload and the expected `run_ingest.url_pool.submit_with_payload` next gate.

## Probe 1: Live AgentCore Search

Command:

```bash
PYTHONPATH=main/backend /opt/homebrew/bin/python3.11 - <<'PY'
from app.services.agent_core import AgentCore, AgentCoreRequest, CoreModelStep, CoreToolCall, FakeCoreProvider, build_project_core_tool_registry
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore

service = AgentSessionService(store=InMemoryAgentSessionStore())
bundle = service.create_session(source="user", entrypoint_type="agent_core", goal="R1 live provider probe", project_key="demo_proj", task_blueprints=[])
registry = build_project_core_tool_registry(service=service, source_library_lister=lambda _: [])
provider = FakeCoreProvider([
    CoreModelStep.tools(CoreToolCall(tool_name="source.web.search", call_id="call-live-search", arguments={
        "query": "robotics commercialization official report policy",
        "provider": "auto",
        "language": "en",
        "max_results": 3,
        "min_trust_score": 0,
    })),
    CoreModelStep.final("live provider probe complete"),
])
out = AgentCore(provider=provider, tool_registry=registry, tool_specs=registry.list_specs()).run(
    AgentCoreRequest(message="live external search provider probe", session_id=bundle["session"]["session_id"], project_key="demo_proj")
)
print(out.tool_results[0].structured_content)
PY
```

Observed result summary:

```text
status=completed
candidate_count=3
provider=auto
next_gate=review_candidates_then_source_library_or_url_pool_ingest
configured_paid_providers=["serper"]
selected_provider_configured=true
```

The first run returned live external candidates including IFR and OSHA results. Provider diagnostics showed:

- `serper.configured=true`;
- `configured_paid_providers=["serper"]`;
- `selected_provider_configured=true`;
- `ddg_requires_no_key=true`, but the selected configured paid provider was Serper.

## Probe 2: Live Candidate Review Gate

Command shape:

```bash
PYTHONPATH=main/backend /opt/homebrew/bin/python3.11 - <<'PY'
# Same AgentCore registry and session:
# 1. run source.web.search against provider=auto;
# 2. pass the first returned candidate into source.candidate.review;
# 3. approve it with preferred_ingest=url_pool.
PY
```

Observed result summary:

```text
session_id=as-ba4117ec073f49cb
search_status=completed
candidate_count=3
configured_paid_providers=["serper"]
selected_provider_configured=true
review_status=completed
review_decision=approved
review_next_gate=run_ingest.url_pool.submit_with_payload
ingest_payload_type=url_pool
artifact_refs=["artifact-e75a41ea419841b3"]
```

The reviewed live candidate returned a concrete `url_pool` ingest payload. This proves the live provider output is compatible with the governed candidate-review and URL-pool handoff contract.

## R1 Closure Decision

R1 is closed for the high-fidelity migration scope:

- live external search provider validation is no longer blocked in this runtime;
- AgentCore can retrieve live candidates through the configured provider;
- candidate review produces the correct governed ingest boundary;
- deterministic tests and browser E2E continue to own the mutating URL-pool/status/writeback path.

Operational caveat: future deployments still need provider readiness diagnostics enabled. If Serper or another stable provider is not configured in a deployment, the agent must report provider limitation and avoid claiming that no external evidence exists.

R3 caveat: this validation must not be reused as proof that single-query source discovery is acceptable. R3 requires matrix execution whenever the user task needs breadth, comparison, or evidence quality: multiple query variants or an explicit pruning rationale, internal/external route separation, provider diagnostics per branch, deduped candidates, and governed review before ingest.
