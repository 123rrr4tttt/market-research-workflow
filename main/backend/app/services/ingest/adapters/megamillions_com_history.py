from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Iterable
from urllib.parse import urljoin

from .http_utils import fetch_html, make_html_parser
from .market_base import MarketAdapter, MarketRecord

logger = logging.getLogger(__name__)


class MegaMillionsComHistoryAdapter(MarketAdapter):
    """从 MegaMillions.com 获取历史开奖数据
    
    数据源: https://www.megamillions.com/Winning-Numbers/Previous-Drawings.aspx
    支持获取多条历史记录
    """

    BASE_URL = "https://www.megamillions.com"
    PREVIOUS_DRAWINGS_URL = f"{BASE_URL}/Winning-Numbers/Previous-Drawings.aspx"
    GAME = "Mega Millions"

    def fetch_records(self, limit: int | None = None) -> Iterable[MarketRecord]:
        """获取历史开奖记录
        
        Args:
            limit: 最大获取记录数，默认50条，None表示不限制
        """
        if limit is None:
            limit = 50
        # 获取历史数据页面
        html, _ = fetch_html(self.PREVIOUS_DRAWINGS_URL)
        parser = make_html_parser(html)

        # 提取历史记录
        records = self._extract_records_from_table(parser)
        logger.info(f"MegaMillionsComHistoryAdapter: 提取到 {len(records)} 条记录")
        
        if not records:
            logger.warning("MegaMillionsComHistoryAdapter: 未提取到任何记录")
        
        count = 0
        for record in records:
            if count >= limit:
                break
            if record:
                yield record
                count += 1
        
        logger.info(f"MegaMillionsComHistoryAdapter: 成功返回 {count} 条记录")

    def _extract_records_from_table(self, parser) -> list[MarketRecord]:
        """从表格中提取历史记录"""
        records = []
        
        # 查找包含历史数据的表格
        tables = parser.css("table")
        
        for table in tables:
            rows = table.css("tbody tr, tr")
            for row in rows:
                cells = [cell.text(strip=True) for cell in row.css("td, th")]
                
                if len(cells) < 3:
                    continue
                
                # 解析日期
                date_str = cells[0] if len(cells) > 0 else None
                draw_date = self._parse_date(date_str) if date_str else None
                if draw_date is None:
                    continue
                
                # 提取中奖号码
                numbers_text = " ".join(cells[1:-1]) if len(cells) > 2 else cells[1]
                winning_numbers = self._extract_numbers_from_text(numbers_text)
                
                # 提取奖池金额（可能在多列中，尝试所有列）
                jackpot = None
                for cell_text in cells:
                    parsed = self._parse_money(cell_text)
                    if parsed and parsed > 1000000:  # 奖池应该至少是百万级别
                        jackpot = parsed
                        break
                
                # 如果没找到，尝试最后一列
                if jackpot is None and len(cells) > 1:
                    jackpot_str = cells[-1]
                    jackpot = self._parse_money(jackpot_str) if jackpot_str else None
                
                # 构建extra字段
                extra = {
                    "winning_numbers": winning_numbers,
                }
                
                record = MarketRecord(
                    state=self.state,
                    date=draw_date,
                    game=self.GAME,
                    jackpot=jackpot,
                    ticket_price=2.0,
                    draw_number=None,
                    source_name="MegaMillions.com (Historical)",
                    uri=self.PREVIOUS_DRAWINGS_URL,
                    extra=extra,
                )
                records.append(record)
        
        return records

    def _extract_numbers_from_text(self, text: str) -> list[str]:
        """从文本中提取号码"""
        numbers = []
        
        # 查找所有数字
        matches = re.findall(r'\b(\d{1,2})\b', text)
        for match in matches:
            num = match
            if num.isdigit() and 1 <= int(num) <= 99:
                if num not in numbers:
                    numbers.append(num)
        
        return numbers[:6]  # Mega Millions有6个号码（5个主号码+1个Mega号码）

    @staticmethod
    def _parse_date(value: str) -> datetime.date | None:
        """解析日期字符串"""
        if not value:
            return None
        
        # 清理文本
        value = value.replace("\xa0", " ").strip()
        
        # 尝试多种日期格式
        date_formats = [
            "%m/%d/%Y",       # 11/01/2025
            "%Y-%m-%d",       # 2025-11-01
            "%a, %b %d, %Y",  # Sat, Nov 1, 2025
            "%b %d, %Y",      # Nov 1, 2025
        ]
        
        for fmt in date_formats:
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        
        return None

    @staticmethod
    def _parse_money(raw: str | None) -> float | None:
        """解析金额字符串"""
        if not raw:
            return None
        
        import re
        
        # 清理文本
        text = raw.strip()
        
        # 使用正则表达式提取金额和单位
        match = re.search(r'\$?([\d,]+(?:\.\d+)?)\s*(million|billion|M|B)?', text, re.IGNORECASE)
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
        
        # 回退到简单解析
        text = text.lower().replace("$", "").replace(",", "")
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

