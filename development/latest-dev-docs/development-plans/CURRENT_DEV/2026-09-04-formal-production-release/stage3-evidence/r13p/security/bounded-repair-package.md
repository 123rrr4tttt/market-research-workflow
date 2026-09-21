# r13p bounded Stage 3 security repair package

Gate result: **FAILED** at the required HIGH/CRITICAL threshold. Trivy found only OS-package findings; it did not establish runtime reachability or exploitability. Backend and migration results are identical and are deduplicated into shared repair work.

## Exact critical findings

| Roles | Origin | Package | Installed | Fixed | CVE | Status |
|---|---|---|---|---|---|---|
| frontend | alpine | libcrypto3 | 3.3.3-r0 | 3.3.7-r0 | CVE-2026-31789 | fixed |
| frontend | alpine | libssl3 | 3.3.3-r0 | 3.3.7-r0 | CVE-2026-31789 | fixed |
| backend, migration-runner | debian | libperl5.40 | 5.40.1-6 | none reported | CVE-2026-13221 | affected |
| backend, migration-runner | debian | libperl5.40 | 5.40.1-6 | none reported | CVE-2026-42496 | fix_deferred |
| backend, migration-runner | debian | libperl5.40 | 5.40.1-6 | none reported | CVE-2026-8376 | affected |
| backend, migration-runner | debian | linux-libc-dev | 6.12.107-1 | none reported | CVE-2026-43185 | affected |
| backend, migration-runner | debian | perl | 5.40.1-6 | none reported | CVE-2026-13221 | affected |
| backend, migration-runner | debian | perl | 5.40.1-6 | none reported | CVE-2026-42496 | fix_deferred |
| backend, migration-runner | debian | perl | 5.40.1-6 | none reported | CVE-2026-8376 | affected |
| backend, migration-runner | debian | perl-base | 5.40.1-6 | none reported | CVE-2026-13221 | affected |
| backend, migration-runner | debian | perl-base | 5.40.1-6 | none reported | CVE-2026-42496 | fix_deferred |
| backend, migration-runner | debian | perl-base | 5.40.1-6 | none reported | CVE-2026-8376 | affected |
| backend, migration-runner | debian | perl-modules-5.40 | 5.40.1-6 | none reported | CVE-2026-13221 | affected |
| backend, migration-runner | debian | perl-modules-5.40 | 5.40.1-6 | none reported | CVE-2026-42496 | fix_deferred |
| backend, migration-runner | debian | perl-modules-5.40 | 5.40.1-6 | none reported | CVE-2026-8376 | affected |

## Bounded repair ownership

- `main/frontend-modern/Dockerfile:18`: refresh the pinned nginx Alpine runtime digest so the 36 reported findings reach their listed fixed versions; rebuild and require zero HIGH/CRITICAL findings.
- `main/backend/Dockerfile:1,11-16`: refresh the pinned Python slim base and keep build-only packages out of runtime layers where feasible. The current Debian 13.6 report provides no fixed version for 148 backend/migration observations; any remainder needs exact VEX/risk disposition, not silent suppression.
- Gitleaks: disposition all 410 redacted current-tree findings. Inspect the private-key signature in the vendored/reference README snapshot first; rotate/remove any real secret, and allowlist only verified non-secret fixtures with narrow paths/rules.

The complete package/version/CVE/role list is in `bounded-repair-package.json`.
