# r13p Stage 3 tests lane

Result: `REBUILD_REQUIRED · PRODUCTION_RELEASE_NOT_AUTHORIZED`.

The mode-preserved r13p successor aggregate completed with PostgreSQL over the fixture-required Unix socket: **1764 passed, 2 skipped, 10 failed, 4 warnings**. The three earlier TCP-only setup errors were environment misuse and are closed by a focused **3 passed** Unix-socket run. The remaining ten failures are deterministic candidate evidence drift and block the required successor/exact-byte/architecture/negative gates.

The r13p Compose argv repair is live in an isolated local project: database, Elasticsearch, Redis, backend, and Celery became healthy; shallow health returned `ok`. Deep health remained `degraded` only because the live provider key was intentionally unavailable, and the frontend profile was not included, so full-stack status stays `PARTIAL`.

All r13p test-owned databases, roles, containers, volumes, networks, and temporary paths were removed or moved recoverably to Trash. The r13o local stack was also removed only after explicit Supervisor authorization. `ops-scrapyd` and unrelated resources were not touched.
