# Legacy Graph Pages Archived

Status: Archived on 2026-03-01.

Scope:
- `main/frontend/templates/policy-graph.html`
- `main/frontend/templates/social-media-graph.html`

Policy:
- These two legacy templates are no longer active development targets.
- Navigation should point to unified graph entry:
  - `graph.html?type=policy`
  - `graph.html?type=social`
- Backend/Frontend feature work should be implemented in unified graph flow (`graph.html` and modern frontend), not in the archived templates.

Notes:
- Archived files may remain in repository for historical reference and rollback safety.
- Bug fixes on archived templates are avoided unless production blocking.
