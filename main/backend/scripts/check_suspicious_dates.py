"""检测和修复可疑的发布日期

这个脚本会：
1. 查找所有 publish_date 与 created_at 日期相近的文档（可能是错误地将创建日期当作了发布日期）
2. 特别关注 publish_date 为 2025-11-16 的数据
3. 重新尝试从 URL、extracted_data 等来源提取正确的发布日期
4. 如果无法提取，将 publish_date 设置为 NULL
"""
from __future__ import annotations

import logging
import re
import json
from datetime import datetime, date, timedelta
from urllib.parse import urlparse, parse_qs
from typing import Optional

from sqlalchemy import select, update, and_, or_
from sqlalchemy.orm import Session
from bs4 import BeautifulSoup

from app.models.base import SessionLocal
from app.models.entities import Document

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


def extract_date_from_html_content(content: str, url: str) -> Optional[date]:
    """从HTML内容中提取发布时间"""
    if not content:
        return None
    
    try:
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
        
    except Exception as e:
        logger.debug(f"Failed to extract date from HTML content {url}: {e}")
    
    return None


def extract_date_from_extracted_data(extracted_data: dict) -> Optional[date]:
    """从extracted_data中提取日期"""
    if not extracted_data:
        return None
    
    try:
        # 检查是否有时间相关的字段
        for key in ['publish_date', 'published_date', 'date', 'timestamp', 'effective_date']:
            if key in extracted_data:
                value = extracted_data[key]
                if isinstance(value, str):
                    # 尝试解析日期字符串
                    for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%Y-%m-%dT%H:%M:%S']:
                        try:
                            dt = datetime.strptime(value[:10], fmt)
                            return dt.date()
                        except ValueError:
                            continue
                elif isinstance(value, (int, float)):
                    # 可能是Unix时间戳
                    try:
                        dt = datetime.fromtimestamp(value)
                        return dt.date()
                    except (ValueError, OSError):
                        pass
        
        # 检查policy或market子对象中的日期
        for sub_key in ['policy', 'market']:
            if sub_key in extracted_data and isinstance(extracted_data[sub_key], dict):
                sub_data = extracted_data[sub_key]
                for date_key in ['effective_date', 'publish_date', 'date']:
                    if date_key in sub_data:
                        value = sub_data[date_key]
                        if isinstance(value, str):
                            for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y']:
                                try:
                                    dt = datetime.strptime(value[:10], fmt)
                                    return dt.date()
                                except ValueError:
                                    continue
                        if value:
                            break
                if value:
                    break
    except Exception as e:
        logger.debug(f"Failed to extract date from extracted_data: {e}")
    
    return None


def check_and_fix_suspicious_dates(
    target_date: Optional[date] = None,
    days_threshold: int = 3,
    dry_run: bool = True,
    limit: Optional[int] = None
) -> dict:
    """检测和修复可疑的发布日期
    
    Args:
        target_date: 如果指定，只检查这个特定日期的数据（例如 2025-11-16）
        days_threshold: 发布日期和创建日期相差多少天以内认为是可疑的（默认3天）
        dry_run: 如果为True，只显示将要更新的记录，不实际更新
        limit: 限制处理的记录数量（用于测试）
    
    Returns:
        包含统计信息的字典
    """
    stats = {
        "total_checked": 0,
        "suspicious_found": 0,
        "fixed": 0,
        "set_to_null": 0,
        "failed": 0,
        "skipped": 0,
    }
    
    with SessionLocal() as session:
        # 构建查询条件
        conditions = []
        
        if target_date:
            # 如果指定了目标日期，只查找这个日期的数据
            conditions.append(Document.publish_date == target_date)
        else:
            # 否则查找所有有发布日期的数据
            conditions.append(Document.publish_date.isnot(None))
        
        query = select(Document).where(and_(*conditions))
        
        if limit:
            query = query.limit(limit)
        
        docs = session.execute(query).scalars().all()
        stats["total_checked"] = len(docs)
        
        logger.info(f"找到 {len(docs)} 个文档需要检查")
        
        for doc in docs:
            try:
                # 检查发布日期和创建日期是否相近
                if not doc.publish_date or not doc.created_at:
                    continue
                
                publish_date = doc.publish_date
                created_date = doc.created_at.date()
                
                # 计算日期差
                date_diff = abs((publish_date - created_date).days)
                
                # 如果日期相近，认为是可疑的
                if date_diff <= days_threshold:
                    stats["suspicious_found"] += 1
                    
                    logger.info(
                        f"发现可疑文档 ID={doc.id}, "
                        f"publish_date={publish_date}, "
                        f"created_at={created_date}, "
                        f"日期差={date_diff}天, "
                        f"URL={doc.uri}"
                    )
                    
                    # 尝试重新提取正确的发布日期
                    new_date = None
                    
                    # 方法1: 从URL中提取日期
                    if doc.uri:
                        new_date = extract_date_from_url(doc.uri)
                    
                    # 方法2: 从HTML内容中提取
                    if not new_date and doc.content:
                        new_date = extract_date_from_html_content(doc.content, doc.uri or "")
                    
                    # 方法3: 从extracted_data中提取
                    if not new_date and doc.extracted_data:
                        new_date = extract_date_from_extracted_data(doc.extracted_data)
                    
                    # 如果提取到了新日期，且新日期与创建日期相差较大，则使用新日期
                    if new_date:
                        new_date_diff = abs((new_date - created_date).days)
                        # 如果新日期与创建日期相差超过阈值，说明可能是正确的发布日期
                        if new_date_diff > days_threshold:
                            if dry_run:
                                logger.info(
                                    f"  将更新为: {new_date} "
                                    f"(与创建日期相差 {new_date_diff} 天)"
                                )
                            else:
                                session.execute(
                                    update(Document)
                                    .where(Document.id == doc.id)
                                    .values(publish_date=new_date)
                                )
                                logger.info(
                                    f"已更新文档 {doc.id} 的发布时间: "
                                    f"{publish_date} -> {new_date}"
                                )
                            stats["fixed"] += 1
                        else:
                            # 新日期也与创建日期相近，可能是错误的，设置为NULL
                            if dry_run:
                                logger.info(
                                    f"  提取的日期 {new_date} 也与创建日期相近，将设置为 NULL"
                                )
                            else:
                                session.execute(
                                    update(Document)
                                    .where(Document.id == doc.id)
                                    .values(publish_date=None)
                                )
                                logger.info(f"已将文档 {doc.id} 的发布时间设置为 NULL")
                            stats["set_to_null"] += 1
                    else:
                        # 无法提取新日期，设置为NULL
                        if dry_run:
                            logger.info(f"  无法提取新日期，将设置为 NULL")
                        else:
                            session.execute(
                                update(Document)
                                .where(Document.id == doc.id)
                                .values(publish_date=None)
                            )
                            logger.info(f"已将文档 {doc.id} 的发布时间设置为 NULL")
                        stats["set_to_null"] += 1
                else:
                    stats["skipped"] += 1
                    
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
    target_date_str = None
    days_threshold = 3
    limit = None
    
    for arg in sys.argv:
        if arg.startswith("--target-date="):
            target_date_str = arg.split("=")[1]
        elif arg.startswith("--days-threshold="):
            days_threshold = int(arg.split("=")[1])
        elif arg.startswith("--limit="):
            limit = int(arg.split("=")[1])
    
    # 解析目标日期
    target_date = None
    if target_date_str:
        try:
            target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        except ValueError:
            logger.error(f"无效的日期格式: {target_date_str}，请使用 YYYY-MM-DD 格式")
            sys.exit(1)
    
    if dry_run:
        print("=" * 60)
        print("DRY RUN 模式 - 不会实际更新数据库")
        print("=" * 60)
    
    if target_date:
        print(f"\n检查目标日期: {target_date}")
    print(f"日期差阈值: {days_threshold} 天")
    
    stats = check_and_fix_suspicious_dates(
        target_date=target_date,
        days_threshold=days_threshold,
        dry_run=dry_run,
        limit=limit
    )
    
    print("\n" + "=" * 60)
    print("统计信息:")
    print(f"  检查的文档数: {stats['total_checked']}")
    print(f"  发现可疑文档数: {stats['suspicious_found']}")
    print(f"  修复的文档数: {stats['fixed']}")
    print(f"  设置为NULL的文档数: {stats['set_to_null']}")
    print(f"  跳过的文档数: {stats['skipped']}")
    print(f"  失败的文档数: {stats['failed']}")
    print("=" * 60)
    
    if dry_run and (stats['fixed'] > 0 or stats['set_to_null'] > 0):
        print("\n提示: 运行时不加 --dry-run 参数将实际更新数据库")

