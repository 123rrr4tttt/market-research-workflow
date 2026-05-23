# Wave40 External Blocker Manifest

Date: 2026-05-23 PST

## Result

This wave converts external-blocked target governance from keyword evidence to a structured manifest contract.

- Manifest: `development/latest-dev-docs/development-plans/EXTERNAL_BLOCKER_MANIFEST.v1.json`
- Checker: `scripts/checkers/check_external_blocker_manifest.py`
- External-blocked review targets covered: `30 / 30`
- Manifest entries covered: `30 / 30`
- Current `CURRENT_DEV` counts remain `partial:0 / not_closed:0 / no_closure_claim:0`

## Contract

Every external-blocked review target must now have:

- `dependency_type`
- `blocked_on`
- `repo_local_evidence`
- `evidence_required`
- `probe_or_manual_evidence`
- `exit_criteria`
- `owner_surface`

The checker derives the authoritative external-blocked target set from
`check_development_plans_status_matrix.py`, so a directory cannot drift into or
out of `external_blocked` without the manifest being updated.
It also rejects probe commands that reference missing local `.py`, `.sh`,
`.js`, `.mjs`, `.ts`, or `.tsx` files.

## Verification

```bash
/Users/wangyiliang/.local/bin/python3.11 scripts/checkers/check_external_blocker_manifest.py --root . --json
/Users/wangyiliang/.local/bin/python3.11 -m pytest -q tests/checkers/test_check_external_blocker_manifest_unittest.py
python3 -m json.tool development/latest-dev-docs/development-plans/EXTERNAL_BLOCKER_MANIFEST.v1.json >/dev/null
```

Observed result:

- `external_blocker_manifest=passed`
- `external_target_count=30`
- `manifest_target_count=30`
- `tests/checkers/test_check_external_blocker_manifest_unittest.py`: `4 passed`

## Boundary

This wave does not claim that live providers, public replay, production data,
tenant DB, browser runtime, OpenClaw runtime, or human-review dependencies have
already succeeded. It closes the repo-local governance gap: each remaining
external dependency now has an explicit evidence entry, probe/manual evidence
shape, exit condition, and owner surface before it may leave
`external_blocked`.
