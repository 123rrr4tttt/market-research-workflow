from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Optional

from .service import (
    extract_entities_relations,
    extract_market_info,
    extract_policy_info,
    extract_structured_sentiment,
)
from .topic_extract import (
    extract_company_info,
    extract_product_info,
    extract_operation_info,
)


@dataclass
class ExtractionApplicationService:
    @staticmethod
    def _resolve_parallel_workers(total_tasks: int) -> int:
        if total_tasks <= 1:
            return 1
        cap_raw = str(os.getenv("EXTRACTION_MAX_PARALLEL", "6")).strip()
        try:
            cap = max(1, int(cap_raw))
        except Exception:
            cap = 6
        return max(1, min(total_tasks, cap))

    def extract_policy(self, text: str) -> Optional[dict[str, Any]]:
        return extract_policy_info(text)

    def extract_market(self, text: str) -> Optional[dict[str, Any]]:
        return extract_market_info(text)

    def extract_entities(self, text: str) -> Optional[dict[str, Any]]:
        return extract_entities_relations(text)

    def extract_sentiment(self, text: str) -> Optional[dict[str, Any]]:
        return extract_structured_sentiment(text)

    def extract_structured_enriched(
        self,
        text: str,
        *,
        include_policy: bool = False,
        include_market: bool = False,
        include_sentiment: bool = False,
        include_company: bool = False,
        include_product: bool = False,
        include_operation: bool = False,
    ) -> Optional[dict[str, Any]]:
        """
        Mainline unified structured extraction:
        - always tries base ER extraction (entities_relations)
        - optionally overlays domain-specific structured fields (policy/market/sentiment)
        Subprojects remain isolated via existing extraction service adapters.
        """
        raw = str(text or "").strip()
        if not raw:
            return None
        out: dict[str, Any] = {}

        # Base graph layer for all content.
        er = extract_entities_relations(raw)
        if er:
            out["entities_relations"] = er
            ents = er.get("entities")
            if isinstance(ents, list) and ents:
                # Backward compatibility for graph adapters that also read extracted_data.entities
                out["entities"] = ents

        # Specialized overlays run in a shared parallel executor.
        tasks: list[tuple[str, Any]] = []
        if include_sentiment:
            tasks.append(("sentiment", extract_structured_sentiment))
        if include_policy:
            tasks.append(("policy", extract_policy_info))
        if include_market:
            tasks.append(("market", extract_market_info))
        if include_company:
            tasks.append(("company_structured", extract_company_info))
        if include_product:
            tasks.append(("product_structured", extract_product_info))
        if include_operation:
            tasks.append(("operation_structured", extract_operation_info))

        if tasks:
            workers = self._resolve_parallel_workers(len(tasks))
            if workers == 1:
                for key, fn in tasks:
                    value = fn(raw)
                    if value:
                        out[key] = value
            else:
                with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="extract-overlay") as executor:
                    future_map = {executor.submit(fn, raw): key for key, fn in tasks}
                    for future in as_completed(future_map):
                        key = future_map[future]
                        try:
                            value = future.result()
                        except Exception:
                            value = None
                        if value:
                            out[key] = value

        sentiment = out.get("sentiment")
        if isinstance(sentiment, dict) and sentiment.get("key_phrases") and not out.get("keywords"):
            out["keywords"] = sentiment["key_phrases"]

        return out or None

    # Backward-compatible alias during migration; use extract_structured_enriched in new code.
    def extract_graph_enriched(
        self,
        text: str,
        *,
        include_policy: bool = False,
        include_market: bool = False,
        include_sentiment: bool = False,
        include_company: bool = False,
        include_product: bool = False,
        include_operation: bool = False,
    ) -> Optional[dict[str, Any]]:
        return self.extract_structured_enriched(
            text,
            include_policy=include_policy,
            include_market=include_market,
            include_sentiment=include_sentiment,
            include_company=include_company,
            include_product=include_product,
            include_operation=include_operation,
        )
