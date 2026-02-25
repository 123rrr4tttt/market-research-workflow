from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ....services.keyword_generation import generate_social_keywords
from ....subprojects.online_lottery.services.lottery_stats import ingest_lottery_stats
from ...interfaces import ChannelHandler, ProjectCustomization, WorkflowDefinition
from .mappings import FIELD_MAPPING, LLM_MAPPING, MENU_CONFIG, WORKFLOW_MAPPING


def _lottery_stats_handler(channel: Dict[str, Any], params: Dict[str, Any], project_key: str | None) -> Dict[str, Any]:
    """Lottery fixed source: CA/NY/TX lottery draw/sales stats."""
    return ingest_lottery_stats(
        state=str(params.get("state") or ""),
        source_hint=params.get("source_hint"),
        limit=int(params["limit"]) if params.get("limit") is not None else None,
        game=params.get("game"),
    )


@dataclass(slots=True)
class OnlineLotteryCustomization(ProjectCustomization):
    project_key: str = "online_lottery"

    def get_menu_config(self) -> Dict[str, Any]:
        return MENU_CONFIG

    def get_workflow_mapping(self) -> Dict[str, WorkflowDefinition]:
        return WORKFLOW_MAPPING

    def get_llm_mapping(self) -> Dict[str, Dict[str, Any]]:
        return LLM_MAPPING

    def get_field_mapping(self) -> Dict[str, Any]:
        return FIELD_MAPPING

    def get_channel_handlers(self) -> Dict[tuple[str, str], ChannelHandler]:
        return {("lottery", "stats"): _lottery_stats_handler}

    def suggest_keywords(
        self,
        topic: str,
        base_keywords: Optional[List[str]] = None,
        platform: Optional[str] = None,
        language: str = "zh",
    ) -> Optional[Dict[str, Any]]:
        """Lottery-specific keyword suggestion via LLM (social_keyword_generation config)."""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(
            "online_lottery.suggest_keywords: topic=%s platform=%s base_keywords=%s",
            topic, platform, base_keywords,
        )
        result = generate_social_keywords(
            topic=topic,
            language=language,
            platform=platform,
            base_keywords=base_keywords,
            return_combined=True,
        )
        if isinstance(result, dict):
            logger.info(
                "online_lottery.suggest_keywords: result search_keywords=%s subreddit_keywords=%s",
                result.get("search_keywords", []), result.get("subreddit_keywords", []),
            )
            return result
        logger.info("online_lottery.suggest_keywords: result (list) keywords=%s", result)
        return {"search_keywords": result, "subreddit_keywords": []}
