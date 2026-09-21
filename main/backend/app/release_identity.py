"""Canonical release identity for the repository and deployment projections."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


RELEASE_VERSION = "1.0.0"

RELEASE_BUILD_COMMIT_ENV = "RELEASE_BUILD_COMMIT"
RELEASE_BUILD_TREE_ENV = "RELEASE_BUILD_TREE"
RELEASE_BUILD_DIGEST_ENV = "RELEASE_BUILD_DIGEST"


@dataclass(frozen=True, slots=True)
class BuildIdentity:
    """Injected build coordinates; unmanaged coordinates remain ``None``."""

    version: str
    commit: str | None
    tree: str | None
    digest: str | None

    @property
    def fully_bound(self) -> bool:
        return all(value is not None for value in (self.commit, self.tree, self.digest))


def _bound_value(env: Mapping[str, str | None], name: str) -> str | None:
    value = env.get(name)
    if not isinstance(value, str):
        return None
    return value.strip() or None


def read_build_identity(
    env: Mapping[str, str | None] = os.environ,
) -> BuildIdentity:
    """Read explicit build coordinates without inventing defaults."""

    return BuildIdentity(
        version=RELEASE_VERSION,
        commit=_bound_value(env, RELEASE_BUILD_COMMIT_ENV),
        tree=_bound_value(env, RELEASE_BUILD_TREE_ENV),
        digest=_bound_value(env, RELEASE_BUILD_DIGEST_ENV),
    )
