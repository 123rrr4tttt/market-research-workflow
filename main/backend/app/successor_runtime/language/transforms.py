"""Named, versioned, serializable transform/merge/discriminator registries.

Program AST nodes only reference registry refs.  Arbitrary Python callables are
never embedded in a persisted program; the registries are process-local and
reject functions that cannot be audited as pure.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable

from .algebra import ObjectType, canonical_digest


class RegistryError(ValueError):
    """Raised for invalid registry entries or references."""


@dataclass(frozen=True, slots=True)
class _RefBase:
    name: str
    version: str
    digest: str
    transform_kind: str

    def label(self) -> str:
        return f"{self.name}@{self.version}"

    def ref_digest(self) -> str:
        return canonical_digest(
            {
                "transform_kind": self.transform_kind,
                "name": self.name,
                "version": self.version,
                "digest": self.digest,
            }
        )

    def to_plain(self) -> "dict[str, Any]":
        return {
            "transform_kind": self.transform_kind,
            "name": self.name,
            "version": self.version,
            "digest": self.digest,
        }


@dataclass(frozen=True, slots=True)
class TransformRef(_RefBase):
    transform_kind: str = "transform"


@dataclass(frozen=True, slots=True)
class MergeRef(_RefBase):
    transform_kind: str = "merge"


@dataclass(frozen=True, slots=True)
class DiscriminatorRef(_RefBase):
    transform_kind: str = "discriminator"


@dataclass(frozen=True, slots=True)
class TransformEntry:
    id: str
    version: str
    input_type: ObjectType
    output_type: ObjectType
    digest: str
    loss_profile_id: "str | None"
    preserves_value_ref: bool
    callable: Callable[..., Any]


@dataclass(frozen=True, slots=True)
class MergeEntry:
    id: str
    version: str
    left_type: ObjectType
    right_type: ObjectType
    output_type: ObjectType
    digest: str
    callable: Callable[..., Any]


@dataclass(frozen=True, slots=True)
class DiscriminatorEntry:
    id: str
    version: str
    input_type: ObjectType
    branch_ids: "tuple[str, ...]"
    digest: str
    callable: Callable[..., str]


def compute_pure_function_digest(
    func: Callable[..., Any],
    input_type: ObjectType,
    output_type: ObjectType,
    *,
    preserves_value_ref: bool = False,
) -> str:
    source = inspect.getsource(func).strip()
    binding = {
        "source": source,
        "module": func.__module__,
        "qualname": func.__qualname__,
        "input_digest": canonical_digest(input_type),
        "output_digest": canonical_digest(output_type),
    }
    if preserves_value_ref:
        binding["preserves_value_ref"] = True
    return canonical_digest(binding)


def _assert_pure_function(func: Callable[..., Any], label: str) -> None:
    if not inspect.isfunction(func):
        raise RegistryError(f"{label}: only plain functions may be registered")
    code = func.__code__
    if code.co_flags & (inspect.CO_NESTED | inspect.CO_COROUTINE | inspect.CO_ASYNC_GENERATOR):
        raise RegistryError(f"{label}: nested or async callables are not allowed")
    if code.co_freevars or code.co_cellvars:
        raise RegistryError(f"{label}: closures are not allowed")
    source = inspect.getsource(func)
    lowered = source.lower()
    if "exec(" in lowered or "eval(" in lowered or "__import__" in lowered:
        raise RegistryError(f"{label}: dynamic execution is not allowed")


class TransformRegistry:
    """Immutable-on-write registry of named pure transforms."""

    def __init__(
        self,
        *,
        registry_id: str = "mrw.successor.default.transforms.v1",
        registry_version: str = "1",
    ) -> None:
        self.registry_id = registry_id
        self.registry_version = registry_version
        self._transforms: "dict[tuple[str, str], TransformEntry]" = {}
        self._merges: "dict[tuple[str, str], MergeEntry]" = {}
        self._discriminators: "dict[tuple[str, str], DiscriminatorEntry]" = {}

    def register_transform(
        self,
        *,
        name: str,
        version: str,
        input_type: ObjectType,
        output_type: ObjectType,
        func: Callable[..., Any],
        loss_profile_id: "str | None" = None,
        preserves_value_ref: bool = False,
    ) -> TransformRef:
        _assert_pure_function(func, name)
        if preserves_value_ref and (
            canonical_digest(input_type) != canonical_digest(output_type)
            or loss_profile_id is not None
        ):
            raise RegistryError(
                f"{name}: ValueRef-preserving transform requires one exact type and no loss profile"
            )
        key = (name, version)
        if key in self._transforms:
            raise RegistryError(f"transform {name}@{version} already registered")
        digest = compute_pure_function_digest(
            func,
            input_type,
            output_type,
            preserves_value_ref=preserves_value_ref,
        )
        self._transforms[key] = TransformEntry(
            id=name,
            version=version,
            input_type=input_type,
            output_type=output_type,
            digest=digest,
            loss_profile_id=loss_profile_id,
            preserves_value_ref=preserves_value_ref,
            callable=func,
        )
        return TransformRef(
            name=name,
            version=version,
            digest=digest,
            transform_kind="transform",
        )

    def register_merge(
        self,
        *,
        name: str,
        version: str,
        left_type: ObjectType,
        right_type: ObjectType,
        output_type: ObjectType,
        func: Callable[..., Any],
    ) -> MergeRef:
        _assert_pure_function(func, name)
        key = (name, version)
        if key in self._merges:
            raise RegistryError(f"merge {name}@{version} already registered")
        digest = canonical_digest(
            {
                "source": inspect.getsource(func).strip(),
                "module": func.__module__,
                "qualname": func.__qualname__,
                "left_digest": canonical_digest(left_type),
                "right_digest": canonical_digest(right_type),
                "output_digest": canonical_digest(output_type),
            }
        )
        self._merges[key] = MergeEntry(
            id=name,
            version=version,
            left_type=left_type,
            right_type=right_type,
            output_type=output_type,
            digest=digest,
            callable=func,
        )
        return MergeRef(
            name=name,
            version=version,
            digest=digest,
            transform_kind="merge",
        )

    def register_discriminator(
        self,
        *,
        name: str,
        version: str,
        input_type: ObjectType,
        branch_ids: "tuple[str, ...]",
        func: Callable[..., str],
    ) -> DiscriminatorRef:
        _assert_pure_function(func, name)
        key = (name, version)
        if key in self._discriminators:
            raise RegistryError(f"discriminator {name}@{version} already registered")
        if not branch_ids or len(set(branch_ids)) != len(branch_ids):
            raise RegistryError("discriminator branch_ids must be unique and non-empty")
        digest = canonical_digest(
            {
                "source": inspect.getsource(func).strip(),
                "module": func.__module__,
                "qualname": func.__qualname__,
                "input_digest": canonical_digest(input_type),
                "branch_ids": sorted(branch_ids),
            }
        )
        self._discriminators[key] = DiscriminatorEntry(
            id=name,
            version=version,
            input_type=input_type,
            branch_ids=branch_ids,
            digest=digest,
            callable=func,
        )
        return DiscriminatorRef(
            name=name,
            version=version,
            digest=digest,
            transform_kind="discriminator",
        )

    def resolve_transform(self, ref: TransformRef) -> TransformEntry:
        entry = self._transforms.get((ref.name, ref.version))
        if entry is None or entry.digest != ref.digest:
            raise RegistryError(f"unknown transform {ref.label()}")
        return entry

    def resolve_merge(self, ref: MergeRef) -> MergeEntry:
        entry = self._merges.get((ref.name, ref.version))
        if entry is None or entry.digest != ref.digest:
            raise RegistryError(f"unknown merge {ref.label()}")
        return entry

    def resolve_discriminator(self, ref: DiscriminatorRef) -> DiscriminatorEntry:
        entry = self._discriminators.get((ref.name, ref.version))
        if entry is None or entry.digest != ref.digest:
            raise RegistryError(f"unknown discriminator {ref.label()}")
        return entry

    def has_transform(self, ref: TransformRef) -> bool:
        entry = self._transforms.get((ref.name, ref.version))
        return entry is not None and entry.digest == ref.digest

    def has_merge(self, ref: MergeRef) -> bool:
        entry = self._merges.get((ref.name, ref.version))
        return entry is not None and entry.digest == ref.digest

    def has_discriminator(self, ref: DiscriminatorRef) -> bool:
        entry = self._discriminators.get((ref.name, ref.version))
        return entry is not None and entry.digest == ref.digest

    def transform_refs(self) -> "tuple[TransformRef, ...]":
        return tuple(
            TransformRef(
                name=entry.id,
                version=entry.version,
                digest=entry.digest,
                transform_kind="transform",
            )
            for entry in self._transforms.values()
        )

    def merge_refs(self) -> "tuple[MergeRef, ...]":
        return tuple(
            MergeRef(
                name=entry.id,
                version=entry.version,
                digest=entry.digest,
                transform_kind="merge",
            )
            for entry in self._merges.values()
        )

    def discriminator_refs(self) -> "tuple[DiscriminatorRef, ...]":
        return tuple(
            DiscriminatorRef(
                name=entry.id,
                version=entry.version,
                digest=entry.digest,
                transform_kind="discriminator",
            )
            for entry in self._discriminators.values()
        )


def merge_output_type(
    registry: TransformRegistry,
    ref: MergeRef,
    left_type: ObjectType,
    right_type: ObjectType,
) -> ObjectType:
    entry = registry.resolve_merge(ref)
    if (
        canonical_digest(entry.left_type) != canonical_digest(left_type)
        or canonical_digest(entry.right_type) != canonical_digest(right_type)
    ):
        raise RegistryError(f"merge {ref.label()} type mismatch")
    return entry.output_type


def discriminator_branch_ids(
    registry: TransformRegistry,
    ref: DiscriminatorRef,
    branch_count: int,
) -> "tuple[str, ...]":
    entry = registry.resolve_discriminator(ref)
    if len(entry.branch_ids) != branch_count:
        raise RegistryError(
            f"discriminator {ref.label()} expects {len(entry.branch_ids)} branches"
        )
    return entry.branch_ids
