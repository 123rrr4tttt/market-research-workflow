#!/usr/bin/env python3
"""测试历史数据适配器的提取逻辑"""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.services.ingest.adapters.http_utils import fetch_html, make_html_parser
from selectolax.parser import HTMLParser
import re


def test_powerball_com():
    """测试Powerball.com页面"""
    print("=" * 80)
    print("测试 Powerball.com 详细结果页面")
    print("=" * 80)
    
    # 测试一个示例URL
    test_url = "https://www.powerball.com/draw-result?gc=powerball&date=2025-11-01"
    
    try:
        html, _ = fetch_html(test_url)
        parser = make_html_parser(html)
        
        print(f"\n✅ 成功获取HTML ({len(html)} 字符)")
        
        # 查找所有包含金额的元素
        print("\n查找金额相关文本：")
        text_content = parser.body.text() if parser.body else ""
        
        # 查找jackpot相关
        jackpot_patterns = [
            r'jackpot[:\s]*\$?([\d,]+(?:\.\d+)?)\s*(million|billion|M|B)?',
            r'estimated jackpot[:\s]*\$?([\d,]+(?:\.\d+)?)\s*(million|billion|M|B)?',
            r'\$([\d,]+(?:\.\d+)?)\s*(million|billion|M|B)?.*jackpot',
        ]
        
        print("\n尝试提取Jackpot:")
        for pattern in jackpot_patterns:
            matches = re.finditer(pattern, text_content, re.IGNORECASE)
            for match in matches:
                print(f"  匹配: {match.group(0)}")
        
        # 查找现金价值
        cash_patterns = [
            r'cash value[:\s]*\$?([\d,]+(?:\.\d+)?)\s*(million|billion|M|B)?',
            r'cash option[:\s]*\$?([\d,]+(?:\.\d+)?)\s*(million|billion|M|B)?',
        ]
        
        print("\n尝试提取Cash Value:")
        for pattern in cash_patterns:
            matches = re.finditer(pattern, text_content, re.IGNORECASE)
            for match in matches:
                print(f"  匹配: {match.group(0)}")
        
        # 查找包含数字和million/billion的元素
        print("\n查找所有包含million/billion的文本:")
        money_matches = re.finditer(r'\$?([\d,]+(?:\.\d+)?)\s*(million|billion|M|B)', text_content, re.IGNORECASE)
        count = 0
        for match in money_matches:
            if count < 10:  # 只显示前10个
                print(f"  {match.group(0)}")
                count += 1
        
        # 查找可能的CSS选择器
        print("\n查找可能的CSS选择器:")
        potential_selectors = [
            "[class*='jackpot']",
            "[class*='prize']",
            "[class*='amount']",
            "[class*='cash']",
            "[id*='jackpot']",
            "[id*='prize']",
        ]
        
        for selector in potential_selectors:
            elements = parser.css(selector)
            if elements:
                print(f"  {selector}: 找到 {len(elements)} 个元素")
                for elem in elements[:3]:
                    text = elem.text(strip=True)
                    if text and len(text) < 100:
                        print(f"    - {text[:80]}")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


def test_megamillions_com():
    """测试MegaMillions.com页面"""
    print("\n" + "=" * 80)
    print("测试 MegaMillions.com 历史数据页面")
    print("=" * 80)
    
    test_url = "https://www.megamillions.com/Winning-Numbers/Previous-Drawings.aspx"
    
    try:
        html, _ = fetch_html(test_url)
        parser = make_html_parser(html)
        
        print(f"\n✅ 成功获取HTML ({len(html)} 字符)")
        
        # 查找所有表格
        tables = parser.css("table")
        print(f"\n找到 {len(tables)} 个表格")
        
        for i, table in enumerate(tables[:3]):
            print(f"\n表格 {i+1}:")
            
            # 查找表头
            thead = table.css_first("thead")
            if thead:
                headers = [th.text(strip=True) for th in thead.css("th")]
                print(f"  表头: {headers}")
            
            # 查找前3行数据
            rows = table.css("tbody tr, tr")
            print(f"  行数: {len(rows)}")
            
            for j, row in enumerate(rows[:3]):
                cells = [cell.text(strip=True) for cell in row.css("td, th")]
                print(f"  第{j+1}行: {cells}")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_powerball_com()
    test_megamillions_com()

