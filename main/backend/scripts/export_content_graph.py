#!/usr/bin/env python3
"""导出社交平台内容图谱"""
import sys
import os
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
from sqlalchemy import select, and_, or_

from app.models.base import SessionLocal
from app.models.entities import Document
from app.services.graph.adapters import normalize_document
from app.services.graph.builder import build_graph, build_topic_subgraph
from app.services.graph.exporter import export_to_json_file, validate_graph

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def export_content_graph(
    output_path: str,
    *,
    days: Optional[int] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    topic: Optional[str] = None,
    state: Optional[str] = None,
    platform: Optional[str] = None,
    limit: Optional[int] = None,
    window: int = 0,
    use_tfidf: bool = True,
    tau: Optional[int] = None,
    validate: bool = True,
) -> dict:
    """
    导出内容图谱
    
    Args:
        output_path: 输出JSON文件路径
        days: 最近N天的数据（与since/until互斥）
        since: 开始时间
        until: 结束时间
        topic: 主题过滤（导出该主题的子图）
        state: 州过滤
        platform: 平台过滤（如"reddit"）
        limit: 限制处理的文档数量
        window: 共现窗口大小（0=整帖共现）
        use_tfidf: 是否使用TF-IDF
        tau: 时间衰减参数（天数）
        validate: 是否进行校验
    
    Returns:
        包含统计信息的字典
    """
    with SessionLocal() as session:
        # 构建查询条件
        conditions = [
            Document.doc_type == "social_sentiment",
            Document.extracted_data.isnot(None)
        ]
        
        # 时间过滤
        if days:
            cutoff_date = datetime.now() - timedelta(days=days)
            conditions.append(Document.created_at >= cutoff_date)
        elif since:
            conditions.append(Document.created_at >= since)
        if until:
            conditions.append(Document.created_at <= until)
        
        # 平台过滤
        if platform:
            # 需要在查询后过滤，因为extracted_data是JSONB
            pass
        
        # 州过滤
        if state:
            conditions.append(Document.state == state)
        
        # 执行查询
        query = select(Document).where(and_(*conditions))
        if limit:
            query = query.limit(limit)
        
        documents = session.execute(query).scalars().all()
        logger.info(f"查询到 {len(documents)} 个文档")
        
        # 规范化文档
        normalized_posts = []
        skipped = 0
        
        for doc in documents:
            # 平台过滤（在规范化时检查）
            if platform:
                if not doc.extracted_data or doc.extracted_data.get("platform", "").lower() != platform.lower():
                    skipped += 1
                    continue
            
            normalized = normalize_document(doc)
            if normalized:
                normalized_posts.append(normalized)
            else:
                skipped += 1
        
        logger.info(f"规范化成功: {len(normalized_posts)}, 跳过: {skipped}")
        
        if not normalized_posts:
            logger.warning("没有可用的文档，无法构建图谱")
            return {
                "success": False,
                "message": "没有可用的文档",
                "total_documents": len(documents),
                "normalized_posts": 0,
                "skipped": skipped,
            }
        
        # 构建图谱
        logger.info("开始构建图谱...")
        graph = build_graph(
            normalized_posts,
            window=window,
            use_tfidf=use_tfidf,
            tau=tau
        )
        
        # 如果指定了主题，构建子图
        if topic:
            logger.info(f"构建主题子图: {topic}")
            if since and until:
                time_window = (since, until)
            else:
                time_window = None
            graph = build_topic_subgraph(graph, topic, time_window=time_window)
        
        # 导出
        logger.info(f"导出图谱到: {output_path}")
        validation_result = export_to_json_file(graph, output_path, validate=validate)
        
        return {
            "success": True,
            "output_path": output_path,
            "total_documents": len(documents),
            "normalized_posts": len(normalized_posts),
            "skipped": skipped,
            "nodes": len(graph.nodes),
            "edges": len(graph.edges),
            "validation": validation_result if validate else None,
        }


def main():
    """CLI入口"""
    parser = argparse.ArgumentParser(description="导出社交平台内容图谱")
    
    parser.add_argument(
        "-o", "--output",
        required=True,
        help="输出JSON文件路径"
    )
    
    # 时间过滤
    time_group = parser.add_mutually_exclusive_group()
    time_group.add_argument(
        "--days",
        type=int,
        help="最近N天的数据"
    )
    time_group.add_argument(
        "--since",
        type=str,
        help="开始时间 (ISO格式，如: 2025-01-01T00:00:00)"
    )
    parser.add_argument(
        "--until",
        type=str,
        help="结束时间 (ISO格式)"
    )
    
    # 过滤选项
    parser.add_argument(
        "--topic",
        type=str,
        help="主题过滤（导出该主题的子图）"
    )
    parser.add_argument(
        "--state",
        type=str,
        help="州过滤（如: CA）"
    )
    parser.add_argument(
        "--platform",
        type=str,
        help="平台过滤（如: reddit）"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="限制处理的文档数量"
    )
    
    # 构图参数
    parser.add_argument(
        "--window",
        type=int,
        default=0,
        help="共现窗口大小（0=整帖共现，默认: 0）"
    )
    parser.add_argument(
        "--no-tfidf",
        action="store_true",
        help="不使用TF-IDF计算权重"
    )
    parser.add_argument(
        "--tau",
        type=int,
        help="时间衰减参数（天数）"
    )
    
    # 其他选项
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="不进行校验"
    )
    
    args = parser.parse_args()
    
    # 解析时间参数
    since = None
    if args.since:
        try:
            since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
        except ValueError:
            logger.error(f"无效的开始时间格式: {args.since}")
            sys.exit(1)
    
    until = None
    if args.until:
        try:
            until = datetime.fromisoformat(args.until.replace("Z", "+00:00"))
        except ValueError:
            logger.error(f"无效的结束时间格式: {args.until}")
            sys.exit(1)
    
    # 执行导出
    try:
        result = export_content_graph(
            output_path=args.output,
            days=args.days,
            since=since,
            until=until,
            topic=args.topic,
            state=args.state,
            platform=args.platform,
            limit=args.limit,
            window=args.window,
            use_tfidf=not args.no_tfidf,
            tau=args.tau,
            validate=not args.no_validate,
        )
        
        if result["success"]:
            logger.info("=" * 60)
            logger.info("导出成功！")
            logger.info(f"输出文件: {result['output_path']}")
            logger.info(f"文档总数: {result['total_documents']}")
            logger.info(f"规范化成功: {result['normalized_posts']}")
            logger.info(f"跳过: {result['skipped']}")
            logger.info(f"节点数: {result['nodes']}")
            logger.info(f"边数: {result['edges']}")
            
            if result.get("validation"):
                validation = result["validation"]
                logger.info(f"校验结果: {'通过' if validation['valid'] else '失败'}")
                if validation.get("statistics"):
                    stats = validation["statistics"]
                    logger.info(f"节点类型分布: {stats.get('node_types', {})}")
                    logger.info(f"边类型分布: {stats.get('edge_types', {})}")
        else:
            logger.error(f"导出失败: {result.get('message', '未知错误')}")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"导出过程中发生错误: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

