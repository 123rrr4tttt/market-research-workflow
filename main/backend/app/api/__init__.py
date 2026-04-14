from fastapi import APIRouter

from .policies import router as policies_router
from .market import router as market_router
from .search import router as search_router
from .reports import router as reports_router
from .config import router as config_router
from .ingest import router as ingest_router
from .discovery import router as discovery_router
from .indexer import router as indexer_router
from .admin import router as admin_router
from .dashboard import router as dashboard_router
from .llm_config import router as llm_config_router
from .process import router as process_router
from .topics import router as topics_router
from .projects import router as projects_router
from .products import router as products_router
from .governance import router as governance_router
from .source_library import router as source_library_router
from .project_customization import router as project_customization_router
from .resource_pool import router as resource_pool_router
from .crawler import router as crawler_router
from .keywords import router as keywords_router
from .llm_report import router as llm_report_router
from .workflow_graph import router as workflow_graph_router
from .stats import router as stats_router
from .writing import router as writing_router
from .agent_batch import router as agent_batch_router
from .agent_sessions import router as agent_sessions_router
from .skills import router as skills_router
from .codex_auth import router as codex_auth_router


router = APIRouter()
router.include_router(policies_router)
router.include_router(market_router)
router.include_router(search_router)
router.include_router(reports_router)
router.include_router(config_router)
router.include_router(ingest_router)
router.include_router(discovery_router)
router.include_router(indexer_router)
router.include_router(admin_router)
router.include_router(dashboard_router)
router.include_router(llm_config_router)
router.include_router(process_router)
router.include_router(topics_router)
router.include_router(projects_router)
router.include_router(products_router)
router.include_router(governance_router)
router.include_router(source_library_router)
router.include_router(project_customization_router)
router.include_router(resource_pool_router)
router.include_router(crawler_router)
router.include_router(keywords_router)
router.include_router(llm_report_router)
router.include_router(workflow_graph_router)
router.include_router(stats_router)
router.include_router(writing_router)
router.include_router(agent_batch_router)
router.include_router(agent_sessions_router)
router.include_router(skills_router)
router.include_router(codex_auth_router)
