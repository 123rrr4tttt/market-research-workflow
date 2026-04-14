from __future__ import annotations

from sqlalchemy import text

from ...models.base import engine
from ..job_logger import complete_job, fail_job, start_job


def _ensure_aggregator_tables() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS aggregator"))
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS aggregator.documents_agg (
                    id BIGSERIAL PRIMARY KEY,
                    project_key VARCHAR(64) NOT NULL,
                    source_id BIGINT NULL,
                    doc_type VARCHAR(32) NOT NULL,
                    title TEXT NULL,
                    summary TEXT NULL,
                    publish_date DATE NULL,
                    uri TEXT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    source_pk BIGINT NOT NULL,
                    UNIQUE(project_key, source_pk)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS aggregator.market_metric_points_agg (
                    id BIGSERIAL PRIMARY KEY,
                    project_key VARCHAR(64) NOT NULL,
                    metric_key VARCHAR(128) NOT NULL,
                    date DATE NOT NULL,
                    value NUMERIC(18, 6) NOT NULL,
                    unit VARCHAR(32) NULL,
                    currency VARCHAR(16) NULL,
                    source_uri TEXT NULL,
                    source_pk BIGINT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE(project_key, source_pk)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS aggregator.price_observations_agg (
                    id BIGSERIAL PRIMARY KEY,
                    project_key VARCHAR(64) NOT NULL,
                    product_id BIGINT NOT NULL,
                    captured_at TIMESTAMPTZ NOT NULL,
                    price NUMERIC(18, 6) NOT NULL,
                    currency VARCHAR(16) NULL,
                    availability VARCHAR(32) NULL,
                    source_uri TEXT NULL,
                    source_pk BIGINT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE(project_key, source_pk)
                )
                """
            )
        )


def _cursor_value(project_key: str, object_name: str) -> int:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT cursor_value
                FROM public.project_sync_state
                WHERE project_key = :project_key AND object_name = :object_name
                """
            ),
            {"project_key": project_key, "object_name": object_name},
        ).first()
        if not row or row[0] is None:
            return 0
        try:
            return int(row[0])
        except Exception:
            return 0


def _save_cursor(project_key: str, object_name: str, value: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO public.project_sync_state(project_key, object_name, cursor_value, updated_at)
                VALUES (:project_key, :object_name, :cursor_value, now())
                ON CONFLICT (project_key, object_name)
                DO UPDATE SET cursor_value = EXCLUDED.cursor_value, updated_at = now()
                """
            ),
            {
                "project_key": project_key,
                "object_name": object_name,
                "cursor_value": str(value),
            },
        )


def sync_project_data_to_aggregator() -> dict:
    job_id = start_job("aggregator_sync", {})
    _ensure_aggregator_tables()
    totals = {"documents": 0, "market_metric_points": 0, "price_observations": 0}

    try:
        with engine.begin() as conn:
            projects = conn.execute(
                text("SELECT project_key, schema_name FROM public.projects WHERE enabled = true")
            ).fetchall()

        for project_key, schema_name in projects:
            # documents
            doc_cursor = _cursor_value(project_key, "documents")
            with engine.begin() as conn:
                conn.execute(
                    text(
                        f"""
                        INSERT INTO aggregator.documents_agg(project_key, source_id, doc_type, title, summary, publish_date, uri, source_pk)
                        SELECT :project_key, d.source_id, d.doc_type, d.title, d.summary, d.publish_date, d.uri, d.id
                        FROM "{schema_name}".documents d
                        WHERE d.id > :cursor
                        ON CONFLICT(project_key, source_pk) DO NOTHING
                        """
                    ),
                    {"project_key": project_key, "cursor": doc_cursor},
                )
                new_max = conn.execute(text(f'SELECT COALESCE(MAX(id), 0) FROM "{schema_name}".documents')).scalar() or 0
            _save_cursor(project_key, "documents", int(new_max))
            totals["documents"] += max(0, int(new_max) - doc_cursor)

            # metric points
            metric_cursor = _cursor_value(project_key, "market_metric_points")
            with engine.begin() as conn:
                conn.execute(
                    text(
                        f"""
                        INSERT INTO aggregator.market_metric_points_agg(project_key, metric_key, date, value, unit, currency, source_uri, source_pk)
                        SELECT :project_key, m.metric_key, m.date, m.value, m.unit, m.currency, m.source_uri, m.id
                        FROM "{schema_name}".market_metric_points m
                        WHERE m.id > :cursor
                        ON CONFLICT(project_key, source_pk) DO NOTHING
                        """
                    ),
                    {"project_key": project_key, "cursor": metric_cursor},
                )
                new_max = conn.execute(text(f'SELECT COALESCE(MAX(id), 0) FROM "{schema_name}".market_metric_points')).scalar() or 0
            _save_cursor(project_key, "market_metric_points", int(new_max))
            totals["market_metric_points"] += max(0, int(new_max) - metric_cursor)

            # price observations
            price_cursor = _cursor_value(project_key, "price_observations")
            with engine.begin() as conn:
                conn.execute(
                    text(
                        f"""
                        INSERT INTO aggregator.price_observations_agg(project_key, product_id, captured_at, price, currency, availability, source_uri, source_pk)
                        SELECT :project_key, p.product_id, p.captured_at, p.price, p.currency, p.availability, p.source_uri, p.id
                        FROM "{schema_name}".price_observations p
                        WHERE p.id > :cursor
                        ON CONFLICT(project_key, source_pk) DO NOTHING
                        """
                    ),
                    {"project_key": project_key, "cursor": price_cursor},
                )
                new_max = conn.execute(text(f'SELECT COALESCE(MAX(id), 0) FROM "{schema_name}".price_observations')).scalar() or 0
            _save_cursor(project_key, "price_observations", int(new_max))
            totals["price_observations"] += max(0, int(new_max) - price_cursor)

        complete_job(job_id, result=totals)
        return totals
    except Exception as exc:  # noqa: BLE001
        fail_job(job_id, str(exc))
        raise
