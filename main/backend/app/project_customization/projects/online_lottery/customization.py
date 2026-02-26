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

    def get_social_keyword_guidelines(self) -> Optional[str]:
        return (
            "生成要求：\n"
            "1. 所有搜索关键词需紧扣彩票主题，同时覆盖玩法、奖金、渠道、用户行为、多人协作等不同场景；\n"
            "2. 结合提供的基础关键词提炼同义词、动名词、复合短语，避免仅做简单的单词变体；\n"
            "3. 每条关键词独立成行，不附加额外说明。"
        )

    def get_domain_tokens(self) -> Optional[list[str]]:
        from ....subprojects.online_lottery.domain.keywords import LOTTERY_TOKENS
        return list(LOTTERY_TOKENS)

    def get_report_title(self) -> str:
        return "彩票情报简报"

    def get_news_resource_handlers(self) -> Dict[str, Any]:
        """Project pool (子项目库): lottery-specific news sources."""
        from ....subprojects.online_lottery.services import (
            collect_calottery_news_for_project,
            collect_calottery_retailer_updates_for_project,
        )
        return {
            "calottery": collect_calottery_news_for_project,
            "calottery_retailer": collect_calottery_retailer_updates_for_project,
        }

    def get_shared_news_resource_handlers(self) -> Dict[str, Any]:
        """Shared pool (总库): none for lottery project; use trunk defaults if any."""
        return {}
