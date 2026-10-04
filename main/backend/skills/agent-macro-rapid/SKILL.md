---
name: agent-macro-rapid
description: Execute the registered Rapid retrieval loop inside the native Agent macro cell.
---

# Native Rapid retrieval

This skill runs the Rapid collection loop for the active MRW project. The user's
free text and the project's current context and outline are the macro input.
Preserve that input; do not replace it with a fixed topic or a new outline.

Use the mounted dynamic Core tools as the ordinary Core tool surface. The
underlying host mechanism is an implementation detail of the native Core
binding and is not a user-visible boundary; do not refuse a mounted tool merely
because the runtime carries it through that host. Do not invoke shell, Python,
browser, MCP discovery, or any undeclared capability. If a required operation
is absent from the mounted tools, report the exact missing capability.

## Loop

1. Read the active project context, summary, outline, vocabulary, and current
   retrieval mode.
2. Choose a small first-round set of queries from the outline facets and
   registered information-retrieval routes.
3. Search and inspect candidates, fetch/read material bodies when available,
   and retain the source and material identities.
4. Build a structured digest containing query IDs, attempt IDs, material refs,
   body digests, and gaps. Keep the digest below formal evidence status.
5. Build an expansion frontier. Every frontier row must cite its parent digest,
   gap, outline section, target edge, and reason for the next query.
6. Save the structured Rapid proposal and read it back.
7. Use the saved frontier continuation capability for a second search round.
   Keep the second round's identities linked to the first round's digest and
   frontier; do not silently restart an unrelated run.
8. Save and read back the updated proposal. Report queries, attempts,
   candidates, materials, body readback, gaps, frontier links, proposal write,
   and proposal readback separately.

Do not claim formal graphs, qualified evidence, or delivery readiness unless a
mounted tool returns those exact observations.
