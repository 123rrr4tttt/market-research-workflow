#!/usr/bin/env python3
"""
测试现有爬虫适配器能获取哪些信息
"""

import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services.ingest.adapters.market_ca_lottery import CaliforniaLotteryMarketAdapter
from app.services.ingest.adapters.market_ca_powerball import CaliforniaPowerballAdapter
from app.services.ingest.adapters.market_ca_mega import CaliforniaMegaMillionsAdapter
from app.services.ingest.adapters.market_tx_lottery import TexasLotteryMarketAdapter
from app.services.ingest.adapters.us_powerball import USPowerballAdapter
import json


def test_adapter(adapter_class, name: str):
    """测试适配器并显示获取的信息"""
    print(f"\n{'='*60}")
    print(f"测试适配器: {name}")
    print(f"{'='*60}")
    
    try:
        adapter = adapter_class("CA" if "CA" in name or "US" in name else "TX")
        records = list(adapter.fetch_records())
        
        print(f"✅ 成功获取 {len(records)} 条记录\n")
        
        if not records:
            print("⚠️  未获取到任何记录")
            return
        
        # 显示第一条记录的详细信息
        record = records[0]
        print("📊 第一条记录详情:")
        print(f"  - date: {record.date}")
        print(f"  - game: {record.game}")
        print(f"  - state: {record.state}")
        print(f"  - sales_volume: {record.sales_volume}")
        print(f"  - revenue: {record.revenue}")
        print(f"  - jackpot: {record.jackpot}")
        print(f"  - ticket_price: {record.ticket_price}")
        print(f"  - draw_number: {record.draw_number}")
        print(f"  - source_name: {record.source_name}")
        print(f"  - uri: {record.uri}")
        
        if record.extra:
            print(f"  - extra: {json.dumps(record.extra, indent=4, default=str)}")
        
        # 统计字段完整度
        fields = {
            'date': record.date is not None,
            'game': record.game is not None,
            'sales_volume': record.sales_volume is not None,
            'revenue': record.revenue is not None,
            'jackpot': record.jackpot is not None,
            'ticket_price': record.ticket_price is not None,
            'draw_number': record.draw_number is not None,
        }
        
        filled = sum(fields.values())
        total = len(fields)
        completeness = (filled / total) * 100
        
        print(f"\n📈 字段完整度: {filled}/{total} ({completeness:.1f}%)")
        print(f"   缺失字段: {[k for k, v in fields.items() if not v]}")
        
        # 显示所有记录的日期范围
        if len(records) > 1:
            dates = [r.date for r in records if r.date]
            if dates:
                print(f"\n📅 日期范围: {min(dates)} 到 {max(dates)}")
                print(f"   共 {len(dates)} 条历史记录")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


def main():
    """测试所有爬虫适配器"""
    print("="*60)
    print("爬虫适配器信息收集能力测试")
    print("="*60)
    
    adapters = [
        (CaliforniaLotteryMarketAdapter, "CaliforniaLotteryMarketAdapter (SuperLotto Plus)"),
        (CaliforniaPowerballAdapter, "CaliforniaPowerballAdapter"),
        (CaliforniaMegaMillionsAdapter, "CaliforniaMegaMillionsAdapter"),
        (TexasLotteryMarketAdapter, "TexasLotteryMarketAdapter"),
        (USPowerballAdapter, "USPowerballAdapter"),
    ]
    
    results = {}
    for adapter_class, name in adapters:
        try:
            test_adapter(adapter_class, name)
            results[name] = "✅ 成功"
        except Exception as e:
            results[name] = f"❌ 失败: {str(e)}"
    
    # 总结
    print(f"\n{'='*60}")
    print("测试总结")
    print(f"{'='*60}")
    for name, status in results.items():
        print(f"{name}: {status}")


if __name__ == "__main__":
    main()

