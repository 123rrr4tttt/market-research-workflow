from __future__ import annotations

import re
from datetime import datetime
from typing import Iterable

from .http_utils import fetch_html, make_html_parser
from .market_base import MarketAdapter, MarketRecord


class CaliforniaMegaMillionsAdapter(MarketAdapter):
    PAGE_URL = "https://www.calottery.com/en/draw-games/mega-millions"
    GAME = "Mega Millions"

    def fetch_records(self) -> Iterable[MarketRecord]:
        html, _ = fetch_html(self.PAGE_URL)
        parser = make_html_parser(html)

        # 提取开奖日期
        date_node = parser.css_first(".draw-cards--draw-date")
        draw_date = self._parse_date(date_node.text(strip=True) if date_node else "")
        if draw_date is None:
            return []

        # 提取开奖期号
        draw_number_node = parser.css_first(".draw-cards--draw-number")
        draw_number = None
        if draw_number_node:
            draw_text = draw_number_node.text(strip=True)
            match = re.search(r'#?\s*(\d+)', draw_text)
            if match:
                draw_number = match.group(1)

        # 提取中奖号码
        winning_numbers = self._extract_winning_numbers(parser)

        # 提取奖级详情和计算数据
        table = parser.css_first("table.table-last-draw")
        jackpot = None
        total_payout = 0.0
        prize_tiers_data = []
        
        if table is not None:
            for row in table.css("tbody tr"):
                cells = [c.text(strip=True) for c in row.css("td")]
                if len(cells) != 3:
                    continue
                tier, winners_raw, prize_raw = cells
                prize_value = self._parse_money(prize_raw)
                winners = self._parse_int(winners_raw)
                
                # 提取jackpot（第一行的头奖金额）
                if jackpot is None and tier.lower().startswith("5 +"):
                    jackpot = prize_value
                
                # 计算总奖金支出
                if prize_value is not None and winners is not None:
                    tier_payout = prize_value * winners
                    total_payout += tier_payout
                    
                    # 保存奖级详情
                    prize_tiers_data.append({
                        "tier": tier,
                        "winners": winners,
                        "prize_per_winner": prize_value,
                        "total_payout": tier_payout,
                    })

        # revenue应该等于销售额，但页面没有显示销售额
        # 暂时使用total_payout作为估算值
        revenue = total_payout if total_payout > 0 else None

        # 构建extra字段，包含更多信息
        extra = {
            "prize_tiers": prize_tiers_data,
            "total_payout": total_payout,
            "winning_numbers": winning_numbers,
        }

        yield MarketRecord(
            state=self.state,
            date=draw_date,
            revenue=revenue,
            jackpot=jackpot,
            ticket_price=2.0,
            draw_number=draw_number,
            source_name=f"California Lottery - {self.GAME}",
            uri=self.PAGE_URL,
            game=self.GAME,
            extra=extra,
        )
    
    def _extract_winning_numbers(self, parser) -> list[str]:
        """提取中奖号码（Mega Millions有5个主号码+1个Mega号码）"""
        numbers = []
        # 尝试多种选择器
        number_nodes = parser.css(".winning-number, .ball-number, [class*='number'][class*='ball']")
        
        # 如果没找到，尝试从文本中提取
        if not number_nodes:
            all_elements = parser.css("[class*='number'], [class*='ball']")
            for elem in all_elements:
                text = elem.text(strip=True)
                if text.isdigit() and 1 <= int(text) <= 99:
                    if text not in numbers:
                        numbers.append(text)
        else:
            for node in number_nodes:
                num = node.text(strip=True)
                if num.isdigit() and num not in numbers:
                    numbers.append(num)
        
        return numbers[:6]  # Mega Millions有6个号码（5个主号码+1个Mega号码）

    @staticmethod
    def _parse_date(value: str):
        if not value:
            return None
        if "/" in value:
            value = value.split("/", 1)[-1].strip()
        try:
            return datetime.strptime(value, "%b %d, %Y").date()
        except ValueError:
            return None

    @staticmethod
    def _parse_money(raw: str | None) -> float | None:
        if not raw:
            return None
        text = raw.strip().lower().replace("$", "").replace(",", "")
        multiplier = 1.0
        if "million" in text:
            multiplier = 1_000_000.0
            text = text.replace("million", "").strip()
        if "billion" in text:
            multiplier = 1_000_000_000.0
            text = text.replace("billion", "").strip()
        try:
            return float(text) * multiplier
        except ValueError:
            return None

    @staticmethod
    def _parse_int(raw: str | None) -> int | None:
        if not raw:
            return None
        try:
            return int(raw.replace(",", ""))
        except ValueError:
            return None


