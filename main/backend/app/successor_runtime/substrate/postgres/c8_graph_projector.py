"""C8.4 content-addressed graph projection PostgreSQL effect slice.

Each projection generation is stored as an exact content-addressed
``GraphProjectionGeneration`` value in project ``successor_values`` and the
active generation is advanced through a CAS ``ProjectionOffsetRepository``
row.  Loss profiles come from the family production composition root's fixed
catalog; this slice accepts no caller loss registry or witness.  Prior
generations are retained; a failed candidate or offset CAS leaves the
previously active generation active.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import MetaData, select, update
from sqlalchemy.engine import Connection

from app.successor_runtime.capabilities import c8_common as c8
from app.successor_runtime.capabilities.c8_graph import project_graph_occurrences
from app.successor_runtime.capabilities.checksum import (
    canonical_json,
    content_digest,
    sha256_hex,
)
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.substrate.postgres.models import (
    PUBLIC_TABLES,
    project_tables,
)
from app.successor_runtime.substrate.postgres.projection_offsets import (
    ProjectionOffsetKey,
    ProjectionOffsetRepository,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    RecordNotFound,
    StaleRevisionError,
)
from app.successor_runtime.substrate.postgres.values import ValueRepository

__all__ = [
    "C8_GRAPH_PROJECTOR_ID",
    "C8_GRAPH_PROJECTOR_VERSION",
    "C8_GRAPH_SOURCE_KIND",
    "C8_GRAPH_VALUE_CODEC_ID",
    "C8_GRAPH_VALUE_OBJECT_TYPE",
    "C8_GRAPH_VALUE_SCHEMA",
    "C8GraphOffsetCasError",
    "C8GraphProjectionIntegrityError",
    "C8GraphProjectionUnavailableError",
    "C8GraphProjectorError",
    "C8GraphProjectorResult",
    "graph_value_id",
    "project_graph_generation",
    "read_active_graph",
]

C8_GRAPH_PROJECTOR_ID = "c8.graph.projector"
C8_GRAPH_PROJECTOR_VERSION = "1"
C8_GRAPH_SOURCE_KIND = "successor_value"
C8_GRAPH_VALUE_SCHEMA = "mrw.successor.c8.graph-projection.v1"
C8_GRAPH_VALUE_OBJECT_TYPE = "GraphProjectionGeneration.v1"
C8_GRAPH_VALUE_CODEC_ID = (
    "mrw.successor.c8.graph-projection-generation.canonical-json.v1"
)
C8_GRAPH_VALUE_STATE = "AVAILABLE"
C8_VALUE_REF_PREFIX = "project-value:"


class C8GraphProjectorError(RuntimeError):
    """Base fail-closed C8 graph projector effect error."""


class C8GraphProjectionUnavailableError(C8GraphProjectorError):
    """No active projection exists for the exact source identity."""


class C8GraphProjectionIntegrityError(C8GraphProjectorError):
    """Stored generation bytes/digest/provenance/authority drift."""


class C8GraphOffsetCasError(C8GraphProjectorError):
    """Projection offset CAS failed; the active generation is unchanged."""


@dataclass(frozen=True, slots=True)
class C8GraphProjectorResult:
    generation: c8.GraphProjectionGeneration
    projection_offset_id: str
    offset: Mapping[str, object]
    active_value_ref: str
    store_writes: Literal[2] = 2
    provider_calls: Literal[0] = 0
    export_calls: Literal[0] = 0
    production_canonical_authority: Literal[False] = False
    live_provider: Literal[False] = False
    promotion: Literal[False] = False


def graph_value_id(graph_id: str, generation: int) -> str:
    return f"c8:graph:{graph_id}:gen:{generation}"


def _graph_source_key(graph_id: str, source_ref: str) -> str:
    return f"graph:{graph_id}:{source_ref}"


def _generation_number(graph_id: str, generation_id: str) -> int:
    prefix = f"c8.graph.generation:{graph_id}:"
    if not generation_id.startswith(prefix):
        raise C8GraphProjectionIntegrityError(
            "graph generation id is not bound to the requested graph"
        )
    suffix = generation_id[len(prefix) :]
    try:
        number = int(suffix)
    except ValueError as exc:
        raise C8GraphProjectionIntegrityError(
            "graph generation id suffix is not an integer"
        ) from exc
    if number < 0:
        raise C8GraphProjectionIntegrityError(
            "graph generation number must be non-negative"
        )
    return number


def _generation_body(generation: c8.GraphProjectionGeneration) -> dict[str, object]:
    return {
        "generation_id": generation.generation_id,
        "project_key": generation.project_key,
        "occurrences": [
            {
                "occurrence_id": occurrence.occurrence_id,
                "edge_type": occurrence.edge_type,
                "source_identity": occurrence.source_identity,
                "target_identity": occurrence.target_identity,
                "position": occurrence.position,
                "occurrence_digest": occurrence.occurrence_digest,
            }
            for occurrence in generation.occurrences
        ],
        "declared_loss": list(generation.declared_loss),
        "provenance_digest": generation.provenance_digest,
        "offset": generation.offset,
        "authority_kind": generation.authority_kind,
        "authority_digest": generation.authority_digest,
        "loss_profile_registry_id": generation.loss_profile_registry_id,
        "loss_profile_registry_digest": generation.loss_profile_registry_digest,
    }


def _generation_bytes(generation: c8.GraphProjectionGeneration) -> bytes:
    return canonical_json(_generation_body(generation)).encode("utf-8")


def _generation_from_body(
    body: Mapping[str, object],
    *,
    content_digest_value: str,
) -> c8.GraphProjectionGeneration:
    occurrences: list[c8.GraphOccurrence] = []
    for raw in body["occurrences"]:
        if not isinstance(raw, Mapping):
            raise C8GraphProjectionIntegrityError(
                "stored graph occurrence is not an object"
            )
        occurrence = c8.GraphOccurrence(
            occurrence_id=str(raw["occurrence_id"]),
            edge_type=str(raw["edge_type"]),
            source_identity=str(raw["source_identity"]),
            target_identity=str(raw["target_identity"]),
            position=int(raw["position"]),
            occurrence_digest=str(raw.get("occurrence_digest") or ""),
        )
        occurrences.append(occurrence)
    generation = c8.GraphProjectionGeneration(
        generation_id=str(body["generation_id"]),
        project_key=str(body["project_key"]),
        occurrences=tuple(occurrences),
        declared_loss=tuple(str(item) for item in body["declared_loss"]),
        provenance_digest=str(body["provenance_digest"]),
        offset=str(body["offset"]),
        authority_kind=str(body["authority_kind"]),
        authority_digest=str(body["authority_digest"]),
        loss_profile_registry_id=str(body["loss_profile_registry_id"]),
        loss_profile_registry_digest=str(body["loss_profile_registry_digest"]),
        projection_digest=content_digest_value,
    )
    recomputed = c8.c8_canonical_digest(_generation_body(generation))
    if recomputed != content_digest_value:
        raise C8GraphProjectionIntegrityError(
            "stored graph generation fails content readback"
        )
    return generation


def _body_from_row(row: Mapping[str, object]) -> dict[str, object]:
    content = row["content_json"]
    if isinstance(content, dict):
        return dict(content)
    raw = row["content_bytes"]
    if raw is None:
        raise C8GraphProjectionIntegrityError(
            "active graph value has neither content_json nor content_bytes"
        )
    exact = bytes(raw)
    if sha256_hex(exact) != str(row["content_digest"]):
        raise C8GraphProjectionIntegrityError(
            "active graph value bytes fail digest readback"
        )
    try:
        parsed = json.loads(exact.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise C8GraphProjectionIntegrityError(
            "active graph value bytes are not canonical JSON"
        ) from exc
    if not isinstance(parsed, dict):
        raise C8GraphProjectionIntegrityError(
            "active graph value JSON is not an object"
        )
    return parsed


def _value_ref(value_id: str) -> str:
    return C8_VALUE_REF_PREFIX + value_id


def _value_id_from_ref(value_ref: str) -> str:
    if not value_ref.startswith(C8_VALUE_REF_PREFIX):
        raise C8GraphProjectionIntegrityError(
            "active projection offset ref is not a project-value ref"
        )
    return value_ref[len(C8_VALUE_REF_PREFIX) :]


def _require_projection_generation(
    connection: Connection,
    *,
    scope: RuntimeScope,
    projection_offset_id: str,
    expected_generation: int,
    current_revision: int,
) -> Mapping[str, object]:
    """Exact-CAS the active projection_generation after shared advance."""

    table = PUBLIC_TABLES["runtime_projection_offsets"]
    result = connection.execute(
        update(table)
        .where(
            table.c.project_key == scope.project_scope.project_key,
            table.c.projection_offset_id == projection_offset_id,
            table.c.revision == current_revision,
        )
        .values(projection_generation=expected_generation)
    )
    if getattr(result, "rowcount", None) != 1:
        raise C8GraphOffsetCasError(
            "projection generation exact CAS failed; active offset unchanged"
        )
    return ProjectionOffsetRepository(connection, scope).load(projection_offset_id)


def _projection_value(
    connection: Connection,
    *,
    scope: RuntimeScope,
    value_id: str,
) -> Mapping[str, object]:
    table = project_tables(
        MetaData(), scope.project_scope.resolved_schema
    ).successor_values
    row = (
        connection.execute(
            select(table).where(
                table.c.project_key == scope.project_scope.project_key,
                table.c.value_id == value_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise C8GraphProjectionUnavailableError(
            f"active graph projection value not found: {value_id}"
        )
    return row


def _write_generation_value(
    connection: Connection,
    *,
    scope: RuntimeScope,
    generation: c8.GraphProjectionGeneration,
    value_id: str,
    source_ref: str,
) -> None:
    exact = _generation_bytes(generation)
    if sha256_hex(exact) != generation.projection_digest:
        raise C8GraphProjectionIntegrityError(
            "graph generation bytes do not match projection digest"
        )
    provenance = {
        "schema": C8_GRAPH_VALUE_SCHEMA,
        "graph_value_id": value_id,
        "generation_id": generation.generation_id,
        "projection_digest": generation.projection_digest,
        "provenance_digest": generation.provenance_digest,
        "source_ref": source_ref,
        "authority_kind": generation.authority_kind,
        "authority_digest": generation.authority_digest,
        "loss_profile_registry_id": generation.loss_profile_registry_id,
        "loss_profile_registry_digest": generation.loss_profile_registry_digest,
    }
    ValueRepository(
        connection,
        project_tables(MetaData(), scope.project_scope.resolved_schema),
    ).put_exact(
        scope,
        value_id=value_id,
        object_type=C8_GRAPH_VALUE_OBJECT_TYPE,
        codec_id=C8_GRAPH_VALUE_CODEC_ID,
        content=exact,
        expected_digest=generation.projection_digest,
        provenance_digest=content_digest(provenance),
        expected_revision=0,
        expected_incarnation=f"c8:graph:{generation.projection_digest}",
        source_ref=source_ref,
        provenance=provenance,
        state=C8_GRAPH_VALUE_STATE,
    )


def project_graph_generation(
    connection: Connection,
    *,
    scope: RuntimeScope,
    graph_id: str,
    generation: int,
    occurrences: tuple[c8.GraphOccurrence, ...],
    loss_profile: c8.GraphLossProfile,
    loss_profile_registry: object,
    loss_witness: object,
    provenance_digest: str,
    source_ref: str,
    source_incarnation: str,
    source_digest: str,
    source_revision: int,
    projector_id: str = C8_GRAPH_PROJECTOR_ID,
    projector_version: str = C8_GRAPH_PROJECTOR_VERSION,
    expected_offset_revision: int | None = None,
    expected_generation: int | None = None,
) -> C8GraphProjectorResult:
    """Write one registered generation and CAS-advance the offset."""

    if generation < 0 or source_revision < 0:
        raise ValueError("graph generation and source revision must be non-negative")
    pure_generation = project_graph_occurrences(
        generation_id=f"c8.graph.generation:{graph_id}:{generation}",
        project_key=scope.project_scope.project_key,
        occurrences=occurrences,
        loss_profile=loss_profile,
        loss_profile_registry=loss_profile_registry,
        loss_witness=loss_witness,
        provenance_digest=provenance_digest,
    )
    value_id = graph_value_id(graph_id, generation)
    offset_ref = _value_ref(value_id)
    stamped = dataclasses.replace(
        pure_generation,
        offset=offset_ref,
        projection_digest="",
    )
    key = ProjectionOffsetKey(
        projector_id=projector_id,
        projector_version=projector_version,
        source_kind=C8_GRAPH_SOURCE_KIND,
        source_ref=_graph_source_key(graph_id, source_ref),
        source_incarnation=source_incarnation,
    )
    projection_offset_id = f"c8:graph:offset:{graph_id}"
    repo = ProjectionOffsetRepository(connection, scope)
    try:
        with connection.begin_nested():
            _write_generation_value(
                connection,
                scope=scope,
                generation=stamped,
                value_id=value_id,
                source_ref=source_ref,
            )
            existing = repo.load_source(key, for_update=True)
            if existing is None:
                if expected_offset_revision is not None:
                    raise C8GraphOffsetCasError(
                        "expected an existing projection offset but none exists"
                    )
                offset = repo.create(
                    projection_offset_id=projection_offset_id,
                    key=key,
                    projection_generation=generation,
                    source_revision=source_revision,
                    source_digest=source_digest,
                    offset_ref=offset_ref,
                )
            else:
                offset = repo.advance(
                    projection_offset_id,
                    key=key,
                    expected_revision=(
                        expected_offset_revision
                        if expected_offset_revision is not None
                        else int(existing["revision"])
                    ),
                    expected_generation=(
                        expected_generation
                        if expected_generation is not None
                        else int(existing["projection_generation"])
                    ),
                    expected_source_revision=int(existing["source_revision"]),
                    expected_source_digest=str(existing["source_digest"]),
                    source_revision=source_revision,
                    source_digest=source_digest,
                    offset_ref=offset_ref,
                )
            offset = _require_projection_generation(
                connection,
                scope=scope,
                projection_offset_id=projection_offset_id,
                expected_generation=generation,
                current_revision=int(offset["revision"]),
            )
    except StaleRevisionError as exc:
        raise C8GraphOffsetCasError(
            "graph projection offset CAS failed; active generation unchanged"
        ) from exc
    return C8GraphProjectorResult(
        generation=stamped,
        projection_offset_id=projection_offset_id,
        offset=offset,
        active_value_ref=offset_ref,
    )


def read_active_graph(
    connection: Connection,
    *,
    scope: RuntimeScope,
    graph_id: str,
    source_ref: str,
    source_incarnation: str,
    projector_id: str = C8_GRAPH_PROJECTOR_ID,
    projector_version: str = C8_GRAPH_PROJECTOR_VERSION,
) -> c8.GraphProjectionGeneration:
    """Read the active generation through the exact projection offset."""

    key = ProjectionOffsetKey(
        projector_id=projector_id,
        projector_version=projector_version,
        source_kind=C8_GRAPH_SOURCE_KIND,
        source_ref=_graph_source_key(graph_id, source_ref),
        source_incarnation=source_incarnation,
    )
    try:
        offset = ProjectionOffsetRepository(connection, scope).load_source(key)
    except RecordNotFound as exc:
        raise C8GraphProjectionUnavailableError(
            f"active graph projection offset not found: {graph_id}"
        ) from exc
    if offset is None:
        raise C8GraphProjectionUnavailableError(
            f"active graph projection offset not found: {graph_id}"
        )
    offset_ref = str(offset["offset_ref"])
    value_id = _value_id_from_ref(offset_ref)
    row = _projection_value(connection, scope=scope, value_id=value_id)
    if (
        str(row["object_type"]) != C8_GRAPH_VALUE_OBJECT_TYPE
        or str(row["codec_id"]) != C8_GRAPH_VALUE_CODEC_ID
    ):
        raise C8GraphProjectionIntegrityError(
            "active graph value codec/object type drift"
        )
    if int(row["revision"]) != 1 or str(row["state"]) != C8_GRAPH_VALUE_STATE:
        raise C8GraphProjectionIntegrityError("active graph value revision/state drift")
    body = _body_from_row(row)
    generation = _generation_from_body(
        body,
        content_digest_value=str(row["content_digest"]),
    )
    if str(offset["source_ref"]) != _graph_source_key(graph_id, source_ref):
        raise C8GraphProjectionIntegrityError(
            "active graph offset source identity drift"
        )
    generation_number = _generation_number(graph_id, generation.generation_id)
    if value_id != graph_value_id(graph_id, generation_number):
        raise C8GraphProjectionIntegrityError(
            "active graph value ref is not bound to the requested graph"
        )
    if int(offset["projection_generation"]) != generation_number:
        raise C8GraphProjectionIntegrityError(
            "active graph projection_generation does not match the generation"
        )
    if generation.offset != offset_ref:
        raise C8GraphProjectionIntegrityError(
            "active graph generation offset does not match the offset row"
        )
    return generation
