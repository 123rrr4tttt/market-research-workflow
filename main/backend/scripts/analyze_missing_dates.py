"""分析无法提取日期的文档，打开链接查看实际内容"""
from __future__ import annotations

import sys
import os
from pathlib import Path

# 添加backend目录到Python路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))
os.environ.setdefault("PYTHONPATH", str(backend_dir))

import logging
import json
from datetime import datetime, date
from typing import Optional, List, Dict
from urllib.parse import urlparse

from sqlalchemy import select
from bs4 import BeautifulSoup

from app.models.base import SessionLocal
from app.models.entities import Document, Source
from app.services.ingest.adapters.http_utils import fetch_html

logger = logging.getLogger(__name__)


def analyze_url_structure(url: str) -> Dict:
    """分析URL的结构，尝试提取日期"""
    analysis = {
        "url": url,
        "domain": None,
        "has_date_in_url": False,
        "date_in_url": None,
        "url_pattern": None,
    }
    
    try:
        parsed = urlparse(url)
        analysis["domain"] = parsed.netloc
        
        # 检查URL路径中的日期
        path_parts = [p for p in parsed.path.split('/') if p]
        for i, part in enumerate(path_parts):
            if len(part) == 4 and part.isdigit():
                year = int(part)
                if 2000 <= year <= 2100:
                    if i + 2 < len(path_parts):
                        try:
                            month = int(path_parts[i + 1])
                            day = int(path_parts[i + 2])
                            if 1 <= month <= 12 and 1 <= day <= 31:
                                analysis["has_date_in_url"] = True
                                analysis["date_in_url"] = f"{year}-{month:02d}-{day:02d}"
                                analysis["url_pattern"] = f"/{year}/{month}/{day}/"
                                break
                        except (ValueError, IndexError):
                            pass
    except Exception as e:
        logger.debug(f"Failed to analyze URL {url}: {e}")
    
    return analysis


def fetch_and_analyze_page(url: str) -> Dict:
    """抓取页面并分析其结构"""
    analysis = {
        "url": url,
        "fetch_success": False,
        "html_size": 0,
        "has_meta_tags": False,
        "meta_dates": [],
        "has_time_tags": False,
        "time_dates": [],
        "has_json_ld": False,
        "json_ld_dates": [],
        "text_preview": "",
        "date_patterns_in_text": [],
        "recommendations": []
    }
    
    try:
        html_content, response = fetch_html(url)
        analysis["fetch_success"] = True
        analysis["html_size"] = len(html_content)
        
        soup = BeautifulSoup(html_content, "html.parser")
        
        # 1. 检查meta标签
        meta_tags = [
            ('property', 'article:published_time'),
            ('property', 'og:published_time'),
            ('name', 'publish-date'),
            ('name', 'pubdate'),
            ('name', 'publication-date'),
            ('name', 'date'),
            ('itemprop', 'datePublished'),
        ]
        
        for attr, value in meta_tags:
            meta = soup.find('meta', {attr: value})
            if meta and meta.get('content'):
                analysis["has_meta_tags"] = True
                analysis["meta_dates"].append({
                    "attr": attr,
                    "value": value,
                    "content": meta.get('content')
                })
        
        # 2. 检查time标签
        time_tags = soup.find_all('time')
        if time_tags:
            analysis["has_time_tags"] = True
            for time_tag in time_tags[:5]:
                datetime_attr = time_tag.get('datetime') or time_tag.get('pubdate')
                if datetime_attr:
                    analysis["time_dates"].append({
                        "datetime": datetime_attr,
                        "text": time_tag.get_text(strip=True)[:50]
                    })
        
        # 3. 检查JSON-LD
        json_ld_scripts = soup.find_all('script', type='application/ld+json')
        if json_ld_scripts:
            analysis["has_json_ld"] = True
            for script in json_ld_scripts[:3]:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict):
                        if 'datePublished' in data:
                            analysis["json_ld_dates"].append(data['datePublished'])
                        if 'publishedTime' in data:
                            analysis["json_ld_dates"].append(data['publishedTime'])
                except Exception:
                    pass
        
        # 4. 提取文本预览
        text_content = soup.get_text(separator=' ', strip=True)
        analysis["text_preview"] = text_content[:500]
        
        # 5. 查找文本中的日期模式
        import re
        date_patterns = [
            r'\d{4}-\d{1,2}-\d{1,2}',
            r'\d{1,2}/\d{1,2}/\d{4}',
            r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}',
        ]
        
        for pattern in date_patterns:
            matches = re.findall(pattern, text_content[:2000], re.IGNORECASE)
            if matches:
                analysis["date_patterns_in_text"].extend(matches[:3])
        
        # 6. 生成建议
        if analysis["has_meta_tags"]:
            analysis["recommendations"].append("可以从meta标签提取日期")
        if analysis["has_time_tags"]:
            analysis["recommendations"].append("可以从time标签提取日期")
        if analysis["has_json_ld"]:
            analysis["recommendations"].append("可以从JSON-LD提取日期")
        if analysis["date_patterns_in_text"]:
            analysis["recommendations"].append("可以从文本内容提取日期")
        
        if not analysis["recommendations"]:
            analysis["recommendations"].append("需要进一步分析或使用created_at作为备选")
    
    except Exception as e:
        analysis["error"] = str(e)
        logger.error(f"Failed to fetch {url}: {e}")
    
    return analysis


def analyze_missing_dates(limit: int = 10) -> List[Dict]:
    """分析无法提取日期的文档"""
    results = []
    
    with SessionLocal() as session:
        # 查找所有 publish_date 为 NULL 的文档
        query = select(Document, Source).join(
            Source, Document.source_id == Source.id, isouter=True
        ).where(
            Document.publish_date.is_(None)
        ).limit(limit)
        
        docs = session.execute(query).all()
        
        logger.info(f"分析 {len(docs)} 个无法提取日期的文档")
        
        for doc, source in docs:
            if not doc.uri:
                continue
            
            result = {
                "doc_id": doc.id,
                "title": doc.title[:80] if doc.title else "N/A",
                "source": source.name if source else "未知",
                "doc_type": doc.doc_type,
                "url_analysis": analyze_url_structure(doc.uri),
            }
            
            # 尝试抓取页面
            try:
                page_analysis = fetch_and_analyze_page(doc.uri)
                result["page_analysis"] = page_analysis
            except Exception as e:
                result["page_analysis"] = {"error": str(e)}
            
            results.append(result)
    
    return results


def print_analysis_report(results: List[Dict]):
    """打印分析报告"""
    print("\n" + "=" * 80)
    print("无法提取日期的文档深度分析报告")
    print("=" * 80)
    
    for i, result in enumerate(results, 1):
        print(f"\n【文档 {i}】")
        print(f"  ID: {result['doc_id']}")
        print(f"  标题: {result['title']}")
        print(f"  来源: {result['source']}")
        print(f"  类型: {result['doc_type']}")
        print(f"  URL: {result['url_analysis']['url']}")
        
        # URL分析
        if result['url_analysis']['has_date_in_url']:
            print(f"\n  ✓ URL中包含日期: {result['url_analysis']['date_in_url']}")
        else:
            print(f"\n  ✗ URL中未找到日期")
        
        # 页面分析
        page_analysis = result.get('page_analysis', {})
        if page_analysis.get('fetch_success'):
            print(f"\n  页面抓取: ✓ 成功 (HTML大小: {page_analysis['html_size']} 字符)")
            
            if page_analysis.get('has_meta_tags'):
                print(f"  ✓ 找到meta标签日期:")
                for meta in page_analysis['meta_dates'][:3]:
                    print(f"    - {meta['attr']}={meta['value']}: {meta['content'][:50]}")
            
            if page_analysis.get('has_time_tags'):
                print(f"  ✓ 找到time标签:")
                for time in page_analysis['time_dates'][:3]:
                    print(f"    - datetime: {time['datetime']}")
                    print(f"      text: {time['text']}")
            
            if page_analysis.get('has_json_ld'):
                print(f"  ✓ 找到JSON-LD日期:")
                for date_val in page_analysis['json_ld_dates'][:3]:
                    print(f"    - {date_val}")
            
            if page_analysis.get('date_patterns_in_text'):
                print(f"  ✓ 文本中找到日期模式:")
                for pattern in set(page_analysis['date_patterns_in_text'][:5]):
                    print(f"    - {pattern}")
            
            if page_analysis.get('recommendations'):
                print(f"\n  建议:")
                for rec in page_analysis['recommendations']:
                    print(f"    - {rec}")
            
            # 显示文本预览
            if page_analysis.get('text_preview'):
                print(f"\n  文本预览 (前200字符):")
                print(f"    {page_analysis['text_preview'][:200]}...")
        else:
            print(f"\n  页面抓取: ✗ 失败")
            if 'error' in page_analysis:
                print(f"    错误: {page_analysis['error']}")
        
        print("-" * 80)


if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    limit = 10
    if len(sys.argv) > 1:
        limit = int(sys.argv[1])
    
    print(f"开始分析无法提取日期的文档（限制: {limit}个）...")
    print("注意: 这将实际访问网页，可能需要一些时间...")
    
    results = analyze_missing_dates(limit=limit)
    print_analysis_report(results)
    
    # 保存结果到JSON文件
    output_file = Path(__file__).parent / "missing_dates_analysis.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"\n详细分析结果已保存到: {output_file}")

