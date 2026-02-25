"""深入分析文档，查找可能包含发布日期的所有位置"""
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
import re
from datetime import datetime, date
from typing import Optional, Dict, List
from collections import defaultdict

from sqlalchemy import select
from bs4 import BeautifulSoup

from app.models.base import SessionLocal
from app.models.entities import Document, Source

logger = logging.getLogger(__name__)


def analyze_document_structure(doc: Document, source: Source) -> Dict:
    """深入分析单个文档的结构，查找所有可能的日期来源"""
    analysis = {
        "doc_id": doc.id,
        "title": doc.title[:100] if doc.title else None,
        "source": source.name if source else "未知",
        "doc_type": doc.doc_type,
        "uri": doc.uri,
        "created_at": str(doc.created_at),
        "date_sources": {
            "url": analyze_url_for_dates(doc.uri),
            "content_html": analyze_html_content(doc.content),
            "content_text": analyze_text_content(doc.content),
            "extracted_data": analyze_extracted_data(doc.extracted_data),
        },
        "recommendations": []
    }
    
    # 生成建议
    if analysis["date_sources"]["url"]["found"]:
        analysis["recommendations"].append("可以从URL中提取日期")
    if analysis["date_sources"]["content_html"]["found"]:
        analysis["recommendations"].append("可以从HTML meta标签中提取日期")
    if analysis["date_sources"]["content_text"]["found"]:
        analysis["recommendations"].append("可以从文本内容中提取日期")
    if analysis["date_sources"]["extracted_data"]["found"]:
        analysis["recommendations"].append("可以从extracted_data中提取日期")
    
    if not any([
        analysis["date_sources"]["url"]["found"],
        analysis["date_sources"]["content_html"]["found"],
        analysis["date_sources"]["content_text"]["found"],
        analysis["date_sources"]["extracted_data"]["found"]
    ]):
        analysis["recommendations"].append("需要重新抓取页面或使用created_at作为备选")
    
    return analysis


def analyze_url_for_dates(url: Optional[str]) -> Dict:
    """分析URL中是否包含日期信息"""
    if not url:
        return {"found": False, "details": []}
    
    details = []
    
    # 检查URL路径中的日期模式
    date_patterns = [
        (r'/(\d{4})/(\d{1,2})/(\d{1,2})/', '路径中的日期'),
        (r'/(\d{4})-(\d{1,2})-(\d{1,2})/', '路径中的日期（连字符）'),
        (r'/(\d{4})/(\d{1,2})/', '路径中的年月'),
    ]
    
    for pattern, desc in date_patterns:
        match = re.search(pattern, url)
        if match:
            details.append({
                "type": desc,
                "pattern": pattern,
                "match": match.group(0),
                "location": "URL路径"
            })
    
    # 检查查询参数
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    date_params = ['date', 'publish_date', 'published', 'time', 'timestamp']
    for param in date_params:
        if param in query_params:
            details.append({
                "type": f"查询参数: {param}",
                "value": query_params[param][0],
                "location": "URL查询参数"
            })
    
    return {
        "found": len(details) > 0,
        "details": details
    }


def analyze_html_content(content: Optional[str]) -> Dict:
    """分析HTML内容中的日期信息"""
    if not content or '<' not in content:
        return {"found": False, "details": []}
    
    details = []
    
    try:
        soup = BeautifulSoup(content, "html.parser")
        
        # 检查meta标签
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
        ]
        
        for attr, value in meta_tags:
            meta = soup.find('meta', {attr: value})
            if meta and meta.get('content'):
                details.append({
                    "type": f"Meta标签: {attr}={value}",
                    "value": meta.get('content'),
                    "location": "HTML head"
                })
        
        # 检查time标签
        time_tags = soup.find_all('time')
        for time_tag in time_tags[:5]:  # 只检查前5个
            datetime_attr = time_tag.get('datetime') or time_tag.get('pubdate')
            if datetime_attr:
                details.append({
                    "type": "Time标签",
                    "value": datetime_attr,
                    "location": "HTML body",
                    "text": time_tag.get_text()[:50]
                })
        
        # 检查JSON-LD
        json_ld_scripts = soup.find_all('script', type='application/ld+json')
        for script in json_ld_scripts[:3]:  # 只检查前3个
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    if 'datePublished' in data:
                        details.append({
                            "type": "JSON-LD: datePublished",
                            "value": data['datePublished'],
                            "location": "JSON-LD结构化数据"
                        })
                    if 'publishedTime' in data:
                        details.append({
                            "type": "JSON-LD: publishedTime",
                            "value": data['publishedTime'],
                            "location": "JSON-LD结构化数据"
                        })
            except Exception:
                continue
        
        # 检查常见的日期显示元素
        date_selectors = [
            ('class', ['date', 'published', 'pub-date', 'publish-date', 'post-date']),
            ('id', ['date', 'published', 'pub-date', 'publish-date']),
        ]
        
        for attr, values in date_selectors:
            for value in values:
                elements = soup.find_all(attrs={attr: re.compile(value, re.I)})
                for elem in elements[:3]:  # 只检查前3个
                    text = elem.get_text(strip=True)
                    if text and re.search(r'\d{4}', text):
                        details.append({
                            "type": f"HTML元素: {attr}={value}",
                            "value": text[:100],
                            "location": "HTML body"
                        })
    
    except Exception as e:
        logger.debug(f"Failed to analyze HTML: {e}")
    
    return {
        "found": len(details) > 0,
        "details": details
    }


def analyze_text_content(content: Optional[str]) -> Dict:
    """分析纯文本内容中的日期信息"""
    if not content:
        return {"found": False, "details": []}
    
    details = []
    
    # 提取文本（如果是HTML，先提取文本）
    if '<' in content and '>' in content:
        try:
            soup = BeautifulSoup(content, "html.parser")
            text = soup.get_text()
        except Exception:
            text = content
    else:
        text = content
    
    # 查找日期模式（只检查前2000字符）
    text_sample = text[:2000]
    
    date_patterns = [
        (r'\d{4}-\d{1,2}-\d{1,2}', 'ISO日期格式'),
        (r'\d{4}/\d{1,2}/\d{1,2}', '斜杠日期格式'),
        (r'\d{1,2}/\d{1,2}/\d{4}', '美式日期格式'),
        (r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}', '英文日期格式'),
    ]
    
    for pattern, desc in date_patterns:
        matches = list(re.finditer(pattern, text_sample, re.IGNORECASE))
        if matches:
            for match in matches[:3]:  # 只取前3个
                context_start = max(0, match.start() - 30)
                context_end = min(len(text_sample), match.end() + 30)
                context = text_sample[context_start:context_end]
                
                details.append({
                    "type": desc,
                    "value": match.group(0),
                    "context": context,
                    "location": "文本内容"
                })
    
    return {
        "found": len(details) > 0,
        "details": details
    }


def analyze_extracted_data(extracted_data: Optional[Dict]) -> Dict:
    """分析extracted_data中的日期信息"""
    if not extracted_data or not isinstance(extracted_data, dict):
        return {"found": False, "details": []}
    
    details = []
    
    # 检查顶层字段
    date_fields = [
        'publish_date', 'published_date', 'date', 'timestamp',
        'created_time', 'effective_date', 'publication_date',
        'pub_date', 'pubDate', 'publishedAt', 'published_at'
    ]
    
    for field in date_fields:
        if field in extracted_data:
            value = extracted_data[field]
            details.append({
                "type": f"顶层字段: {field}",
                "value": str(value),
                "location": "extracted_data顶层"
            })
    
    # 检查嵌套对象
    nested_objects = ['policy', 'market', 'article', 'metadata']
    for obj_key in nested_objects:
        if obj_key in extracted_data and isinstance(extracted_data[obj_key], dict):
            obj_data = extracted_data[obj_key]
            for field in date_fields:
                if field in obj_data:
                    value = obj_data[field]
                    details.append({
                        "type": f"嵌套对象 {obj_key}.{field}",
                        "value": str(value),
                        "location": f"extracted_data.{obj_key}"
                    })
    
    # 显示所有字段（用于调试）
    all_keys = list(extracted_data.keys())
    
    return {
        "found": len(details) > 0,
        "details": details,
        "all_fields": all_keys[:20]  # 只显示前20个字段
    }


def analyze_sample_documents(limit: int = 20) -> Dict:
    """分析样本文档"""
    results = {
        "total_analyzed": 0,
        "by_source": defaultdict(list),
        "by_doc_type": defaultdict(list),
        "date_source_statistics": {
            "url": 0,
            "content_html": 0,
            "content_text": 0,
            "extracted_data": 0,
            "none": 0
        },
        "detailed_analyses": []
    }
    
    with SessionLocal() as session:
        query = select(Document, Source).join(
            Source, Document.source_id == Source.id, isouter=True
        ).where(
            Document.publish_date.is_(None)
        ).limit(limit)
        
        results_list = session.execute(query).all()
        results["total_analyzed"] = len(results_list)
        
        for doc, source in results_list:
            analysis = analyze_document_structure(doc, source)
            results["detailed_analyses"].append(analysis)
            
            source_name = source.name if source else "未知"
            results["by_source"][source_name].append(analysis)
            results["by_doc_type"][doc.doc_type].append(analysis)
            
            # 统计日期来源
            has_date = False
            if analysis["date_sources"]["url"]["found"]:
                results["date_source_statistics"]["url"] += 1
                has_date = True
            if analysis["date_sources"]["content_html"]["found"]:
                results["date_source_statistics"]["content_html"] += 1
                has_date = True
            if analysis["date_sources"]["content_text"]["found"]:
                results["date_source_statistics"]["content_text"] += 1
                has_date = True
            if analysis["date_sources"]["extracted_data"]["found"]:
                results["date_source_statistics"]["extracted_data"] += 1
                has_date = True
            
            if not has_date:
                results["date_source_statistics"]["none"] += 1
    
    return results


def print_analysis_report(results: Dict):
    """打印分析报告"""
    print("\n" + "=" * 80)
    print("文档发布日期来源深度分析报告")
    print("=" * 80)
    
    print(f"\n分析样本数: {results['total_analyzed']} 个文档")
    
    print("\n按来源统计:")
    for source, analyses in sorted(results['by_source'].items(), key=lambda x: len(x[1]), reverse=True):
        print(f"  {source}: {len(analyses)} 个文档")
    
    print("\n按文档类型统计:")
    for doc_type, analyses in sorted(results['by_doc_type'].items(), key=lambda x: len(x[1]), reverse=True):
        print(f"  {doc_type}: {len(analyses)} 个文档")
    
    print("\n日期来源统计:")
    stats = results['date_source_statistics']
    print(f"  可从URL提取: {stats['url']}")
    print(f"  可从HTML meta标签提取: {stats['content_html']}")
    print(f"  可从文本内容提取: {stats['content_text']}")
    print(f"  可从extracted_data提取: {stats['extracted_data']}")
    print(f"  无法找到日期来源: {stats['none']}")
    
    # 详细分析示例
    print("\n" + "=" * 80)
    print("详细分析示例（前5个文档）")
    print("=" * 80)
    
    for i, analysis in enumerate(results['detailed_analyses'][:5], 1):
        print(f"\n【文档 {i}】")
        print(f"  ID: {analysis['doc_id']}")
        print(f"  标题: {analysis['title']}")
        print(f"  来源: {analysis['source']}")
        print(f"  类型: {analysis['doc_type']}")
        print(f"  URL: {analysis['uri'][:80] if analysis['uri'] else 'N/A'}...")
        
        print(f"\n  日期来源分析:")
        for source_type, source_data in analysis['date_sources'].items():
            if source_data['found']:
                print(f"    ✓ {source_type}:")
                for detail in source_data['details'][:3]:  # 只显示前3个
                    print(f"      - {detail.get('type', 'N/A')}: {detail.get('value', 'N/A')[:60]}")
            else:
                print(f"    ✗ {source_type}: 未找到")
        
        if analysis['recommendations']:
            print(f"\n  建议:")
            for rec in analysis['recommendations']:
                print(f"    - {rec}")


if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    limit = 20
    if len(sys.argv) > 1:
        limit = int(sys.argv[1])
    
    print("开始深度分析文档结构...")
    results = analyze_sample_documents(limit=limit)
    print_analysis_report(results)
    
    # 保存详细结果到JSON文件
    output_file = Path(__file__).parent / "date_source_analysis.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"\n详细分析结果已保存到: {output_file}")

