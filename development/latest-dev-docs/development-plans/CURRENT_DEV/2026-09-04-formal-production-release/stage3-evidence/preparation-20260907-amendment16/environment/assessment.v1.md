# Amendment 16 environment preparation

Status: READ_ONLY_PREPARATION_NOT_AUTHORITY. Candidate-bound: false. Contract 16 read in full. No suites, installation, service/container startup, database connection, source/lock/binding mutation or signing performed. Observations are local macOS arm64, not workflow parity. Probe outputs and command/exit/hash records are in `observations.v1.json`.

## Current observations

| Requirement | Observation | Exit | Readiness |
| --- | --- | --- | --- |
| Docker context | `docker context show`: desktop-linux | 0 | Selected context only |
| Docker daemon | `docker version`: Client 29.2.1/API 1.53; sandbox permission denied | 1 | Follow-up required |
| Docker unrestricted read | Same `docker version`, require_escalated, tool chunk a92e96: Cannot connect to Docker daemon | 1 | Daemon unavailable; raw output transcribed verbatim in docker-version-unrestricted.raw.log |
| Compose | `docker compose version`: v5.0.2 | 0 | CLI available; service capability untested |
| Buildx | `docker buildx version`: v0.31.1-desktop.1 | 0 | CLI available; builder execution untested |
| Node 22 workflow | `node --version`: v26.4.0 | 0 | Default major differs from required 22 |
| Node 22 bounded alternate | `/opt/homebrew/opt/node@22/bin/node --version`: missing | 127 | No Node 22 confirmed; not an exhaustive installation search |
| Python default | `python3 --version`: 3.14.7 | 0 | Default differs from workflow 3.11 |
| Python 3.11 | `python3.11 --version`: 3.11.15 | 0 | Interpreter available, dependencies not checked |
| Backend existing venv | `main/backend/.venv311/bin/python --version`: 3.11.14 | 0 | Interpreter available, not isolated candidate dependency proof |
| PostgreSQL tools | `psql`, `pg_isready`, `initdb`, `pg_ctl`, each `--version`: 18.3 Homebrew | 0 each | Tools available; no dedicated database provisioned or contacted |
| cosign | `cosign version`: executable missing | 127 | Not on current command path |
| syft | `syft version`: executable missing | 127 | Not on current command path |
| trivy | `trivy --version`: executable missing | 127 | Not on current command path |

Current `.github/workflows/backend-tests.yml` uses Node 22 and Python 3.11, Buildx setup v3, build provenance/SBOM outputs, and containerized `aquasec/trivy:0.67.2`. Therefore absent host trivy is not itself proof the workflow scanner cannot execute; daemon and qualified images are the concrete dependencies. Host syft/cosign absence is recorded, not promoted to an unconditional implementation requirement: current workflow uses Buildx attestations; signing remains separately unauthorized under contract 16. Frozen plan section Stage 3 requires SBOM/provenance/scans/signature evidence; versions and authority for the eventual signing implementation remain to be fixed by its owner.

## Reused v6 evidence (historical, not refreshed)

`../../v6/recovery-ops/report.v1.json` and `followup.v1.json` report Docker unavailable in both sandbox and unrestricted read. Their tool raw logs record Python 3.14.7, Compose v5.0.2, bandit 1.8.6 on Python 3.9.6, pip-audit 2.9.0 with LibreSSL warning. Gitleaks follow-up installed v8.24.2 by source selector, but version output only says `version is set by build process`; that text does not independently prove a binary semantic version. Those scanners were not rerun. Current refresh confirms the Docker availability gap persists.

## Next-candidate prerequisites and owners

| Gap identity | Required action before dependent rehearsal | Owner | blocked_by |
| --- | --- | --- | --- |
| ENV-DOCKER | Make an isolated approved Docker daemon/builder available and record context/resources; then validate service readiness | Stage 1/2 security/environment resource owner | Daemon unreachable on selected desktop-linux context |
| ENV-NODE22 | Select confirmed Node 22 executable and fix single-owner candidate dependency installation/lockfile | Stage 1/2 frontend owner | Default Node 26; bounded alternate missing |
| ENV-PY311 | Select Python 3.11 and isolated candidate dependencies, cwd/PYTHONPATH before long tests | Stage 1/2 backend/environment owner | Dependencies and isolation not tested in this preparation |
| ENV-DEDICATED-DB | Declare isolated test DB lifecycle, endpoint, version parity, cleanup and single owner; provision only within that owner's authority | Stage 1/2 security/environment owner | Dedicated service not provisioned; tool version alone is insufficient |
| ENV-EFFECT-ISOLATION | Cover Python/native/subprocess effects used by each test; classify gaps per test | Stage 1/2 security/environment owner | No isolation validation performed; DNS failure injection is insufficient |
| ENV-ARTIFACT | Rebuild three roles using candidate shape and fixed inputs; obtain SBOM/provenance and pinned container scanner evidence | Stage 1/2 build/supply-chain owner | Docker daemon and stable candidate inputs; host scanner absence may be bypassed by the specified workflow container |
| ENV-SIGNING | Fix verifier/signature tool requirement and explicit authority before any signing operation | External release/signing authority owner via supervisor | NO_SIGNING_WRITE remains; host cosign unavailable |

Integration owner remains original Stage 1/2 task `01a074e1-da0d-7a70-9c45-daff7b8bc9ad`; this preparation owns no runtime resource. Backend isolated non-service work can proceed after its own prerequisites without waiting for Docker/signing. Final candidate verification must bind final commit/tree and actual environment/log hashes. No aggregate or full-closure claim is made here.
