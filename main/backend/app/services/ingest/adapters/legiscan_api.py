from __future__ import annotations

from datetime import datetime
from typing import Iterable

import httpx

from .base import PolicyAdapter, PolicyDocument
from ....settings.config import settings


class LegiScanApiAdapter(PolicyAdapter):
    BASE_URL = "https://api.legiscan.com/"

    def __init__(self, state: str, keyword: str = "lottery"):
        super().__init__(state)
        self.keyword = keyword
        if not settings.legiscan_api_key:
            raise RuntimeError("LEGISCAN_API_KEY 未配置，无法使用 LegiScan API")

    def fetch_documents(self) -> Iterable[PolicyDocument]:
        params = {
            "key": settings.legiscan_api_key,
            "op": "getSearch",
            "state": self.state.lower(),
            "search": self.keyword,
            "year": datetime.utcnow().year,
        }

        response = httpx.get(self.BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()

        results = (
            payload.get("searchresult", {})
            .get("results", [])
        )

        for item in results:
            bill = item.get("bill", {})
            text = bill.get("title") or ""
            summary = bill.get("summary") or bill.get("description") or text
            publish_date = None
            if bill.get("last_action_date"):
                try:
                    publish_date = datetime.strptime(bill["last_action_date"], "%Y-%m-%d").date()
                except ValueError:
                    publish_date = None

            yield PolicyDocument(
                state=self.state.upper(),
                title=bill.get("title") or bill.get("bill_number") or "Legislation",
                status=bill.get("status_name"),
                publish_date=publish_date,
                summary=summary,
                content="\n".join(
                    filter(
                        None,
                        [
                            bill.get("title"),
                            bill.get("description"),
                            bill.get("text_url"),
                        ],
                    )
                ),
                uri=bill.get("state_link") or bill.get("text_url"),
                source_name="LegiScan API",
            )

