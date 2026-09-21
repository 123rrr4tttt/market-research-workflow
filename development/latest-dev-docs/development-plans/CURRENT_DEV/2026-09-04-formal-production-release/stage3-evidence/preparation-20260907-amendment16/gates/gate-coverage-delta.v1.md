# Amendment 16 gate coverage preparation

Status: READ_ONLY_PREPARATION_NOT_CANDIDATE_EVIDENCE. Observed 2026-09-07 Asia/Shanghai. No tests, installs, services, builds, network requests, or source/binding edits performed. This file is create-only and non-authoritative.

Read amendment 16 completely. Reuse `../../v6/test-gates.final.v1.json` as the historical 23-family result inventory; do not rerun or replace it. Its candidate is commit `909eb608e538b6427bcbacca974f1efb05fef611`, tree `a60b795e509aa5dc479904a321fba32ed0ab9ab2`. Current checkout HEAD observed `3706655f372f6d34fc62683551b8c3d1f4ff8146`; workflow, backend Dockerfile and frontend package.json are modified. Current bytes are mutable preparation input, not an admitted successor. All commands below are inventory only and were NOT EXECUTED.

## Input identities

Paths 04/09/15/16 below are relative to the formal-production-release directory.

| Input | SHA256 |
| --- | --- |
| 04_production-deployment-stage-plan.v1.md | d04ae870b5d2a13afacdc7a07e9d5a89b7ab77e7b6c2d6cdd4bd2101151f76fa |
| 09_production-deployment-stage3-successor-contract.v1.md | 61d5b99ce8966b1bdb4eadf754ae03b7651026098b38da09dd46a69e773237be |
| 15_production-deployment-stage3-v6-contract.v1.md | f7d3637c5cc48eaf7396331c3657cc6cff42269dbf4ffab17af4f7a7a3170d5a |
| 16_stage-convergence-execution-amendment.v1.md | 316339cdfa538f66272802e31dd236c0838f1fcd093169d79408b81e816ded6f |
| stage3-evidence/v6/test-gates.final.v1.json | 88329083d77d683b8352e0f51849f3b6500c271087b3f22957e9de016b6730ad |
| .github/workflows/backend-tests.yml (root-relative, mutable) | a2340a6971fb24019bab96b730f9598be934d57e1df4ddbe263e8f41a32f8c98 |
| main/frontend-modern/package.json (root-relative, mutable) | e5f770eaebb634e6ba3f2c83a9ad1ce8ba0d4ebc790ed1bb460eefae0bd66f0c |

## Existing families: command and dependency supplement

Owners: B=Stage1/2 backend/architecture; F=Stage1/2 frontend; S=Stage1/2 security/environment; A=Stage1/2 build/supply-chain; I=Stage1/2 integration/final binding; V=original Stage3 validation task after successor admission; H=human/external authority owner. I owns rehearsal materialization and immutable successor, V owns final evidence. ROOT means final candidate root; BE means its main/backend; FE means its main/frontend-modern. Workflow step references identify exact multi-line commands or action inputs without inventing a replacement shell command. Unresolved command inputs remain blocked, never guessed.

Shared blocked_by C: admitted final candidate identity/environment not fixed. C blocks final acceptance, not independent Stage1/2 fixes. Shared difference E: workflow Ubuntu/Python3.11/Node22/pnpm11.22.0 versus historical v6 macOS/Node26.4.0; v6 backend temporary socket guard raises plain OSError and native isolation was incomplete. Stage2 DNS injection is not equivalent. Guard exceptions must not be changed to obtain PASS. Environment owner must bind PYTHONPATH, dedicated services and Python/native/subprocess isolation before execution.

| Existing family | Owner; dependency | Exact command or source entry | Guard/workflow difference; blocked_by beyond C |
| --- | --- | --- | --- |
| candidate_identity | I,V; final materialization | historical `v6/recovery-preflight/r1-final-clean.command.json`; ROOT `git rev-parse HEAD HEAD^{tree}` and `git status --porcelain` | identity command alone does not cover R1 hashes/parent/closure; final inputs unbound |
| fresh_r1_r2_r3 | I,V; identity and actual manifest | historical `v6/recovery-preflight/r1-final-clean.command.json`, `r3.command.json`, `r2-conformance-and-workflow.command.json` | synthetic R2 is contract test only; actual R2 separate below |
| architecture_registry_law_negative | B,V; root deps, registries/baseline/full implementation overlay | ROOT `python -m pytest tests -q -ra` (historical run.py) | no equivalent full-root job located in current workflow; E, historical missing candidate closure |
| backend_unit | B,V; BE deps, standards | BE `pytest -m "unit and not external and not flaky" -q` | E; historical failures not all source failures |
| backend_integration | B,S,V; dedicated services | BE `pytest -m "integration and not external and not flaky" -q` | workflow has no dedicated service provision in this job; E, service readiness |
| core_business | B,V; deps/services | BE `pytest -m "(unit or integration or contract or e2e) and not external" tests/core_business -q` | own job exists, absent from required-convergence needs; E |
| successor_runtime | B,S,V; services and full candidate fragments | BE `python -m pytest tests/successor_runtime -m 'not external' -q -ra` | historical interrupted run has no full verdict; no dedicated workflow job located; E |
| migration_graph | B,V; alembic deps | BE `alembic heads`; workflow migration-single-head-check also asserts exactly one `(head)` | graph alone does not execute upgrade/recovery; no DB used |
| production_compose_syntax | A,V; synthetic required env | workflow docker-config-check `docker compose -f main/ops/docker-compose.production.yml config --quiet` with that job's env | render only; no smoke, mount or image qualification implied |
| frontend_frozen_install | F,V; Node/pnpm and lockfile | FE `pnpm install --frozen-lockfile` | E; dependency/network availability |
| frontend_lint | F,V; frozen install | FE `pnpm lint` | E; historical 12 errors are not current results |
| frontend_typecheck_build | F,V; frozen install | FE `pnpm exec tsc -b`; `pnpm build` | separate workflow jobs, preserve both receipts; E |
| frontend_storybook | F,V; frozen install | FE `pnpm storybook:build` | historical unresolved three import; E |
| frontend_e2e | F,S,V; browser and dedicated backend/services | FE `pnpm exec playwright install --with-deps chromium`; `pnpm test:e2e` | workflow component-e2e does not provision backend; historical early-stop skips not completed cases; E |
| frontend_dependency_audit | F,S,V; lockfile/advisory data | FE `pnpm audit --prod --audit-level high` | retain below-threshold advisory and scanner coverage; E |
| bandit | S,V; scanner version/source | ROOT `bandit -q -r main/backend/app -x main/backend/tests --severity-level high --confidence-level high` | retain lower findings; historical B324 remains historical |
| gitleaks | S,V; history/scanner config | workflow security-check action `gitleaks/gitleaks-action@v2` | action is exact entry, not invented CLI; historical 346 findings require adjudication, not credential count |
| pip_audit | S,V; dependency resolution/advisory data | ROOT `pip-audit -r main/backend/requirements.txt --strict` | historical non-PyPI functorial-kit exception; non-PyPI coverage needs explicit evidence |
| postgresql_opt_in | S,B,V; dedicated owned cluster | `main/backend/scripts/run_successor_postgres_validation.py` explicit `--database-url` and child command; final URL/suite binding NOT_FIXED | runner requires Unix socket and owned disposable DB/role, rejects default admin DB; no default localhost probing; service/isolation/residue receipt |
| docker_full_stack | A,S,V; exclusive compose project/resources | workflow docker-config-check `docker compose -f main/ops/docker-compose.yml --profile "${{ github.event.inputs.test_profile || 'test' }}" up --build --abort-on-container-exit --exit-code-from backend-test backend-test` | job name does not prove actual full-stack paths; service/owned project isolation required; historical daemon unavailable not fresh observation |
| artifacts_rebuild_sbom_provenance_image_scan | A,V; pinned FROM, Docker/buildx, frozen lock | workflow artifact-metadata-check canonical/rebuild build-push-action steps, targets backend-runtime/frontend-runtime/migration-runner; image-vulnerability-scan-check lines 1081-1098 exact Trivy OCI commands | current mutable workflow adds separate builders and role-indexed evidence; not execution proof; artifact subjects and reproducibility unbound |
| remote_required_checks | V,H; admitted SHA hosted remotely | historical `v6/recovery-remote/readback.py` and unrestricted-readonly observations; next exact SHA endpoint NOT_FIXED | historical 422/unprotected branch not current live facts; remote SHA and enforcement readback |
| signature_registry | V,H; artifact subject/namespace/existing signature | command NOT_FIXED: digest, namespace, verifier identity/policy not yet bound | current workflow explicitly UNEXECUTED_AUTHORITY_REQUIRED; read-only verification separate from signing/publishing authority |

Every row retains historical result/evidence by reference to its same-named v6 family. No row has a new actual result: all current results are NOT_EXECUTED_PREPARATION_ONLY. Historical v6 statuses must not be carried into current source bytes.

## Required coverage corrections to the 23-family presentation

These are explicit subgates/receipts required by 04/09/15, not a claim that every item needs a new CI job.

| Subgate | Owner/dependency | Exact entry/command | Difference / blocked_by |
| --- | --- | --- | --- |
| actual-release-manifest-R2 | V; all real receipts/artifacts | ROOT `python3 scripts/formal_release/check_release_evidence.py --manifest <final-actual-manifest>` | placeholder cannot be executed until bound; synthetic workflow test cannot satisfy this |
| schema/migration service path | B,S,V; dedicated DB/es/redis | workflow schema-guard-check `docker compose -f main/ops/docker-compose.yml run --rm backend-test tests/integration/test_project_schema_guard_unittest.py -q` after its dedicated service setup | single-head PASS insufficient; existing schema job absent from required-convergence needs; safe resource binding required |
| exact-byte and full implementation selection | B,I,V; manifest overlay/DELETE/UPSERT | ROOT full tests entry above plus formal materializer's closure contract; precise new manifest NOT_FIXED | missing registries/baseline can be omitted by selection; deselected cases do not establish coverage |
| digest pins and no production checkout bind mount | A,V; all Docker/compose inputs | `python3 scripts/formal_release/check_static_production_contract.py` plus immutable input inspection | compose config syntax not sufficient; current dirty Docker changes unqualified |
| second independent clean rebuild per role | A,V; canonical role digests/build inputs | workflow artifact-metadata-check canonical-builder/rebuild-builder comparison steps | same candidate and platform required; non-bit-for-bit exception needs explicit difference domain, signed provenance and runtime equivalence, not just a mismatch waiver |
| dedicated PostgreSQL zero residue and owned resource cleanup | S,V; service execution receipts | validation runner above; workflow cleanup commands apply only to an explicitly owned project | no teardown PASS without before/after readback; no broad cleanup authorized here |
| warnings/skips/deselect/native abort/scanner exception ownership | every gate owner,V; logs/JUnit | deterministic receipt accounting over every executed command | separate denominators and interrupted/unexecuted identities; aggregation cannot sum overlapping tests |
| manifest subject/toolchain/run/hash closure and authority ceilings | I,V; final identity/all evidence | actual R2 command above; 09 sections 6-7 | final evidence unbound; external_effects and retained resources must be explicitly reported |

## Workflow entry coverage, without inventing new release requirements

Current `required-convergence-check` lists 13 direct dependencies. Existing workflow jobs `core-business-check` and `schema-guard-check` correspond to explicit frozen families but are absent from that aggregate. Full root architecture/registry/law/negative and successor-runtime selectors have no named equivalent job located. This is an aggregation/coverage question for Stage1/2; remote branch/ruleset could require other checks independently. Absence from this single aggregate alone does NOT establish missing live enforcement.

Other existing entries must be accounted for, but their mere existence does not upgrade them to frozen Stage3 hard gates:

| Existing entry | Owner; dependency | Exact command (BE unless ROOT stated) | Disposition / blocked_by |
| --- | --- | --- | --- |
| standards-check | B; Python | ROOT `python main/backend/scripts/check_api_layer_imports.py` | transitive dependency of backend jobs |
| llm-report-must-check | B; requirements | ROOT `python main/backend/scripts/check_llm_report_must_minset.py --artifact-dir artifacts/llm-report-must-check` | entry coverage confirmation; not automatically extra release gate |
| gateplus-guard-check | B; requirements/compat level BACKWARD | `GATEPLUS_ARTIFACT_DIR=.artifacts/gateplus ./scripts/gateplus_ci_guard.sh` | independent gateplus-required aggregate; live-required status separately read back |
| coverage-check | B; pytest-cov/core-path env | `pytest -m "(unit or integration) and not external" --cov=app --cov-report=term-missing --cov-report=xml:coverage.xml -q`; `python scripts/check_coverage_thresholds.py --coverage-file coverage.xml --core-paths "${CORE_COVERAGE_PATHS}" --core-threshold 100 --other-threshold 20` | retain command/env when applicable; coverage threshold not inferred from 04 |
| contract-check | B,S; services as used | `pytest -m "contract and not external" -q` | selector coverage confirm; backend unit/integration deselection does not cover it |
| e2e-check | B,S; services as used | `pytest -m "e2e and not external" -q` | backend e2e distinct from FE Playwright |
| flaky-observe | B; requirements | `pytest -m "flaky and not external" --junitxml=artifacts/flaky-junit.xml -q`; follow workflow registry/trend steps | explicitly observation and PR continue-on-error; preserve exclusions |
| contracts-governance-observe/contracts-required-check | B; contract modules and CONTRACTS_REQUIRED | exact workflow steps lines 883-982 | default CONTRACTS_REQUIRED=false; non-blocking label cannot imply release success |
| frontend named package checks | F; Node/browser depending script | FE `pnpm check:graph-force3d-frontend-contract`, other literal `check:*` scripts in package.json | finite entry list exists; scoped applicability owner confirms, not every helper automatically required |

## Handoff

Stage1/2 owners fix and rehearse in the unique candidate-shaped copy, then integration binds once. Stage3 must wait for admitted successor for final execution. Recheck this mutable workflow inventory at that boundary; no source file or previous evidence was changed here. Stage4 remains not admitted. NO_DEPLOY/NO_LIVE/NO_PRODUCTION_WRITE/NO_EXTERNAL_DELIVERY/NO_CANARY/NO_CUTOVER/NO_AUTHORITY_TRANSFER/NO_LEGACY_RETIREMENT/NO_PUSH/NO_REMOTE_MUTATION/NO_REGISTRY_WRITE/NO_SIGNING_WRITE remain in force.
