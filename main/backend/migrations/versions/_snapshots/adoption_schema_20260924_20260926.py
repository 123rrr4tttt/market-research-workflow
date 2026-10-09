"""Immutable DDL and adoption checks for the 20260924/20260926 revisions.

This module deliberately owns a revision-local copy of the five table shapes.
Historical migrations must not import mutable application ORM declarations.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import re
from typing import Final, Literal

from alembic.operations import Operations
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


DefaultKind = Literal[
    "none",
    "owned_sequence",
    "true",
    "false",
    "now",
    "empty_object",
    "empty_array",
]
TypeKind = Literal["bigint", "varchar", "jsonb", "boolean", "timestamptz"]


class MigrationAdoptionError(RuntimeError):
    """An existing table cannot be safely adopted by the revision."""


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    type_kind: TypeKind
    nullable: bool
    default_kind: DefaultKind = "none"
    length: int | None = None
    primary_key: bool = False

    def build(self) -> sa.Column:
        if self.type_kind == "bigint":
            column_type: sa.types.TypeEngine = sa.BigInteger()
        elif self.type_kind == "varchar":
            column_type = sa.String(self.length)
        elif self.type_kind == "jsonb":
            column_type = postgresql.JSONB()
        elif self.type_kind == "boolean":
            column_type = sa.Boolean()
        elif self.type_kind == "timestamptz":
            column_type = sa.DateTime(timezone=True)
        else:  # pragma: no cover - closed Literal and immutable constants
            raise AssertionError

        defaults = {
            "none": None,
            "owned_sequence": None,
            "true": sa.true(),
            "false": sa.false(),
            "now": sa.func.now(),
            "empty_object": sa.text("'{}'::jsonb"),
            "empty_array": sa.text("'[]'::jsonb"),
        }
        return sa.Column(
            self.name,
            column_type,
            nullable=self.nullable,
            primary_key=self.primary_key,
            autoincrement=True if self.default_kind == "owned_sequence" else "auto",
            server_default=defaults[self.default_kind],
        )


@dataclass(frozen=True)
class UniqueSpec:
    name: str
    columns: tuple[str, ...]


@dataclass(frozen=True)
class IndexSpec:
    name: str
    columns: tuple[str, ...]
    unique: bool = False
    predicate: str | None = None


@dataclass(frozen=True)
class TableSpec:
    name: str
    columns: tuple[ColumnSpec, ...]
    uniques: tuple[UniqueSpec, ...] = ()
    indexes: tuple[IndexSpec, ...] = ()


@dataclass(frozen=True)
class AdoptionPlan:
    schema: str
    table: TableSpec
    create_table: bool
    missing_uniques: tuple[UniqueSpec, ...] = ()
    missing_indexes: tuple[IndexSpec, ...] = ()


def _id() -> ColumnSpec:
    return ColumnSpec(
        "id", "bigint", nullable=False, default_kind="owned_sequence", primary_key=True
    )


def _varchar(name: str, length: int, *, nullable: bool = False) -> ColumnSpec:
    return ColumnSpec(name, "varchar", nullable=nullable, length=length)


def _jsonb(
    name: str, *, nullable: bool = False, default_kind: DefaultKind = "none"
) -> ColumnSpec:
    return ColumnSpec(name, "jsonb", nullable=nullable, default_kind=default_kind)


def _boolean(name: str, default_kind: Literal["true", "false"]) -> ColumnSpec:
    return ColumnSpec(name, "boolean", nullable=False, default_kind=default_kind)


def _created(name: str = "created_at") -> ColumnSpec:
    return ColumnSpec(name, "timestamptz", nullable=False, default_kind="now")


INFORMATION_TOPOLOGY_TABLES: Final[tuple[TableSpec, ...]] = (
    TableSpec(
        "information_topology_states",
        (
            _id(),
            _varchar("project_key", 128),
            _varchar("module_id", 128),
            _varchar("namespace", 255),
            _varchar("state_id", 255),
            _varchar("profile_id", 255),
            _varchar("profile_version", 128),
            ColumnSpec("revision", "bigint", nullable=False),
            _jsonb("payload"),
            _jsonb("provenance", nullable=True),
            _varchar("digest", 64),
            _boolean("is_current", "true"),
            _boolean("deleted", "false"),
            _created(),
        ),
        uniques=(
            UniqueSpec(
                "uq_information_topology_state_revision",
                ("project_key", "module_id", "namespace", "state_id", "revision"),
            ),
        ),
        indexes=(
            IndexSpec(
                "uq_information_topology_state_current",
                ("project_key", "module_id", "namespace", "state_id"),
                unique=True,
                predicate="is_current IS TRUE",
            ),
            IndexSpec(
                "ix_information_topology_state_project_module",
                ("project_key", "module_id"),
            ),
        ),
    ),
    TableSpec(
        "information_topology_links",
        (
            _id(),
            _varchar("project_key", 128),
            _varchar("link_id", 255),
            ColumnSpec("revision", "bigint", nullable=False),
            _varchar("record_kind", 32),
            _varchar("type_or_rule_ref", 512),
            _jsonb("endpoints"),
            _jsonb("payload"),
            _jsonb("provenance", nullable=True),
            _varchar("digest", 64),
            _boolean("is_current", "true"),
            _boolean("deleted", "false"),
            _created(),
        ),
        uniques=(
            UniqueSpec(
                "uq_information_topology_link_revision",
                ("project_key", "link_id", "revision"),
            ),
        ),
        indexes=(
            IndexSpec(
                "uq_information_topology_link_current",
                ("project_key", "link_id"),
                unique=True,
                predicate="is_current IS TRUE",
            ),
            IndexSpec(
                "ix_information_topology_link_project_kind",
                ("project_key", "record_kind"),
            ),
        ),
    ),
)


PROJECT_RETRIEVAL_TABLES: Final[tuple[TableSpec, ...]] = (
    TableSpec(
        "project_retrieval_modes",
        (
            _id(),
            _varchar("project_key", 128),
            _varchar("mode_id", 128),
            _varchar("version", 128),
            _varchar("source_revision", 64),
            _jsonb("snapshot"),
            _boolean("is_current", "true"),
            _created(),
        ),
        uniques=(
            UniqueSpec(
                "uq_project_retrieval_mode_version",
                ("project_key", "mode_id", "version"),
            ),
        ),
        indexes=(
            IndexSpec(
                "uq_project_retrieval_mode_current",
                ("project_key",),
                unique=True,
                predicate="is_current IS TRUE",
            ),
        ),
    ),
    TableSpec(
        "project_retrieval_plans",
        (
            _id(),
            _varchar("project_key", 128),
            _varchar("plan_id", 64),
            _varchar("mode_id", 128),
            _varchar("mode_version", 128),
            _jsonb("payload"),
            _created(),
        ),
        uniques=(
            UniqueSpec(
                "uq_project_retrieval_plan", ("project_key", "plan_id")
            ),
        ),
    ),
    TableSpec(
        "project_retrieval_runs",
        (
            _id(),
            _varchar("project_key", 128),
            _varchar("run_id", 64),
            _varchar("plan_id", 64),
            _varchar("idempotency_key", 255),
            _varchar("status", 32),
            _varchar("phase", 64),
            _jsonb("counts", default_kind="empty_object"),
            _jsonb("errors", default_kind="empty_array"),
            _jsonb("receipt", default_kind="empty_object"),
            _created(),
            _created("updated_at"),
        ),
        uniques=(
            UniqueSpec("uq_project_retrieval_run", ("project_key", "run_id")),
            UniqueSpec(
                "uq_project_retrieval_idempotency",
                ("project_key", "idempotency_key"),
            ),
        ),
    ),
)


def _fail(schema: str, table: str, prop: str, detail: str) -> MigrationAdoptionError:
    return MigrationAdoptionError(f"{schema}.{table}: incompatible {prop}: {detail}")


def _type_matches(actual: sa.types.TypeEngine, expected: ColumnSpec) -> bool:
    if expected.type_kind == "bigint":
        return isinstance(actual, sa.BigInteger)
    if expected.type_kind == "varchar":
        return isinstance(actual, sa.String) and actual.length == expected.length
    if expected.type_kind == "jsonb":
        return isinstance(actual, postgresql.JSONB)
    if expected.type_kind == "boolean":
        return isinstance(actual, sa.Boolean)
    if expected.type_kind == "timestamptz":
        return isinstance(actual, sa.DateTime) and bool(actual.timezone)
    return False


def _strip_outer_parentheses(value: str) -> str:
    value = value.strip()
    while value.startswith("(") and value.endswith(")"):
        depth = 0
        balanced = True
        for position, character in enumerate(value):
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0 and position != len(value) - 1:
                    balanced = False
                    break
        if not balanced or depth != 0:
            break
        value = value[1:-1].strip()
    return value


def _normalized_sql(value: object | None) -> str | None:
    if value is None:
        return None
    sql = _strip_outer_parentheses(str(value).strip()).lower()
    return re.sub(r"\s+", "", sql.replace('"', ""))


def _default_matches(actual: object | None, expected: DefaultKind) -> bool:
    if expected == "none":
        return actual is None
    normalized = _normalized_sql(actual)
    if normalized is None:
        return False
    if expected == "owned_sequence":
        return normalized.startswith("nextval(") and normalized.endswith(")")
    if expected == "true":
        return normalized in {"true", "true::boolean", "'true'::boolean"}
    if expected == "false":
        return normalized in {"false", "false::boolean", "'false'::boolean"}
    if expected == "now":
        return normalized in {"now()", "current_timestamp", "transaction_timestamp()"}
    if expected == "empty_object":
        return normalized in {"'{}'::jsonb", "'{}'::json"}
    if expected == "empty_array":
        return normalized in {"'[]'::jsonb", "'[]'::json"}
    return False


def _predicate_matches(actual: object | None, expected: str | None) -> bool:
    return _normalized_sql(actual) == _normalized_sql(expected)


def _quoted(conn: sa.Connection, name: str) -> str:
    return conn.dialect.identifier_preparer.quote(name)


def _assert_owned_sequence(
    conn: sa.Connection, *, schema: str, table: str, column: str
) -> None:
    sequence = conn.execute(
        sa.text(
            "SELECT pg_get_serial_sequence(format('%I.%I', :schema_name, :table_name), "
            ":column_name)"
        ),
        {"schema_name": schema, "table_name": table, "column_name": column},
    ).scalar_one_or_none()
    if not sequence:
        raise _fail(
            schema,
            table,
            f"column {column} sequence ownership",
            "default sequence is absent or is not owned by this column",
        )


def _duplicate_sample(
    conn: sa.Connection,
    *,
    schema: str,
    table: str,
    columns: tuple[str, ...],
    predicate: str | None = None,
) -> object | None:
    quoted_columns = ", ".join(_quoted(conn, column) for column in columns)
    qualified = f"{_quoted(conn, schema)}.{_quoted(conn, table)}"
    where = f" WHERE {predicate}" if predicate else ""
    statement = sa.text(
        f"SELECT {quoted_columns}, count(*) AS duplicate_count "
        f"FROM {qualified}{where} GROUP BY {quoted_columns} "
        "HAVING count(*) > 1 LIMIT 1"
    )
    return conn.execute(statement).first()


def _validate_existing_table(
    conn: sa.Connection,
    inspector: sa.Inspector,
    *,
    schema: str,
    table: TableSpec,
) -> AdoptionPlan:
    reflected_columns = {
        str(column["name"]): column
        for column in inspector.get_columns(table.name, schema=schema)
    }
    reflected_names = set(reflected_columns)
    expected_names = {column.name for column in table.columns}
    if reflected_names != expected_names:
        raise _fail(
            schema,
            table.name,
            "columns",
            f"missing={sorted(expected_names - reflected_names)}, "
            f"unexpected={sorted(reflected_names - expected_names)}",
        )
    for expected in table.columns:
        actual = reflected_columns.get(expected.name)
        assert actual is not None  # established by the exact name-set comparison
        if not _type_matches(actual["type"], expected):
            raise _fail(
                schema,
                table.name,
                f"column {expected.name} type",
                f"expected {expected.type_kind}"
                + (f"({expected.length})" if expected.length is not None else "")
                + f", found {actual['type']}",
            )
        if bool(actual.get("nullable")) != expected.nullable:
            raise _fail(
                schema,
                table.name,
                f"column {expected.name} nullability",
                f"expected nullable={expected.nullable}, found nullable={actual.get('nullable')}",
            )
        if not _default_matches(actual.get("default"), expected.default_kind):
            raise _fail(
                schema,
                table.name,
                f"column {expected.name} default",
                f"expected {expected.default_kind}, found {actual.get('default')!r}",
            )
        if expected.default_kind == "owned_sequence":
            _assert_owned_sequence(
                conn, schema=schema, table=table.name, column=expected.name
            )

    primary_key = inspector.get_pk_constraint(table.name, schema=schema)
    actual_primary_key = tuple(primary_key.get("constrained_columns") or ())
    expected_primary_key = tuple(
        column.name for column in table.columns if column.primary_key
    )
    if actual_primary_key != expected_primary_key:
        raise _fail(
            schema,
            table.name,
            "primary key",
            f"expected columns {expected_primary_key}, found {actual_primary_key}",
        )

    uniques_by_name = {
        str(constraint["name"]): constraint
        for constraint in inspector.get_unique_constraints(table.name, schema=schema)
        if constraint.get("name")
    }
    missing_uniques: list[UniqueSpec] = []
    for expected in table.uniques:
        actual = uniques_by_name.get(expected.name)
        if actual is None:
            duplicate = _duplicate_sample(
                conn,
                schema=schema,
                table=table.name,
                columns=expected.columns,
            )
            if duplicate is not None:
                raise _fail(
                    schema,
                    table.name,
                    f"unique constraint {expected.name}",
                    f"historical rows conflict for columns {expected.columns}: {tuple(duplicate)!r}",
                )
            missing_uniques.append(expected)
            continue
        actual_columns = tuple(actual.get("column_names") or ())
        if actual_columns != expected.columns:
            raise _fail(
                schema,
                table.name,
                f"unique constraint {expected.name}",
                f"expected columns {expected.columns}, found {actual_columns}",
            )

    indexes_by_name = {
        str(index["name"]): index
        for index in inspector.get_indexes(table.name, schema=schema)
        if index.get("name")
    }
    missing_indexes: list[IndexSpec] = []
    for expected in table.indexes:
        actual = indexes_by_name.get(expected.name)
        if actual is None:
            if expected.unique:
                duplicate = _duplicate_sample(
                    conn,
                    schema=schema,
                    table=table.name,
                    columns=expected.columns,
                    predicate=expected.predicate,
                )
                if duplicate is not None:
                    raise _fail(
                        schema,
                        table.name,
                        f"index {expected.name}",
                        f"historical rows conflict for columns {expected.columns}: {tuple(duplicate)!r}",
                    )
            missing_indexes.append(expected)
            continue
        actual_columns = tuple(actual.get("column_names") or ())
        actual_unique = bool(actual.get("unique"))
        actual_predicate = (actual.get("dialect_options") or {}).get(
            "postgresql_where"
        )
        if (
            actual_columns != expected.columns
            or actual_unique != expected.unique
            or not _predicate_matches(actual_predicate, expected.predicate)
        ):
            raise _fail(
                schema,
                table.name,
                f"index {expected.name}",
                "expected "
                f"columns={expected.columns}, unique={expected.unique}, predicate={expected.predicate!r}; "
                "found "
                f"columns={actual_columns}, unique={actual_unique}, predicate={actual_predicate!r}",
            )

    return AdoptionPlan(
        schema=schema,
        table=table,
        create_table=False,
        missing_uniques=tuple(missing_uniques),
        missing_indexes=tuple(missing_indexes),
    )


def preflight_adoption(
    conn: sa.Connection,
    schemas: Sequence[str],
    tables: Sequence[TableSpec],
) -> tuple[AdoptionPlan, ...]:
    """Inspect all targets before any DDL so deterministic failures are atomic."""

    inspector = sa.inspect(conn)
    plans: list[AdoptionPlan] = []
    for schema in schemas:
        for table in tables:
            if inspector.has_table(table.name, schema=schema):
                plans.append(
                    _validate_existing_table(
                        conn, inspector, schema=schema, table=table
                    )
                )
            else:
                plans.append(AdoptionPlan(schema, table, create_table=True))
    return tuple(plans)


def _create_table(operations: Operations, plan: AdoptionPlan) -> None:
    table = plan.table
    constraints = [
        sa.UniqueConstraint(*constraint.columns, name=constraint.name)
        for constraint in table.uniques
    ]
    operations.create_table(
        table.name,
        *(column.build() for column in table.columns),
        *constraints,
        schema=plan.schema,
    )
    for index in table.indexes:
        operations.create_index(
            index.name,
            table.name,
            list(index.columns),
            unique=index.unique,
            schema=plan.schema,
            postgresql_where=sa.text(index.predicate) if index.predicate else None,
        )


def apply_adoption(operations: Operations, plans: Sequence[AdoptionPlan]) -> None:
    for plan in plans:
        if plan.create_table:
            _create_table(operations, plan)
            continue
        for constraint in plan.missing_uniques:
            operations.create_unique_constraint(
                constraint.name,
                plan.table.name,
                list(constraint.columns),
                schema=plan.schema,
            )
        for index in plan.missing_indexes:
            operations.create_index(
                index.name,
                plan.table.name,
                list(index.columns),
                unique=index.unique,
                schema=plan.schema,
                postgresql_where=(
                    sa.text(index.predicate) if index.predicate else None
                ),
            )


def adopt_or_create_tables(
    conn: sa.Connection,
    operations: Operations,
    schemas: Sequence[str],
    tables: Sequence[TableSpec],
) -> tuple[AdoptionPlan, ...]:
    plans = preflight_adoption(conn, schemas, tables)
    apply_adoption(operations, plans)
    return plans
