import json
import runpy
import sqlalchemy as sa
from sqlalchemy import MetaData

ns = runpy.run_path('/tmp/seed.py')
c9 = ns['c9']
engine = ns['engine']
from app.successor_runtime.substrate.postgres.models import project_tables
from scripts.c9_projection_rebuild import PostgresC9ProjectionRebuilder
from app.successor_runtime.substrate.postgres.projection_offsets import ProjectionOffsetKey

project = project_tables(MetaData(schema=ns['PROJECT_SCHEMA']), ns['PROJECT_SCHEMA'])
with engine.begin() as conn:
    source_digest, source_revision = c9._source_digest(conn, project, source_ref=c9.SOURCE_REF)
    key = ProjectionOffsetKey(c9.PROJECTOR_ID, c9.PROJECTOR_VERSION, 'successor_values', c9.SOURCE_REF, c9.SCOPE_INCARNATION)
    outcome = PostgresC9ProjectionRebuilder(conn, c9.SCOPE, tables=project).rebuild(
        key=key,
        source_revision=source_revision,
        source_digest=source_digest,
        source_ref=c9.SOURCE_REF,
    )
    counts = {
        'values': conn.execute(sa.select(sa.func.count()).select_from(project.successor_values)).scalar_one(),
        'receipts': conn.execute(sa.select(sa.func.count()).select_from(project.successor_receipts)).scalar_one(),
        'idempotency': conn.execute(sa.select(sa.func.count()).select_from(c9.PUBLIC_TABLES['runtime_idempotency'])).scalar_one(),
        'offsets': conn.execute(sa.select(sa.func.count()).select_from(c9.PUBLIC_TABLES['runtime_projection_offsets'])).scalar_one(),
    }
    print(json.dumps({'generation': outcome.generation, 'generation_activated': outcome.generation_activated, 'counts': counts, 'sink_statuses': [s.outcome for s in outcome.sink_statuses]}, sort_keys=True))
