from .extraction_adapter import DemoProjExtractionAdapter
from .customization import DemoProjCustomization

PROJECT_KEY = "demo_proj"
PROJECT_KEY_PREFIX_ALIASES = ["embodied"]
PROJECT_EXTRACTION_ADAPTER_CLASS = DemoProjExtractionAdapter

__all__ = [
    "DemoProjExtractionAdapter",
    "DemoProjCustomization",
    "PROJECT_KEY",
    "PROJECT_KEY_PREFIX_ALIASES",
    "PROJECT_EXTRACTION_ADAPTER_CLASS",
]
