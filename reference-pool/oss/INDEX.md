# OSS Reference Pool Index

Updated: 2026-03-09 (PST)
Base Dir: `reference-pool/oss`

## Workflow / Runtime Repositories

| Name | Local Path | Remote | Commit (short) | Notes |
|---|---|---|---|---|
| n8n | `reference-pool/oss/n8n` | https://github.com/n8n-io/n8n.git | `2e35bb32` | Expression engine + item linking + execution persistence |
| dify | `reference-pool/oss/dify` | https://github.com/langgenius/dify.git | `92bde35` | VariablePool + LLM node templates + run/node persistence |
| Flowise | `reference-pool/oss/Flowise` | https://github.com/FlowiseAI/Flowise.git | `84758d7` | Node interface schema-driven parameter UI |
| langflow | `reference-pool/oss/langflow` | https://github.com/langflow-ai/langflow.git | `902252e` | Typed component I/O + component template system |
| pipelines | `reference-pool/oss/pipelines` | https://github.com/open-webui/pipelines.git | `039f9c5` | Provider adapter pipeline / OpenAI-compatible surface |
| temporal | `reference-pool/oss/temporal` | https://github.com/temporalio/temporal.git | `45617a8` | Durable execution runtime model |

## Writing / Markdown / Knowledge Repositories

| Name | Local Path | Remote | Commit (short) | Notes |
|---|---|---|---|---|
| tiptap | `reference-pool/oss/tiptap` | https://github.com/ueberdosis/tiptap.git | `8d1009f` | Headless editor. Start at `packages/markdown`, `packages/react`, `packages/core`, `demos/src`. |
| codemirror | `reference-pool/oss/codemirror` | https://github.com/codemirror/dev.git | `2cfd8b0` | Meta repo only. Useful for package orchestration, but real code is in `codemirror-view` and `codemirror-lang-markdown`. |
| codemirror-view | `reference-pool/oss/codemirror-view` | https://github.com/codemirror/view.git | `07d54a0` | Editor view internals. Start at `src/tooltip.ts`, `src/panel.ts`, `src/editorview.ts`, `src/draw-selection.ts`. |
| codemirror-lang-markdown | `reference-pool/oss/codemirror-lang-markdown` | https://github.com/codemirror/lang-markdown.git | `f4846f4` | Markdown parser and commands. Start at `src/markdown.ts`, `src/commands.ts`, `src/index.ts`. |
| outline | `reference-pool/oss/outline` | https://github.com/outline/outline.git | `db19a5c` | Collaborative knowledge base. Start at `app/editor`, `app/components/Sidebar`, `app/components/HoverPreview`, `app/components/Template`, `app/components/TemplatizeDialog`. |
| silverbullet | `reference-pool/oss/silverbullet` | https://github.com/silverbulletmd/silverbullet.git | `15cd08f` | Markdown live preview + wiki links + templates/widgets. Start at `client/codemirror`, `client/markdown_parser`, `client/markdown_renderer`, `client/components`, `client/space_lua`. |
| silverbullet-ai | `reference-pool/oss/silverbullet-ai` | https://github.com/justyns/silverbullet-ai.git | `bea4474` | Right-side AI panel + prompts + embeddings. Start at `src/chat-panel.ts`, `src/prompts.ts`, `src/embeddings.ts`, `src/editorUtils.ts`, `assets/chat-panel.html`. |
| logseq | `reference-pool/oss/logseq` | https://github.com/logseq/logseq.git | `7c5146a` | Bidirectional links / graph knowledge UX. Start at `src/main/frontend/components`, `src/main/frontend/search`, `src/main/frontend/extensions`, `src/main/frontend/modules`, `src/resources/templates`. |

## Agent Orchestration Case Repositories

| Name | Local Path | Remote | Commit (short) | Notes |
|---|---|---|---|---|
| spec-to-agents | `reference-pool/oss/agent-cases/spec-to-agents` | https://github.com/microsoft/spec-to-agents | `30009fc` | Full multi-agent workflow sample with search tool and handoff tests. |
| openai-agents-js | `reference-pool/oss/agent-cases/openai-agents-js` | https://github.com/openai/openai-agents-js | `448b9c2` | Agent loop, handoff, guardrails, runtime state, and parallel pattern examples. |
| langgraph | `reference-pool/oss/agent-cases/langgraph` | https://github.com/langchain-ai/langgraph | `46fed9d` | State graph runtime with branch/interrupt/checkpoint primitives. |

Agent-case docs:
- `reference-pool/oss/agent-cases/README.md`
- `reference-pool/oss/agent-cases/IO_ARCHITECTURE_MATRIX_2026-03-10.md`

## Fastest Reuse Paths

- Markdown editor MVP: `tiptap`, `codemirror-view`, `codemirror-lang-markdown`
- Keyword hover / side card interaction: `codemirror-view`, `outline`, `logseq`
- Markdown live preview and wiki-link behavior: `silverbullet`, `logseq`
- Template / prompt / AI side panel: `silverbullet-ai`, `dify`, `langflow`
- Knowledge base shell and sidebar composition: `outline`

## Fetch Mode

All repositories were cloned as shallow refs:

```bash
git clone --depth 1 --filter=blob:none <repo-url>
```
