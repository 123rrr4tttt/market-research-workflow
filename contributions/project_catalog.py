"""Single project-level catalog composed from the native MRW families."""

from __future__ import annotations

from typing import Any

from app.composition.installed_operation import installed_operation_contribution_catalog
from app.composition.raw_material_import_task import (
    raw_material_import_task_contribution_catalog,
)
from app.contracts.ingest_config_failures import ingest_config_failures
from app.successor_runtime.capabilities.workflow_common import (
    WORKFLOW_DEFINITION_FAILURES,
)
from functorial_kit.contributions import (
    Contribution,
    ContributionCatalog,
    ContributionSpec,
    contribution_failures,
    define_contribution,
)

from mrw_functorial_kit.contributions.batch import batch_contribution_catalog
from mrw_functorial_kit.contributions.retrieval import retrieval_contribution_catalog
from mrw_functorial_kit.contributions.source import source_contribution_catalog
from mrw_functorial_kit.contributions.task import task_contribution_catalog
from mrw_functorial_kit.core.application_failure_semantics import (
    source_library_contract_failures,
)
from mrw_functorial_kit.core.provider_port_failures import (
    ingest_operation_failures,
    resource_pool_http_fetch_failures,
)
from mrw_functorial_kit.core.service_failure_semantics import material_query_failures

# Family modules remain the authored semantic sources.  This tuple is the
# only project-level composition used by the CLI and architecture check.
project_contribution_catalog: tuple[Contribution[Any, Any], ...] = (
    define_contribution(
        ContributionSpec[object, object](
            id="mrw.project.failure.metadata.v1",
            owner="mrw.project",
            failures=(
                WORKFLOW_DEFINITION_FAILURES,
                contribution_failures,
                source_library_contract_failures,
                ingest_operation_failures,
                resource_pool_http_fetch_failures,
                material_query_failures,
                ingest_config_failures,
            ),
        )
    ),
    *source_contribution_catalog,
    *batch_contribution_catalog,
    *task_contribution_catalog,
    *raw_material_import_task_contribution_catalog,
    *installed_operation_contribution_catalog,
    *retrieval_contribution_catalog,
)

contribution_catalog = ContributionCatalog(
    contributions=project_contribution_catalog,
    registries_dir="registries",
    sketches_path="sketches.json",
)

__all__ = ["contribution_catalog", "project_contribution_catalog"]
