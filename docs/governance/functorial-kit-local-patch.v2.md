# Functorial Kit Consumer Gate Amendment v2

Status: `LOCAL_TEST_TOOL_NOT_RUNTIME_AUTHORITY`.

This additive governance note supplements v1 under stage-convergence contract 16.
Historical v6 candidate bytes and v1 evidence remain unchanged. The runtime kit
dependency remains commit `785ff25e201c9eae84c862e68e786bc975e7a800`.

## Scanner refinement

The cumulative consumer-gate patch SHA256 is
`f6145cafe16db0805ded7d93f752189ed4849353a1a10033c405310ed11dee03`.
Its predecessor patch SHA256 is
`bab5ddcf18a9312d99be4972e7c2addec233dab8faf7281d27f2148546cc0098`.
The source manifest binds the unchanged base and all three patched target hashes.
The ordinary create-only materializer must verify and apply these bytes; a runtime
package installation alone does not provide the consumer-gate fixes.

Exact Python-file shell declarations match that file, not sibling modules. A
directory declaration still includes descendants. Runtime aliases are derived
from observed package initializers, while repository-qualified and relative
imports retain their resolution. Conflicting source owners fail visibly.

Witnesses include `test_INVARIANT__exact_shell_init_flags_package_import_but_not_sibling_target`,
`test_INVARIANT__exact_shell_file_flags_exact_target_only`,
`test_INVARIANT__directory_shell_path_keeps_prefix_semantics`,
`test_INVARIANT__relative_import_preserves_from_file_semantics`, and absolute-alias
equivalence/conflict tests in the patched kit. This refines static import-target
classification; it does not prove absence of dynamic imports or runtime effects.

## Exact effect ownership

The following existing modules are declared as exact shell files based on their
operations, not merely because a scanner reported an import:

| Backend service path | Effect owner |
| --- | --- |
| `projects/schema_initialization.py` | Serialized DDL, advisory lock and transaction boundary |
| `workflow_graph/store.py` | SQL sessions, schema DDL and store writes |
| `workflow_graph/runtime.py` | Executor and run-store execution |
| `workflow_graph/handoff_store.py` | Store composition and audit-event writes |
| `workflow_graph/__init__.py` | Store/runtime construction and session bridge |
| `agent_batch/executor_health.py` | Broker inspection RPC and clock observation |
| `agent_core/project_tools.py` | Tool execution, task dispatch, session and external-service operations |
| `agent_runtime/interactive_agent.py` | Approval-gated execution and session/task/artifact updates |
| `agent_runtime/read_only_tools.py` | Session, workflow, job and document reads |
| `ingest/canary_handoff_live.py` | Explicit database/API canary test runner |
| `agent_core/__init__.py` | Compatibility facade that exports contracts and effectful tool assembly |
| `agent_core/functorial/__init__.py` | Compatibility facade for the mutable catalog singleton |
| `agent_core/functorial/operator.py` | Catalog assembly by constructing tool runtimes to obtain descriptors |
| `agent_core/functorial/run.py` | Ordered tool execution and session/store operations |
| `agent_core/functorial/catalog.py` | Metadata catalog lookup and upsert facade |
| `agent_core/functorial/registry.py` | JSONL loading, append writes and mutable catalog ownership |
| `agent_core/functorial/motif.py` | Catalog resolution and persisted motif construction |
| `agent_core/functorial/workflow.py` | Catalog resolution and persisted workflow construction |

`typed_knowledge/adapters` additionally owns the newly extracted live database
session and transaction adapter. No entire `services`, `agent_core`,
`agent_runtime` or `workflow_graph` directory is newly classified as shell.
The `functorial` directory is not a shell declaration either: its `compose.py`
and `contracts.py` remain core. The package-level tool-registry re-export is
preserved for compatibility rather than removed on the basis of no observed
internal callers. This classification does not retire that public surface.
The run loop's concrete runtime import is type-only and is now guarded by
`TYPE_CHECKING`; its execution logic is unchanged.

## Retained debt and limits

The store file still mixes in-memory and SQL representations. The tool/runtime
files still mix pure helpers with effectful execution. These are named mixed-file
debts, not completed extraction or evidence of a pure core. Exact-file ownership
also leaves `OperatorSpec` and pure schema helpers mixed with catalog assembly;
a future extraction must preserve their public identity and descriptor source.
The catalog module's old import-time-upsert description is historical wording:
current seeding is invoked through `ensure_operator_catalog`, not asserted here
to occur automatically on every import.

Exact-file ownership
does not remove obligations for callers that remain core: the strengthened gate
must expose those callers for disposition, without baseline suppression or new
boundary exemptions.

The canary runner is classified but not executed by this amendment. This note
grants no live, deployment, signing, registry, retirement or production authority.
