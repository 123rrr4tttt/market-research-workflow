from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Literal, NoReturn, Protocol, TypeAlias, runtime_checkable

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter, ValidationError
from sqlalchemy import select, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql.schema import Table

from ..contracts import ApiEnvelope, ErrorCode, error_response
from ..contracts.responses import ok
from ..models.base import SessionLocal, engine
from ..models.base import Base
from ..models.information_topology_entities import InformationTopologyLink, InformationTopologyState
from ..models.entities import (
    ConfigState,
    Document,
    IngestChannel,
    KeywordHistory,
    KeywordPrior,
    MarketMetricPoint,
    MarketStat,
    PriceObservation,
    Product,
    Project,
    ResourcePoolUrl,
    ResourcePoolSiteEntry,
    SearchHistory,
    SourceLibraryItem,
    Source,
    Topic,
)
from ..models.writing_entities import WritingDocument, WritingDocumentCitation, WritingDocumentDraft
from ..services.llm.config_service import LlmConfigService
from ..services.llm.codex_cli import CodexCliChatModel
from ..services.llm.provider import get_chat_model
from ..services.projects import bind_project, bind_schema, normalize_project_key, project_schema_name
from ..services.projects.bootstrap import TENANT_TABLES, tenant_table_exists


router = APIRouter(prefix="/projects", tags=["projects"])
logger = logging.getLogger(__name__)
ProjectJsonObject: TypeAlias = dict[str, JsonValue]
_PROJECT_JSON_OBJECT_ADAPTER = TypeAdapter(ProjectJsonObject)
_PROJECT_MESSAGE_LIST_ADAPTER = TypeAdapter(list[JsonValue])


class ProjectJsonValueError(ValueError):
    def __init__(self, field: str) -> None:
        super().__init__(f"{field} must be a JSON object")


class ProjectMessageContentError(TypeError):
    def __init__(self) -> None:
        super().__init__("prompt factory response content must be JSON-compatible text")


class ProjectFieldTypeError(TypeError):
    def __init__(self, field: str, expected: str) -> None:
        super().__init__(f"project {field} must be {expected}")


class ProjectSeedConnectionError(TypeError):
    def __init__(self) -> None:
        super().__init__("project seed connection does not expose a DBAPI cursor")


class ProjectRecordProjectionError(TypeError):
    def __init__(self) -> None:
        super().__init__("project record projection is invalid")


class PromptFactoryResponseError(TypeError):
    def __init__(self) -> None:
        super().__init__("prompt factory response must contain a services array")


def _parse_project_json_object(value: object, *, field: str) -> ProjectJsonObject:
    try:
        return _PROJECT_JSON_OBJECT_ADAPTER.validate_python(value, strict=True)
    except ValidationError as exc:
        raise ProjectJsonValueError(field) from exc


def _project_message_content_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        raise ProjectMessageContentError
    try:
        content = _PROJECT_MESSAGE_LIST_ADAPTER.validate_python(value, strict=True)
    except ValidationError as exc:
        raise ProjectMessageContentError from exc
    return "\n".join(
        item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
        for item in content
    )


@runtime_checkable
class _SeedCursor(Protocol):
    def execute(self, statement: str) -> object: ...

    def close(self) -> None: ...


@runtime_checkable
class _SeedDriverConnection(Protocol):
    def cursor(self) -> _SeedCursor: ...


class ProjectRecordProjection(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_key: str
    name: str
    schema_name: str
    enabled: bool
    is_active: bool


class ProjectListItem(ProjectRecordProjection):
    archived: bool
    schema_ready: bool
    has_worker_fixture: bool
    nightly_matrix_eligible: bool


class ProjectListData(BaseModel):
    items: list[ProjectListItem]


class ProjectCreatedData(BaseModel):
    id: int
    schema_name: str


class ProjectInjectedData(BaseModel):
    project_key: str
    name: str
    schema_name: str
    source_project_key: str
    activated: bool
    copied_counts: dict[str, int]


class ProjectAutoCreatedData(BaseModel):
    project_key: str
    name: str
    schema_name: str
    source_project_key: str
    activated: bool
    copied_counts: dict[str, int]
    created_mode: Literal["inject_initial", "create_empty"]
    template_project_key: str
    llm_configs_applied: int


class ProjectAutoEmptyData(BaseModel):
    project_key: str
    name: str
    schema_name: str
    activated: bool
    copied_counts: dict[str, int]
    created_mode: Literal["create_empty"]
    template_project_key: str
    llm_configs_applied: int


class ProjectUpdatedData(BaseModel):
    project_key: str


class ProjectUpdatedWithFallbackData(ProjectUpdatedData):
    fallback_active_project_key: str


class ProjectArchiveData(BaseModel):
    project_key: str
    archived: bool


class ProjectActivationData(BaseModel):
    active_project_key: str


class ProjectArchiveDeleteData(BaseModel):
    project_key: str
    deleted: bool
    archived: bool


class ProjectHardDeleteData(BaseModel):
    project_key: str
    deleted: bool
    hard: bool


_PROJECT_TEXT_FIELDS: TypeAlias = Literal["project_key", "name", "schema_name"]
_PROJECT_BOOL_FIELDS: TypeAlias = Literal["enabled", "is_active"]


def _project_text(record: Project, field: _PROJECT_TEXT_FIELDS) -> str:
    value: object = getattr(record, field)
    if not isinstance(value, str):
        raise ProjectFieldTypeError(field, "a string")
    return value


def _project_bool(record: Project, field: _PROJECT_BOOL_FIELDS) -> bool:
    value: object = getattr(record, field)
    if not isinstance(value, bool):
        raise ProjectFieldTypeError(field, "a boolean")
    return value


def _set_project_text(record: Project, field: _PROJECT_TEXT_FIELDS, value: str) -> None:
    setattr(record, field, value)


def _set_project_bool(record: Project, field: _PROJECT_BOOL_FIELDS, value: bool) -> None:
    setattr(record, field, value)


def _new_project(
    *,
    project_key: str,
    name: str,
    schema_name: str,
    enabled: bool,
    is_active: bool,
) -> Project:
    project = Project()
    _set_project_text(project, "project_key", project_key)
    _set_project_text(project, "name", name)
    _set_project_text(project, "schema_name", schema_name)
    _set_project_bool(project, "enabled", enabled)
    _set_project_bool(project, "is_active", is_active)
    return project


def _raise_invalid_input(message: str, *, status_code: int = 400) -> NoReturn:
    raise HTTPException(
        status_code=status_code,
        detail=error_response(
            ErrorCode.INVALID_INPUT,
            message,
        ),
    )


def _raise_not_found(message: str) -> NoReturn:
    raise HTTPException(
        status_code=404,
        detail=error_response(
            ErrorCode.NOT_FOUND,
            message,
        ),
    )


def _raise_internal_error(message: str) -> NoReturn:
    raise HTTPException(
        status_code=500,
        detail=error_response(
            ErrorCode.INTERNAL_ERROR,
            message,
        ),
    )


class CreateProjectPayload(BaseModel):
    project_key: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    enabled: bool = True


class UpdateProjectPayload(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    enabled: bool | None = None


class InjectInitialProjectPayload(BaseModel):
    project_key: str = Field(..., min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    source_project_key: str = Field(default="demo_proj", min_length=1, max_length=64)
    overwrite: bool = False
    activate: bool = True


class AutoLlmConfigPayload(BaseModel):
    service_name: str = Field(..., min_length=1, max_length=64)
    description: str | None = None
    system_prompt: str | None = None
    user_prompt_template: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    enabled: bool = True

    def values(self) -> ProjectLlmConfigPayload:
        return ProjectLlmConfigPayload(
            description=self.description,
            system_prompt=self.system_prompt,
            user_prompt_template=self.user_prompt_template,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            top_p=self.top_p,
            presence_penalty=self.presence_penalty,
            frequency_penalty=self.frequency_penalty,
            enabled=self.enabled,
        )


class ProjectLlmConfigPayload(BaseModel):
    description: str | None = None
    system_prompt: str | None = None
    user_prompt_template: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    enabled: bool = True


class GeneratedPromptServicePayload(ProjectLlmConfigPayload):
    service_name: str


class AutoCreateProjectPayload(BaseModel):
    project_name: str = Field(..., min_length=1, max_length=255)
    project_key: str | None = Field(default=None, min_length=1, max_length=64)
    template_project_key: str = Field(default="demo_proj", min_length=1, max_length=64)
    activate: bool = True
    copy_initial_data: bool = True
    llm_configs: list[AutoLlmConfigPayload] = Field(default_factory=list)


def _resolve_inject_target_key(raw_project_key: str, *, source_key: str, overwrite: bool) -> str:
    if not str(raw_project_key or "").strip():
        _raise_invalid_input("project_key is required for inject-initial")
    target_key = normalize_project_key(raw_project_key)
    if target_key == "public":
        _raise_invalid_input("project_key is reserved", status_code=409)
    if target_key == "default" and not overwrite:
        _raise_invalid_input("project_key is reserved (set overwrite=true to replace default)", status_code=409)
    return target_key


# Seed/inject path uses a safe subset of tenant tables (exclude embeddings/vector + llm configs).
INITIAL_PROJECT_TABLES: list[Table] = [
    Source.__table__,
    Document.__table__,
    MarketStat.__table__,
    ConfigState.__table__,
    SearchHistory.__table__,
    KeywordHistory.__table__,
    KeywordPrior.__table__,
    Topic.__table__,
    IngestChannel.__table__,
    SourceLibraryItem.__table__,
    MarketMetricPoint.__table__,
    Product.__table__,
    PriceObservation.__table__,
    ResourcePoolUrl.__table__,
    ResourcePoolSiteEntry.__table__,
    WritingDocument.__table__,
    WritingDocumentDraft.__table__,
    WritingDocumentCitation.__table__,
]


_JSON_UDT_NAMES = {"json", "jsonb"}


def _quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _column_udt_name(column: dict[str, object]) -> str:
    return str(column.get("udt_name") or column.get("data_type") or "").lower()


def _initial_project_column_metadata(
    conn: Connection,
    *,
    schema_name: str,
    table_name: str,
) -> list[dict[str, object]]:
    result = conn.execute(
        text(
            """
            SELECT column_name, udt_name, data_type, ordinal_position
            FROM information_schema.columns
            WHERE table_schema=:schema_name
              AND table_name=:table_name
              AND is_generated='NEVER'
            ORDER BY ordinal_position
            """
        ),
        {"schema_name": schema_name, "table_name": table_name},
    )
    return [dict(row) for row in result.mappings().all()]


def _initial_project_copy_expression(
    source_column: dict[str, object],
    target_column: dict[str, object],
) -> str:
    source_expr = _quote_ident(str(source_column["column_name"]))
    target_udt = _column_udt_name(target_column)
    if target_udt not in _JSON_UDT_NAMES:
        return source_expr

    source_udt = _column_udt_name(source_column)
    if target_udt == "jsonb":
        if source_udt == "jsonb":
            return source_expr
        return f"{source_expr}::jsonb"

    if source_udt == "json":
        return source_expr
    return f"{source_expr}::json"


def _build_initial_project_copy_insert_sql(
    *,
    source_schema: str,
    target_schema: str,
    table_name: str,
    source_columns: list[dict[str, object]],
    target_columns: list[dict[str, object]],
) -> str | None:
    source_by_name = {str(column["column_name"]): column for column in source_columns}
    copy_pairs = [
        (target_column, source_by_name[str(target_column["column_name"])])
        for target_column in target_columns
        if str(target_column["column_name"]) in source_by_name
    ]
    if not copy_pairs:
        return None

    target_column_sql = ", ".join(_quote_ident(str(target["column_name"])) for target, _source in copy_pairs)
    source_expr_sql = ", ".join(
        _initial_project_copy_expression(source, target) for target, source in copy_pairs
    )
    return (
        f"INSERT INTO {_quote_ident(target_schema)}.{_quote_ident(table_name)} ({target_column_sql}) "
        f"SELECT {source_expr_sql} FROM {_quote_ident(source_schema)}.{_quote_ident(table_name)}"
    )


def _copy_initial_project_table(
    conn: Connection,
    *,
    source_schema: str,
    target_schema: str,
    table_name: str,
) -> int:
    conn.execute(
        text(f"TRUNCATE TABLE {_quote_ident(target_schema)}.{_quote_ident(table_name)} RESTART IDENTITY CASCADE")
    )
    source_columns = _initial_project_column_metadata(conn, schema_name=source_schema, table_name=table_name)
    target_columns = _initial_project_column_metadata(conn, schema_name=target_schema, table_name=table_name)
    copy_sql = _build_initial_project_copy_insert_sql(
        source_schema=source_schema,
        target_schema=target_schema,
        table_name=table_name,
        source_columns=source_columns,
        target_columns=target_columns,
    )
    if copy_sql is None:
        logger.info(
            "inject_initial_project_copy_skipped table=%s source_schema=%s target_schema=%s reason=no_common_columns",
            table_name,
            source_schema,
            target_schema,
        )
        return 0

    inserted = conn.execute(text(copy_sql))
    return int(inserted.rowcount or 0)


llm_config_service = LlmConfigService()


def _backend_root_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def _locate_demo_seed_file() -> Path | None:
    seed_dir = _backend_root_dir() / "seed_data"
    candidates = list(seed_dir.glob("project_demo_proj*.sql"))
    if not candidates:
        return None

    def _version_key(path: Path) -> tuple[int, ...]:
        # e.g. project_demo_proj_v0.9-rc2.0.sql -> (0, 9, 2, 0)
        nums = re.findall(r"\d+", path.name)
        return tuple(int(n) for n in nums) if nums else (0,)

    return sorted(candidates, key=_version_key)[-1]


def _demo_schema_has_seed_data(schema_name: str) -> bool:
    with engine.begin() as conn:
        table_exists = conn.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema=:schema AND table_name='documents')"
            ),
            {"schema": schema_name},
        ).scalar()
        if not table_exists:
            return False
        count = conn.execute(text(f'SELECT COUNT(*) FROM "{schema_name}"."documents"')).scalar()
        return int(count or 0) > 0


def _execute_seed_sql(conn: Connection, sql: str) -> None:
    """
    Execute pg_dump data SQL without passing SQLAlchemy's empty parameter mapping.

    The bundled seed can contain literal percent signs in crawled page bodies.
    Passing it through exec_driver_sql can make psycopg2 interpret SQLAlchemy's
    immutable empty mapping as DBAPI parameters and raise "dict is not a sequence".
    """
    raw_connection = conn.connection
    driver_connection_value: object = raw_connection.driver_connection
    if not isinstance(driver_connection_value, _SeedDriverConnection):
        raise ProjectSeedConnectionError
    driver_connection = driver_connection_value
    cursor = driver_connection.cursor()
    try:
        cursor.execute(sql)
    finally:
        cursor.close()


def _filter_seed_sql_text(sql_text: str) -> str:
    filtered_lines: list[str] = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if re.search(r"pg_catalog\.setval", line, re.IGNORECASE):
            continue
        if re.match(r"\\(?:un)?restrict\b", stripped):
            continue
        if re.match(r"SET\s+transaction_timeout\b", stripped, re.IGNORECASE):
            continue
        filtered_lines.append(line)
    return "\n".join(filtered_lines)


def _bootstrap_demo_seed_if_needed(source_key: str) -> None:
    if source_key != "demo_proj":
        return
    source_schema = project_schema_name(source_key)
    if _demo_schema_has_seed_data(source_schema):
        return

    seed_file = _locate_demo_seed_file()
    if not seed_file:
        _raise_internal_error("demo seed file not found under backend/seed_data")

    sql_text = seed_file.read_text(encoding="utf-8")
    filtered_sql = _filter_seed_sql_text(sql_text)

    _create_tenant_tables_best_effort(source_schema)

    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{source_schema}"'))
        _execute_seed_sql(conn, filtered_sql)

    # Ensure full tenant table structure + schema-local id sequence defaults.
    _create_tenant_tables_best_effort(source_schema)

    with bind_schema("public"):
        with SessionLocal() as session:
            row = session.execute(select(Project).where(Project.project_key == source_key)).scalar_one_or_none()
            if row is None:
                session.add(
                    _new_project(
                        project_key=source_key,
                        name="Demo Project",
                        schema_name=source_schema,
                        enabled=True,
                        is_active=False,
                    )
                )
            else:
                _set_project_text(row, "schema_name", source_schema)
                _set_project_bool(row, "enabled", True)
            session.commit()
PROMPT_FACTORY_SERVICE_NAME = "prompt_factory"
PROMPT_FACTORY_TARGET_SERVICES = [
    "keyword_generation",
    "social_keyword_generation",
    "policy_extraction",
    "market_info_extraction",
    "entities_relations_extraction",
    "site_entry_classification",
    "document_classification",
]


def _safe_parse_json_from_text(raw: str) -> ProjectJsonObject | None:
    text = (raw or "").strip()
    if not text:
        return None
    # direct json
    try:
        parsed: object = json.loads(text)
        return _parse_project_json_object(parsed, field="prompt factory response")
    except (json.JSONDecodeError, ProjectJsonValueError):
        pass
    # fenced json
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            candidate = part.strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            try:
                parsed = json.loads(candidate)
                return _parse_project_json_object(parsed, field="prompt factory fenced response")
            except (json.JSONDecodeError, ProjectJsonValueError):
                continue
    return None


def _fallback_prompt_factory_bundle(requirement: str) -> dict[str, ProjectLlmConfigPayload]:
    return {
        service_name: ProjectLlmConfigPayload(
            description=f"Auto-generated by prompt_factory for {service_name}",
            user_prompt_template=(
                f"[Project Requirement]\n{requirement}\n\n"
                f"[Target Service]\n{service_name}\n\n"
                "Generate output that is directly usable by this service. "
                "Keep constraints explicit, avoid ambiguity, and prioritize stable structured fields."
            ),
            enabled=True,
        )
        for service_name in PROMPT_FACTORY_TARGET_SERVICES
    }


def _invoke_prompt_factory_bundle(
    requirement: str,
    factory_payload: ProjectLlmConfigPayload,
) -> dict[str, ProjectLlmConfigPayload]:
    model = get_chat_model(
        model=factory_payload.model,
        temperature=factory_payload.temperature if factory_payload.temperature is not None else 0.2,
        max_tokens=factory_payload.max_tokens if factory_payload.max_tokens is not None else 2400,
    )
    instruction = (
        "You are Prompt Factory. Generate prompt configurations for downstream services.\n"
        "Return strict JSON only with shape:\n"
        "{"
        '"services":[{"service_name":"...","description":"...","system_prompt":"...","user_prompt_template":"...","enabled":true}]'
        "}\n"
        f"Target services: {', '.join(PROMPT_FACTORY_TARGET_SERVICES)}\n"
        f"Project requirement:\n{requirement}\n"
        "Rules:\n"
        "1) Include all target services exactly once.\n"
        "2) Make user_prompt_template concrete and executable.\n"
        "3) Keep language concise.\n"
        "4) enabled=true.\n"
    )
    if isinstance(model, CodexCliChatModel):
        response = model.invoke(instruction)
    else:
        response = model.with_retry().invoke(instruction)
    content = _project_message_content_text(response.content)
    parsed = _safe_parse_json_from_text(content)
    services = parsed.get("services") if parsed is not None else None
    if not isinstance(services, list):
        raise PromptFactoryResponseError

    built: dict[str, ProjectLlmConfigPayload] = {}
    for item in services:
        if not isinstance(item, dict):
            continue
        try:
            generated = GeneratedPromptServicePayload.model_validate(item)
        except ValidationError:
            continue
        service_name = generated.service_name.strip()
        if service_name not in PROMPT_FACTORY_TARGET_SERVICES:
            continue
        built[service_name] = ProjectLlmConfigPayload(
            description=generated.description or f"Generated by prompt_factory for {service_name}",
            system_prompt=generated.system_prompt,
            user_prompt_template=generated.user_prompt_template,
            enabled=generated.enabled,
        )
    return built


def _generate_prompt_factory_bundle(
    requirement: str,
    factory_payload: ProjectLlmConfigPayload,
) -> dict[str, ProjectLlmConfigPayload]:
    try:
        built = _invoke_prompt_factory_bundle(requirement, factory_payload)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        logger.warning("prompt_factory generation fallback due to error: %s", exc)
        return _fallback_prompt_factory_bundle(requirement)
    for service_name, fallback_payload in _fallback_prompt_factory_bundle(requirement).items():
        built.setdefault(service_name, fallback_payload)
    return built


def _build_auto_project_key(project_name: str, project_key: str | None) -> str:
    explicit = normalize_project_key(project_key or "")
    if explicit:
        return explicit
    base = normalize_project_key(project_name)
    if not base or base == "default":
        base = "project"
    suffix = int(time.time() * 1000) % 1000000
    return normalize_project_key(f"{base}_{suffix}")


def _project_exists(project_key: str) -> bool:
    normalized = normalize_project_key(project_key)
    with bind_schema("public"):
        with SessionLocal() as session:
            row = session.execute(select(Project).where(Project.project_key == normalized)).scalar_one_or_none()
            return row is not None


def _project_projection(row: Project) -> ProjectRecordProjection:
    try:
        return ProjectRecordProjection.model_validate(row)
    except ValidationError as exc:
        raise ProjectRecordProjectionError from exc


def _project_injected_data(value: object, *, source_project_key: str) -> ProjectInjectedData:
    try:
        envelope = ApiEnvelope[ProjectInjectedData].model_validate(value)
    except ValidationError:
        direct = _parse_project_json_object(value, field="project injection result")
        direct.setdefault("source_project_key", source_project_key)
        return ProjectInjectedData.model_validate(direct)
    if envelope.data is None:
        _raise_internal_error("initial project injection returned no data")
    return envelope.data


def _project_list_item(row: Project) -> ProjectListItem:
    project = _project_projection(row)
    enabled = project.enabled
    schema_name = project.schema_name.strip()
    archived = not enabled
    schema_ready = (
        bool(schema_name)
        and schema_name != "public"
        and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", schema_name) is not None
    )
    has_worker_fixture = enabled and schema_ready
    nightly_matrix_eligible = enabled and schema_ready and has_worker_fixture
    return ProjectListItem(
        **project.model_dump(),
        archived=archived,
        schema_ready=schema_ready,
        has_worker_fixture=has_worker_fixture,
        nightly_matrix_eligible=nightly_matrix_eligible,
    )


def _create_tenant_tables_best_effort(schema_name: str) -> None:
    """
    Create tenant tables, but tolerate missing pgvector extension by
    skipping only the embeddings table instead of failing project creation.
    """
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
    for table in TENANT_TABLES:
        with engine.begin() as conn:
            conn.execute(text(f'SET search_path TO "{schema_name}", public'))
            if tenant_table_exists(
                conn,
                schema_name=schema_name,
                table_name=table.name,
            ):
                continue
            try:
                table.create(bind=conn, checkfirst=False)
            except SQLAlchemyError as exc:
                table_name = table.name
                message = str(exc).lower()
                if table_name == "embeddings" and "vector" in message and "does not exist" in message:
                    logger.warning(
                        "skip embeddings table for schema=%s because pgvector extension is unavailable: %s",
                        schema_name,
                        exc,
                    )
                    continue
                raise
    _ensure_tenant_id_sequences(schema_name)


def _ensure_tenant_id_sequences(schema_name: str) -> None:
    """
    Ensure every tenant table uses schema-local id sequence default.

    This prevents cross-schema sequence drift such as:
    project_x.table.id DEFAULT nextval('project_default.table_id_seq'::regclass)
    """
    table_names = [t.name for t in TENANT_TABLES if "id" in t.c]
    for table_name in table_names:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    DO $$
                    DECLARE
                      seq_qualified text := format('%I.%I_id_seq', :schema_name, :table_name);
                      table_qualified text := format('%I.%I', :schema_name, :table_name);
                      has_table regclass;
                    BEGIN
                      EXECUTE format('SELECT to_regclass(%L)', table_qualified) INTO has_table;
                      IF has_table IS NULL THEN
                        RETURN;
                      END IF;

                      EXECUTE format('CREATE SEQUENCE IF NOT EXISTS %s', seq_qualified);
                      EXECUTE format('ALTER SEQUENCE %s OWNED BY %I.%I.id', seq_qualified, :schema_name, :table_name);
                      EXECUTE format(
                        'ALTER TABLE %I.%I ALTER COLUMN id SET DEFAULT nextval(%L::regclass)',
                        :schema_name, :table_name, seq_qualified
                      );
                      EXECUTE format(
                        'SELECT setval(%L, COALESCE((SELECT MAX(id) FROM %I.%I), 0) + 1, false)',
                        seq_qualified, :schema_name, :table_name
                      );
                    END$$;
                    """
                ),
                {"schema_name": schema_name, "table_name": table_name},
            )


def _apply_llm_configs_to_project(project_key: str, llm_configs: list[AutoLlmConfigPayload]) -> int:
    if not llm_configs:
        return 0
    normalized = normalize_project_key(project_key)
    merged_payload: dict[str, ProjectLlmConfigPayload] = {}

    # 1) user provided configs (highest priority)
    for item in llm_configs:
        service_name = item.service_name.strip()
        if not service_name:
            continue
        merged_payload[service_name] = item.values()

    # 2) if prompt_factory exists, auto-generate prompt bundle for core services
    factory_payload = merged_payload.get(PROMPT_FACTORY_SERVICE_NAME)
    if factory_payload is not None:
        requirement = (factory_payload.user_prompt_template or "").strip() or "general market intelligence"
        factory_payload = factory_payload.model_copy(
            update={
                "description": factory_payload.description
                if factory_payload.description is not None
                else "Prompt factory: generate/maintain prompts for downstream services based on project requirement.",
                "system_prompt": factory_payload.system_prompt
                if factory_payload.system_prompt is not None
                else (
                    "You are Prompt Factory. Produce high-quality prompts for downstream modules "
                    "with strict JSON-compatible output."
                ),
                "user_prompt_template": factory_payload.user_prompt_template
                if factory_payload.user_prompt_template is not None
                else requirement,
                "enabled": factory_payload.enabled,
            }
        )
        merged_payload[PROMPT_FACTORY_SERVICE_NAME] = factory_payload
        generated_bundle = _generate_prompt_factory_bundle(requirement, factory_payload)
        for service_name, generated_payload in generated_bundle.items():
            merged_payload.setdefault(service_name, generated_payload)

    applied = 0
    with bind_project(normalized):
        with SessionLocal() as db:
            for service_name, payload in merged_payload.items():
                llm_config_service.upsert_config(
                    db,
                    service_name,
                    payload.model_dump(exclude_none=True),
                )
                applied += 1
    return applied


@router.get("", response_model=ApiEnvelope[ProjectListData])
def list_projects() -> ProjectJsonObject:
    # Control-plane data always read from public schema.
    try:
        with bind_schema("public"):
            with SessionLocal() as session:
                rows = session.execute(select(Project).order_by(Project.id.asc())).scalars().all()
                data = ProjectListData(items=[_project_list_item(row) for row in rows])
                return ok(data.model_dump())
    except SQLAlchemyError as exc:
        logger.warning("project_list_degraded error=%s", exc.__class__.__name__)
        return ok(ProjectListData(items=[]).model_dump())


@router.post("", response_model=ApiEnvelope[ProjectCreatedData])
def create_project(payload: CreateProjectPayload) -> ProjectJsonObject:
    normalized_key = normalize_project_key(payload.project_key)
    if normalized_key in ("public", "default"):
        _raise_invalid_input("project_key is reserved", status_code=409)
    schema_name = project_schema_name(normalized_key)

    with bind_schema("public"):
        with SessionLocal() as session:
            existed = session.execute(
                select(Project).where(Project.project_key == normalized_key)
            ).scalar_one_or_none()
            if existed:
                _raise_invalid_input("project_key already exists", status_code=409)

            row = _new_project(
                project_key=normalized_key,
                name=payload.name,
                schema_name=schema_name,
                enabled=payload.enabled,
                is_active=False,
            )
            session.add(row)
            session.commit()
            session.refresh(row)

    # Initialize tenant tables in target schema (best-effort for optional pgvector).
    _create_tenant_tables_best_effort(schema_name)

    created = _project_projection(row)
    return ok(ProjectCreatedData(id=created.id, schema_name=schema_name).model_dump())


@router.post("/inject-initial", response_model=ApiEnvelope[ProjectInjectedData])
def inject_initial_project(payload: InjectInitialProjectPayload) -> ProjectJsonObject:
    source_project_key_raw = (payload.source_project_key or "").strip()
    if not source_project_key_raw:
        _raise_invalid_input("source_project_key is required")
    source_key = normalize_project_key(source_project_key_raw)
    target_key = _resolve_inject_target_key(
        payload.project_key,
        source_key=source_key,
        overwrite=bool(payload.overwrite),
    )
    source_schema = project_schema_name(source_key)
    target_schema = project_schema_name(target_key)
    target_name = (payload.name or f"{source_key}（初始注入）").strip()

    # New-deploy convenience: lazily bootstrap demo template from bundled seed archive.
    _bootstrap_demo_seed_if_needed(source_key)

    with engine.begin() as conn:
        source_exists = conn.execute(
            text("SELECT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name=:s)"),
            {"s": source_schema},
        ).scalar()
        if not source_exists:
            _raise_not_found(f"source project schema not found: {source_schema}")

    with bind_schema("public"):
        with SessionLocal() as session:
            src_project = session.execute(select(Project).where(Project.project_key == source_key)).scalar_one_or_none()
            if src_project is None:
                _raise_not_found(f"source project not found: {source_key}")

            existed = session.execute(select(Project).where(Project.project_key == target_key)).scalar_one_or_none()
            if existed and not payload.overwrite:
                _raise_invalid_input("project_key already exists (set overwrite=true)", status_code=409)

            if existed and payload.overwrite:
                session.delete(existed)
                session.commit()
                with engine.begin() as conn:
                    conn.execute(text(f'DROP SCHEMA IF EXISTS "{target_schema}" CASCADE'))

            row = _new_project(
                project_key=target_key,
                name=target_name,
                schema_name=target_schema,
                enabled=True,
                is_active=False,
            )
            session.add(row)
            session.commit()
            session.refresh(row)

    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{target_schema}"'))
        conn.execute(text(f'SET search_path TO "{target_schema}"'))
        Base.metadata.create_all(bind=conn, tables=INITIAL_PROJECT_TABLES, checkfirst=True)
        # Topology tables are project-local but never cloned from the seed
        # project's structural state; new projects start with empty topology.
        InformationTopologyState.__table__.create(bind=conn, checkfirst=True)
        InformationTopologyLink.__table__.create(bind=conn, checkfirst=True)

        copied_counts: dict[str, int] = {}
        # Copy only tables that exist in source schema.
        for table in INITIAL_PROJECT_TABLES:
            tname = table.name
            source_table_exists = conn.execute(
                text(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema=:schema AND table_name=:table)"
                ),
                {"schema": source_schema, "table": tname},
            ).scalar()
            if not source_table_exists:
                copied_counts[tname] = 0
                continue
            copied_counts[tname] = _copy_initial_project_table(
                conn,
                source_schema=source_schema,
                target_schema=target_schema,
                table_name=tname,
            )
            # best-effort sequence alignment for id-based tables
            try:
                conn.execute(
                    text(
                        """
                        DO $$
                        DECLARE seq_name text;
                        BEGIN
                          SELECT pg_get_serial_sequence(format('%I.%I', :schema_name, :table_name), 'id') INTO seq_name;
                          IF seq_name IS NOT NULL THEN
                            EXECUTE format(
                              'SELECT setval(%L, COALESCE((SELECT MAX(id) FROM %I.%I), 0) + 1, false)',
                              seq_name, :schema_name, :table_name
                            );
                          END IF;
                        END$$;
                        """
                    ),
                    {"schema_name": target_schema, "table_name": tname},
                )
            except SQLAlchemyError:
                # not all copied tables have id sequences; ignore
                pass

    # Ensure inject path has full tenant tables + schema-local id sequence defaults.
    _create_tenant_tables_best_effort(target_schema)

    if payload.activate:
        with bind_schema("public"):
            with SessionLocal() as session:
                all_rows = session.execute(select(Project)).scalars().all()
                for p in all_rows:
                    _set_project_bool(p, "is_active", _project_text(p, "project_key") == target_key)
                session.commit()

    return ok(
        ProjectInjectedData(
            project_key=target_key,
            name=target_name,
            schema_name=target_schema,
            source_project_key=source_key,
            activated=payload.activate,
            copied_counts=copied_counts,
        ).model_dump()
    )


@router.post(
    "/auto-create",
    response_model=ApiEnvelope[ProjectAutoCreatedData | ProjectAutoEmptyData],
)
def auto_create_project(payload: AutoCreateProjectPayload) -> ProjectJsonObject:
    target_key = _build_auto_project_key(payload.project_name, payload.project_key)
    if target_key in ("public", "default"):
        _raise_invalid_input("project_key is reserved", status_code=409)
    if _project_exists(target_key):
        _raise_invalid_input("project_key already exists", status_code=409)

    template_key = normalize_project_key(payload.template_project_key)
    if payload.copy_initial_data:
        if not _project_exists(template_key):
            _raise_not_found(f"template project not found: {template_key}")
        created_response = inject_initial_project(
            InjectInitialProjectPayload(
                project_key=target_key,
                name=payload.project_name,
                source_project_key=template_key,
                overwrite=False,
                activate=payload.activate,
            )
        )
        created_data = _project_injected_data(created_response, source_project_key=template_key)
        created_project_key = created_data.project_key
        created_name = created_data.name
        created_schema_name = created_data.schema_name
        created_source_project_key = created_data.source_project_key
        created_activated = created_data.activated
        created_counts = created_data.copied_counts
        created_mode = "inject_initial"
    else:
        created_response = create_project(
            CreateProjectPayload(
                project_key=target_key,
                name=payload.project_name,
                enabled=True,
            )
        )
        created_envelope = ApiEnvelope[ProjectCreatedData].model_validate(created_response)
        if created_envelope.data is None:
            _raise_internal_error("project creation returned no data")
        if payload.activate:
            activate_project(target_key)
        created_project_key = target_key
        created_name = payload.project_name
        created_schema_name = created_envelope.data.schema_name
        created_source_project_key = None
        created_activated = payload.activate
        created_counts = {}
        created_mode = "create_empty"

    llm_applied = _apply_llm_configs_to_project(target_key, payload.llm_configs)
    if created_source_project_key is not None:
        response_data: ProjectAutoCreatedData | ProjectAutoEmptyData = ProjectAutoCreatedData(
            project_key=created_project_key,
            name=created_name,
            schema_name=created_schema_name,
            source_project_key=created_source_project_key,
            activated=created_activated,
            copied_counts=created_counts,
            created_mode=created_mode,
            template_project_key=template_key,
            llm_configs_applied=llm_applied,
        )
    else:
        response_data = ProjectAutoEmptyData(
            project_key=created_project_key,
            name=created_name,
            schema_name=created_schema_name,
            activated=created_activated,
            copied_counts=created_counts,
            created_mode="create_empty",
            template_project_key=template_key,
            llm_configs_applied=llm_applied,
        )
    return ok(response_data.model_dump())


@router.patch(
    "/{project_key}",
    response_model=ApiEnvelope[ProjectUpdatedData | ProjectUpdatedWithFallbackData],
)
def update_project(project_key: str, payload: UpdateProjectPayload) -> ProjectJsonObject:
    normalized_key = normalize_project_key(project_key)
    with bind_schema("public"):
        with SessionLocal() as session:
            project = session.execute(
                select(Project).where(Project.project_key == normalized_key)
            ).scalar_one_or_none()
            if project is None:
                _raise_not_found("project not found")

            changed = False
            if payload.name is not None:
                _set_project_text(project, "name", payload.name)
                changed = True
            if payload.enabled is not None:
                _set_project_bool(project, "enabled", payload.enabled)
                if not payload.enabled and _project_bool(project, "is_active"):
                    _set_project_bool(project, "is_active", False)
                changed = True

            if changed:
                session.commit()
                session.refresh(project)

            # If disabling an active project, pick a fallback active.
            if payload.enabled is False:
                active = session.execute(select(Project).where(Project.is_active.is_(True))).scalar_one_or_none()
                if active is None:
                    fallback = (
                        session.execute(
                            select(Project)
                            .where(Project.enabled.is_(True))
                            .order_by(Project.project_key.asc())
                        )
                        .scalars()
                        .first()
                    )
                    if fallback is not None:
                        _set_project_bool(fallback, "is_active", True)
                        session.commit()
                        return ok(
                            ProjectUpdatedWithFallbackData(
                                project_key=normalized_key,
                                fallback_active_project_key=_project_text(fallback, "project_key"),
                            ).model_dump()
                        )

    return ok(ProjectUpdatedData(project_key=normalized_key).model_dump())


@router.post("/{project_key}/archive", response_model=ApiEnvelope[ProjectArchiveData])
def archive_project(project_key: str) -> ProjectJsonObject:
    normalized_key = normalize_project_key(project_key)
    with bind_schema("public"):
        with SessionLocal() as session:
            project = session.execute(
                select(Project).where(Project.project_key == normalized_key)
            ).scalar_one_or_none()
            if project is None:
                _raise_not_found("project not found")

            _set_project_bool(project, "enabled", False)
            if _project_bool(project, "is_active"):
                _set_project_bool(project, "is_active", False)

            # Pick fallback active if needed.
            active = session.execute(select(Project).where(Project.is_active.is_(True))).scalar_one_or_none()
            if active is None:
                fallback = (
                    session.execute(
                        select(Project)
                        .where(Project.enabled.is_(True))
                        .order_by(Project.project_key.asc())
                    )
                    .scalars()
                    .first()
                )
                if fallback is not None:
                    _set_project_bool(fallback, "is_active", True)

            session.commit()

    return ok(ProjectArchiveData(project_key=normalized_key, archived=True).model_dump())


@router.post("/{project_key}/restore", response_model=ApiEnvelope[ProjectArchiveData])
def restore_project(project_key: str) -> ProjectJsonObject:
    normalized_key = normalize_project_key(project_key)
    with bind_schema("public"):
        with SessionLocal() as session:
            project = session.execute(
                select(Project).where(Project.project_key == normalized_key)
            ).scalar_one_or_none()
            if project is None:
                _raise_not_found("project not found")
            _set_project_bool(project, "enabled", True)
            session.commit()
    return ok(ProjectArchiveData(project_key=normalized_key, archived=False).model_dump())


@router.post("/{project_key}/activate", response_model=ApiEnvelope[ProjectActivationData])
def activate_project(project_key: str) -> ProjectJsonObject:
    normalized_key = normalize_project_key(project_key)
    with bind_schema("public"):
        with SessionLocal() as session:
            project = session.execute(
                select(Project).where(Project.project_key == normalized_key)
            ).scalar_one_or_none()
            if project is None:
                _raise_not_found("project not found")
            if not _project_bool(project, "enabled"):
                _raise_invalid_input("project is archived/disabled", status_code=409)

            all_rows = session.execute(select(Project)).scalars().all()
            for row in all_rows:
                _set_project_bool(row, "is_active", _project_text(row, "project_key") == normalized_key)
            session.commit()

    return ok(ProjectActivationData(active_project_key=normalized_key).model_dump())


@router.delete(
    "/{project_key}",
    response_model=ApiEnvelope[ProjectArchiveDeleteData | ProjectHardDeleteData],
)
def delete_project(project_key: str, hard: bool = Query(default=False)) -> ProjectJsonObject:
    normalized_key = normalize_project_key(project_key)
    if hard and normalized_key == "default":
        _raise_invalid_input("default project cannot be hard-deleted", status_code=409)

    with bind_schema("public"):
        with SessionLocal() as session:
            project = session.execute(
                select(Project).where(Project.project_key == normalized_key)
            ).scalar_one_or_none()
            if project is None:
                _raise_not_found("project not found")

            schema_name = _project_text(project, "schema_name")
            was_active = _project_bool(project, "is_active")

            if not hard:
                # Soft-delete == archive
                _set_project_bool(project, "enabled", False)
                _set_project_bool(project, "is_active", False)
                if was_active:
                    fallback = (
                        session.execute(
                            select(Project)
                            .where(Project.enabled.is_(True))
                            .where(Project.project_key != normalized_key)
                            .order_by(Project.project_key.asc())
                        )
                        .scalars()
                        .first()
                    )
                    if fallback is not None:
                        _set_project_bool(fallback, "is_active", True)
                session.commit()
                return ok(
                    ProjectArchiveDeleteData(
                        project_key=normalized_key,
                        deleted=False,
                        archived=True,
                    ).model_dump()
                )

            # Hard delete: remove control-plane row and drop schema
            if was_active:
                fallback = (
                    session.execute(
                        select(Project)
                        .where(Project.enabled.is_(True))
                        .where(Project.project_key != normalized_key)
                        .order_by(Project.project_key.asc())
                    )
                    .scalars()
                    .first()
                )
                if fallback is not None:
                    _set_project_bool(fallback, "is_active", True)

            session.delete(project)
            session.commit()

    with engine.begin() as conn:
        # best-effort cleanup sync cursors
        conn.execute(text("DELETE FROM public.project_sync_state WHERE project_key = :k"), {"k": normalized_key})
        if schema_name:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))

    return ok(
        ProjectHardDeleteData(
            project_key=normalized_key,
            deleted=True,
            hard=True,
        ).model_dump()
    )
