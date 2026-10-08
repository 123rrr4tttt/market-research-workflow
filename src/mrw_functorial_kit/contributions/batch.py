"""Contribution metadata for the retained agent-batch failure authority."""

from __future__ import annotations

from functorial_kit.contributions import (
    ContributionCatalog,
    ContributionSpec,
    define_contribution,
)
from mrw_functorial_kit.core.agent_service_semantics import agent_batch_failures


batch_contribution = define_contribution(
    ContributionSpec[None, None](
        id="mrw.batch.failure.metadata.v1",
        owner="mrw.batch",
        failures=(agent_batch_failures,),
    )
)

batch_contribution_catalog = (batch_contribution,)

contribution_catalog = ContributionCatalog(
    contributions=batch_contribution_catalog,
    registries_dir="registries",
    sketches_path="sketches.json",
)

__all__ = ["batch_contribution_catalog", "contribution_catalog"]
