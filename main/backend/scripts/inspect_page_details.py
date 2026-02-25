#!/usr/bin/env python3
"""
检查页面详细信息，查找隐藏的数据和结构
"""

import httpx
from selectolax.parser import HTMLParser
import re
import json


def inspect_ca_page(url: str, name: str):
    """详细检查CA页面"""
    print("\n" + "="*70)
    print(f"详细检查: {name}")
    print(f"URL: {url}")
    print("="*70)
    
    try:
        response = httpx.get(url, timeout=30, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        response.raise_for_status()
        html = response.text
        parser = HTMLParser(html)
        
        print(f"✅ HTML大小: {len(html)} 字符\n")
        
        # 1. 查找所有包含数据的section
        print("📑 查找页面区块:")
        sections = parser.css("section, div[class*='section'], div[id*='section']")
        print(f"  找到 {len(sections)} 个section/div区块")
        
        data_sections = []
        for section in sections[:10]:
            section_id = section.attributes.get("id", "")
            section_class = section.attributes.get("class", "")
            text_preview = section.text(strip=True)[:100]
            
            if any(kw in (section_id + " " + section_class).lower() for kw in ["draw", "result", "winning", "number", "history"]):
                data_sections.append({
                    "id": section_id,
                    "class": section_class,
                    "preview": text_preview
                })
        
        if data_sections:
            print(f"  找到 {len(data_sections)} 个数据相关区块:")
            for sec in data_sections[:5]:
                print(f"    - id={sec['id']}, class={sec['class'][:50]}")
                print(f"      预览: {sec['preview']}")
        
        # 2. 查找所有表格及其结构
        print("\n📊 详细分析表格:")
        tables = parser.css("table")
        for i, table in enumerate(tables[:5]):
            print(f"\n  表格 {i+1}:")
            
            # 查找thead
            thead = table.css_first("thead")
            if thead:
                headers = [th.text(strip=True) for th in thead.css("th, td")]
                print(f"    列头: {headers}")
            
            # 查找tbody
            tbody = table.css_first("tbody")
            if tbody:
                rows = tbody.css("tr")
                print(f"    行数: {len(rows)}")
                
                # 显示前3行数据
                for j, row in enumerate(rows[:3]):
                    cells = [cell.text(strip=True) for cell in row.css("td, th")]
                    print(f"      行{j+1}: {cells}")
            
            # 检查是否有data属性
            data_attrs = {k: v for k, v in table.attributes.items() if k.startswith("data-")}
            if data_attrs:
                print(f"    data属性: {data_attrs}")
        
        # 3. 查找JavaScript中的数据
        print("\n💻 查找JavaScript中的数据:")
        scripts = parser.css("script")
        found_data = False
        
        for script in scripts:
            script_text = script.text()
            if not script_text:
                continue
            
            # 查找数据对象
            patterns = [
                (r'var\s+(\w+)\s*=\s*({[\s\S]{50,2000}?});', "var对象"),
                (r'const\s+(\w+)\s*=\s*({[\s\S]{50,2000}?});', "const对象"),
                (r'window\.(\w+)\s*=\s*({[\s\S]{50,2000}?});', "window对象"),
                (r'data:\s*({[\s\S]{50,2000}?})', "data对象"),
            ]
            
            for pattern, desc in patterns:
                matches = re.findall(pattern, script_text, re.DOTALL)
                for match in matches[:2]:
                    obj_str = match[1] if isinstance(match, tuple) else match
                    try:
                        obj = json.loads(obj_str)
                        if isinstance(obj, dict) and len(obj) > 2:
                            print(f"  ✅ 找到{desc}:")
                            print(f"     keys: {list(obj.keys())[:10]}")
                            if "draw" in str(obj).lower() or "result" in str(obj).lower():
                                print(f"     ⭐ 可能包含开奖数据!")
                            found_data = True
                    except:
                        pass
        
        if not found_data:
            print("  ❌ 未找到JavaScript数据对象")
        
        # 4. 查找所有可能的AJAX请求URL
        print("\n🌐 查找AJAX请求URL:")
        ajax_patterns = [
            r'fetch\(["\']([^"\']+)["\']',
            r'\.get\(["\']([^"\']+)["\']',
            r'\.post\(["\']([^"\']+)["\']',
            r'url:\s*["\']([^"\']+)["\']',
            r'endpoint:\s*["\']([^"\']+)["\']',
            r'apiUrl:\s*["\']([^"\']+)["\']',
        ]
        
        ajax_urls = set()
        for script in scripts:
            script_text = script.text()
            for pattern in ajax_patterns:
                matches = re.findall(pattern, script_text, re.IGNORECASE)
                for match in matches:
                    if any(kw in match.lower() for kw in ["draw", "result", "winning", "number", "api", "data"]):
                        if match.startswith("/") or match.startswith("http"):
                            ajax_urls.add(match)
        
        if ajax_urls:
            print(f"  找到 {len(ajax_urls)} 个可能的AJAX URL:")
            for url_pattern in sorted(ajax_urls)[:10]:
                print(f"    - {url_pattern}")
        else:
            print("  ❌ 未找到AJAX URL")
        
        # 5. 查找页面上显示的所有数字（可能是数据）
        print("\n🔢 分析页面数字模式:")
        all_text = parser.body.text()
        
        # 查找日期模式
        dates = re.findall(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}\b', all_text)
        unique_dates = sorted(set(dates))
        if unique_dates:
            print(f"  日期: {len(unique_dates)} 个唯一值")
            print(f"    最新: {unique_dates[-1]}")
            print(f"    最早: {unique_dates[0] if len(unique_dates) > 1 else unique_dates[0]}")
        
        # 查找金额模式
        amounts = re.findall(r'\$[\d,]+(?:\.\d+)?\s*(?:million|billion|M|B|K)?', all_text, re.IGNORECASE)
        unique_amounts = sorted(set(amounts), key=lambda x: len(x), reverse=True)
        if unique_amounts:
            print(f"  金额: {len(unique_amounts)} 个唯一值")
            print(f"    最大值: {unique_amounts[0]}")
            print(f"    示例: {unique_amounts[:5]}")
        
        # 6. 检查是否有"加载更多"或"查看历史"按钮
        print("\n🔘 查找交互元素:")
        buttons = parser.css("button, a[class*='button'], a[class*='load'], a[class*='more'], a[class*='view']")
        relevant_buttons = []
        for btn in buttons:
            text = btn.text(strip=True).lower()
            onclick = btn.attributes.get("onclick", "").lower()
            href = btn.attributes.get("href", "").lower()
            
            if any(kw in (text + onclick + href) for kw in ["more", "load", "history", "past", "all", "view", "see"]):
                relevant_buttons.append({
                    "text": btn.text(strip=True),
                    "href": btn.attributes.get("href", ""),
                    "onclick": btn.attributes.get("onclick", "")[:100]
                })
        
        if relevant_buttons:
            print(f"  找到 {len(relevant_buttons)} 个相关按钮:")
            for btn in relevant_buttons[:5]:
                print(f"    - {btn['text']}")
                if btn['href']:
                    print(f"      href: {btn['href']}")
                if btn['onclick']:
                    print(f"      onclick: {btn['onclick']}")
        else:
            print("  ❌ 未找到相关按钮")
        
        return {
            "tables": len(tables),
            "ajax_urls": list(ajax_urls),
            "dates_found": len(unique_dates),
            "amounts_found": len(unique_amounts),
        }
        
    except Exception as e:
        print(f"❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def check_network_requests():
    """模拟浏览器，检查网络请求"""
    print("\n" + "="*70)
    print("检查可能的网络请求模式")
    print("="*70)
    
    # 检查常见的数据获取模式
    base_url = "https://www.calottery.com"
    
    # 可能的API路径（基于常见模式）
    possible_paths = [
        "/api/v1/lottery/draws",
        "/api/lottery/draws",
        "/api/v1/results",
        "/api/results",
        "/_api/draws",
        "/services/api/draws",
        "/en/api/draws",
        "/data/draws",
        "/winning-numbers/api",
    ]
    
    print("测试可能的API路径:")
    found = []
    for path in possible_paths:
        url = base_url + path
        try:
            response = httpx.get(url, timeout=3, follow_redirects=True)
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "")
                if "json" in content_type or response.text.strip().startswith("{"):
                    found.append(url)
                    print(f"  ✅ {url}")
        except:
            pass
    
    if not found:
        print("  ❌ 未找到可用的API路径")


def search_alternative_websites():
    """搜索其他可能的网站"""
    print("\n" + "="*70)
    print("搜索其他数据源网站")
    print("="*70)
    
    websites = [
        {
            "name": "Powerball.com (官方)",
            "url": "https://www.powerball.com",
            "note": "Powerball全国官网"
        },
        {
            "name": "MegaMillions.com (官方)",
            "url": "https://www.megamillions.com",
            "note": "Mega Millions全国官网"
        },
        {
            "name": "Lottery USA",
            "url": "https://www.lotteryusa.com/california/",
            "note": "第三方数据聚合"
        },
    ]
    
    for site in websites:
        print(f"\n🔍 {site['name']} ({site['note']})")
        try:
            response = httpx.get(site["url"], timeout=10, follow_redirects=True)
            if response.status_code == 200:
                parser = HTMLParser(response.text)
                tables = parser.css("table")
                links = parser.css("a[href*='result'], a[href*='draw'], a[href*='history']")
                print(f"  ✅ 可访问")
                print(f"     - HTML: {len(response.text)} 字符")
                print(f"     - 表格: {len(tables)} 个")
                print(f"     - 相关链接: {len(links)} 个")
                if links:
                    for link in links[:3]:
                        href = link.attributes.get("href", "")
                        print(f"       - {link.text(strip=True)[:30]}: {href[:60]}")
            else:
                print(f"  ⚠️  状态码: {response.status_code}")
        except Exception as e:
            print(f"  ❌ 错误: {e}")


def main():
    """主函数"""
    print("="*70)
    print("深度网页结构分析 - 查找所有数据源")
    print("="*70)
    
    # 详细检查CA页面
    ca_pages = [
        ("CA SuperLotto Plus", "https://www.calottery.com/en/draw-games/superlotto-plus"),
        ("CA Powerball", "https://www.calottery.com/en/draw-games/powerball"),
        ("CA Winning Numbers", "https://www.calottery.com/winning-numbers"),
    ]
    
    results = []
    for name, url in ca_pages:
        result = inspect_ca_page(url, name)
        if result:
            results.append({**{"name": name, "url": url}, **result})
    
    # 检查网络请求模式
    check_network_requests()
    
    # 搜索其他网站
    search_alternative_websites()
    
    # 总结
    print("\n" + "="*70)
    print("分析总结")
    print("="*70)
    for result in results:
        print(f"\n{result['name']}:")
        print(f"  - 表格: {result.get('tables', 0)} 个")
        print(f"  - AJAX URL: {len(result.get('ajax_urls', []))} 个")
        print(f"  - 日期: {result.get('dates_found', 0)} 个")
        print(f"  - 金额: {result.get('amounts_found', 0)} 个")


if __name__ == "__main__":
    main()

