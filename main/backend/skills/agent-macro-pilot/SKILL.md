---
name: agent-macro-pilot
description: Read and explain an identified retrieval run when the user asks about its recorded status or result.
---

# Retrieval run readback

## When this method applies

Use this method only when the user asks to inspect or explain a retrieval run and supplies its run ID, or the trusted invocation context provides one. It is a newly authored, ordinary read-only skill specimen for the Agent macro pilot. It is not the original Rapid method or a Rapid execution loop.

For unrelated questions, answer normally. For a request to search, fetch sources, start a retrieval run, or save material, this method alone does not authorize or perform that work. Do not turn a request to inspect a run into an execution request. If no run ID is available, ask for it instead of searching for runs.

## Method

1. Use the project identity supplied by the trusted invocation context. Do not accept a user-provided project key as an override or inspect another project.
2. Read the named run with `project_retrieval.read_run` when that read-only tool is available in the invocation environment. This name identifies the existing MRW compatibility handler; its presence in this text does not mean a native Codex tool mount has been observed.
3. Summarize only the returned `run_id`, `plan_id`, `status`, `phase`, `counts`, `errors`, `receipt`, and timestamps that answer the user's question. Keep empty or missing receipt fields distinct from successful completion.
4. State clearly that this method reads persisted run state, not live source content or a newly executed run. A `queued` state does not prove worker execution; a receipt field is evidence only to the extent of its recorded contents.
5. If the tool is unavailable, returns an error, or the active project is unresolved, report that limitation. Do not substitute `project_retrieval.current`, `project_retrieval.preview`, `project_retrieval.start`, `execute_retrieval_run`, historical candidate data, or a manual search.

## Local result

Return a concise project-scoped readback of the identified run, including its recorded status and phase, relevant counts or errors, and receipt contents when present. Mark absent or unobserved details as unknown. Do not manufacture a plan, candidate, receipt, digest, frontier, or claim of completed retrieval.

## Boundaries

- `project_retrieval.read_run` is the only operation this skill requests. Do not invoke current, preview, start, run, write, ingest, or formalization operations.
- The existing `project_retrieval/skill.py` is a thin adapter to project retrieval service methods. It is not the skill body and does not itself establish Codex-native adoption.
- The fixed `execute_retrieval_run` executes a bounded project plan. It is not evidence that an original Rapid adaptive loop has been located or preserved.
- Historical Rapid round/facet/candidate records, including the 57 imported Hong Kong states, retain their historical identities. Never recast them as attempts or candidates from a new run.
- If the request requires original Rapid methods, an autonomous retrieval loop, or a structured Rapid digest/frontier, this skill is insufficient. Preserve that gap as `SOURCE_NOT_LOCATED:rapid_method_or_runner` until the authoritative source and executor are located.
