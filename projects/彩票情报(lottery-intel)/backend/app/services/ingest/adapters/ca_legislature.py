from __future__ import annotations

from datetime import date
from typing import Iterable

import httpx
from bs4 import BeautifulSoup

from .base import PolicyAdapter, PolicyDocument


class CaliforniaLegislatureAdapter(PolicyAdapter):
    """Rudimentary adapter for California legislature public site.

    Notes
    -----
    The CA legislature provides multiple endpoints. For MVP we keep a
    lightweight HTML fetch to unblock pipeline wiring. Full scraping with
    Playwright/structured parsing will replace this stub in later iterations.
    """

    SEARCH_URL = (
        "https://leginfo.legislature.ca.gov/faces/billSearchClient.xhtml"
        "?session_year=2023&keyword=lottery"
    )

    def fetch_documents(self) -> Iterable[PolicyDocument]:
        try:
            response = httpx.get(self.SEARCH_URL, timeout=30)
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("California legislature fetch failed") from exc

        soup = BeautifulSoup(response.text, "html.parser")
        rows = soup.select("table tbody tr")
        today = date.today()

        emitted = False
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            title = cells[1].get_text(strip=True)
            if not title:
                continue

            status = cells[2].get_text(strip=True) if len(cells) > 2 else None
            link = cells[1].find("a")
            href = link.get("href") if link else self.SEARCH_URL

            description_parts = [cell.get_text(" ", strip=True) for cell in cells]
            description = " | ".join(part for part in description_parts if part)

            yield PolicyDocument(
                state="CA",
                title=title,
                status=status,
                publish_date=today,
                summary=description[:400] or None,
                content=description,
                uri=href,
                source_name="CA Legislature Search",
            )
            emitted = True

        if not emitted:
            text = soup.get_text(" ", strip=True)
            snippet = text[:1200]
            yield PolicyDocument(
                state="CA",
                title="California Lottery Legislative Update (fallback)",
                status=None,
                publish_date=today,
                summary=snippet[:300] or None,
                content=snippet,
                uri=self.SEARCH_URL,
                source_name="CA Legislature Search",
            )


