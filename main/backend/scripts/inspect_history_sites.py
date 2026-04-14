#!/usr/bin/env python3
"""检查历史数据网站的HTML结构"""

import re
import requests
from selectolax.parser import HTMLParser
from urllib.parse import urljoin

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/127.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.8",
}


def fetch_html_direct(url):
    """直接获取HTML"""
    response = requests.get(url, headers=DEFAULT_HEADERS, timeout=30)
    response.raise_for_status()
    return response.text, response


def inspect_powerball_com():
    """检查 Powerball.com 的历史结果页面"""
    print("=" * 80)
    print("检查 Powerball.com 历史结果页面")
    print("=" * 80)
    
    url = "https://www.powerball.com/previous-results?gc=powerball"
    
    try:
        html, _ = fetch_html_direct(url)
        parser = HTMLParser(html)
        
        print(f"\n✅ 成功获取HTML ({len(html)} 字符)")
        
        # 查找所有链接
        print("\n查找所有链接:")
        all_links = parser.css("a[href]")
        print(f"  找到 {len(all_links)} 个链接")
        
        # 查找包含 draw-result 的链接
        draw_result_links = parser.css("a[href*='draw-result']")
        print(f"\n包含 'draw-result' 的链接: {len(draw_result_links)} 个")
        for i, link in enumerate(draw_result_links[:5], 1):
            href = link.attributes.get("href", "")
            text = link.text(strip=True)
            print(f"  {i}. {href[:80]} - {text[:50]}")
        
        # 查找包含日期的链接
        print("\n查找包含日期的链接:")
        date_links = []
        for link in all_links:
            href = link.attributes.get("href", "")
            if re.search(r'\d{4}[-/]\d{2}[-/]\d{2}', href):
                date_links.append((href, link.text(strip=True)))
        
        print(f"  找到 {len(date_links)} 个包含日期的链接")
        for i, (href, text) in enumerate(date_links[:5], 1):
            print(f"  {i}. {href[:80]} - {text[:50]}")
        
        # 检查详细结果页面
        if draw_result_links:
            href = draw_result_links[0].attributes.get("href", "")
            test_url = urljoin("https://www.powerball.com", href)
            print(f"\n检查详细结果页面: {test_url}")
            inspect_powerball_detail_page(test_url)
        else:
            print("\n⚠️ 未找到详细结果页面链接")
            
    except Exception as e:
        print(f"\n❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()


def inspect_powerball_detail_page(url):
    """检查 Powerball.com 详细结果页面"""
    try:
        html, _ = fetch_html_direct(url)
        parser = HTMLParser(html)
        
        print(f"\n✅ 成功获取详细页面HTML ({len(html)} 字符)")
        
        # 查找所有包含金额的元素
        print("\n查找金额相关信息:")
        text_content = parser.body.text() if parser.body else ""
        
        # 查找jackpot
        jackpot_patterns = [
            r'jackpot[:\s]*\$?([\d,]+(?:\.\d+)?)\s*(million|billion|M|B)?',
            r'\$([\d,]+(?:\.\d+)?)\s*(million|billion|M|B)?.*jackpot',
        ]
        
        print("\n尝试匹配Jackpot:")
        for pattern in jackpot_patterns:
            matches = list(re.finditer(pattern, text_content, re.IGNORECASE))
            if matches:
                for match in matches[:3]:
                    print(f"  匹配: {match.group(0)[:100]}")
        
        # 查找所有大金额
        print("\n查找所有大金额 ($XXX million/billion):")
        money_matches = list(re.finditer(r'\$([\d,]+(?:\.\d+)?)\s*(million|billion|M|B)', text_content, re.IGNORECASE))
        print(f"  找到 {len(money_matches)} 个金额")
        for i, match in enumerate(money_matches[:10], 1):
            context_start = max(0, match.start() - 30)
            context_end = min(len(text_content), match.end() + 30)
            context = text_content[context_start:context_end].replace('\n', ' ')
            print(f"  {i}. {match.group(0)} - 上下文: ...{context}...")
        
        # 查找可能的CSS选择器
        print("\n查找可能的CSS选择器:")
        selectors = [
            "[class*='jackpot']",
            "[class*='prize']",
            "[class*='amount']",
            "[class*='cash']",
            "[id*='jackpot']",
            "[id*='prize']",
            "[data-jackpot]",
            "[data-prize]",
        ]
        
        for selector in selectors:
            elements = parser.css(selector)
            if elements:
                print(f"  {selector}: 找到 {len(elements)} 个元素")
                for elem in elements[:3]:
                    text = elem.text(strip=True)
                    if text and len(text) < 150:
                        print(f"    - {text}")
        
        # 查找表格
        print("\n查找表格:")
        tables = parser.css("table")
        print(f"  找到 {len(tables)} 个表格")
        for i, table in enumerate(tables[:3], 1):
            rows = table.css("tr")
            print(f"  表格 {i}: {len(rows)} 行")
            if rows:
                first_row = rows[0]
                cells = [cell.text(strip=True) for cell in first_row.css("td, th")]
                print(f"    第一行: {cells[:5]}")
        
    except Exception as e:
        print(f"\n❌ 检查详细页面失败: {e}")
        import traceback
        traceback.print_exc()


def inspect_megamillions_com():
    """检查 MegaMillions.com 的历史数据页面"""
    print("\n" + "=" * 80)
    print("检查 MegaMillions.com 历史数据页面")
    print("=" * 80)
    
    url = "https://www.megamillions.com/Winning-Numbers/Previous-Drawings.aspx"
    
    try:
        html, _ = fetch_html_direct(url)
        parser = HTMLParser(html)
        
        print(f"\n✅ 成功获取HTML ({len(html)} 字符)")
        
        # 查找所有表格
        print("\n查找表格:")
        tables = parser.css("table")
        print(f"  找到 {len(tables)} 个表格")
        
        for i, table in enumerate(tables[:5], 1):
            print(f"\n  表格 {i}:")
            
            # 查找表头
            thead = table.css_first("thead")
            if thead:
                headers = [th.text(strip=True) for th in thead.css("th")]
                print(f"    表头: {headers}")
            
            # 查找前5行数据
            rows = table.css("tbody tr, tr")
            print(f"    行数: {len(rows)}")
            
            for j, row in enumerate(rows[:5], 1):
                cells = [cell.text(strip=True) for cell in row.css("td, th")]
                print(f"    第{j}行: {cells}")
                
                # 检查是否有链接
                links = row.css("a[href]")
                if links:
                    for link in links:
                        href = link.attributes.get("href", "")
                        print(f"      链接: {href[:80]}")
        
        # 查找包含金额的文本
        print("\n查找金额信息:")
        text_content = parser.body.text() if parser.body else ""
        money_matches = list(re.finditer(r'\$([\d,]+(?:\.\d+)?)\s*(million|billion|M|B)?', text_content, re.IGNORECASE))
        print(f"  找到 {len(money_matches)} 个金额")
        for i, match in enumerate(money_matches[:10], 1):
            print(f"  {i}. {match.group(0)}")
            
    except Exception as e:
        print(f"\n❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()


def inspect_us_powerball():
    """检查 USPowerballAdapter 使用的API"""
    print("\n" + "=" * 80)
    print("检查 Powerball.com Recent Results API")
    print("=" * 80)
    
    url = "https://www.powerball.com/api/v1/numbers/powerball/recent?_format=json"
    
    try:
        html, _ = fetch_html_direct(url)
        parser = HTMLParser(html)
        
        print(f"\n✅ 成功获取HTML ({len(html)} 字符)")
        
        # 检查返回的内容类型
        print(f"\n前500个字符:")
        print(html[:500])
        
        # 查找卡片
        cards = parser.css("a.card")
        print(f"\n找到 {len(cards)} 个卡片")
        
        if cards:
            card = cards[0]
            print(f"\n第一个卡片的内容:")
            print(f"  HTML: {str(card)[:300]}")
            print(f"  文本: {card.text(strip=True)[:200]}")
            
            # 查找金额
            text_content = card.text(strip=True)
            money_matches = list(re.finditer(r'\$([\d,]+(?:\.\d+)?)\s*(million|billion|M|B)?', text_content, re.IGNORECASE))
            if money_matches:
                print(f"\n  找到 {len(money_matches)} 个金额:")
                for match in money_matches:
                    print(f"    - {match.group(0)}")
            else:
                print("\n  ⚠️ 未找到金额信息")
        
    except Exception as e:
        print(f"\n❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    inspect_powerball_com()
    inspect_megamillions_com()
    inspect_us_powerball()

