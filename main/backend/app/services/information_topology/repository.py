"""PostgreSQL revision repository for information-topology states and links.

The repository owns topology rows only. Callers supply profiles and source-specific
provenance; native records remain with their existing owners.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session
from functorial_kit import Failure

from app.models.information_topology_entities import InformationTopologyLink, InformationTopologyState
from .contracts import TopologyState, topology_failures, topology_state_codec
from .profiles import ProfileSpec, decode_state, encode_state

StateKey = tuple[str, str, str, str]  # project, module, namespace, state id
ProfileResolver = Callable[
    [str, str, str, Mapping[str, Any], Mapping[str, Any] | None],
    ProfileSpec | Failure,
]


def _retrieval_profile_from_payload(
    project_key: str,
    profile_id: str,
    profile_version: str,
    payload: Mapping[str, Any],
    source_ref: Mapping[str, Any] | None = None,
) -> ProfileSpec | Failure:
    """Reconstruct a retrieval profile only from its persisted vocabulary snapshot."""
    from .modules.retrieval import profile_from_state_payload

    profile = profile_from_state_payload(project_key, profile_id, profile_version, payload)
    if isinstance(profile, Failure):
        return topology_failures.fail(
            "UNKNOWN_PROFILE", "persisted payload does not resolve to a registered retrieval profile",
            {"cause_code": profile.code, "cause_context": profile.context},
        )
    if source_ref is None:
        return profile
    parsed = topology_state_codec.parse(payload)
    if isinstance(parsed, Failure):
        return parsed
    vocabulary = next(element for element in parsed.elements if element.ref.ref.type_id == "domain_vocabulary")
    if dict(source_ref) != dict(vocabulary.attributes["source_ref"]):
        return topology_failures.fail("UNKNOWN_PROFILE", "supplied source_ref differs from persisted vocabulary binding")
    return profile


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class StateWrite:
    key: StateKey
    state: TopologyState
    expected_revision: int | None
    provenance: Mapping[str, Any] | None = None
    deleted: bool = False


@dataclass(frozen=True, slots=True)
class LinkWrite:
    project_key: str
    link_id: str
    record_kind: str
    type_or_rule_ref: str
    endpoints: Sequence[Mapping[str, Any]]
    payload: Mapping[str, Any]
    expected_revision: int | None
    provenance: Mapping[str, Any] | None = None
    deleted: bool = False


@dataclass(frozen=True, slots=True)
class StateRead:
    key: StateKey
    expected_revision: int


@dataclass(frozen=True, slots=True)
class LinkRead:
    project_key: str
    link_id: str
    expected_revision: int


class InformationTopologyRepository:
    """Methods accept an active SQLAlchemy transaction; no implicit commit occurs."""

    def __init__(
        self,
        profiles: Mapping[tuple[str, str], ProfileSpec] | None = None,
        *,
        profile_resolver: ProfileResolver | None = None,
    ):
        self._profiles = profiles or {}
        self._profile_resolver = profile_resolver

    def resolve_profile(
        self,
        project_key: str,
        profile_id: str,
        profile_version: str,
        payload: Mapping[str, Any],
        source_ref: Mapping[str, Any] | None = None,
    ) -> ProfileSpec | Failure:
        """Resolve one exact profile from static declarations or a persisted snapshot."""
        static = self._profiles.get((profile_id, profile_version))
        if static is not None:
            return static
        resolver = self._profile_resolver or _retrieval_profile_from_payload
        try:
            resolved = resolver(project_key, profile_id, profile_version, payload, source_ref)
        except Exception as exc:  # custom resolvers fail closed at this boundary
            return topology_failures.fail("UNKNOWN_PROFILE", "profile resolver failed", {"reason": str(exc)})
        if isinstance(resolved, Failure):
            return resolved
        if not isinstance(resolved, ProfileSpec) or (resolved.profile_id, resolved.version) != (profile_id, profile_version):
            return topology_failures.fail("UNKNOWN_PROFILE", "profile resolver returned a different profile identity")
        return resolved

    def list_profile_identities(self, session: Session, project_key: str) -> tuple[dict[str, Any], ...]:
        """List each current, non-deleted profile identity used by this project.

        A representative canonical payload accompanies each pair so the service
        can rebuild its exact ProfileSpec through ``resolve_profile``. No global
        profile registry or cross-project read is introduced.
        """
        rows = session.execute(
            select(
                InformationTopologyState.profile_id,
                InformationTopologyState.profile_version,
                InformationTopologyState.payload,
            ).where(
                InformationTopologyState.project_key == project_key,
                InformationTopologyState.is_current.is_(True),
                InformationTopologyState.deleted.is_(False),
            ).order_by(
                InformationTopologyState.profile_id,
                InformationTopologyState.profile_version,
                InformationTopologyState.module_id,
                InformationTopologyState.namespace,
                InformationTopologyState.state_id,
            )
        ).all()
        identities: dict[tuple[str, str], dict[str, Any]] = {}
        for profile_id, profile_version, payload in rows:
            identities.setdefault((profile_id, profile_version), {
                "profile_id": profile_id, "profile_version": profile_version, "payload": payload,
            })
        return tuple(identities[key] for key in sorted(identities))

    def list_current_states(self, session: Session, project_key: str) -> tuple[dict[str, Any], ...]:
        """List current topology identities and counts without decoding their payloads."""
        rows = session.execute(
            select(
                InformationTopologyState.module_id,
                InformationTopologyState.namespace,
                InformationTopologyState.state_id,
                InformationTopologyState.profile_id,
                InformationTopologyState.profile_version,
                InformationTopologyState.revision,
                InformationTopologyState.digest,
                InformationTopologyState.created_at,
                InformationTopologyState.payload,
            ).where(
                InformationTopologyState.project_key == project_key,
                InformationTopologyState.is_current.is_(True),
                InformationTopologyState.deleted.is_(False),
            ).order_by(
                InformationTopologyState.module_id,
                InformationTopologyState.namespace,
                InformationTopologyState.state_id,
            )
        ).all()
        return tuple({
            "module_id": module_id, "namespace": namespace, "state_id": state_id,
            "profile_id": profile_id, "profile_version": profile_version,
            "revision": revision, "digest": digest,
            "element_count": len(payload.get("elements", ())) if isinstance(payload, Mapping) else 0,
            "payload": payload,
        } for module_id, namespace, state_id, profile_id, profile_version, revision, digest, created_at, payload in rows)

    def prepare_state_write(self, write: StateWrite) -> Mapping[str, Any] | Failure:
        """Canonicalize and validate one candidate without touching a database session."""
        payload = topology_state_codec.to_wire(write.state)
        profile = self.resolve_profile(write.key[0], write.state.profile_id, write.state.profile_version, payload)
        if isinstance(profile, Failure):
            return profile
        encoded = encode_state(profile, write.state)
        if isinstance(encoded, Failure):
            return encoded
        if any(element.ref.ref.project_key != write.key[0] for element in write.state.elements):
            return topology_failures.fail("IDENTITY_CONFLICT", "state key project differs from element refs")
        return encoded

    def read_state(self, session: Session, key: StateKey, *, revision: int | None = None) -> dict[str, Any] | None | Failure:
        query = select(InformationTopologyState).where(
            InformationTopologyState.project_key == key[0],
            InformationTopologyState.module_id == key[1],
            InformationTopologyState.namespace == key[2],
            InformationTopologyState.state_id == key[3],
        )
        query = query.where(InformationTopologyState.is_current.is_(True)) if revision is None else query.where(
            InformationTopologyState.revision == revision
        )
        row = session.execute(query).scalar_one_or_none()
        if row is None:
            return None
        state = self.decode_row(row)
        if isinstance(state, Failure):
            return state
        return {
            "key": key, "revision": row.revision, "profile_id": row.profile_id,
            "profile_version": row.profile_version, "payload": row.payload,
            "provenance": row.provenance, "digest": row.digest,
            "deleted": row.deleted, "is_current": row.is_current,
            "state": state,
        }

    def apply_batch(
        self,
        session: Session,
        *,
        states: Sequence[StateWrite] = (),
        links: Sequence[LinkWrite] = (),
        read_set: Sequence[StateRead] = (),
        link_read_set: Sequence[LinkRead] = (),
    ) -> tuple[dict[str, int], ...] | Any:
        """Validate all target bases and protected reads before writing any revision.

        Caller must wrap this call in one ``with session.begin()`` transaction.
        PostgreSQL row locks serialize existing-object updates; partial unique
        indexes arbitrate first-creation races. Integrity conflicts must roll back
        the enclosing transaction.
        """
        state_keys = [write.key for write in states]
        link_keys = [(write.project_key, write.link_id) for write in links]
        if len(set(state_keys)) != len(state_keys) or len(set(link_keys)) != len(link_keys):
            return topology_failures.fail("INVALID_PATCH", "batch contains duplicate write targets")

        prepared: dict[StateKey, Mapping[str, Any]] = {}
        for write in states:
            payload = self.prepare_state_write(write)
            if isinstance(payload, Failure):
                return payload
            prepared[write.key] = payload
        for write in links:
            if write.record_kind not in {"relation", "mapping"}:
                return topology_failures.fail("INVALID_STRUCTURE", "link record_kind must be relation or mapping")
            try:
                _canonical({"endpoints": list(write.endpoints), "payload": dict(write.payload),
                            "provenance": dict(write.provenance or {})})
            except (TypeError, ValueError):
                return topology_failures.fail("INVALID_STRUCTURE", "link content must be canonical JSON data")

        # Read/protection locks use one deterministic order. Lock current rows first,
        # then compare every expected revision before any current flag is changed.
        locked_states: dict[StateKey, InformationTopologyState | None] = {}
        expected_state_keys = {entry.key: entry.expected_revision for entry in read_set}
        expected_state_keys.update({write.key: write.expected_revision for write in states})
        if len(expected_state_keys) != len(read_set) + len(states):
            return topology_failures.fail("INVALID_PATCH", "duplicate state in write/read set")
        for key in sorted(expected_state_keys):
            row = session.execute(
                select(InformationTopologyState).where(
                    InformationTopologyState.project_key == key[0],
                    InformationTopologyState.module_id == key[1],
                    InformationTopologyState.namespace == key[2],
                    InformationTopologyState.state_id == key[3],
                    InformationTopologyState.is_current.is_(True),
                ).with_for_update()
            ).scalar_one_or_none()
            locked_states[key] = row
            expected = expected_state_keys[key]
            actual = row.revision if row is not None else None
            if actual != expected:
                return topology_failures.fail(
                    "VERSION_CONFLICT", "state base revision changed",
                    {"key": key, "expected_revision": expected, "actual_revision": actual},
                )

        link_expected = {(entry.project_key, entry.link_id): entry.expected_revision for entry in link_read_set}
        for write in links:
            key = (write.project_key, write.link_id)
            if key in link_expected:
                return topology_failures.fail("INVALID_PATCH", "duplicate link in write/read set")
            link_expected[key] = write.expected_revision
        locked_links: dict[tuple[str, str], InformationTopologyLink | None] = {}
        for key in sorted(link_expected):
            row = session.execute(
                select(InformationTopologyLink).where(
                    InformationTopologyLink.project_key == key[0],
                    InformationTopologyLink.link_id == key[1],
                    InformationTopologyLink.is_current.is_(True),
                ).with_for_update()
            ).scalar_one_or_none()
            locked_links[key] = row
            actual = row.revision if row is not None else None
            expected = link_expected[key]
            if actual != expected:
                return topology_failures.fail(
                    "VERSION_CONFLICT", "link base revision changed",
                    {"key": key, "expected_revision": expected, "actual_revision": actual},
                )

        if any(locked_states[write.key] is not None and locked_states[write.key].deleted for write in states):
            return topology_failures.fail("IDENTITY_CONFLICT", "tombstoned state identity cannot be reused")
        if any(locked_links[(write.project_key, write.link_id)] is not None and
               locked_links[(write.project_key, write.link_id)].deleted for write in links):
            return topology_failures.fail("IDENTITY_CONFLICT", "tombstoned link identity cannot be reused")

        results: list[dict[str, int]] = []
        for write in states:
            payload = prepared[write.key]
            old = locked_states[write.key]
            revision = 1 if old is None else old.revision + 1
            if old is not None:
                old.is_current = False
            row = InformationTopologyState(
                project_key=write.key[0], module_id=write.key[1], namespace=write.key[2], state_id=write.key[3],
                profile_id=write.state.profile_id, profile_version=write.state.profile_version,
                revision=revision, payload=dict(payload), provenance=dict(write.provenance or {}),
                digest=_digest(payload), is_current=True, deleted=write.deleted,
            )
            session.add(row)
            results.append({"revision": revision})

        for write in links:
            old = locked_links[(write.project_key, write.link_id)]
            revision = 1 if old is None else old.revision + 1
            if old is not None:
                old.is_current = False
            content = {
                "record_kind": write.record_kind, "type_or_rule_ref": write.type_or_rule_ref,
                "endpoints": list(write.endpoints), "payload": dict(write.payload),
            }
            session.add(InformationTopologyLink(
                project_key=write.project_key, link_id=write.link_id, revision=revision,
                record_kind=write.record_kind, type_or_rule_ref=write.type_or_rule_ref,
                endpoints=list(write.endpoints), payload=dict(write.payload),
                provenance=dict(write.provenance or {}), digest=_digest(content), is_current=True,
                deleted=write.deleted,
            ))
            results.append({"revision": revision})
        session.flush()
        return tuple(results)

    def decode_row(self, row: InformationTopologyState) -> TopologyState | Failure:
        profile = self.resolve_profile(
            row.project_key, row.profile_id, row.profile_version, row.payload,
        )
        if isinstance(profile, Failure):
            return profile
        return decode_state(profile, row.payload)
