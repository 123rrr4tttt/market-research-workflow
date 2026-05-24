# OSS Code Harvest + IO-Level Task Plan (Node Platformization)

Date: 2026-03-05 (PST)
Owner: Codex + parallel agents
Scope: workflow node platformization for internal platform (frontend node designer + backend runtime + persistence)

## 0. Local Harvest Result

- OSS code pool dir: `reference-pool/oss`
- Index doc: `reference-pool/oss/INDEX.md`
- Included repos: `n8n`, `dify`, `Flowise`, `langflow`, `pipelines`, `temporal`

## 1. Target State (single plan)

1. Node schema-driven form layer (Flowise/Langflow pattern)
2. Unified variable selector + expression binding (n8n/Dify pattern)
3. LLM node template contract (Dify/OpenWebUI pattern)
4. Runtime input resolver + deterministic node I/O envelope (n8n pattern)
5. Persistent run/node event store + replay-ready log (Dify/Temporal pattern)

## 2. IO Contract (project internal)

### 2.1 Node Definition IO

Input:

```json
{
  "node_type": "llm_call|vector_search|join|...",
  "schema_version": "1.0",
  "input_schema": [
    {
      "name": "query",
      "value_type": "string|number|boolean|json|array",
      "source": "input|context|node_output|constant|expression",
      "from_node": "node-id",
      "from_key": "key",
      "expr": "={{$json.query}}",
      "required": true,
      "default_value": ""
    }
  ],
  "output_schema": [
    { "name": "text", "value_type": "string" }
  ],
  "llm": {
    "provider": "openai|azure|litellm|...",
    "model": "...",
    "temperature": 0.2,
    "top_p": 1,
    "max_tokens": 1024,
    "prompt_class": "analyst",
    "prompt_template": "..."
  }
}
```

Output:

```json
{
  "node_id": "...",
  "compiled_params": {},
  "input_bindings": [],
  "output_bindings": []
}
```

### 2.2 Runtime Execution IO

Input:

```json
{
  "graph_id": "...",
  "run_id": "...",
  "input": {"query": "..."}
}
```

Output:

```json
{
  "run_id": "...",
  "status": "queued|running|succeeded|failed",
  "node_statuses": {"node-a": "succeeded"},
  "final_output": {},
  "events": []
}
```

## 3. Atomic Task Clusters (parallel-ready)

### Cluster A: Node Schema Platformization

A

1. Build node schema registry

- Goal: centralized schema for each node type
- Input: existing node templates + OSS references (Flowise/Langflow)
- Output: `node_schema_registry` with typed fields/options/validation
- Acceptance: frontend can render form from schema only (no hardcoded fields)

A

1. Schema-driven NodeInfoCard renderer

- Goal: render controls by schema (input/select/switch/list/json)
- Input: node schema registry
- Output: reusable dynamic form renderer in card
- Acceptance: llm/vector/join all editable without raw JSON mode

A

1. IO typed validation

- Goal: validate value type/source/from mapping before save
- Input: node draft + schema
- Output: validation errors with field path
- Acceptance: invalid `node_output` binding blocked with clear message

### Cluster B: Variable Selector + Expression Binding

B

1. Add unified variable selector model

- Goal: `node.key` / `sys.key` selector model
- Input: graph topology + node output schemas
- Output: selector datasource API + UI dropdown
- Acceptance: selecting upstream node auto-populates key list

B

1. Add expression field and safe evaluator adapter

- Goal: support `=...` expression in input bindings
- Input: runtime context (`input/context/upstream`)
- Output: expression evaluation adapter and fallback behavior
- Acceptance: expression and direct binding can coexist

B

1. Auto-binding on edge connect

- Goal: connect edge => auto create target input bindings
- Input: source output schema + target required inputs
- Output: deterministic auto-mapping strategy
- Acceptance: newly connected edge creates non-duplicate bindings

### Cluster C: LLM Template Contract

C

1. Create LLM profile templates

- Goal: `analyst/summarizer/extractor/rewriter` profile packs
- Input: current LLM node + Dify/OpenWebUI patterns
- Output: profile registry + defaults per provider
- Acceptance: one click applies full param template

C

1. Prompt template variable extraction

- Goal: parse prompt vars from template and map to input_vars
- Input: `prompt_template`
- Output: required variable list
- Acceptance: missing required variables block run with clear error

C

1. Provider param normalization

- Goal: normalize provider-agnostic params to provider-specific call args
- Input: llm contract
- Output: normalized payload (`model/temp/top_p/max_tokens/...`)
- Acceptance: same node config works for multiple providers

### Cluster D: Runtime & Persistence

D

1. Runtime resolver v2

- Goal: resolve `input_vars` from `input/context/node_output/constant/expression`
- Input: node params + runtime state
- Output: resolved node inputs
- Acceptance: run output trace shows each input source resolution

D

1. Node execution envelope standardization

- Goal: consistent node result envelope (`data/error/meta/io_trace`)
- Input: executor raw outputs
- Output: standardized node result object
- Acceptance: all executors return same envelope shape

D

1. Persistent run/node events

- Goal: move from in-memory to DB-backed run store
- Input: run lifecycle events
- Output: tables/repo API for run + node events + latest snapshot
- Acceptance: process restart does not lose run history

D

1. Replay-ready event log

- Goal: append-only event stream for run replay/audit
- Input: execution events
- Output: event sequence with version and idempotency key
- Acceptance: can reconstruct node statuses from event log only

### Cluster E: API/Frontend Integration & Smoke

E

1. API contract alignment

- Goal: frontend compile/run/get-run/get-events aligns with new envelopes
- Input: existing endpoints
- Output: contract version update + compatibility adapter
- Acceptance: no breaking changes for existing UI operations

E

1. End-to-end smoke workflow set

- Goal: 8 primary chains smoke tests with platformized nodes
- Input: standard DSL fixtures
- Output: smoke script + result report
- Acceptance: local non-docker smoke all pass

E

1. Migration scripts

- Goal: auto-upgrade old node configs to new schema
- Input: historical DSL/config records
- Output: migration script + dry-run mode
- Acceptance: dry-run diff stable, apply mode idempotent

## 4. Dependency Graph (serial + parallel)

1. A1 -> A2 -> A3
2. B1 || C1 (parallel)
3. B2 depends on B1
4. B3 depends on A1 + B1
5. C2 depends on C1
6. C3 depends on C1
7. D1 depends on A1 + B1 + C3
8. D2 depends on D1
9. D3 depends on D2
10. D4 depends on D3
11. E1 depends on D2
12. E2 depends on E1 + D3
13. E3 depends on A1 + E1

## 5. Minimal Gate for each atomic task

- At least one of: `lint` / `unit test` / `contract check`
- Required report format:
  - Result
  - Changed files
  - Validation status
  - Risk

## 6. Immediate Execution Batch (first 2-day fast cut)

1. A1 + A2 + B1 + B3 + C1 + D1
2. E1 contract adapter
3. E2 minimal smoke set (llm/vector/join + one composite chain)

Exit Criteria (T+2 days):

- Node card no longer depends on manual JSON editing for main fields
- Edge connect auto-parameter binding available and editable
- LLM node has full template fields and profile one-click apply
- Runtime consumes binding sources and returns source trace

## 7. Source Anchors

- n8n: expression, item-linking, execution persistence
- Dify: variable pool, LLM node template, run/node repositories
- Flowise/Langflow: schema-driven node component UI
- Open WebUI Pipelines: provider adapter and param normalization
- Temporal: durable execution, event history, replay semantics

## 8. Wave8-8 Search / Vectorization IO Evidence

2026-05-22 补充一个与 node platformization 相关的最小 IO 证据层：

- Evidence：[wave8-search-vectorization-contract/2026-05-22](../../../automation-runs/wave8-search-vectorization-contract/2026-05-22/README.md)
- Checker：`ops/search-lab/scripts/wave8_search_vectorization_contract.py`

该 checker 把 search provider trace、local open-search replay summary、`local_index` LanceDB runtime smoke、benchmark quality artifact 串成稳定 JSON contract，可作为后续 `vector_search` / external-search node 的输入边界参考。它不声明实时容器可用，不证明生产 embedding 语义质量，也不关闭全局 vector object schema；这些仍应留在向量化 foundation 与节点 IO contract 后续任务中处理。
