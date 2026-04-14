from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Iterable

from .http_utils import fetch_html, make_html_parser
from .market_base import MarketAdapter, MarketRecord

logger = logging.getLogger(__name__)


class PowerballComHistoryAdapter(MarketAdapter):
    """从 Powerball.com 获取历史开奖数据
    
    使用API获取历史记录列表，然后访问详细页面获取完整数据
    数据源: https://www.powerball.com/api/v1/numbers/powerball/recent?_format=json
    """

    BASE_URL = "https://www.powerball.com"
    API_URL = f"{BASE_URL}/api/v1/numbers/powerball/recent?_format=json"
    GAME = "Powerball"

    def fetch_records(self, limit: int | None = None) -> Iterable[MarketRecord]:
        """获取历史开奖记录
        
        Args:
            limit: 最大获取记录数，默认50条
        """
        if limit is None:
            limit = 50
        
        # 使用API获取历史记录列表
        headers = {"X-Requested-With": "XMLHttpRequest"}
        html, _ = fetch_html(self.API_URL, headers=headers)
        parser = make_html_parser(html)

        # 提取所有卡片链接 - 使用属性选择器（selectolax可能不支持.class语法）
        cards = parser.css("a[class*='card']") or parser.css("a.card")
        logger.info(f"PowerballComHistoryAdapter: 找到 {len(cards)} 个历史记录卡片")
        
        if not cards:
            logger.warning("PowerballComHistoryAdapter: 未找到任何历史记录")
            # 尝试备用方法：使用正则表达式
            import re
            card_pattern = r'<a[^>]*class=[\"\'][^\"\']*card[^\"\']*[\"\'][^>]*href=[\"\']([^\"\']+)[\"\']'
            matches = re.findall(card_pattern, html)
            if matches:
                logger.info(f"PowerballComHistoryAdapter: 使用正则表达式找到 {len(matches)} 个链接")
                # 暂时返回，后续可以改进使用正则表达式解析
            return

        count = 0
        for card in cards[:limit]:
            if count >= limit:
                break
            
            try:
                # 从卡片中提取基本信息
                record = self._parse_card(card)
                if record:
                    # 尝试从详细页面获取更多信息（奖池等）
                    detail_record = self._fetch_detail_info(record.uri)
                    if detail_record:
                        # 合并信息：优先使用详细页面的数据
                        record.jackpot = detail_record.jackpot or record.jackpot
                        record.revenue = detail_record.revenue or record.revenue
                        if detail_record.extra:
                            record.extra = {**(record.extra or {}), **detail_record.extra}
                    
                    yield record
                    count += 1
            except Exception as e:
                logger.warning(f"PowerballComHistoryAdapter: 处理卡片失败: {e}")
                continue
        
        logger.info(f"PowerballComHistoryAdapter: 成功提取 {count} 条记录")

    def _parse_card(self, card) -> MarketRecord | None:
        """从卡片中解析基本信息"""
        # 提取日期 - 使用多种选择器
        title_node = card.css_first("h5.card-title") or card.css_first("h5[class*='card-title']") or card.css_first("h5")
        if not title_node:
            logger.debug("PowerballComHistoryAdapter: 未找到日期节点")
            return None
        
        date_text = title_node.text(strip=True)
        try:
            draw_date = datetime.strptime(date_text, "%a, %b %d, %Y").date()
        except ValueError:
            return None

        # 提取链接
        href = card.attributes.get("href", "")
        if not href.startswith("http"):
            href = f"{self.BASE_URL}{href}" if href.startswith("/") else f"{self.BASE_URL}/{href}"

        # 提取中奖号码
        winning_numbers = []
        # 查找所有号码（可能是span或其他元素）
        number_elements = card.css("[class*='ball'], [class*='number'], span")
        for elem in number_elements:
            text = elem.text(strip=True)
            if text.isdigit() and 1 <= int(text) <= 99:
                if text not in winning_numbers:
                    winning_numbers.append(text)
        
        # 提取Power Play
        power_play = None
        pp_text = card.text(strip=True)
        pp_match = re.search(r'power\s*play[:\s]*(\d+)x?', pp_text, re.IGNORECASE)
        if pp_match:
            power_play = pp_match.group(1) + "x"

        extra = {
            "winning_numbers": winning_numbers[:6],  # 5个主号码 + 1个Powerball
            "power_play": power_play,
        }

        return MarketRecord(
            state=self.state,
            date=draw_date,
            game=self.GAME,
            jackpot=None,  # 需要从详细页面获取
            revenue=None,
            ticket_price=2.0,
            draw_number=None,
            source_name="Powerball.com (Historical)",
            uri=href,
            extra=extra,
        )

    def _fetch_detail_info(self, url: str | None) -> MarketRecord | None:
        """从详细页面获取奖池等信息"""
        if not url:
            return None
        
        try:
            html, _ = fetch_html(url)
            parser = make_html_parser(html)
            
            # 提取奖池金额
            jackpot = self._extract_jackpot(parser)
            
            # 提取现金价值
            cash_value = self._extract_cash_value(parser)
            
            # 提取奖级详情
            prize_tiers = self._extract_prize_tiers(parser)
            
            extra = {
                "cash_value": cash_value,
                "prize_tiers": prize_tiers,
            }
            
            return MarketRecord(
                state=self.state,
                date=None,  # 不需要日期
                game=self.GAME,
                jackpot=jackpot,
                revenue=None,  # Powerball.com通常不显示revenue
                ticket_price=None,
                draw_number=None,
                source_name=None,
                uri=None,
                extra=extra,
            )
        except Exception as e:
            logger.debug(f"PowerballComHistoryAdapter: 获取详细页面信息失败 {url}: {e}")
            return None

    def _extract_jackpot(self, parser) -> float | None:
        """提取奖池金额 - 使用多种方法"""
        # 方法1: 查找包含 "jackpot" 关键词的元素
        jackpot_elements = parser.css("[class*='jackpot'], [id*='jackpot'], [class*='prize'], [class*='amount']")
        for elem in jackpot_elements:
            text = elem.text(strip=True)
            money = self._parse_money_from_text(text)
            if money and money > 1000000:
                return money
        
        # 方法2: 从整个页面文本中提取
        text_content = parser.body.text() if parser.body else ""
        
        # 查找金额模式
        patterns = [
            r'jackpot[:\s]*\$?([\d,]+(?:\.\d+)?)\s*(million|billion|M|B)?',
            r'estimated jackpot[:\s]*\$?([\d,]+(?:\.\d+)?)\s*(million|billion|M|B)?',
            r'\$([\d,]+(?:\.\d+)?)\s*(million|billion|M|B)?.*jackpot',
            r'jackpot.*\$([\d,]+(?:\.\d+)?)\s*(million|billion|M|B)?',
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
        
        # 方法3: 查找所有大金额，取最大的
        all_money = re.findall(r'\$([\d,]+(?:\.\d+)?)\s*(million|billion|M|B)?', text_content, re.IGNORECASE)
        max_money = None
        for amount_str, multiplier_str in all_money:
            try:
                amount = float(amount_str.replace(",", ""))
                multiplier = 1_000_000.0 if "million" in (multiplier_str or "").lower() or (multiplier_str or "").upper() == "M" else (
                    1_000_000_000.0 if "billion" in (multiplier_str or "").lower() or (multiplier_str or "").upper() == "B" else 1.0
                )
                value = amount * multiplier
                if value > 1000000 and (max_money is None or value > max_money):
                    max_money = value
            except ValueError:
                continue
        
        return max_money

    def _extract_cash_value(self, parser) -> float | None:
        """提取现金价值"""
        cash_elements = parser.css("[class*='cash'], [id*='cash']")
        for elem in cash_elements:
            text = elem.text(strip=True)
            money = self._parse_money_from_text(text)
            if money:
                return money
        
        text_content = parser.body.text() if parser.body else ""
        patterns = [
            r'cash value[:\s]*\$?([\d,]+(?:\.\d+)?)\s*(million|billion|M|B)?',
            r'cash option[:\s]*\$?([\d,]+(?:\.\d+)?)\s*(million|billion|M|B)?',
            r'\$([\d,]+(?:\.\d+)?)\s*(million|billion|M|B)?.*cash',
            r'cash.*\$([\d,]+(?:\.\d+)?)\s*(million|billion|M|B)?',
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
                    return amount * multiplier
                except (ValueError, IndexError):
                    continue
        
        return None
    
    def _parse_money_from_text(self, text: str) -> float | None:
        """从文本中解析金额"""
        if not text:
            return None
        
        patterns = [
            r'\$([\d,]+(?:\.\d+)?)\s*(million|billion|M|B)?',
            r'([\d,]+(?:\.\d+)?)\s*(million|billion|M|B)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                amount_str = match.group(1).replace(",", "")
                multiplier_str = match.group(2) if len(match.groups()) > 1 and match.group(2) else ""
                
                try:
                    amount = float(amount_str)
                    multiplier = 1_000_000.0 if "million" in (multiplier_str or "").lower() or (multiplier_str or "").upper() == "M" else (
                        1_000_000_000.0 if "billion" in (multiplier_str or "").lower() or (multiplier_str or "").upper() == "B" else 1.0
                    )
                    return amount * multiplier
                except (ValueError, IndexError):
                    continue
        
        return None

    def _extract_prize_tiers(self, parser) -> list[dict]:
        """提取奖级详情"""
        prize_tiers = []
        table = parser.css_first("table")
        if table:
            rows = table.css("tbody tr, tr")
            for row in rows:
                cells = [cell.text(strip=True) for cell in row.css("td")]
                if len(cells) >= 2:
                    tier_info = {
                        "tier": cells[0] if len(cells) > 0 else None,
                        "winners": self._parse_int(cells[1]) if len(cells) > 1 else None,
                        "prize": self._parse_money(cells[2]) if len(cells) > 2 else None,
                    }
                    prize_tiers.append(tier_info)
        return prize_tiers

    @staticmethod
    def _parse_date(value: str) -> datetime.date | None:
        """解析日期字符串"""
        if not value:
            return None
        value = value.replace("\xa0", " ").strip()
        date_formats = [
            "%a, %b %d, %Y",
            "%b %d, %Y",
            "%Y-%m-%d",
            "%m/%d/%Y",
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
        """解析整数字符串"""
        if not raw:
            return None
        try:
            return int(raw.replace(",", ""))
        except ValueError:
            return None
