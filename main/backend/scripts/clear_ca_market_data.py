#!/usr/bin/env python3
"""清空加州市场数据并重新摄取"""

import sys
import os
from pathlib import Path

# 添加项目根目录到路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# 设置环境变量（如果需要）
os.environ.setdefault("PYTHONPATH", str(backend_dir))

from sqlalchemy import text
from app.models.base import SessionLocal


def clear_ca_market_data():
    """清空加州市场数据"""
    print("正在清空加州市场数据...")
    
    with SessionLocal() as session:
        try:
            # 使用SQL直接删除，避免导入模型类导致的版本兼容问题
            result = session.execute(
                text("DELETE FROM market_stats WHERE state = 'CA'")
            )
            deleted_count = result.rowcount
            session.commit()
            print(f"✅ 已清空 {deleted_count} 条加州市场数据记录")
            return deleted_count
        except Exception as e:
            session.rollback()
            print(f"❌ 清空数据失败: {e}")
            import traceback
            traceback.print_exc()
            raise


def reingest_ca_market_data():
    """重新摄取加州市场数据"""
    print("\n开始重新摄取加州市场数据...")
    print("=" * 60)
    print("\n提示：请通过以下方式重新摄取数据：")
    print("  1. API调用: POST /api/v1/ingest/market")
    print("     请求体: {\"state\": \"CA\", \"async_mode\": false}")
    print("  2. 或者使用前端界面进行数据摄取")
    print("\n新的适配器配置将自动使用多数据源融合策略：")
    print("  - CA官方数据源（最新数据）")
    print("  - Powerball.com历史数据")
    print("  - MegaMillions.com历史数据")


def main():
    """主函数"""
    print("=" * 60)
    print("加州市场数据清理和重新摄取")
    print("=" * 60)
    
    # 1. 清空数据
    clear_ca_market_data()
    
    # 2. 重新摄取
    reingest_ca_market_data()
    
    print("\n" + "=" * 60)
    print("✅ 完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()

