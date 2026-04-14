from __future__ import annotations


LLM_MAPPING: dict[str, dict] = {
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
