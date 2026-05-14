# Agent vs WritingWorkbench Contract Alignment

## Status

passed

## Evidence

- WritingWorkbench selected-text material action was covered by e2e: `searches selected material through the writing agent without writing back`.
- The frontend sent selected-text context with `project_key`, `doc_id`, `version`, `etag`, `selected_text`, `selection_start`, `selection_end`, `active_heading`, and pinned materials.
- The AgentCore material-search turn called `project.context.bundle` and `writing.document.list`.
- The material-search turn did not call `writing.document.insert_paragraph` as an actual tool call.
- Backend material retrieval replay status: `passed` with `10` local-index result(s).

## Boundary

The writing workbench can ask for materials without writing back. Writeback remains a separate explicit action and must preserve document version / etag / selection provenance.
