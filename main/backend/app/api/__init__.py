from fastapi import APIRouter, Depends

from app.composition.production import is_production_environment
from app.composition.production_runtime import (
    build_production_successor_runtime_app_dependencies,
)
from app.models.base import engine
from app.successor_runtime.assembly.app_assembly import (
    build_successor_runtime_app_dependencies,
)

from .admin import router as admin_router
from .agent_batch import router as agent_batch_router
from .agent_chat import router as agent_chat_router
from .agent_sessions import router as agent_sessions_router
from .business_lines import router as business_lines_router
from .clue_chains import router as clue_chains_router
from .codex_auth import bootstrap_router as codex_auth_bootstrap_router
from .codex_auth import router as codex_auth_router
from .config import router as config_router
from .crawler import router as crawler_router
from .dashboard import router as dashboard_router
from .discovery import router as discovery_router
from .functorial import router as functorial_router
from .governance import router as governance_router
from .indexer import router as indexer_router
from .ingest import router as ingest_router
from .keywords import router as keywords_router
from .llm_config import router as llm_config_router
from .llm_report import router as llm_report_router
from .market import router as market_router
from .policies import router as policies_router
from .process import router as process_router
from .products import router as products_router
from .project_customization import router as project_customization_router
from .projects import router as projects_router
from .reports import router as reports_router
from .resource_pool import router as resource_pool_router
from .search import router as search_router
from .skills import router as skills_router
from .source_library import router as source_library_router
from .stats import router as stats_router
from .successor_runtime import create_successor_runtime_router
from .topics import router as topics_router
from .typed_knowledge import router as typed_knowledge_router
from .workflow_graph import router as workflow_graph_router
from .writing import router as writing_router
from ..composition.production import require_production_policy

# One root dependency is the sole production deny gate.  The dependency is a
# no-op in dev/test/local, preserving the existing route behavior there.
router = APIRouter()
codex_auth_public_router = APIRouter()
codex_auth_public_router.include_router(codex_auth_bootstrap_router)
router.include_router(codex_auth_public_router)

production_policy_router = APIRouter(dependencies=[Depends(require_production_policy)])
production_policy_router.include_router(codex_auth_router)
production_policy_router.include_router(policies_router)
production_policy_router.include_router(market_router)
production_policy_router.include_router(search_router)
production_policy_router.include_router(reports_router)
production_policy_router.include_router(config_router)
production_policy_router.include_router(ingest_router)
production_policy_router.include_router(discovery_router)
production_policy_router.include_router(functorial_router)
production_policy_router.include_router(indexer_router)
production_policy_router.include_router(admin_router)
production_policy_router.include_router(dashboard_router)
production_policy_router.include_router(llm_config_router)
production_policy_router.include_router(process_router)
production_policy_router.include_router(topics_router)
production_policy_router.include_router(projects_router)
production_policy_router.include_router(products_router)
production_policy_router.include_router(governance_router)
production_policy_router.include_router(source_library_router)
production_policy_router.include_router(project_customization_router)
production_policy_router.include_router(resource_pool_router)
production_policy_router.include_router(crawler_router)
production_policy_router.include_router(keywords_router)
production_policy_router.include_router(llm_report_router)
production_policy_router.include_router(workflow_graph_router)
production_policy_router.include_router(stats_router)
production_policy_router.include_router(writing_router)
production_policy_router.include_router(typed_knowledge_router)
production_policy_router.include_router(agent_batch_router)
production_policy_router.include_router(agent_chat_router)
production_policy_router.include_router(agent_sessions_router)
production_policy_router.include_router(business_lines_router)
production_policy_router.include_router(skills_router)
production_policy_router.include_router(clue_chains_router)
# Production queries read the authoritative PostgreSQL scope and projection;
# dev/test/local retain the closed deterministic mount.
_successor_runtime_dependencies = (
    build_production_successor_runtime_app_dependencies(engine)
    if is_production_environment()
    else build_successor_runtime_app_dependencies()
)
production_policy_router.include_router(
    create_successor_runtime_router(
        resolver=_successor_runtime_dependencies.resolver,
        facade=_successor_runtime_dependencies.facade,
        actor_provider=_successor_runtime_dependencies.actor_provider,
    )
)
router.include_router(production_policy_router)
