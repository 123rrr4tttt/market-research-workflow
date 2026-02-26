from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, date
from typing import Dict, List, Tuple, Optional
from urllib.parse import urlparse, parse_qs

from sqlalchemy import text
from bs4 import BeautifulSoup

from ..http.client import default_http_client
from ..llm.provider import get_chat_model
from ...settings.config import settings
from ..indexer.policy import index_policy_documents
from ...models.base import SessionLocal
from ...models.entities import Source, Document
from ..extraction.extract import extract_policy_info, extract_market_info, extract_entities_relations


logger = logging.getLogger(__name__)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _normalize_url(url: str) -> str:
    try:
        p = urlparse(url)
        # drop fragments
        return p._replace(fragment="").geturl()
    except Exception:
        return url


# Common selectors for news/article content when article/main/body yields empty
_ARTICLE_FALLBACK_SELECTORS = [
    "article", "main", "[role='main']", ".article-content", ".article-body",
    ".post-content", ".content", "#content", ".main-content", ".entry-content",
    "[data-role='article']", ".news-content", ".text-content", ".body-content",
]


def _extract_text_from_soup(soup: BeautifulSoup, selectors: List[str]) -> str:
    """Try selectors in order, return first non-empty text."""
    for sel in selectors:
        try:
            if sel.startswith("[") or sel.startswith(".") or sel.startswith("#"):
                node = soup.select_one(sel)
            else:
                node = soup.find(sel)
            if node:
                t = node.get_text("\n", strip=True)
                if t and len(t) > 100:
                    return t
        except Exception:
            pass
    return ""


def _fetch_content(url: str) -> tuple[str | None, BeautifulSoup | None, dict | None]:
    """获取网页内容，返回文本、BeautifulSoup对象和HTTP响应头"""
    try:
        response_headers = {}
        try:
            response = default_http_client._client.head(url, timeout=10, follow_redirects=True)
            if "last-modified" in response.headers:
                response_headers["last-modified"] = response.headers["last-modified"]
        except Exception:
            pass

        html = default_http_client.get_text(url)
        soup = BeautifulSoup(html, "html.parser")
        article = soup.find("article") or soup.find("main") or soup.body
        text = article.get_text("\n", strip=True) if article else soup.get_text("\n", strip=True)

        # When primary extraction yields empty or too short, try fallback selectors
        if not text or len(text) < 100:
            text = _extract_text_from_soup(soup, _ARTICLE_FALLBACK_SELECTORS)
        if not text:
            # Last resort: full body text (may include nav/footer noise)
            body = soup.find("body")
            if body:
                text = body.get_text("\n", strip=True)
        if not text:
            text = soup.get_text("\n", strip=True)

        if not text or len(text.strip()) < 50:
            return None, soup, response_headers if response_headers else None
        text = text.replace("\x00", "")
        return text[:20000], soup, response_headers if response_headers else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("discovery.store fetch content failed url=%s err=%s", url, exc)
        return None, None, None


def fetch_content_from_url(url: str) -> str | None:
    """Public helper: fetch article content from URL. Returns None on failure."""
    content, _, _ = _fetch_content(url)
    return content


def _extract_date_from_url(url: str) -> Optional[date]:
    """从URL中提取日期（增强版：支持PDF文件名和财政年度）"""
    if not url:
        return None
    
    try:
        parsed = urlparse(url)
        
        # 从路径中提取日期 (例如: /2024/01/15/article)
        path_parts = [p for p in parsed.path.split('/') if p]
        for i, part in enumerate(path_parts):
            # 检查是否是年份格式 (4位数字)
            if len(part) == 4 and part.isdigit():
                year = int(part)
                if 2000 <= year <= 2100:  # 合理的年份范围
                    # 检查后面是否有月份和日期
                    if i + 2 < len(path_parts):
                        try:
                            month = int(path_parts[i + 1])
                            day = int(path_parts[i + 2])
                            if 1 <= month <= 12 and 1 <= day <= 31:
                                return date(year, month, day)
                        except (ValueError, IndexError):
                            pass
        
        # 从文件名中提取日期（特别是PDF文件）
        if path_parts:
            filename = path_parts[-1]
            # 检查文件名中的日期模式: YYYY-MM-DD, YYYYMMDD, YYYY_MM_DD
            date_patterns = [
                r'(\d{4})[-_](\d{1,2})[-_](\d{1,2})',  # 2024-01-15 或 2024_01_15
                r'(\d{4})(\d{2})(\d{2})',  # 20240115
                r'(\d{1,2})[-_](\d{1,2})[-_](\d{2,4})',  # 3-3-14 或 03-03-2014
            ]
            for pattern in date_patterns:
                match = re.search(pattern, filename)
                if match:
                    groups = match.groups()
                    try:
                        if len(groups[0]) == 4:  # YYYY-MM-DD格式
                            year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                        elif len(groups[2]) == 2:  # MM-DD-YY格式
                            month, day = int(groups[0]), int(groups[1])
                            year_val = int(groups[2])
                            year = 2000 + year_val if year_val < 50 else 1900 + year_val
                        elif len(groups[2]) == 4:  # MM-DD-YYYY格式
                            month, day, year = int(groups[0]), int(groups[1]), int(groups[2])
                        else:
                            continue
                        if 2000 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
                            return date(year, month, day)
                    except (ValueError, IndexError):
                        continue
            
            # 检查财政年度格式: FY 2023-24
            fy_match = re.search(r'FY\s*(\d{4})-(\d{2,4})', filename, re.IGNORECASE)
            if fy_match:
                year = int(fy_match.group(1))
                # 使用财政年度开始日期（7月1日）作为近似日期
                if 2000 <= year <= 2100:
                    return date(year, 7, 1)
        
        # 从查询参数中提取日期
        query_params = parse_qs(parsed.query)
        for key in ['date', 'publish_date', 'published', 'time']:
            if key in query_params:
                date_str = query_params[key][0]
                # 尝试解析日期字符串
                for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%d/%m/%Y']:
                    try:
                        return datetime.strptime(date_str, fmt).date()
                    except ValueError:
                        continue
        
        # 从URL中查找日期模式 (例如: 2024-01-15)
        date_patterns = [
            r'(\d{4})-(\d{2})-(\d{2})',  # 2024-01-15
            r'(\d{4})/(\d{2})/(\d{2})',  # 2024/01/15
            r'(\d{2})/(\d{2})/(\d{4})',  # 01/15/2024
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, url)
            if match:
                groups = match.groups()
                if len(groups) == 3:
                    try:
                        if len(groups[0]) == 4:  # YYYY-MM-DD 或 YYYY/MM/DD
                            year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                        else:  # MM/DD/YYYY
                            month, day, year = int(groups[0]), int(groups[1]), int(groups[2])
                        
                        if 2000 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
                            return date(year, month, day)
                    except (ValueError, IndexError):
                        continue
        
    except Exception as e:
        logger.debug("Failed to extract date from URL %s: %s", url, e)
    
    return None


def _extract_date_from_html(soup: BeautifulSoup, url: str) -> Optional[date]:
    """从HTML中提取发布时间（增强版：改进优先级和格式支持）"""
    if not soup:
        return None
    
    try:
        import json
        
        # 1. 检查meta标签中的发布时间（按优先级排序：Open Graph > Schema.org > Dublin Core）
        meta_tags = [
            # Open Graph Protocol (最高优先级)
            ('property', 'article:published_time'),
            ('property', 'og:published_time'),
            # Schema.org
            ('itemprop', 'datePublished'),
            ('itemprop', 'datepublished'),
            # Dublin Core
            ('name', 'DC.date'),
            ('name', 'DC.Date'),
            # 其他常见格式
            ('name', 'publish-date'),
            ('name', 'pubdate'),
            ('name', 'publication-date'),
            ('name', 'date'),
        ]
        
        for attr, value in meta_tags:
            meta = soup.find('meta', {attr: value})
            if meta and meta.get('content'):
                date_str = meta.get('content')
                # 尝试解析ISO格式日期（支持时区和微秒）
                date_formats = [
                    '%Y-%m-%d',
                    '%Y-%m-%dT%H:%M:%S',
                    '%Y-%m-%dT%H:%M:%SZ',
                    '%Y-%m-%dT%H:%M:%S.%fZ',
                    '%Y-%m-%dT%H:%M:%S%z',
                    '%Y-%m-%dT%H:%M:%S.%f%z',
                ]
                
                for fmt in date_formats:
                    try:
                        if '%f' in fmt:
                            # 处理微秒
                            if '.' in date_str:
                                parts = date_str.split('.')
                                if len(parts) >= 2:
                                    base = parts[0]
                                    micro_part = parts[1].rstrip('Z').split('+')[0].split('-')[0]
                                    if len(micro_part) > 6:
                                        micro_part = micro_part[:6]
                                    date_str_parsed = f"{base}.{micro_part}"
                                    dt = datetime.strptime(date_str_parsed, '%Y-%m-%dT%H:%M:%S.%f')
                                    return dt.date()
                        elif '%z' in fmt:
                            # 处理时区，只提取日期部分
                            if len(date_str) >= 10:
                                dt = datetime.strptime(date_str[:10], '%Y-%m-%d')
                                return dt.date()
                        else:
                            # 标准格式
                            date_part = date_str[:len(fmt.replace('T', ' ').replace('Z', ''))]
                            dt = datetime.strptime(date_part, fmt.replace('T', ' ').replace('Z', ''))
                            return dt.date()
                    except ValueError:
                        continue
                
                # 尝试解析其他格式
                for fmt in ['%Y/%m/%d', '%m/%d/%Y', '%d/%m/%Y']:
                    try:
                        if len(date_str) >= 10:
                            dt = datetime.strptime(date_str[:10], fmt)
                            return dt.date()
                    except ValueError:
                        continue
        
        # 2. 检查JSON-LD结构化数据（递归检查嵌套对象）
        def extract_date_from_json_ld(obj, visited=None):
            """递归提取JSON-LD中的日期"""
            if visited is None:
                visited = set()
            
            # 防止循环引用
            obj_id = id(obj)
            if obj_id in visited:
                return None
            visited.add(obj_id)
            
            if not isinstance(obj, dict):
                return None
            
            # 检查常见的日期字段（按优先级排序）
            date_fields = [
                'datePublished', 'publishedTime', 'dateCreated',
                'dateModified', 'date', 'published', 'created',
            ]
            
            for field in date_fields:
                if field in obj:
                    date_value = obj[field]
                    if date_value:
                        date_str = str(date_value).strip()
                        if not date_str:
                            continue
                        
                        # 先尝试直接提取日期部分（最可靠）
                        try:
                            if len(date_str) >= 10:
                                dt = datetime.strptime(date_str[:10], '%Y-%m-%d')
                                if 2000 <= dt.year <= 2100:
                                    return dt.date()
                        except ValueError:
                            pass
                        
                        # 支持多种完整格式
                        date_formats = [
                            '%Y-%m-%d',
                            '%Y-%m-%dT%H:%M:%S',
                            '%Y-%m-%dT%H:%M:%SZ',
                            '%Y-%m-%dT%H:%M:%S.%fZ',
                            '%Y-%m-%dT%H:%M:%S%z',
                        ]
                        
                        for fmt in date_formats:
                            try:
                                if '%f' in fmt:
                                    if '.' in date_str:
                                        parts = date_str.split('.')
                                        if len(parts) >= 2:
                                            base = parts[0]
                                            micro_part = parts[1].rstrip('Z').split('+')[0].split('-')[0]
                                            if len(micro_part) > 6:
                                                micro_part = micro_part[:6]
                                            date_str_parsed = f"{base}.{micro_part}"
                                            dt = datetime.strptime(date_str_parsed, '%Y-%m-%dT%H:%M:%S.%f')
                                            return dt.date()
                                elif '%z' in fmt:
                                    if len(date_str) >= 10:
                                        dt = datetime.strptime(date_str[:10], '%Y-%m-%d')
                                        return dt.date()
                                else:
                                    date_part = date_str[:len(fmt.replace('T', ' ').replace('Z', ''))]
                                    dt = datetime.strptime(date_part, fmt.replace('T', ' ').replace('Z', ''))
                                    return dt.date()
                            except ValueError:
                                continue
            
            # 递归检查嵌套对象
            for key, value in obj.items():
                if isinstance(value, dict):
                    result = extract_date_from_json_ld(value, visited)
                    if result:
                        return result
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            result = extract_date_from_json_ld(item, visited)
                            if result:
                                return result
            
            return None
        
        json_ld_scripts = soup.find_all('script', type='application/ld+json')
        for script in json_ld_scripts:
            try:
                if not script.string:
                    continue
                data = json.loads(script.string)
                date_result = extract_date_from_json_ld(data)
                if date_result:
                    return date_result
            except (json.JSONDecodeError, Exception):
                continue
        
        # 3. 检查time标签
        time_tags = soup.find_all('time')
        for time_tag in time_tags[:5]:  # 只检查前5个
            datetime_attr = time_tag.get('datetime') or time_tag.get('pubdate')
            if datetime_attr:
                # 支持多种日期时间格式
                date_formats = [
                    '%Y-%m-%d',
                    '%Y-%m-%dT%H:%M:%S',
                    '%Y-%m-%dT%H:%M:%SZ',
                    '%Y-%m-%dT%H:%M:%S%z',
                ]
                
                for fmt in date_formats:
                    try:
                        if '%z' in fmt:
                            if len(datetime_attr) >= 10:
                                dt = datetime.strptime(datetime_attr[:10], '%Y-%m-%d')
                                return dt.date()
                        else:
                            date_part = datetime_attr[:len(fmt.replace('T', ' ').replace('Z', ''))]
                            dt = datetime.strptime(date_part, fmt.replace('T', ' ').replace('Z', ''))
                            return dt.date()
                    except ValueError:
                        continue
        
    except Exception as e:
        logger.debug("Failed to extract date from HTML %s: %s", url, e)
    
    return None


def _extract_date_from_http_headers(headers: dict | None) -> Optional[date]:
    """从HTTP响应头中提取日期（Last-Modified）"""
    if not headers or 'last-modified' not in headers:
        return None
    
    try:
        from email.utils import parsedate_to_datetime
        last_modified = parsedate_to_datetime(headers['last-modified'])
        if last_modified:
            return last_modified.date()
    except Exception as e:
        logger.debug("Failed to parse Last-Modified header: %s", e)
    
    return None


def _extract_date_from_text(content: str) -> Optional[date]:
    """从文本内容中提取日期（增强版：支持带上下文的日期）"""
    if not content:
        return None
    
    month_map = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4,
        'may': 5, 'june': 6, 'july': 7, 'august': 8,
        'september': 9, 'october': 10, 'november': 11, 'december': 12,
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
        'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
        'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    }
    
    # 常见的日期模式（按优先级排序）
    date_patterns = [
        # 带上下文的日期（优先级最高）
        (r'(Published|Last\s+updated?|Effective|Date|发布日期|最后更新|生效日期)[:\s]+(\d{1,2})[/-](\d{1,2})[/-](\d{4})', 'context_mdy'),
        (r'(Published|Last\s+updated?|Effective|Date|发布日期|最后更新|生效日期)[:\s]+(\d{4})[/-](\d{1,2})[/-](\d{1,2})', 'context_ymd'),
        # ISO格式
        (r'(\d{4})-(\d{1,2})-(\d{1,2})', 'iso'),
        # 斜杠格式
        (r'(\d{4})/(\d{1,2})/(\d{1,2})', 'iso_slash'),
        # 美式格式 (MM/DD/YYYY)
        (r'(\d{1,2})/(\d{1,2})/(\d{4})', 'us'),
        # 英文月份格式 (January 15, 2024)
        (r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})', 'english'),
        # 英文月份缩写格式 (Jan 15, 2024)
        (r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+(\d{1,2}),?\s+(\d{4})', 'english_short'),
    ]
    
    # 查找所有匹配的日期（只检查前5000字符以提高性能）
    text_sample = content[:5000]
    found_dates = []
    
    for pattern_info in date_patterns:
        pattern = pattern_info[0]
        pattern_type = pattern_info[1]
        
        matches = re.finditer(pattern, text_sample, re.IGNORECASE)
        for match in matches:
            try:
                groups = match.groups()
                if pattern_type == 'context_mdy' and len(groups) >= 4:
                    month, day, year = int(groups[1]), int(groups[2]), int(groups[3])
                    if 1 <= month <= 12 and 1 <= day <= 31 and 2000 <= year <= 2100:
                        found_dates.append((date(year, month, day), True))
                elif pattern_type == 'context_ymd' and len(groups) >= 4:
                    year, month, day = int(groups[1]), int(groups[2]), int(groups[3])
                    if 1 <= month <= 12 and 1 <= day <= 31 and 2000 <= year <= 2100:
                        found_dates.append((date(year, month, day), True))
                elif pattern_type in ['iso', 'iso_slash'] and len(groups) == 3:
                    year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                    if 2000 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
                        found_dates.append((date(year, month, day), False))
                elif pattern_type == 'us' and len(groups) == 3:
                    month, day, year = int(groups[0]), int(groups[1]), int(groups[2])
                    if 1 <= month <= 12 and 1 <= day <= 31 and 2000 <= year <= 2100:
                        found_dates.append((date(year, month, day), False))
                elif pattern_type in ['english', 'english_short'] and len(groups) == 3:
                    month_name = groups[0].lower().rstrip('.')
                    day = int(groups[1])
                    year = int(groups[2])
                    month = month_map.get(month_name)
                    if month and 1 <= day <= 31 and 2000 <= year <= 2100:
                        found_dates.append((date(year, month, day), False))
            except (ValueError, IndexError, KeyError):
                continue
    
    # 优先返回带上下文的日期，否则返回第一个找到的日期
    if found_dates:
        # 按优先级排序：带上下文的日期优先
        found_dates.sort(key=lambda x: (not x[1], x[0]))
        return found_dates[0][0]
    
    return None


def _extract_publish_date(url: str, soup: BeautifulSoup | None, content: str | None, extracted_data: dict | None, http_headers: dict | None = None) -> Optional[date]:
    """提取发布时间，按优先级尝试多种方法（增强版）"""
    # 1. 从URL中提取（包括PDF文件名）
    date_from_url = _extract_date_from_url(url)
    if date_from_url:
        logger.debug("Extracted publish_date from URL: %s", date_from_url)
        return date_from_url
    
    # 2. 从HTML meta标签和JSON-LD中提取
    if soup:
        date_from_html = _extract_date_from_html(soup, url)
        if date_from_html:
            logger.debug("Extracted publish_date from HTML: %s", date_from_html)
            return date_from_html
    
    # 3. 从HTTP响应头中提取（特别是PDF文件的Last-Modified）
    if http_headers:
        date_from_headers = _extract_date_from_http_headers(http_headers)
        if date_from_headers:
            logger.debug("Extracted publish_date from HTTP headers: %s", date_from_headers)
            return date_from_headers
    
    # 4. 从extracted_data中提取（包括嵌套对象）
    if extracted_data:
        def extract_from_dict(data: dict) -> Optional[date]:
            """递归从字典中提取日期"""
            date_fields = [
                'publish_date', 'published_date', 'date', 'effective_date',
                'publication_date', 'pub_date', 'pubDate', 'publishedAt',
            ]
            
            for key in date_fields:
                if key in data:
                    value = data[key]
                    if isinstance(value, str):
                        for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ']:
                            try:
                                dt = datetime.strptime(value[:10], fmt)
                                logger.debug("Extracted publish_date from extracted_data[%s]: %s", key, dt.date())
                                return dt.date()
                            except ValueError:
                                continue
                    elif isinstance(value, (int, float)):
                        try:
                            dt = datetime.fromtimestamp(value)
                            logger.debug("Extracted publish_date from extracted_data[%s] (timestamp): %s", key, dt.date())
                            return dt.date()
                        except (ValueError, OSError):
                            pass
            
            # 检查嵌套对象
            for key in ['policy', 'market', 'article', 'metadata']:
                if key in data and isinstance(data[key], dict):
                    result = extract_from_dict(data[key])
                    if result:
                        return result
            
            return None
        
        date_from_extracted = extract_from_dict(extracted_data)
        if date_from_extracted:
            return date_from_extracted
    
    # 5. 从内容文本中提取（增强版：支持带上下文的日期）
    if content:
        date_from_text = _extract_date_from_text(content)
        if date_from_text:
            logger.debug("Extracted publish_date from content (regex): %s", date_from_text)
            return date_from_text
    
    return None


def _get_or_create_source(session, domain: str) -> int:
    src = session.query(Source).filter(Source.base_url == domain).one_or_none()
    if src:
        return src.id
    src = Source(name=domain, kind="web", base_url=domain)
    session.add(src)
    session.flush()
    return src.id


_POLICY_TOKENS = {
    "regulation", "regulations", "policy", "policies", "bill", "bills", "legislation",
    "statute", "ordinance", "rulemaking", "notice", "committee", "assembly", "senate",
    "法规", "法案", "政策", "立法", "条例", "公告",
}

_MARKET_TOKENS = {
    "market", "sales", "revenue", "jackpot", "draw", "winning", "numbers", "ticket", "prize",
    "trend", "report", "payout", "volume",
    "市场", "销售", "收入", "奖池", "开奖", "中奖", "票价", "走势", "报告",
}


def _classify_kind(title: str, snippet: str, content: str | None) -> str:
    text = " ".join([title or "", snippet or "", (content or "")[:2000]]).lower()
    p_hits = sum(1 for t in _POLICY_TOKENS if t in text)
    m_hits = sum(1 for t in _MARKET_TOKENS if t in text)
    if p_hits >= m_hits + 1:
        return "policy"
    if m_hits >= p_hits + 1:
        return "market"

    # Fallback to LLM when ambiguous
    try:
        # 尝试从数据库读取配置
        from ..llm.config_loader import get_llm_config, format_prompt_template
        
        config = get_llm_config("document_classification")
        
        if config and config.get("user_prompt_template"):
            # 使用配置的提示词
            prompt = format_prompt_template(
                config["user_prompt_template"],
                title=title,
                snippet=snippet,
                content=(content or '')[:800]
            )
            model = get_chat_model(
                model=config.get("model"),
                temperature=config.get("temperature"),
                max_tokens=config.get("max_tokens"),
                top_p=config.get("top_p"),
                presence_penalty=config.get("presence_penalty"),
                frequency_penalty=config.get("frequency_penalty"),
            )
        else:
            # 使用默认提示词（向后兼容）
            prompt = (
                "请将以下内容粗分类为'policy'或'market'之一，仅返回这两个词之一。\n"
                f"标题: {title}\n摘要: {snippet}\n正文片段: {(content or '')[:800]}\n分类:"
            )
            model = get_chat_model()
        
        resp = model.invoke(prompt)
        txt = getattr(resp, "content", str(resp)).strip().lower()
        if "policy" in txt and "market" not in txt:
            return "policy"
        if "market" in txt and "policy" not in txt:
            return "market"
    except Exception:
        pass
    # Default heuristic
    return "policy" if p_hits >= m_hits else "market"


_DOMAIN_STATE = {
    "www.calottery.com": "CA",
    "calottery.com": "CA",
    "static.www.calottery.com": "CA",
    "data.ny.gov": "NY",
    "ny.gov": "NY",
    "www.texaslottery.com": "TX",
    "texaslottery.com": "TX",
}


def _infer_state(domain: str, title: str, snippet: str) -> str | None:
    if domain in _DOMAIN_STATE:
        return _DOMAIN_STATE[domain]
    lower = (title + " " + snippet).lower()
    if "california" in lower:  # heuristic
        return "CA"
    if "new york" in lower:
        return "NY"
    if "texas" in lower:
        return "TX"
    return None


def _store_tables_available(session) -> bool:
    """Check if sources and documents tables exist (auto-detect schema readiness)."""
    try:
        session.execute(text("SELECT 1 FROM sources LIMIT 1"))
        session.execute(text("SELECT 1 FROM documents LIMIT 1"))
        return True
    except Exception as e:
        err = str(e).lower()
        if "does not exist" in err or "undefined_table" in err:
            logger.info("discovery.store: tables not ready (sources/documents), skip persist")
            return False
        raise


def store_results(
    results: List[Dict],
    *,
    project_key: str | None = None,
    job_type: str | None = None,
) -> Dict[str, int]:
    inserted = 0
    updated = 0
    skipped = 0
    policy_to_index: List[int] = []

    with SessionLocal() as session:
        if not _store_tables_available(session):
            return {"inserted": 0, "updated": 0, "skipped": len(results), "store_available": False}
        for item in results:
            try:
                link = _normalize_url((item.get("link") or "").strip())
                if not link:
                    skipped += 1
                    continue
                # Resource pool capture hook: append URL when capture enabled for project + job_type
                if project_key and job_type:
                    try:
                        from ..resource_pool import DefaultResourcePoolAppendAdapter
                        adapter = DefaultResourcePoolAppendAdapter()
                        adapter.append_url(
                            link,
                            source="discovery",
                            source_ref={"domain": item.get("domain") or urlparse(link).netloc},
                            project_key=project_key,
                            job_type=job_type,
                        )
                    except Exception as rp_exc:  # noqa: BLE001
                        logger.debug("resource_pool append skipped: %s", rp_exc)
                domain = item.get("domain") or urlparse(link).netloc
                title = (item.get("title") or "").replace("\x00", "").strip() or domain
                snippet = (item.get("snippet") or "").replace("\x00", "").strip()

                source_id = _get_or_create_source(session, domain)

                # Dedup by URI first
                doc = session.query(Document).filter(Document.uri == link).one_or_none()
                if doc:
                    # Fetch content for date extraction if publish_date is missing
                    content_for_date = None
                    soup_for_date = None
                    headers_for_date = None
                    if not doc.publish_date:
                        content_for_date, soup_for_date, headers_for_date = _fetch_content(link)

                    # light update if missing summary/title/content
                    changed = False
                    if not (doc.content and len(doc.content.strip()) >= 50):
                        content_fetched, soup_for_date, headers_for_date = _fetch_content(link)
                        if content_fetched and len(content_fetched.strip()) >= 50:
                            doc.content = content_fetched[:20000]
                            content_for_date = content_fetched
                            changed = True
                            logger.info("discovery.store filled empty content for url=%s", link[:60])
                    if not doc.title and title:
                        doc.title = title
                        changed = True
                    if not doc.summary and snippet:
                        doc.summary = snippet
                        changed = True
                    if not doc.summary and snippet:
                        doc.summary = snippet
                        changed = True
                    # 补充 doc_type（若之前为 external）
                    if doc.doc_type in (None, "external"):
                        content_peek = (doc.content or "")[:800]
                        doc.doc_type = _classify_kind(title, snippet, content_peek)
                        changed = True
                    # 补充 state
                    if not doc.state:
                        inferred = _infer_state(domain, title, snippet)
                        if inferred:
                            doc.state = inferred
                            changed = True
                    # 补充 publish_date（如果缺失）
                    if not doc.publish_date:
                        # 尝试从URL、HTML、HTTP响应头或extracted_data中提取
                        extracted_data_peek = doc.extracted_data or {}
                        publish_date = _extract_publish_date(link, soup_for_date, content_for_date, extracted_data_peek, headers_for_date)
                        if publish_date:
                            doc.publish_date = publish_date
                            changed = True
                            logger.info("discovery.store updated publish_date=%s for existing doc url=%s", publish_date, link)
                    if changed:
                        updated += 1
                        if doc.doc_type == "policy":
                            policy_to_index.append(doc.id)
                    else:
                        skipped += 1
                    continue

                # Fetch content best-effort（不阻塞失败）
                content, soup, http_headers = _fetch_content(link)
                text_hash = _sha256((content or title) + "\n" + link)

                # Unique by text_hash as well（DB 层有唯一约束可利用）
                exists = session.query(Document).filter(Document.text_hash == text_hash).one_or_none()
                if exists:
                    skipped += 1
                    continue

                kind = _classify_kind(title, snippet, content)
                state = _infer_state(domain, title, snippet)
                
                # 结构化提取（Phase 2）
                extracted_data = None
                if content:
                    try:
                        from ..extraction.application import ExtractionApplicationService
                        extraction_app = ExtractionApplicationService()
                        if kind == "policy":
                            extracted_data = extraction_app.extract_structured_enriched(content, include_policy=True)
                        
                        elif kind == "market":
                            extracted_data = extraction_app.extract_structured_enriched(content, include_market=True)
                    except Exception as e:
                        logger.warning("discovery.store extraction failed url=%s err=%s", link, e)
                
                # 提取发布时间（增强版：包括HTTP响应头）
                publish_date = _extract_publish_date(link, soup, content, extracted_data, http_headers)
                if publish_date:
                    logger.info("discovery.store extracted publish_date=%s for url=%s", publish_date, link)
                
                doc = Document(
                    source_id=source_id,
                    state=state,
                    doc_type=kind,
                    title=title,
                    status=None,
                    publish_date=publish_date,
                    content=(content or None),
                    summary=snippet,
                    text_hash=text_hash,
                    uri=link,
                    extracted_data=extracted_data,
                )
                session.add(doc)
                inserted += 1
                if kind == "policy":
                    session.flush()
                    policy_to_index.append(doc.id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("discovery.store skipped error err=%s", exc)
                skipped += 1

        session.commit()

    # 触发索引（仅当配置了 OPENAI_API_KEY 且有新增/更新政策文档）
    if settings.openai_api_key and policy_to_index:
        try:
            index_policy_documents(document_ids=policy_to_index)
        except Exception as exc:  # noqa: BLE001
            logger.warning("discovery.store index failed ids=%s err=%s", policy_to_index, exc)

    return {"inserted": inserted, "updated": updated, "skipped": skipped, "store_available": True}
