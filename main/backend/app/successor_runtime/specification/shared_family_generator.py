"""Shared deterministic generator for successor family evidence fragments.

A thin family config supplies identity, cell-spec/ABI inputs, binding targets,
cell declarations and observation glue.  This module owns the mechanical
pipeline so that new families submit data and differences instead of a full
handwritten generator: repository-relative path confinement, the shared
capability-spec canonical JSON/digest rules, all-false authority ceilings,
deterministic fragment assembly, a strictly read-only ``--check`` gate, and
atomic write-if-changed output.

Two fragment paths are supported.  The pilot path assembles cells from
``CellFragmentConfig`` declarations plus observation glue (the C7 family).
Families whose fragment schema predates the pilot (``p3_fragment.v1`` and the
C8/C9 ``p4_fragment.v1`` variants) provide a body builder that receives the
already-computed exact bindings and returns the complete fragment body; the
shared module still owns confinement, digest, authority, determinism,
self-check and the read-only check gate.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .capability_cell_spec import CapabilityCellSpec
from .runtime_kernel_abi import RuntimeKernelABI

BindingsByKind = Mapping[str, list[dict[str, Any]]]
FragmentBodyBuilder = Callable[[Path, BindingsByKind], Mapping[str, Any]]


class FamilyGeneratorError(ValueError):
    """Invalid family input, escaped path or failed fragment invariant."""


ObservationPair = tuple[Mapping[str, Any], Mapping[str, Any]]
RollbackBuilder = Callable[
    [str, Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]
]


@dataclass(frozen=True, slots=True)
class BindingTarget:
    """Repository-relative file path and evidence role for one exact binding."""

    path: str
    role: str
    read_only: bool = False


@dataclass(frozen=True, slots=True)
class CellFragmentConfig:
    """Declared cell data; observations stay in family observation glue."""

    cell_id: str
    contract_ids: tuple[str, ...]
    p1_locator_paths: tuple[str, ...]
    p1_locator_status: str
    postgres_requirement: str


@dataclass(frozen=True, slots=True)
class FamilyFragmentConfig:
    """Thin family declaration consumed by the shared fragment pipeline."""

    family_id: str
    phase: str
    schema: str
    fragment_id: str
    status: str
    fragment_output_rel: str
    source_bindings: tuple[BindingTarget, ...]
    implementation_bindings: tuple[BindingTarget, ...]
    test_bindings: tuple[BindingTarget, ...]
    authority: Mapping[str, bool]
    open_findings: tuple[Mapping[str, Any], ...]
    lifecycle_state: str = ""
    project_key: str = ""
    registry_revision: int = 0
    resolved_schema: str = ""
    scope_incarnation: str = ""
    cell_spec_path: str | None = None
    runtime_kernel_abi_path: str | None = None
    cells: tuple[CellFragmentConfig, ...] = ()
    build_observations: Callable[[str], ObservationPair] | None = None
    build_rollback_observation: RollbackBuilder | None = None
    body_builder: FragmentBodyBuilder | None = None
    self_check: Callable[[Mapping[str, Any]], None] | None = None
    serialize_fragment: Callable[[Mapping[str, Any]], bytes] | None = None


def canonical_json(value: Any) -> str:
    """Canonical JSON string for family fragment evidence.

    The family fragment convention matches the legacy fragment generators:
    sort keys, compact separators and ``ensure_ascii=True`` so non-ASCII
    payloads are escaped deterministically.
    """

    return _family_canonical_bytes(value).decode("utf-8")


def content_digest(value: Any) -> str:
    """Canonical content digest shared by fragments and family glue."""

    return hashlib.sha256(_family_canonical_bytes(value)).hexdigest()


def _family_canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _require_text(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise FamilyGeneratorError(f"{label} must be a non-empty string")


def validate_config(config: FamilyFragmentConfig) -> None:
    """Fail closed on missing fields, drift-prone data or enabled authority."""

    for label in (
        "family_id",
        "phase",
        "schema",
        "fragment_id",
        "status",
        "fragment_output_rel",
    ):
        _require_text(getattr(config, label), label)
    if not isinstance(config.authority, Mapping) or not config.authority:
        raise FamilyGeneratorError("authority must be a non-empty mapping")
    if not all(isinstance(value, bool) for value in config.authority.values()):
        raise FamilyGeneratorError("authority values must be booleans")
    if any(config.authority.values()):
        raise FamilyGeneratorError("authority ceiling must be all false")
    for label in ("source_bindings", "implementation_bindings", "test_bindings"):
        entries = getattr(config, label)
        if not isinstance(entries, (list, tuple)) or not entries:
            raise FamilyGeneratorError(f"{label} must be a non-empty list/tuple")
        if any(not isinstance(entry, BindingTarget) for entry in entries):
            raise FamilyGeneratorError(f"{label} must contain BindingTarget values")
        for entry in entries:
            _require_text(entry.path, f"{label} path")
            _require_text(entry.role, f"{label} role")
            if not isinstance(entry.read_only, bool):
                raise FamilyGeneratorError(f"{label} read_only must be a boolean")
        paths = [entry.path for entry in entries]
        if len(paths) != len(set(paths)):
            raise FamilyGeneratorError(f"{label} paths must be unique")
    if config.body_builder is None:
        if config.cell_spec_path is None or config.runtime_kernel_abi_path is None:
            raise FamilyGeneratorError(
                "pilot fragment path requires cell_spec_path and "
                "runtime_kernel_abi_path"
            )
        for label in (
            "lifecycle_state",
            "project_key",
            "resolved_schema",
            "scope_incarnation",
        ):
            _require_text(getattr(config, label), label)
        if (
            not isinstance(config.registry_revision, int)
            or config.registry_revision <= 0
        ):
            raise FamilyGeneratorError("registry_revision must be a positive integer")
        if not isinstance(config.cells, (list, tuple)) or not config.cells:
            raise FamilyGeneratorError("cells must be a non-empty list/tuple")
        seen_cells: set[str] = set()
        for cell in config.cells:
            if not isinstance(cell, CellFragmentConfig):
                raise FamilyGeneratorError(
                    "cells must contain CellFragmentConfig values"
                )
            _require_text(cell.cell_id, "cell.cell_id")
            if cell.cell_id in seen_cells:
                raise FamilyGeneratorError(f"duplicate cell_id: {cell.cell_id}")
            seen_cells.add(cell.cell_id)
            if (
                not isinstance(cell.contract_ids, (list, tuple))
                or not cell.contract_ids
            ):
                raise FamilyGeneratorError(
                    f"{cell.cell_id} contract_ids must be non-empty"
                )
            if not isinstance(cell.p1_locator_paths, (list, tuple)) or not (
                cell.p1_locator_paths
            ):
                raise FamilyGeneratorError(
                    f"{cell.cell_id} p1_locator_paths must be non-empty"
                )
            _require_text(cell.p1_locator_status, f"{cell.cell_id} p1_locator_status")
            _require_text(
                cell.postgres_requirement, f"{cell.cell_id} postgres_requirement"
            )
        if not callable(config.build_observations):
            raise FamilyGeneratorError("build_observations must be callable")
        if not callable(config.build_rollback_observation):
            raise FamilyGeneratorError("build_rollback_observation must be callable")
    else:
        if not callable(config.body_builder):
            raise FamilyGeneratorError("body_builder must be callable")
        if config.self_check is not None and not callable(config.self_check):
            raise FamilyGeneratorError("self_check must be callable when provided")
        if config.serialize_fragment is not None and not callable(
            config.serialize_fragment
        ):
            raise FamilyGeneratorError(
                "serialize_fragment must be callable when provided"
            )


def confine(root: Path, relative: str) -> Path:
    """Resolve one repository-relative path, rejecting escape or absolutes."""

    _require_text(relative, "path")
    candidate = Path(relative)
    if candidate.is_absolute():
        raise FamilyGeneratorError(f"path must be repository-relative: {relative}")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise FamilyGeneratorError(f"path escapes repository root: {relative}") from exc
    return resolved


def _load_json_object(path: Path, label: str) -> Mapping[str, Any]:
    if not path.is_file():
        raise FamilyGeneratorError(f"{label} missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FamilyGeneratorError(f"{label} invalid: {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise FamilyGeneratorError(f"{label} must be a JSON object: {path}")
    return value


def validate_inputs(root: Path, config: FamilyFragmentConfig) -> None:
    """Load and validate the declared cell spec and runtime kernel ABI."""

    if config.cell_spec_path is not None:
        spec_path = confine(root, config.cell_spec_path)
        spec = CapabilityCellSpec.from_dict(
            _load_json_object(spec_path, "capability cell spec")
        )
        if spec.family_id != config.family_id:
            raise FamilyGeneratorError(
                f"cell spec family {spec.family_id} != config {config.family_id}"
            )
        if config.body_builder is None:
            cell_ids = {cell.cell_id for cell in config.cells}
            if spec.cell_id not in cell_ids:
                raise FamilyGeneratorError(
                    f"cell spec {spec.cell_id} not declared by family config"
                )
        if any(spec.authority_ceiling.to_dict().values()):
            raise FamilyGeneratorError("cell spec authority ceiling must be all false")
    if config.runtime_kernel_abi_path is not None:
        abi_path = confine(root, config.runtime_kernel_abi_path)
        RuntimeKernelABI.from_dict(
            _load_json_object(abi_path, "runtime kernel ABI")
        ).with_digest()


def bind_file(root: Path, target: BindingTarget) -> dict[str, Any]:
    """Compute one exact evidence binding; missing files fail closed."""

    path = confine(root, target.path)
    if not path.is_file():
        raise FamilyGeneratorError(f"binding missing: {target.path}")
    data = path.read_bytes()
    binding = {
        "path": str(path.relative_to(root.resolve())),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "lines": len(data.splitlines()),
        "role": target.role,
    }
    if target.read_only:
        binding["read_only"] = True
    return binding


def build_fragment(config: FamilyFragmentConfig, repo_root: Path) -> dict[str, Any]:
    """Assemble one deterministic family fragment with a self-digest."""

    validate_config(config)
    root = repo_root.resolve()
    validate_inputs(root, config)
    bindings: dict[str, list[dict[str, Any]]] = {
        "source_bindings": [
            bind_file(root, target) for target in config.source_bindings
        ],
        "implementation_bindings": [
            bind_file(root, target) for target in config.implementation_bindings
        ],
        "test_bindings": [bind_file(root, target) for target in config.test_bindings],
    }
    if config.body_builder is not None:
        body = dict(config.body_builder(root, bindings))
        body.pop("content_digest", None)
        fragment: dict[str, Any] = dict(body)
        fragment["content_digest"] = content_digest(
            {key: value for key, value in fragment.items() if key != "content_digest"}
        )
        generic_self_test(fragment, config)
        if config.self_check is not None:
            config.self_check(fragment)
        return fragment
    cells: list[dict[str, Any]] = []
    for cell in config.cells:
        successor, legacy = config.build_observations(cell.cell_id)
        if not isinstance(successor, Mapping) or not isinstance(legacy, Mapping):
            raise FamilyGeneratorError(f"{cell.cell_id} observations must be mappings")
        rollback = config.build_rollback_observation(cell.cell_id, successor, legacy)
        if not isinstance(rollback, Mapping) or not rollback.get("rollback_digest"):
            raise FamilyGeneratorError(
                f"{cell.cell_id} rollback observation must carry a rollback_digest"
            )
        cells.append(
            {
                "cell_id": cell.cell_id,
                "p1_locators": {
                    "locator_paths": list(cell.p1_locator_paths),
                    "locator_status": cell.p1_locator_status,
                },
                "contract_ids": list(cell.contract_ids),
                "legacy_observation": dict(legacy),
                "successor_observation": dict(successor),
                "rollback_observation": dict(rollback),
                "provider_calls": 0,
                "postgres_requirement": cell.postgres_requirement,
            }
        )
    fragment: dict[str, Any] = {
        "schema": config.schema,
        "phase": config.phase,
        "family": config.family_id,
        "fragment_id": config.fragment_id,
        "status": config.status,
        "lifecycle_state": config.lifecycle_state,
        "cells": cells,
        "source_bindings": [
            bind_file(root, target) for target in config.source_bindings
        ],
        "implementation_bindings": [
            bind_file(root, target) for target in config.implementation_bindings
        ],
        "test_bindings": [bind_file(root, target) for target in config.test_bindings],
        "authority": dict(config.authority),
        "open_findings": [dict(finding) for finding in config.open_findings],
        "content_digest": "",
    }
    fragment["content_digest"] = content_digest(
        {key: value for key, value in fragment.items() if key != "content_digest"}
    )
    return fragment


def generic_self_test(
    fragment: Mapping[str, Any], config: FamilyFragmentConfig
) -> None:
    """Verify the shared invariants of a config-built fragment body."""

    expected = content_digest(
        {key: value for key, value in fragment.items() if key != "content_digest"}
    )
    if fragment.get("content_digest") != expected:
        raise FamilyGeneratorError("fragment content_digest mismatch")
    for fragment_label, config_attr in (
        ("schema", "schema"),
        ("phase", "phase"),
        ("family", "family_id"),
        ("fragment_id", "fragment_id"),
        ("status", "status"),
    ):
        if fragment.get(fragment_label) != getattr(config, config_attr):
            raise FamilyGeneratorError(
                f"fragment {fragment_label} does not match config"
            )
    authority = fragment["authority"]
    if not isinstance(authority, Mapping) or not authority or any(authority.values()):
        raise FamilyGeneratorError("authority ceiling must be non-empty and all false")
    if not fragment.get("cells"):
        raise FamilyGeneratorError("fragment must contain cells")
    for label in ("source_bindings", "implementation_bindings", "test_bindings"):
        bindings = fragment[label]
        if not bindings:
            raise FamilyGeneratorError(f"{label} must not be empty")
        for binding in bindings:
            allowed = {"path", "sha256", "bytes", "lines", "role"}
            if binding.get("read_only") is True:
                allowed.add("read_only")
            if set(binding) != allowed:
                raise FamilyGeneratorError(f"{label} binding shape mismatch")
            if len(binding["sha256"]) != 64:
                raise FamilyGeneratorError(f"{label} sha256 must be hex-64")
    findings = fragment["open_findings"]
    if not findings or any("id" not in finding for finding in findings):
        raise FamilyGeneratorError("open_findings must be non-empty with ids")


def self_test(fragment: Mapping[str, Any], config: FamilyFragmentConfig) -> None:
    """Verify shared fragment invariants before any output is accepted."""

    expected = content_digest(
        {key: value for key, value in fragment.items() if key != "content_digest"}
    )
    if fragment.get("content_digest") != expected:
        raise FamilyGeneratorError("fragment content_digest mismatch")
    config_fields = {
        "schema": "schema",
        "phase": "phase",
        "family": "family_id",
        "fragment_id": "fragment_id",
        "status": "status",
        "lifecycle_state": "lifecycle_state",
    }
    for fragment_label, config_attr in config_fields.items():
        if fragment.get(fragment_label) != getattr(config, config_attr):
            raise FamilyGeneratorError(
                f"fragment {fragment_label} does not match config"
            )
    authority = fragment["authority"]
    if not isinstance(authority, Mapping) or not authority or any(authority.values()):
        raise FamilyGeneratorError("authority ceiling must be non-empty and all false")
    cells = fragment["cells"]
    if not cells:
        raise FamilyGeneratorError("fragment must contain cells")
    for cell in cells:
        for key in (
            "cell_id",
            "p1_locators",
            "contract_ids",
            "legacy_observation",
            "successor_observation",
            "rollback_observation",
            "provider_calls",
            "postgres_requirement",
        ):
            if key not in cell:
                raise FamilyGeneratorError(f"cell missing required field {key}")
        if cell["provider_calls"] != 0:
            raise FamilyGeneratorError("cell provider_calls must be zero")
        for observation in ("successor_observation", "legacy_observation"):
            if cell[observation]["provider_calls"] != 0:
                raise FamilyGeneratorError(
                    f"{cell['cell_id']} {observation} provider_calls must be zero"
                )
            if cell[observation]["authority"] is not False:
                raise FamilyGeneratorError(
                    f"{cell['cell_id']} {observation} authority must be False"
                )
        if not cell["rollback_observation"].get("rollback_digest"):
            raise FamilyGeneratorError(f"{cell['cell_id']} rollback_digest is required")
        if not cell["p1_locators"].get("locator_paths"):
            raise FamilyGeneratorError(f"{cell['cell_id']} locator_paths are required")
    for label in ("source_bindings", "implementation_bindings", "test_bindings"):
        bindings = fragment[label]
        if not bindings:
            raise FamilyGeneratorError(f"{label} must not be empty")
        for binding in bindings:
            allowed = {"path", "sha256", "bytes", "lines", "role"}
            if binding.get("read_only") is True:
                allowed.add("read_only")
            if set(binding) != allowed:
                raise FamilyGeneratorError(f"{label} binding shape mismatch")
            if len(binding["sha256"]) != 64:
                raise FamilyGeneratorError(f"{label} sha256 must be hex-64")
    findings = fragment["open_findings"]
    if not findings or any("id" not in finding for finding in findings):
        raise FamilyGeneratorError("open_findings must be non-empty with ids")


def build_fragment_bytes(fragment: Mapping[str, Any]) -> bytes:
    """Canonical persisted bytes; callers add no formatting or comments."""

    return _family_canonical_bytes(fragment) + b"\n"


def fragment_bytes(config: FamilyFragmentConfig, fragment: Mapping[str, Any]) -> bytes:
    """Persisted bytes for one family, honoring a family serializer when set."""

    if config.serialize_fragment is not None:
        return config.serialize_fragment(fragment)
    return build_fragment_bytes(fragment)


def write_atomic_if_changed(path: Path, data: bytes) -> bool:
    """Write atomically only when the current bytes differ."""

    if path.is_file() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return True


def run_generate(
    config: FamilyFragmentConfig,
    repo_root: Path,
    *,
    check: bool = False,
    output_path: Path | None = None,
) -> int:
    """Run the shared pipeline: UNKNOWN=2, DRIFT=1, MATCH=0 in check mode.

    ``output_path`` is an explicit alternate target used by tests; production
    callers omit it and the configured repository-relative output is confined.
    """

    try:
        root = Path(repo_root).resolve()
        output = (
            confine(root, config.fragment_output_rel)
            if output_path is None
            else output_path.resolve()
        )
        first = build_fragment(config, root)
        second = build_fragment(config, root)
        if fragment_bytes(config, first) != fragment_bytes(config, second):
            raise FamilyGeneratorError("fragment generation is not deterministic")
        if config.body_builder is None:
            self_test(first, config)
        expected = fragment_bytes(config, first)
    except (
        FamilyGeneratorError,
        TypeError,
        ValueError,
        KeyError,
        AttributeError,
        OSError,
    ) as exc:
        print(f"UNKNOWN: {exc}", file=os.sys.stderr)
        return 2

    if check:
        if not output.is_file() or output.read_bytes() != expected:
            print(f"DRIFT: {output}", file=os.sys.stderr)
            return 1
        print(f"MATCH: {output}")
        return 0
    write_atomic_if_changed(output, expected)
    print(f"WROTE: {output}")
    return 0
