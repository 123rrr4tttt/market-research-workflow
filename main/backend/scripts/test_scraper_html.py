#!/usr/bin/env python3
"""
直接测试网站HTML结构，查看能获取哪些信息
"""

import httpx
from selectolax.parser import HTMLParser
from datetime import datetime
import re


def fetch_html_direct(url: str):
    """直接获取HTML"""
    try:
        response = httpx.get(url, timeout=30, follow_redirects=True)
        response.raise_for_status()
        return response.text, response.url
    except Exception as e:
        raise RuntimeError(f"Failed to fetch {url}: {e}")


def test_ca_superlotto():
    """测试CA SuperLotto Plus页面"""
    print("\n" + "="*60)
    print("测试: California SuperLotto Plus")
    print("="*60)
    
    url = "https://www.calottery.com/en/draw-games/superlotto-plus"
    
    try:
        html, final_url = fetch_html_direct(url)
        parser = HTMLParser(html)
        
        print(f"✅ 成功获取HTML ({len(html)} 字符)")
        print(f"   最终URL: {final_url}\n")
        
        # 查找关键元素
        print("🔍 查找关键信息:")
        
        # 1. 开奖日期
        date_node = parser.css_first(".draw-cards--draw-date")
        if date_node:
            date_text = date_node.text(strip=True)
            print(f"  ✅ 找到开奖日期: {date_text}")
            try:
                if "/" in date_text:
                    parts = date_text.split("/", 1)
                    date_text = parts[1] if len(parts) > 1 else parts[0]
                date_text = date_text.replace("\xa0", " ").strip()
                parsed_date = datetime.strptime(date_text, "%b %d, %Y").date()
                print(f"     解析后: {parsed_date}")
            except Exception as e:
                print(f"     ⚠️  解析失败: {e}")
        else:
            print("  ❌ 未找到开奖日期 (.draw-cards--draw-date)")
        
        # 2. 开奖期号 - 尝试多种选择器
        draw_selectors = [
            ".draw-number",
            "[data-draw-number]",
            ".draw-cards--draw-number",
            ".draw-id",
            "[class*='draw'][class*='number']",
        ]
        found_draw_number = False
        for selector in draw_selectors:
            nodes = parser.css(selector)
            if nodes:
                for node in nodes[:3]:
                    text = node.text(strip=True)
                    if text and not found_draw_number:
                        print(f"  ✅ 找到可能的开奖期号 ({selector}): {text}")
                        found_draw_number = True
        if not found_draw_number:
            print("  ❌ 未找到开奖期号")
        
        # 3. 中奖号码
        number_selectors = [
            ".winning-number",
            ".ball-number",
            ".number-ball",
            "[class*='ball']",
            "[class*='number']",
        ]
        found_numbers = False
        for selector in number_selectors:
            nodes = parser.css(selector)
            if nodes:
                numbers = [n.text(strip=True) for n in nodes[:10] if n.text(strip=True).isdigit()]
                if numbers and not found_numbers:
                    print(f"  ✅ 找到中奖号码 ({selector}): {numbers[:10]}")
                    found_numbers = True
        if not found_numbers:
            print("  ❌ 未找到中奖号码")
        
        # 4. 奖池金额
        jackpot_selectors = [
            ".jackpot",
            ".jackpot-amount",
            "[data-jackpot]",
            "[class*='jackpot']",
        ]
        found_jackpot = False
        for selector in jackpot_selectors:
            nodes = parser.css(selector)
            if nodes:
                for node in nodes[:3]:
                    text = node.text(strip=True)
                    if "$" in text or "million" in text.lower() or "billion" in text.lower():
                        if not found_jackpot:
                            print(f"  ✅ 找到奖池金额 ({selector}): {text[:100]}")
                            found_jackpot = True
        if not found_jackpot:
            print("  ❌ 未找到奖池金额")
        
        # 5. 销售额
        sales_selectors = [
            ".sales",
            ".sales-volume",
            ".total-sales",
            "[data-sales]",
            "[class*='sales']",
        ]
        found_sales = False
        for selector in sales_selectors:
            nodes = parser.css(selector)
            if nodes:
                for node in nodes[:3]:
                    text = node.text(strip=True)
                    if "$" in text or any(c.isdigit() for c in text):
                        if not found_sales:
                            print(f"  ✅ 找到销售额 ({selector}): {text[:100]}")
                            found_sales = True
        if not found_sales:
            print("  ❌ 未找到销售额")
        
        # 6. 开奖详情表格
        table = parser.css_first("table.table-last-draw")
        if table:
            print(f"  ✅ 找到开奖详情表格 (table.table-last-draw)")
            rows = table.css("tbody tr")
            print(f"     包含 {len(rows)} 行数据")
            
            # 显示前3行
            for i, row in enumerate(rows[:3]):
                cells = [cell.text(strip=True) for cell in row.css("td")]
                print(f"     第{i+1}行: {cells}")
        else:
            print("  ❌ 未找到开奖详情表格 (table.table-last-draw)")
        
        # 7. 查找所有可能的数字字段
        print("\n🔢 页面中的关键数字:")
        all_text = parser.body.text()
        
        # 查找美元金额
        dollar_amounts = re.findall(r'\$[\d,]+(?:\.\d+)?\s*(?:million|billion|M|B)?', all_text, re.IGNORECASE)
        unique_amounts = list(set(dollar_amounts))[:10]
        if unique_amounts:
            print(f"  找到 {len(unique_amounts)} 个美元金额: {unique_amounts}")
        else:
            print("  未找到美元金额")
        
        # 查找日期
        dates = re.findall(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}\b', all_text)
        unique_dates = list(set(dates))[:5]
        if unique_dates:
            print(f"  找到 {len(unique_dates)} 个日期: {unique_dates}")
        
        # 8. 检查是否有历史数据链接
        history_links = parser.css('a[href*="history"], a[href*="past"], a[href*="archive"], a[href*="draw-history"]')
        if history_links:
            print(f"\n📚 找到 {len(history_links)} 个可能的历史数据链接:")
            for link in history_links[:5]:
                href = link.attributes.get("href", "")
                text = link.text(strip=True)
                if href:
                    print(f"  - {text[:50]}: {href[:80]}")
        else:
            print("\n❌ 未找到历史数据链接")
        
        # 9. 保存HTML片段用于分析
        print("\n💾 HTML结构分析:")
        if date_node:
            print(f"  开奖日期HTML片段: {date_node.html[:200]}")
        if table:
            print(f"  表格HTML片段: {table.html[:300]}")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


def test_ca_powerball():
    """测试CA Powerball页面"""
    print("\n" + "="*60)
    print("测试: California Powerball")
    print("="*60)
    
    url = "https://www.calottery.com/en/draw-games/powerball"
    
    try:
        html, final_url = fetch_html_direct(url)
        parser = HTMLParser(html)
        
        print(f"✅ 成功获取HTML ({len(html)} 字符)\n")
        
        # 检查与SuperLotto相同的结构
        date_node = parser.css_first(".draw-cards--draw-date")
        table = parser.css_first("table.table-last-draw")
        
        print(f"  开奖日期节点: {'✅ 存在' if date_node else '❌ 不存在'}")
        print(f"  详情表格: {'✅ 存在' if table else '❌ 不存在'}")
        
        if table:
            rows = table.css("tbody tr")
            print(f"  表格行数: {len(rows)}")
            if rows:
                first_row = rows[0]
                cells = [cell.text(strip=True) for cell in first_row.css("td")]
                print(f"  第一行数据: {cells}")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")


def test_tx_powerball():
    """测试TX Powerball页面"""
    print("\n" + "="*60)
    print("测试: Texas Powerball")
    print("="*60)
    
    url = "https://www.texaslottery.com/export/sites/lottery/Games/Powerball/index.html"
    
    try:
        html, final_url = fetch_html_direct(url)
        parser = HTMLParser(html)
        
        print(f"✅ 成功获取HTML ({len(html)} 字符)\n")
        
        # 查找历史记录表格
        table = parser.css_first("#PastResults table tbody")
        if table:
            rows = table.css("tr")
            print(f"  ✅ 找到历史记录表格 (#PastResults)，包含 {len(rows)} 行")
            
            # 显示前3行结构
            for i, row in enumerate(rows[:3]):
                cells = [cell.text(strip=True) for cell in row.css("td")]
                print(f"  第{i+1}行: {cells}")
                
                # 检查是否有详情链接
                link = row.css_first("a.detailsLink")
                if link:
                    href = link.attributes.get("href", "")
                    print(f"    详情链接: {href}")
        else:
            print("  ❌ 未找到历史记录表格 (#PastResults)")
            
            # 尝试其他选择器
            all_tables = parser.css("table")
            print(f"  页面共有 {len(all_tables)} 个表格")
            for i, tbl in enumerate(all_tables[:3]):
                thead = tbl.css_first("thead")
                if thead:
                    headers = [th.text(strip=True) for th in thead.css("th")]
                    print(f"  表格{i+1}列头: {headers}")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")


def main():
    """运行所有测试"""
    print("="*60)
    print("爬虫适配器HTML结构分析")
    print("="*60)
    
    test_ca_superlotto()
    test_ca_powerball()
    test_tx_powerball()
    
    print("\n" + "="*60)
    print("测试完成")
    print("="*60)


if __name__ == "__main__":
    main()
