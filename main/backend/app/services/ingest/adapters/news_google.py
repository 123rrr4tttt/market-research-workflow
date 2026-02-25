"""Google News爬虫适配器"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Iterable, List, Optional
from urllib.parse import quote_plus, urljoin, urlparse
from xml.etree import ElementTree as ET

from .http_utils import fetch_html, make_html_parser

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class GoogleNewsItem:
    """Google News新闻项数据结构"""
    title: str
    link: str
    summary: Optional[str] = None
    source: Optional[str] = None
    date: Optional[datetime] = None
    keyword: Optional[str] = None


class GoogleNewsAdapter:
    """Google News数据适配器"""
    
    def __init__(self):
        self.base_url = "https://news.google.com"
    
    def search(
        self,
        keyword: str,
        limit: int = 20,
        hl: str = "en",
        gl: str = "US",
    ) -> Iterable[GoogleNewsItem]:
        """
        搜索Google News
        
        Args:
            keyword: 搜索关键词
            limit: 返回结果数量限制
            hl: 语言代码（默认en）
            gl: 国家代码（默认US）
        """
        # 构建搜索URL
        query = quote_plus(keyword)
        url = f"{self.base_url}/search?q={query}&hl={hl}&gl={gl}&ceid={gl}:{hl}"

        items: List[GoogleNewsItem] = []

        try:
            html, _ = fetch_html(url)
            items = list(self._parse_google_news_html(html, keyword))
        except Exception as exc:
            logger.warning("Google News HTML fetch failed for '%s': %s", keyword, exc)

        if not items:
            rss_items = self._fetch_rss(keyword, limit, hl, gl)
            if rss_items:
                return rss_items[:limit]

        return items[:limit]
    
    def search_multiple_keywords(
        self,
        keywords: List[str],
        limit_per_keyword: int = 20,
    ) -> Iterable[GoogleNewsItem]:
        """
        搜索多个关键词
        
        Args:
            keywords: 关键词列表
            limit_per_keyword: 每个关键词的结果数量限制
        """
        for keyword in keywords:
            try:
                for item in self.search(keyword, limit_per_keyword):
                    yield item
            except Exception as exc:
                logger.warning("Failed to search keyword '%s': %s", keyword, exc)
                continue
        return
    
    def _parse_google_news_html(self, html: str, keyword: str) -> Iterable[GoogleNewsItem]:
        """解析Google News HTML页面"""
        parser = make_html_parser(html)
        
        # Google News使用article标签
        articles = parser.css("article")
        
        seen_links = set()
        
        for article in articles:
            try:
                # 提取标题和链接
                # Google News的链接在h3或h4标签内的a标签中
                title_node = article.css_first("h3, h4")
                if not title_node:
                    continue
                
                link_node = title_node.css_first("a")
                if not link_node:
                    continue
                
                # Google News使用相对链接，需要转换为绝对链接
                href = link_node.attributes.get("href") or ""
                if not href:
                    continue
                
                # Google News链接格式通常是 /articles/... 或 /stories/...
                # 需要转换为完整URL
                if href.startswith("./"):
                    href = href[2:]
                if href.startswith("/"):
                    link = urljoin(self.base_url, href)
                elif href.startswith("http"):
                    link = href
                else:
                    link = urljoin(self.base_url, "/" + href)
                
                # 去除Google News的跟踪参数
                parsed = urlparse(link)
                clean_link = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                if parsed.query:
                    # 保留部分查询参数，但移除Google跟踪参数
                    params = {}
                    for param in parsed.query.split("&"):
                        if "=" in param:
                            k, v = param.split("=", 1)
                            if k not in ["utm_source", "utm_medium", "utm_campaign"]:
                                params[k] = v
                    if params:
                        clean_link += "?" + "&".join(f"{k}={v}" for k, v in params.items())
                
                if clean_link in seen_links:
                    continue
                seen_links.add(clean_link)
                
                title = link_node.text(strip=True) or ""
                if not title:
                    continue
                
                # 提取来源和时间
                source = None
                date = None
                
                # 来源通常在div中，包含时间信息
                # Google News的结构可能是：<div>来源 · 时间</div>
                source_time_node = article.css_first("div[jslog]")
                if source_time_node:
                    text = source_time_node.text(strip=True)
                    if text:
                        # 尝试解析 "来源 · X小时前" 或 "来源 · 日期"
                        parts = text.split("·")
                        if len(parts) >= 1:
                            source = parts[0].strip()
                        if len(parts) >= 2:
                            time_str = parts[1].strip()
                            date = self._parse_time_string(time_str)
                
                # 如果没有找到，尝试其他选择器
                if not source:
                    source_node = article.css_first("div[data-n-tid]")
                    if source_node:
                        source = source_node.text(strip=True)
                
                # 提取摘要（如果有）
                summary = None
                summary_node = article.css_first("div[jslog='9386']")
                if summary_node:
                    summary = summary_node.text(strip=True)
                
                item = GoogleNewsItem(
                    title=title,
                    link=clean_link,
                    summary=summary,
                    source=source,
                    date=date,
                    keyword=keyword,
                )
                yield item
                
            except Exception as exc:
                logger.warning("Failed to parse article: %s", exc)
                continue
    
    def _fetch_rss(
        self,
        keyword: str,
        limit: int,
        hl: str,
        gl: str,
    ) -> List[GoogleNewsItem]:
        """通过RSS获取Google News数据，作为HTML解析的备用方案"""
        query = quote_plus(keyword)
        language = hl.split("-")[0]
        hl_param = hl if "-" in hl else f"{hl}-{gl}"
        rss_url = f"{self.base_url}/rss/search?q={query}&hl={hl_param}&gl={gl}&ceid={gl}:{language}"

        try:
            rss_text, _ = fetch_html(rss_url)
        except Exception as exc:
            logger.warning("Google News RSS fetch failed for '%s': %s", keyword, exc)
            return []

        try:
            root = ET.fromstring(rss_text)
        except ET.ParseError as exc:
            logger.warning("Google News RSS parse error for '%s': %s", keyword, exc)
            return []

        channel = root.find("channel")
        if channel is None:
            return []

        items: List[GoogleNewsItem] = []
        for item_elem in channel.findall("item"):
            if len(items) >= limit:
                break

            title = unescape(item_elem.findtext("title") or "").strip()
            link = (item_elem.findtext("link") or "").strip()
            if not title or not link:
                continue

            summary_raw = item_elem.findtext("description")
            summary = unescape(summary_raw).strip() if summary_raw else None

            source = None
            for child in item_elem:
                if child.tag.endswith("source") and child.text:
                    source = child.text.strip()
                    break

            pub_date = item_elem.findtext("pubDate")
            pub_datetime: Optional[datetime] = None
            if pub_date:
                try:
                    pub_datetime = parsedate_to_datetime(pub_date)
                except Exception:
                    pub_datetime = None

            items.append(
                GoogleNewsItem(
                    title=title,
                    link=link,
                    summary=summary,
                    source=source,
                    date=pub_datetime,
                    keyword=keyword,
                )
            )

        return items

    def _parse_time_string(self, time_str: str) -> Optional[datetime]:
        """解析Google News的时间字符串"""
        if not time_str:
            return None
        
        time_str = time_str.strip().lower()
        now = datetime.utcnow()
        
        # 处理相对时间
        if "minute" in time_str or "分钟" in time_str:
            match = re.search(r"(\d+)", time_str)
            if match:
                minutes = int(match.group(1))
                return now - timedelta(minutes=minutes)
        elif "hour" in time_str or "小时" in time_str:
            match = re.search(r"(\d+)", time_str)
            if match:
                hours = int(match.group(1))
                return now - timedelta(hours=hours)
        elif "day" in time_str or "天" in time_str:
            match = re.search(r"(\d+)", time_str)
            if match:
                days = int(match.group(1))
                return now - timedelta(days=days)
        elif "week" in time_str or "周" in time_str:
            match = re.search(r"(\d+)", time_str)
            if match:
                weeks = int(match.group(1))
                return now - timedelta(weeks=weeks)
        
        # 处理绝对日期格式（如果Google News提供）
        # 常见的格式如 "Jan 15" 或 "2024-01-15"
        date_formats = [
            "%b %d",  # Jan 15
            "%B %d",  # January 15
            "%b %d, %Y",  # Jan 15, 2024
            "%B %d, %Y",  # January 15, 2024
            "%Y-%m-%d",  # 2024-01-15
            "%m/%d/%Y",  # 01/15/2024
            "%d/%m/%Y",  # 15/01/2024
            "%Y/%m/%d",  # 2024/01/15
            "%d-%m-%Y",  # 15-01-2024
        ]
        
        for fmt in date_formats:
            try:
                parsed = datetime.strptime(time_str, fmt)
                # 如果没有年份，假设是今年
                if "%Y" not in fmt:
                    parsed = parsed.replace(year=now.year)
                    # 如果解析出的日期在未来，可能是去年的
                    if parsed > now:
                        parsed = parsed.replace(year=now.year - 1)
                return parsed
            except ValueError:
                continue
        
        # 尝试使用正则表达式提取日期
        date_patterns = [
            (r'(\d{4})-(\d{2})-(\d{2})', '%Y-%m-%d'),  # 2024-01-15
            (r'(\d{2})/(\d{2})/(\d{4})', '%m/%d/%Y'),  # 01/15/2024
            (r'(\d{4})/(\d{2})/(\d{2})', '%Y/%m/%d'),  # 2024/01/15
        ]
        
        for pattern, fmt in date_patterns:
            match = re.search(pattern, time_str)
            if match:
                try:
                    date_str = match.group(0)
                    parsed = datetime.strptime(date_str, fmt)
                    return parsed
                except ValueError:
                    continue
        
        return None

