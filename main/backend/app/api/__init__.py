from fastapi import APIRouter

from .policies import router as policies_router
from .market import router as market_router
from .search import router as search_router
from .reports import router as reports_router
from .config import router as config_router
from .ingest import router as ingest_router
from .discovery import router as discovery_router
from .indexer import router as indexer_router


router = APIRouter()
router.include_router(policies_router)
router.include_router(market_router)
router.include_router(search_router)
router.include_router(reports_router)
router.include_router(config_router)
router.include_router(ingest_router)
router.include_router(discovery_router)
router.include_router(indexer_router)


