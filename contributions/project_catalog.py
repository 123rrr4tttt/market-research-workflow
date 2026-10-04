"""Single project-level catalog composed from the native MRW families."""

from __future__ import annotations

from functorial_kit.contributions import ContributionCatalog

from mrw_functorial_kit.contributions.workflow import workflow_contribution_catalog
from mrw_functorial_kit.contributions.source import source_contribution_catalog
from mrw_functorial_kit.contributions.acquisition import acquisition_contribution_catalog
from mrw_functorial_kit.contributions.batch import batch_contribution_catalog
from mrw_functorial_kit.contributions.task import task_contribution_catalog
from mrw_functorial_kit.contributions.material import material_contribution_catalog
from mrw_functorial_kit.contributions.knowledge import knowledge_contribution_catalog
from mrw_functorial_kit.contributions.projection import projection_contribution_catalog
from mrw_functorial_kit.contributions.retrieval import retrieval_contribution_catalog


# Family modules remain the authored semantic sources.  This tuple is the
# only project-level composition used by the CLI and architecture check.
project_contribution_catalog = (
    *workflow_contribution_catalog,
    *source_contribution_catalog,
    *acquisition_contribution_catalog,
    *batch_contribution_catalog,
    *task_contribution_catalog,
    *material_contribution_catalog,
    *knowledge_contribution_catalog,
    *projection_contribution_catalog,
    *retrieval_contribution_catalog,
)

contribution_catalog = ContributionCatalog(
    contributions=project_contribution_catalog,
    registries_dir="registries",
    sketches_path="sketches.json",
)

__all__ = ["contribution_catalog", "project_contribution_catalog"]
