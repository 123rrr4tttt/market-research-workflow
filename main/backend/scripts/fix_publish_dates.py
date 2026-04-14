"""修复数据库中缺失的发布时间

这个脚本会：
1. 查找所有 publish_date 为 NULL 的文档
2. 尝试从 URL、extracted_data 或其他来源提取发布时间
3. 更新数据库中的 publish_date 字段
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

# 添加backend目录到Python路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))
os.environ.setdefault("PYTHONPATH", str(backend_dir))

import logging
import re
import json
from datetime import datetime, date
from urllib.parse import urlparse, parse_qs
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session
from bs4 import BeautifulSoup

from app.models.base import SessionLocal
from app.models.entities import Document

logger = logging.getLogger(__name__)


def extract_date_from_url(url: str) -> Optional[date]:
    """从URL中提取日期
    
    很多网站的URL包含日期信息，例如：
    - https://example.com/2024/01/15/article
    - https://example.com/article?date=2024-01-15
    - PDF文件名中的日期: FY 2023-24, 2024-01-15-report.pdf
    """
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
            ]
            for pattern in date_patterns:
                match = re.search(pattern, filename)
                if match:
                    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
                    if 2000 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
                        return date(year, month, day)
            
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
        logger.debug(f"Failed to extract date from URL {url}: {e}")
    
    return None


def extract_date_from_text(content: str) -> Optional[date]:
    """从纯文本内容中提取日期（使用正则表达式）
    
    增强版本：支持更多日期格式和上下文关键词
    """
    if not content:
        return None
    
    # 常见的日期模式（按优先级排序）
    date_patterns = [
        # 带上下文的日期（优先级最高）
        (r'(Published|Last\s+updated?|Effective|Date|发布日期|最后更新|生效日期)[:\s]+(\d{1,2})[/-](\d{1,2})[/-](\d{4})', None, 'context'),
        (r'(Published|Last\s+updated?|Effective|Date|发布日期|最后更新|生效日期)[:\s]+(\d{4})[/-](\d{1,2})[/-](\d{1,2})', None, 'context'),
        # ISO格式
        (r'(\d{4})-(\d{1,2})-(\d{1,2})', '%Y-%m-%d', None),
        # 斜杠格式
        (r'(\d{4})/(\d{1,2})/(\d{1,2})', '%Y/%m/%d', None),
        # 美式格式 (MM/DD/YYYY)
        (r'(\d{1,2})/(\d{1,2})/(\d{4})', '%m/%d/%Y', None),
        # 英文月份格式 (January 15, 2024)
        (r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})', None, 'english'),
        # 英文月份缩写格式 (Jan 15, 2024)
        (r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+(\d{1,2}),?\s+(\d{4})', None, 'english_short'),
    ]
    
    month_map = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4,
        'may': 5, 'june': 6, 'july': 7, 'august': 8,
        'september': 9, 'october': 10, 'november': 11, 'december': 12,
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
        'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
        'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    }
    
    # 查找所有匹配的日期（只检查前5000字符以提高性能）
    text_sample = content[:5000]
    found_dates = []
    
    for pattern_info in date_patterns:
        pattern = pattern_info[0]
        fmt = pattern_info[1] if len(pattern_info) > 1 else None
        pattern_type = pattern_info[2] if len(pattern_info) > 2 else None
        
        matches = re.finditer(pattern, text_sample, re.IGNORECASE)
        for match in matches:
            try:
                if fmt:
                    # 标准格式日期
                    date_str = match.group(0)
                    dt = datetime.strptime(date_str, fmt)
                    if 2000 <= dt.year <= 2100:  # 合理的年份范围
                        found_dates.append((dt.date(), pattern_type == 'context'))
                elif pattern_type == 'context':
                    # 带上下文的日期格式
                    groups = match.groups()
                    if len(groups) >= 4:
                        # 第一个模式: (关键词, month, day, year) - 4个组
                        try:
                            month, day, year = int(groups[1]), int(groups[2]), int(groups[3])
                            if 1 <= month <= 12 and 1 <= day <= 31 and 2000 <= year <= 2100:
                                found_dates.append((date(year, month, day), True))
                        except (ValueError, IndexError):
                            # 第二个模式: (关键词, year, month, day) - 4个组
                            try:
                                year, month, day = int(groups[1]), int(groups[2]), int(groups[3])
                                if 1 <= month <= 12 and 1 <= day <= 31 and 2000 <= year <= 2100:
                                    found_dates.append((date(year, month, day), True))
                            except (ValueError, IndexError):
                                pass
                elif pattern_type in ['english', 'english_short']:
                    # 英文月份格式
                    groups = match.groups()
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


def extract_date_from_html_content(content: str, url: str) -> Optional[date]:
    """从HTML内容中提取发布时间"""
    if not content:
        return None
    
    # 如果内容看起来不像HTML，直接作为文本处理
    if '<' not in content or '>' not in content:
        return extract_date_from_text(content)
    
    try:
        soup = BeautifulSoup(content, "html.parser")
        
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
            # HTTP响应头（通过meta标签）
            ('http-equiv', 'last-modified'),
        ]
        
        for attr, value in meta_tags:
            meta = soup.find('meta', {attr: value})
            if meta and meta.get('content'):
                date_str = meta.get('content')
                # 尝试解析ISO格式日期（支持多种格式）
                # 先尝试提取日期部分（前10个字符）
                try:
                    if len(date_str) >= 10:
                        # 直接提取日期部分 YYYY-MM-DD
                        dt = datetime.strptime(date_str[:10], '%Y-%m-%d')
                        return dt.date()
                except ValueError:
                    pass
                
                # 尝试解析完整的时间戳格式
                date_formats = [
                    '%Y-%m-%dT%H:%M:%S',  # 2025-04-07T13:30:19
                    '%Y-%m-%dT%H:%M:%SZ',  # 2025-04-07T13:30:19Z
                    '%Y-%m-%dT%H:%M:%S.%fZ',  # 2025-07-29T21:37:09.000Z
                    '%Y-%m-%dT%H:%M:%S%z',  # 2025-04-07T13:30:19+00:00
                    '%Y-%m-%dT%H:%M:%S.%f%z',  # 2025-04-07T13:30:19.000+00:00
                ]
                
                for fmt in date_formats:
                    try:
                        if '%f' in fmt:
                            # 处理微秒格式
                            # 移除时区部分，先解析日期时间
                            if '+' in date_str or date_str.endswith('Z'):
                                # 有时区或Z结尾
                                date_part = date_str.split('+')[0].split('-')[0] if '+' in date_str else date_str.rstrip('Z')
                                # 尝试找到微秒部分
                                if '.' in date_part:
                                    parts = date_part.split('.')
                                    if len(parts) == 2:
                                        base = parts[0]
                                        micro = parts[1].rstrip('Z')[:6]  # 最多6位微秒
                                        date_part = f"{base}.{micro}"
                                        dt = datetime.strptime(date_part, '%Y-%m-%dT%H:%M:%S.%f')
                                        return dt.date()
                            else:
                                dt = datetime.strptime(date_str, fmt)
                                return dt.date()
                        elif '%z' in fmt:
                            # 处理时区格式
                            if len(date_str) >= 19:
                                # 只提取日期部分
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
        
        # 2. 检查time标签（包括datetime属性和文本内容）
        time_tags = soup.find_all('time')
        for time_tag in time_tags[:5]:  # 只检查前5个
            # 先检查datetime属性
            datetime_attr = time_tag.get('datetime') or time_tag.get('pubdate')
            if datetime_attr:
                # 支持多种日期时间格式，包括时区
                date_formats = [
                    '%Y-%m-%d',  # 2025-01-22
                    '%Y-%m-%dT%H:%M:%S',  # 2025-01-22T22:38:37
                    '%Y-%m-%dT%H:%M:%SZ',  # 2025-01-22T22:38:37Z
                    '%Y-%m-%dT%H:%M:%S%z',  # 2025-01-22T22:38:37-0800
                    '%Y-%m-%dT%H:%M:%S%z',  # 2025-01-22T22:38:37+0800
                ]
                
                for fmt in date_formats:
                    try:
                        # 处理时区格式
                        if '%z' in fmt:
                            # 尝试解析带时区的格式
                            # 格式可能是 -0800 或 +0800
                            if len(datetime_attr) >= 19:
                                date_part = datetime_attr[:19]
                                # 移除时区部分，只解析日期时间
                                dt = datetime.strptime(date_part, '%Y-%m-%dT%H:%M:%S')
                                return dt.date()
                        else:
                            # 标准格式
                            date_str = datetime_attr[:len(fmt.replace('T', ' ').replace('%z', '').replace('Z', ''))]
                            dt = datetime.strptime(date_str, fmt.replace('T', ' ').replace('Z', ''))
                            return dt.date()
                    except ValueError:
                        continue
                
                # 如果上面的格式都失败，尝试只提取日期部分
                try:
                    if len(datetime_attr) >= 10:
                        date_part = datetime_attr[:10]
                        dt = datetime.strptime(date_part, '%Y-%m-%d')
                        return dt.date()
                except ValueError:
                    pass
            
            # 检查time标签的文本内容
            time_text = time_tag.get_text(strip=True)
            if time_text:
                date_from_text = extract_date_from_text(time_text)
                if date_from_text:
                    return date_from_text
        
        # 3. 检查JSON-LD结构化数据
        json_ld_scripts = soup.find_all('script', type='application/ld+json')
        for script in json_ld_scripts:
            try:
                script_content = script.string
                if not script_content:
                    continue
                    
                data = json.loads(script_content)
                
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
                        'modified', 'updateDate', 'publishDate', 'publicationDate',
                        'datePosted', 'postDate', 'releaseDate'
                    ]
                    
                    for field in date_fields:
                        if field in obj:
                            date_value = obj[field]
                            if date_value:
                                # 尝试解析日期字符串
                                date_str = str(date_value).strip()
                                if not date_str:
                                    continue
                                
                                # 先尝试直接提取日期部分（最可靠）
                                try:
                                    if len(date_str) >= 10:
                                        dt = datetime.strptime(date_str[:10], '%Y-%m-%d')
                                        if 2000 <= dt.year <= 2100:  # 验证年份合理性
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
                                elif isinstance(item, str):
                                    # 检查是否是日期字符串
                                    try:
                                        if len(item) >= 10:
                                            dt = datetime.strptime(item[:10], '%Y-%m-%d')
                                            if 2000 <= dt.year <= 2100:
                                                return dt.date()
                                    except ValueError:
                                        pass
                    
                    return None
                
                # 处理dict类型
                if isinstance(data, dict):
                    date_result = extract_date_from_json_ld(data)
                    if date_result:
                        return date_result
                # 处理list类型
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            date_result = extract_date_from_json_ld(item)
                            if date_result:
                                return date_result
            except (json.JSONDecodeError, Exception) as e:
                logger.debug(f"Failed to parse JSON-LD: {e}")
                continue
        
        # 4. 检查常见的日期CSS类或ID
        date_selectors = [
            {'class': re.compile(r'date|published|pub-date|publish-date|post-date', re.I)},
            {'id': re.compile(r'date|published|pub-date|publish-date', re.I)},
        ]
        
        for selector in date_selectors:
            elements = soup.find_all(attrs=selector)
            for elem in elements[:5]:  # 只检查前5个
                elem_text = elem.get_text(strip=True)
                if elem_text:
                    date_from_text = extract_date_from_text(elem_text)
                    if date_from_text:
                        return date_from_text
        
        # 5. 从HTML文本内容中提取日期（提取所有文本后分析）
        text_content = soup.get_text(separator=' ', strip=True)
        if text_content:
            date_from_text = extract_date_from_text(text_content)
            if date_from_text:
                return date_from_text
        
    except Exception as e:
        logger.debug(f"Failed to extract date from HTML content {url}: {e}")
        # 如果HTML解析失败，尝试作为纯文本提取
        return extract_date_from_text(content)
    
    return None


def extract_date_from_reddit_url(url: str) -> Optional[date]:
    """从Reddit URL提取帖子日期
    
    Reddit URL格式: https://www.reddit.com/r/subreddit/comments/POST_ID/title/
    
    方法1: 使用Reddit JSON API (不需要API凭证)
    方法2: 从网页的time标签提取
    """
    if not url or 'reddit.com' not in url.lower():
        return None
    
    try:
        import requests
        
        # 方法1: 使用Reddit JSON API (在URL后加.json)
        # 例如: https://www.reddit.com/r/subreddit/comments/POST_ID/title/.json
        json_url = url.rstrip('/') + '.json'
        
        try:
            response = requests.get(
                json_url,
                timeout=10,
                headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
            )
            if response.status_code == 200:
                data = response.json()
                # Reddit JSON API返回一个列表，第一个元素是帖子数据
                if isinstance(data, list) and len(data) > 0:
                    post_data = data[0]
                    if 'data' in post_data and 'children' in post_data['data']:
                        children = post_data['data']['children']
                        if len(children) > 0:
                            submission = children[0].get('data', {})
                            # 提取created_utc时间戳
                            created_utc = submission.get('created_utc')
                            if created_utc:
                                try:
                                    dt = datetime.fromtimestamp(created_utc)
                                    return dt.date()
                                except (ValueError, OSError):
                                    pass
        except (requests.RequestException, json.JSONDecodeError, KeyError, Exception) as e:
            logger.debug(f"Reddit JSON API提取失败 {url}: {e}")
        
        # 方法2: 尝试从Reddit网页提取time标签
        try:
            response = requests.get(
                url,
                timeout=10,
                headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
            )
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                # Reddit使用time标签存储发布时间
                time_tags = soup.find_all('time')
                for time_tag in time_tags:
                    datetime_attr = time_tag.get('datetime')
                    if datetime_attr:
                        # 格式通常是: 2025-01-22T10:30:00+00:00
                        try:
                            if len(datetime_attr) >= 10:
                                dt = datetime.strptime(datetime_attr[:10], '%Y-%m-%d')
                                return dt.date()
                        except ValueError:
                            continue
        except (requests.RequestException, Exception) as e:
            logger.debug(f"从Reddit网页提取日期失败 {url}: {e}")
            
    except Exception as e:
        logger.debug(f"Reddit日期提取异常 {url}: {e}")
    
    return None


def extract_date_from_reddit_timestamp(extracted_data: dict) -> Optional[date]:
    """从Reddit的extracted_data中提取时间戳
    
    Reddit的extracted_data可能包含时间信息，如created_utc时间戳
    """
    if not extracted_data:
        return None
    
    # 检查是否有Reddit相关的时间字段
    reddit_date_fields = ['created_utc', 'created', 'timestamp', 'date']
    
    for field in reddit_date_fields:
        if field in extracted_data:
            value = extracted_data[field]
            if isinstance(value, (int, float)):
                # Unix时间戳
                try:
                    dt = datetime.fromtimestamp(value)
                    return dt.date()
                except (ValueError, OSError):
                    pass
            elif isinstance(value, str):
                # 日期字符串
                try:
                    if len(value) >= 10:
                        dt = datetime.strptime(value[:10], '%Y-%m-%d')
                        return dt.date()
                except ValueError:
                    pass
    
    return None


def fix_publish_dates(dry_run: bool = True, limit: Optional[int] = None, enable_fetch: bool = False) -> dict:
    """修复缺失的发布时间
    
    Args:
        dry_run: 如果为True，只显示将要更新的记录，不实际更新
        limit: 限制处理的记录数量（用于测试）
    
    Returns:
        包含统计信息的字典
    """
    stats = {
        "total_checked": 0,
        "fixed": 0,
        "failed": 0,
        "skipped": 0,
    }
    
    with SessionLocal() as session:
        # 查找所有 publish_date 为 NULL 的文档
        query = select(Document).where(Document.publish_date.is_(None))
        
        if limit:
            query = query.limit(limit)
        
        docs = session.execute(query).scalars().all()
        stats["total_checked"] = len(docs)
        
        logger.info(f"找到 {len(docs)} 个缺失发布时间的文档")
        
        for idx, doc in enumerate(docs, 1):
            if idx % 10 == 0:
                logger.info(f"处理进度: {idx}/{len(docs)} ({idx*100//len(docs)}%)")
            try:
                new_date = None
                
                # 方法1: 从URL中提取日期
                if doc.uri:
                    # 先检查是否是Reddit URL
                    if 'reddit.com' in doc.uri.lower():
                        new_date = extract_date_from_reddit_url(doc.uri)
                    else:
                        new_date = extract_date_from_url(doc.uri)
                
                # 方法2: 从HTML内容中提取（如果文档有保存的HTML内容）
                if not new_date and doc.content:
                    # 尝试从content中提取HTML并解析
                    new_date = extract_date_from_html_content(doc.content, doc.uri or "")
                
                # 方法2.5: 如果content中没有找到，尝试重新抓取页面（可选，默认禁用）
                if not new_date and doc.uri and enable_fetch:
                    # 跳过PDF文件和其他非HTML内容
                    uri_lower = doc.uri.lower()
                    if any(ext in uri_lower for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip', '.rar']):
                        logger.debug(f"文档 {doc.id}: 跳过非HTML文件 {doc.uri}")
                    else:
                        try:
                            import requests
                            
                            # 使用requests设置超时（10秒），允许重定向（特别是Google News）
                            try:
                                response = requests.get(doc.uri, timeout=10, allow_redirects=True, headers={
                                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                                })
                                
                                # 检查HTTP响应头的Last-Modified
                                if 'last-modified' in response.headers:
                                    try:
                                        from email.utils import parsedate_to_datetime
                                        last_modified = parsedate_to_datetime(response.headers['last-modified'])
                                        if last_modified:
                                            new_date = last_modified.date()
                                            logger.info(f"文档 {doc.id}: 从HTTP响应头Last-Modified提取到日期 {new_date}")
                                    except Exception as e:
                                        logger.debug(f"文档 {doc.id}: 解析Last-Modified失败: {e}")
                                
                                # 从HTML内容提取
                                if not new_date and response.status_code == 200 and 'text/html' in response.headers.get('content-type', ''):
                                    html_content = response.text
                                    new_date = extract_date_from_html_content(html_content, doc.uri)
                                    if new_date:
                                        logger.info(f"文档 {doc.id}: 通过重新抓取提取到日期 {new_date}")
                            except requests.Timeout:
                                logger.debug(f"文档 {doc.id}: 重新抓取超时（10秒）")
                            except requests.RequestException as e:
                                logger.debug(f"文档 {doc.id}: 重新抓取失败: {e}")
                        except Exception as e:
                            logger.debug(f"文档 {doc.id}: 重新抓取异常: {e}")
                
                # 方法3: 从extracted_data中提取（如果有）
                if not new_date and doc.extracted_data:
                    extracted = doc.extracted_data
                    
                    # 如果是Reddit来源，优先使用Reddit专用提取方法
                    if doc.uri and 'reddit.com' in doc.uri.lower():
                        reddit_date = extract_date_from_reddit_timestamp(extracted)
                        if reddit_date:
                            new_date = reddit_date
                    
                    if not new_date:
                        # 检查顶层时间相关的字段（扩展字段列表）
                        date_fields = [
                            'publish_date', 'published_date', 'date', 'timestamp', 
                            'created_time', 'effective_date', 'publication_date',
                            'pub_date', 'pubDate', 'publishedAt', 'published_at',
                            'created_at', 'updated_at', 'last_updated'
                        ]
                        
                        for key in date_fields:
                            if key in extracted:
                                value = extracted[key]
                                if isinstance(value, str) and value:
                                    # 尝试解析日期字符串
                                    for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ']:
                                        try:
                                            dt = datetime.strptime(value[:10], fmt)
                                            new_date = dt.date()
                                            break
                                        except ValueError:
                                            continue
                                elif isinstance(value, (int, float)):
                                    # 可能是Unix时间戳
                                    try:
                                        dt = datetime.fromtimestamp(value)
                                        new_date = dt.date()
                                        break
                                    except (ValueError, OSError):
                                        pass
                            if new_date:
                                break
                        
                        # 检查嵌套对象中的日期（扩展嵌套对象列表）
                        if not new_date:
                            nested_objects = ['policy', 'market', 'article', 'metadata', 'info']
                            for sub_key in nested_objects:
                                if sub_key in extracted and isinstance(extracted[sub_key], dict):
                                    sub_data = extracted[sub_key]
                                    # 检查多种日期字段
                                    for date_key in date_fields + ['report_date', 'release_date', 'announcement_date']:
                                        if date_key in sub_data:
                                            value = sub_data[date_key]
                                            if isinstance(value, str) and value:
                                                for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%Y-%m-%dT%H:%M:%S']:
                                                    try:
                                                        dt = datetime.strptime(value[:10], fmt)
                                                        new_date = dt.date()
                                                        break
                                                    except ValueError:
                                                        continue
                                            elif isinstance(value, (int, float)):
                                                try:
                                                    dt = datetime.fromtimestamp(value)
                                                    new_date = dt.date()
                                                    break
                                                except (ValueError, OSError):
                                                    pass
                                            if new_date:
                                                break
                                    if new_date:
                                        break
                
                # 方法4: 如果所有方法都失败，使用created_at作为备选
                if not new_date and doc.created_at:
                    new_date = doc.created_at.date()
                    logger.info(f"文档 {doc.id}: 使用created_at作为备选日期 {new_date}")
                
                if new_date:
                    if dry_run:
                        logger.info(f"文档 {doc.id} ({doc.title[:50]}...): 将从 {doc.uri} 提取日期 {new_date}")
                    else:
                        # 更新数据库
                        session.execute(
                            update(Document)
                            .where(Document.id == doc.id)
                            .values(publish_date=new_date)
                        )
                        logger.info(f"已更新文档 {doc.id} 的发布时间为 {new_date}")
                    stats["fixed"] += 1
                else:
                    stats["skipped"] += 1
                    logger.debug(f"文档 {doc.id}: 无法提取发布时间（也没有created_at）")
                    
            except Exception as e:
                stats["failed"] += 1
                logger.error(f"处理文档 {doc.id} 时出错: {e}", exc_info=True)
        
        if not dry_run:
            session.commit()
            logger.info("数据库更新完成")
    
    return stats


if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 检查命令行参数
    dry_run = "--dry-run" in sys.argv or "-d" in sys.argv
    enable_fetch = "--fetch" in sys.argv or "-f" in sys.argv
    limit = None
    for arg in sys.argv:
        if arg.startswith("--limit="):
            limit = int(arg.split("=")[1])
    
    if dry_run:
        print("=" * 60)
        print("DRY RUN 模式 - 不会实际更新数据库")
        print("=" * 60)
    
    stats = fix_publish_dates(dry_run=dry_run, limit=limit, enable_fetch=enable_fetch)
    
    print("\n" + "=" * 60)
    print("统计信息:")
    print(f"  检查的文档数: {stats['total_checked']}")
    print(f"  修复的文档数: {stats['fixed']}")
    print(f"  跳过的文档数: {stats['skipped']}")
    print(f"  失败的文档数: {stats['failed']}")
    print("=" * 60)
    
    if dry_run and stats['fixed'] > 0:
        print("\n提示: 运行时不加 --dry-run 参数将实际更新数据库")
    
    if not enable_fetch and stats['skipped'] > 0:
        print("\n提示: 使用 --fetch 或 -f 参数可以启用重新抓取功能（可能较慢）")

