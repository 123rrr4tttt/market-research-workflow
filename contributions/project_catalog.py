"""Single project-level catalog composed from the native MRW families."""

from __future__ import annotations

from functorial_kit.contributions import (
    ContributionCatalog,
    ContributionSpec,
    contribution_failures,
    define_contribution,
)

from app.successor_runtime.capabilities.workflow_common import (
    WORKFLOW_DEFINITION_FAILURES,
)
from app.composition.installed_operation import installed_operation_contribution_catalog

from mrw_functorial_kit.contributions.source import source_contribution_catalog
from mrw_functorial_kit.contributions.batch import batch_contribution_catalog
from mrw_functorial_kit.contributions.task import task_contribution_catalog
from mrw_functorial_kit.contributions.retrieval import retrieval_contribution_catalog


# Family modules remain the authored semantic sources.  This tuple is the
# only project-level composition used by the CLI and architecture check.
project_contribution_catalog = (
    define_contribution(
        ContributionSpec(
            id="mrw.project.failure.metadata.v1",
            owner="mrw.project",
            failures=(WORKFLOW_DEFINITION_FAILURES, contribution_failures),
        )
    ),
    *source_contribution_catalog,
    *batch_contribution_catalog,
    *task_contribution_catalog,
    *installed_operation_contribution_catalog,
    *retrieval_contribution_catalog,
)

contribution_catalog = ContributionCatalog(
    contributions=project_contribution_catalog,
    registries_dir="registries",
    sketches_path="sketches.json",
)

__all__ = ["contribution_catalog", "project_contribution_catalog"]
