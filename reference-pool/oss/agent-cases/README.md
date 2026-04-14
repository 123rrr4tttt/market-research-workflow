# Agent Cases Reference Library

Updated: 2026-03-10 (PST)
Base Dir: `reference-pool/oss/agent-cases`

## Repositories

- `spec-to-agents` (`30009fc`): workflow executor + specialist handoff + search tools.
- `openai-agents-js` (`448b9c2`): run loop + handoff + guardrails + tool execution + tracing.
- `langgraph` (`46fed9d`): state graph + branch + pregel loop + checkpoint + interrupt + tool node.

## Key Documents

- [IO Architecture Matrix](./IO_ARCHITECTURE_MATRIX_2026-03-10.md)

## Usage

1. Read `IO Architecture Matrix` first.
2. Freeze a project-wide canonical skill envelope.
3. Implement adapters by stage: intake -> handoff -> guardrails -> tool dispatch -> checkpoint/replay -> observability.
