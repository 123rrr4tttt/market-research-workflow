from __future__ import annotations

from ....project_customization.interfaces import CustomizationJsonObject


LLM_MAPPING: dict[str, CustomizationJsonObject] = {
    "policy_summary": {
        "provider": "default",
        "model": "gpt-4o-mini",
        "prompt_source": "project_config",
    },
    "policy_classification": {
        "provider": "default",
        "model": "gpt-4o-mini",
        "prompt_source": "project_config",
    },
}
