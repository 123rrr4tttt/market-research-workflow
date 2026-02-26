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


