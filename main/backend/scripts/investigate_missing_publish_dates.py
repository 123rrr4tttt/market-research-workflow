"""调查没有publish_date的文档，尝试从多个来源获取发布日期

这个脚本会：
1. 查找所有 publish_date 为 NULL 的文档
2. 分析这些文档的特征（来源、类型、是否有URL等）
3. 尝试从多个来源提取日期：
   - URL
   - HTML内容（如果保存了）
   - extracted_data
   - 重新抓取页面（如果URL存在且可访问）
4. 生成详细的报告
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
from collections import defaultdict

from sqlalchemy import select, func
from sqlalchemy.orm import Session
from bs4 import BeautifulSoup

from app.models.base import SessionLocal
from app.models.entities import Document, Source
from app.services.ingest.adapters.http_utils import fetch_html

logger = logging.getLogger(__name__)


def extract_date_from_url(url: str) -> Optional[date]:
    """从URL中提取日期"""
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
                if 2000 <= year <= 2100:
                    # 检查后面是否有月份和日期
                    if i + 2 < len(path_parts):
                        try:
                            month = int(path_parts[i + 1])
                            day = int(path_parts[i + 2])
                            if 1 <= month <= 12 and 1 <= day <= 31:
                                return date(year, month, day)
                        except (ValueError, IndexError):
                            pass
        
        # 从查询参数中提取日期
        query_params = parse_qs(parsed.query)
        for key in ['date', 'publish_date', 'published', 'time']:
            if key in query_params:
                date_str = query_params[key][0]
                for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%d/%m/%Y']:
                    try:
                        return datetime.strptime(date_str, fmt).date()
                    except ValueError:
                        continue
        
        # 从URL中查找日期模式
        date_patterns = [
            r'(\d{4})-(\d{2})-(\d{2})',
            r'(\d{4})/(\d{2})/(\d{2})',
            r'(\d{2})/(\d{2})/(\d{4})',
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, url)
            if match:
                groups = match.groups()
                if len(groups) == 3:
                    try:
                        if len(groups[0]) == 4:
                            year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                        else:
                            month, day, year = int(groups[0]), int(groups[1]), int(groups[2])
                        
                        if 2000 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
                            return date(year, month, day)
                    except (ValueError, IndexError):
                        continue
        
    except Exception as e:
        logger.debug(f"Failed to extract date from URL {url}: {e}")
    
    return None


def extract_date_from_text(content: str) -> Optional[date]:
    """从纯文本内容中提取日期（使用正则表达式）"""
    if not content:
        return None
    
    # 常见的日期模式
    date_patterns = [
        (r'(\d{4})-(\d{1,2})-(\d{1,2})', '%Y-%m-%d'),  # 2024-01-15
        (r'(\d{4})/(\d{1,2})/(\d{1,2})', '%Y/%m/%d'),  # 2024/1/15
        (r'(\d{1,2})/(\d{1,2})/(\d{4})', '%m/%d/%Y'),  # 1/15/2024
        (r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})', None),  # January 15, 2024
    ]
    
    # 查找所有匹配的日期
    found_dates = []
    for pattern, fmt in date_patterns:
        matches = re.finditer(pattern, content[:5000], re.IGNORECASE)  # 只检查前5000字符
        for match in matches:
            if fmt:
                try:
                    date_str = match.group(0)
                    dt = datetime.strptime(date_str, fmt)
                    if 2000 <= dt.year <= 2100:  # 合理的年份范围
                        found_dates.append(dt.date())
                except ValueError:
                    continue
            else:
                # 处理月份名称格式
                try:
                    month_name = match.group(1)
                    day = int(match.group(2))
                    year = int(match.group(3))
                    month_map = {
                        'january': 1, 'february': 2, 'march': 3, 'april': 4,
                        'may': 5, 'june': 6, 'july': 7, 'august': 8,
                        'september': 9, 'october': 10, 'november': 11, 'december': 12
                    }
                    month = month_map.get(month_name.lower())
                    if month and 1 <= day <= 31 and 2000 <= year <= 2100:
                        found_dates.append(date(year, month, day))
                except (ValueError, IndexError):
                    continue
    
    # 返回找到的第一个合理日期
    if found_dates:
        return found_dates[0]
    
    return None


def extract_date_from_html_content(content: str, url: str) -> Optional[date]:
    """从HTML内容中提取发布时间"""
    if not content:
        return None
    
    # 首先尝试作为HTML解析
    try:
        # 检查是否看起来像HTML
        if '<' in content and '>' in content:
            soup = BeautifulSoup(content, "html.parser")
            
            # 1. 检查meta标签中的发布时间
            meta_tags = [
                ('property', 'article:published_time'),
                ('property', 'og:published_time'),
                ('name', 'publish-date'),
                ('name', 'pubdate'),
                ('name', 'publication-date'),
                ('name', 'date'),
                ('name', 'DC.date'),
                ('name', 'DC.Date'),
                ('itemprop', 'datePublished'),
                ('itemprop', 'datepublished'),
            ]
            
            for attr, value in meta_tags:
                meta = soup.find('meta', {attr: value})
                if meta and meta.get('content'):
                    date_str = meta.get('content')
                    # 尝试解析ISO格式日期
                    for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ']:
                        try:
                            dt = datetime.strptime(date_str[:19], fmt.replace('T', ' '))
                            return dt.date()
                        except ValueError:
                            continue
                    # 尝试解析其他格式
                    for fmt in ['%Y/%m/%d', '%m/%d/%Y', '%d/%m/%Y']:
                        try:
                            dt = datetime.strptime(date_str[:10], fmt)
                            return dt.date()
                        except ValueError:
                            continue
            
            # 2. 检查time标签
            time_tag = soup.find('time')
            if time_tag:
                datetime_attr = time_tag.get('datetime') or time_tag.get('pubdate')
                if datetime_attr:
                    for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ']:
                        try:
                            dt = datetime.strptime(datetime_attr[:19], fmt.replace('T', ' '))
                            return dt.date()
                        except ValueError:
                            continue
            
            # 3. 检查JSON-LD结构化数据
            json_ld_scripts = soup.find_all('script', type='application/ld+json')
            for script in json_ld_scripts:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict):
                        date_published = data.get('datePublished') or data.get('publishedTime')
                        if date_published:
                            for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ']:
                                try:
                                    dt = datetime.strptime(str(date_published)[:19], fmt.replace('T', ' '))
                                    return dt.date()
                                except ValueError:
                                    continue
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict):
                                date_published = item.get('datePublished') or item.get('publishedTime')
                                if date_published:
                                    for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ']:
                                        try:
                                            dt = datetime.strptime(str(date_published)[:19], fmt.replace('T', ' '))
                                            return dt.date()
                                        except ValueError:
                                            continue
                except Exception:
                    continue
            
            # 4. 从HTML文本内容中提取日期
            text_content = soup.get_text()
            date_from_text = extract_date_from_text(text_content)
            if date_from_text:
                return date_from_text
        else:
            # 看起来是纯文本，直接提取
            date_from_text = extract_date_from_text(content)
            if date_from_text:
                return date_from_text
        
    except Exception as e:
        logger.debug(f"Failed to extract date from HTML content {url}: {e}")
        # 如果HTML解析失败，尝试作为纯文本提取
        date_from_text = extract_date_from_text(content)
        if date_from_text:
            return date_from_text
    
    return None


def extract_date_from_extracted_data(extracted_data: dict) -> Optional[date]:
    """从extracted_data中提取日期"""
    if not extracted_data:
        return None
    
    # 检查顶层字段
    for key in ['publish_date', 'published_date', 'date', 'timestamp', 'created_time', 'effective_date']:
        if key in extracted_data:
            value = extracted_data[key]
            if isinstance(value, str):
                for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%Y-%m-%dT%H:%M:%S']:
                    try:
                        dt = datetime.strptime(value[:10], fmt)
                        return dt.date()
                    except ValueError:
                        continue
            elif isinstance(value, (int, float)):
                try:
                    dt = datetime.fromtimestamp(value)
                    return dt.date()
                except (ValueError, OSError):
                    pass
    
    # 检查policy或market子对象中的日期
    for sub_key in ['policy', 'market']:
        if sub_key in extracted_data and isinstance(extracted_data[sub_key], dict):
            sub_data = extracted_data[sub_key]
            for date_key in ['effective_date', 'publish_date', 'date', 'report_date', 'published_date']:
                if date_key in sub_data:
                    value = sub_data[date_key]
                    if isinstance(value, str) and value:
                        for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y']:
                            try:
                                dt = datetime.strptime(value[:10], fmt)
                                return dt.date()
                            except ValueError:
                                continue
                    if isinstance(value, (int, float)):
                        try:
                            dt = datetime.fromtimestamp(value)
                            return dt.date()
                        except (ValueError, OSError):
                            pass
    
    return None


def fetch_and_extract_date_from_url(url: str) -> tuple[Optional[date], Optional[str]]:
    """重新抓取页面并提取日期
    
    Returns:
        (提取到的日期, 错误信息)
    """
    try:
        html_content, _ = fetch_html(url)
        if html_content:
            date_from_html = extract_date_from_html_content(html_content, url)
            return date_from_html, None
    except Exception as e:
        return None, str(e)
    
    return None, None


def investigate_missing_publish_dates(limit: Optional[int] = None, try_fetch: bool = False) -> dict:
    """调查缺失发布日期的文档
    
    Args:
        limit: 限制处理的记录数量（用于测试）
        try_fetch: 是否尝试重新抓取页面
    
    Returns:
        包含统计信息的字典
    """
    stats = {
        "total_missing": 0,
        "by_source": defaultdict(int),
        "by_doc_type": defaultdict(int),
        "has_url": 0,
        "has_content": 0,
        "has_extracted_data": 0,
        "can_extract_from_url": 0,
        "can_extract_from_content": 0,
        "can_extract_from_extracted_data": 0,
        "can_extract_from_fetch": 0,
        "cannot_extract": 0,
        "examples": {
            "from_url": [],
            "from_content": [],
            "from_extracted_data": [],
            "from_fetch": [],
            "cannot_extract": []
        }
    }
    
    with SessionLocal() as session:
        # 查找所有 publish_date 为 NULL 的文档
        query = select(Document, Source).join(Source, Document.source_id == Source.id, isouter=True).where(
            Document.publish_date.is_(None)
        )
        
        if limit:
            query = query.limit(limit)
        
        results = session.execute(query).all()
        stats["total_missing"] = len(results)
        
        logger.info(f"找到 {len(results)} 个缺失发布时间的文档")
        
        for doc, source in results:
            source_name = source.name if source else "未知来源"
            stats["by_source"][source_name] += 1
            stats["by_doc_type"][doc.doc_type] += 1
            
            extraction_results = {
                "doc_id": doc.id,
                "title": doc.title[:80] if doc.title else "N/A",
                "source": source_name,
                "doc_type": doc.doc_type,
                "uri": doc.uri[:100] if doc.uri else None,
                "has_content": bool(doc.content),
                "has_extracted_data": bool(doc.extracted_data),
                "extracted_date": None,
                "extraction_method": None,
                "error": None
            }
            
            # 方法1: 从URL中提取日期
            if doc.uri:
                stats["has_url"] += 1
                date_from_url = extract_date_from_url(doc.uri)
                if date_from_url:
                    stats["can_extract_from_url"] += 1
                    extraction_results["extracted_date"] = str(date_from_url)
                    extraction_results["extraction_method"] = "URL"
                    if len(stats["examples"]["from_url"]) < 5:
                        stats["examples"]["from_url"].append(extraction_results.copy())
                    continue
            
            # 方法2: 从HTML内容中提取
            if doc.content:
                stats["has_content"] += 1
                date_from_content = extract_date_from_html_content(doc.content, doc.uri or "")
                if date_from_content:
                    stats["can_extract_from_content"] += 1
                    extraction_results["extracted_date"] = str(date_from_content)
                    extraction_results["extraction_method"] = "HTML内容"
                    if len(stats["examples"]["from_content"]) < 5:
                        stats["examples"]["from_content"].append(extraction_results.copy())
                    continue
            
            # 方法3: 从extracted_data中提取
            if doc.extracted_data:
                stats["has_extracted_data"] += 1
                date_from_extracted = extract_date_from_extracted_data(doc.extracted_data)
                if date_from_extracted:
                    stats["can_extract_from_extracted_data"] += 1
                    extraction_results["extracted_date"] = str(date_from_extracted)
                    extraction_results["extraction_method"] = "extracted_data"
                    if len(stats["examples"]["from_extracted_data"]) < 5:
                        stats["examples"]["from_extracted_data"].append(extraction_results.copy())
                    continue
            
            # 方法4: 重新抓取页面（如果启用）
            if try_fetch and doc.uri:
                date_from_fetch, error = fetch_and_extract_date_from_url(doc.uri)
                if date_from_fetch:
                    stats["can_extract_from_fetch"] += 1
                    extraction_results["extracted_date"] = str(date_from_fetch)
                    extraction_results["extraction_method"] = "重新抓取"
                    if len(stats["examples"]["from_fetch"]) < 5:
                        stats["examples"]["from_fetch"].append(extraction_results.copy())
                    continue
                elif error:
                    extraction_results["error"] = error
            
            # 无法提取
            stats["cannot_extract"] += 1
            if len(stats["examples"]["cannot_extract"]) < 5:
                stats["examples"]["cannot_extract"].append(extraction_results.copy())
    
    return stats


def print_report(stats: dict):
    """打印调查报告"""
    print("\n" + "=" * 80)
    print("缺失发布日期的文档调查报告")
    print("=" * 80)
    
    print(f"\n总计: {stats['total_missing']} 个文档缺少 publish_date")
    
    print("\n按来源统计:")
    for source, count in sorted(stats['by_source'].items(), key=lambda x: x[1], reverse=True):
        print(f"  {source}: {count}")
    
    print("\n按文档类型统计:")
    for doc_type, count in sorted(stats['by_doc_type'].items(), key=lambda x: x[1], reverse=True):
        print(f"  {doc_type}: {count}")
    
    print("\n数据可用性:")
    print(f"  有URL: {stats['has_url']}")
    print(f"  有content: {stats['has_content']}")
    print(f"  有extracted_data: {stats['has_extracted_data']}")
    
    print("\n可提取性分析:")
    print(f"  可从URL提取: {stats['can_extract_from_url']}")
    print(f"  可从content提取: {stats['can_extract_from_content']}")
    print(f"  可从extracted_data提取: {stats['can_extract_from_extracted_data']}")
    print(f"  可从重新抓取提取: {stats['can_extract_from_fetch']}")
    print(f"  无法提取: {stats['cannot_extract']}")
    
    total_extractable = (
        stats['can_extract_from_url'] +
        stats['can_extract_from_content'] +
        stats['can_extract_from_extracted_data'] +
        stats['can_extract_from_fetch']
    )
    if stats['total_missing'] > 0:
        extractable_rate = (total_extractable / stats['total_missing']) * 100
        print(f"\n可提取率: {extractable_rate:.1f}% ({total_extractable}/{stats['total_missing']})")
    
    # 打印示例
    print("\n" + "=" * 80)
    print("示例文档")
    print("=" * 80)
    
    for method, examples in stats['examples'].items():
        if examples:
            print(f"\n【可从{method}提取的示例】")
            for i, ex in enumerate(examples, 1):
                print(f"\n  示例 {i}:")
                print(f"    ID: {ex['doc_id']}")
                print(f"    标题: {ex['title']}")
                print(f"    来源: {ex['source']}")
                print(f"    类型: {ex['doc_type']}")
                print(f"    URL: {ex['uri']}")
                print(f"    提取方法: {ex['extraction_method']}")
                print(f"    提取到的日期: {ex['extracted_date']}")
                if ex.get('error'):
                    print(f"    错误: {ex['error']}")


if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    limit = None
    try_fetch = False
    
    for arg in sys.argv:
        if arg.startswith("--limit="):
            limit = int(arg.split("=")[1])
        elif arg == "--fetch" or arg == "-f":
            try_fetch = True
    
    print("开始调查缺失发布日期的文档...")
    if limit:
        print(f"限制处理数量: {limit}")
    if try_fetch:
        print("将尝试重新抓取页面（这可能会比较慢）")
    
    stats = investigate_missing_publish_dates(limit=limit, try_fetch=try_fetch)
    print_report(stats)
    
    print("\n" + "=" * 80)
    print("提示:")
    print("  - 使用 --limit=N 限制处理的文档数量")
    print("  - 使用 --fetch 或 -f 启用重新抓取页面（较慢但更全面）")
    print("  - 运行 fix_publish_dates.py 可以批量修复这些文档")
    print("=" * 80)

