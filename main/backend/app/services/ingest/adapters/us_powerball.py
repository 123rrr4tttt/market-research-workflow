from __future__ import annotations

from datetime import datetime
from typing import Iterable

from selectolax.parser import HTMLParser

from ...http.client import HttpClient
from .market_base import MarketAdapter, MarketRecord


class USPowerballAdapter(MarketAdapter):
    """Fetch recent national Powerball results from powerball.com."""

    RECENT_URL = "https://www.powerball.com/api/v1/numbers/powerball/recent?_format=json"
    SOURCE_NAME = "Powerball.com Recent Results"

    def __init__(self, state: str):
        super().__init__(state)
        self.http_client = HttpClient()

    def fetch_records(self, limit: int = 10) -> Iterable[MarketRecord]:
        headers = {"X-Requested-With": "XMLHttpRequest"}
        html = self.http_client.get_text(self.RECENT_URL, headers=headers, follow_redirects=True)
        tree = HTMLParser(html)

        # 使用属性选择器（selectolax可能不完全支持.class语法）
        cards = tree.css("a[class*='card']") or tree.css("a.card")
        for card in cards[:limit]:
            # 使用多种选择器查找日期节点
            title_node = card.css_first("h5.card-title") or card.css_first("h5[class*='card-title']") or card.css_first("h5")
            if not title_node:
                continue

            date_text = title_node.text(strip=True)
            try:
                draw_date = datetime.strptime(date_text, "%a, %b %d, %Y").date()
            except ValueError:
                continue

            # 提取链接
            href = card.attributes.get("href", "")
            if href and not href.startswith("http"):
                href = f"https://www.powerball.com{href}" if href.startswith("/") else f"https://www.powerball.com/{href}"

            # 提取号码 - 尝试多种选择器
            white_balls = []
            number_elements = card.css(".white-balls, [class*='ball'], [class*='number'], span")
            for elem in number_elements:
                text = elem.text(strip=True)
                if text.isdigit() and 1 <= int(text) <= 99:
                    if text not in white_balls:
                        white_balls.append(text)
            
            powerball_node = card.css_first(".powerball, [class*='powerball']")
            powerball_num = powerball_node.text(strip=True) if powerball_node else None

            # 提取Power Play
            multiplier = None
            multiplier_node = card.css_first(".power-play .multiplier, [class*='multiplier']")
            if multiplier_node:
                multiplier = multiplier_node.text(strip=True)
            else:
                # 尝试从文本中提取
                import re
                card_text = card.text(strip=True)
                pp_match = re.search(r'power\s*play[:\s]*(\d+)x?', card_text, re.IGNORECASE)
                if pp_match:
                    multiplier = pp_match.group(1) + "x"

            extra = {
                "white_balls": white_balls[:5],  # 只取前5个主号码
                "powerball": powerball_num,
                "multiplier": multiplier,
            }

            # 尝试从详细页面获取奖池信息
            jackpot = None
            if href:
                try:
                    detail_html = self.http_client.get_text(href, headers=headers, follow_redirects=True)
                    detail_tree = HTMLParser(detail_html)
                    jackpot = self._extract_jackpot_from_detail(detail_tree)
                except Exception:
                    pass  # 如果获取失败，继续使用None

            yield MarketRecord(
                state=self.state,
                date=draw_date,
                game="Powerball US",
                jackpot=jackpot,
                sales_volume=None,
                revenue=None,
                ticket_price=2.0,
                draw_number=None,
                extra=extra,
                source_name=self.SOURCE_NAME,
                uri=href,
            )
    
    def _extract_jackpot_from_detail(self, parser: HTMLParser) -> float | None:
        """从详细页面提取奖池金额"""
        import re
        
        # 方法1: 查找包含jackpot的元素
        jackpot_elements = parser.css("[class*='jackpot'], [id*='jackpot']")
        for elem in jackpot_elements:
            text = elem.text(strip=True)
            money = self._parse_money_from_text(text)
            if money and money > 1000000:
                return money
        
        # 方法2: 从页面文本中提取
        text_content = parser.body.text() if parser.body else ""
        patterns = [
            r'jackpot[:\s]*\$?([\d,]+(?:\.\d+)?)\s*(million|billion|M|B)?',
            r'\$([\d,]+(?:\.\d+)?)\s*(million|billion|M|B)?.*jackpot',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text_content, re.IGNORECASE)
            if match:
                amount_str = match.group(1).replace(",", "")
                multiplier_str = match.group(2) if len(match.groups()) > 1 and match.group(2) else ""
                
                try:
                    amount = float(amount_str)
                    multiplier = 1_000_000.0 if "million" in multiplier_str.lower() or multiplier_str.upper() == "M" else (
                        1_000_000_000.0 if "billion" in multiplier_str.lower() or multiplier_str.upper() == "B" else 1.0
                    )
                    result = amount * multiplier
                    if result > 1000000:
                        return result
                except (ValueError, IndexError):
                    continue
        
        return None
    
    def _parse_money_from_text(self, text: str) -> float | None:
        """从文本中解析金额"""
        if not text:
            return None
        
        import re
        match = re.search(r'\$([\d,]+(?:\.\d+)?)\s*(million|billion|M|B)?', text, re.IGNORECASE)
        if match:
            amount_str = match.group(1).replace(",", "")
            multiplier_str = match.group(2) if match.group(2) else ""
            
            try:
                amount = float(amount_str)
                multiplier = 1_000_000.0 if "million" in multiplier_str.lower() or multiplier_str.upper() == "M" else (
                    1_000_000_000.0 if "billion" in multiplier_str.lower() or multiplier_str.upper() == "B" else 1.0
                )
                return amount * multiplier
            except ValueError:
                pass
        
        return None


