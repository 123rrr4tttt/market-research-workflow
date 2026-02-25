#!/usr/bin/env python3
"""
专门查找数据源：分析页面链接、查找API、查找历史数据页面
"""

import httpx
from selectolax.parser import HTMLParser
import re
from urllib.parse import urljoin, urlparse
import json


def fetch_html(url: str):
    """获取HTML"""
    try:
        response = httpx.get(url, timeout=30, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        response.raise_for_status()
        return response.text, str(response.url)
    except Exception as e:
        return None, str(e)


def extract_all_links(html: str, base_url: str):
    """提取所有链接并分类"""
    parser = HTMLParser(html)
    all_links = parser.css("a[href]")
    
    categories = {
        "draw_games": [],
        "history": [],
        "results": [],
        "winning_numbers": [],
        "api": [],
        "other": [],
    }
    
    for link in all_links:
        href = link.attributes.get("href", "")
        text = link.text(strip=True).lower()
        href_lower = href.lower()
        
        try:
            full_url = urljoin(base_url, href)
        except:
            continue
        
        # 分类
        if any(kw in href_lower for kw in ["/draw-games/", "draw-game"]):
            categories["draw_games"].append({"text": link.text(strip=True), "href": href, "url": full_url})
        elif any(kw in href_lower or kw in text for kw in ["history", "past", "archive", "previous"]):
            categories["history"].append({"text": link.text(strip=True), "href": href, "url": full_url})
        elif any(kw in href_lower or kw in text for kw in ["result", "winning", "number"]):
            categories["results"].append({"text": link.text(strip=True), "href": href, "url": full_url})
        elif any(kw in href_lower for kw in ["api", "json", "/api/"]):
            categories["api"].append({"text": link.text(strip=True), "href": href, "url": full_url})
        else:
            categories["other"].append({"text": link.text(strip=True), "href": href, "url": full_url})
    
    return categories


def find_embedded_data(html: str):
    """查找嵌入的JSON数据"""
    findings = []
    
    # 查找script标签中的JSON
    script_pattern = r'<script[^>]*>([\s\S]*?)</script>'
    scripts = re.findall(script_pattern, html, re.IGNORECASE)
    
    for script in scripts:
        # 查找JSON对象
        json_patterns = [
            r'({[\s\S]{20,5000}?})',
            r'window\.__\w+\s*=\s*({.+?});',
            r'var\s+\w+\s*=\s*({.+?});',
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, script, re.DOTALL)
            for match in matches[:3]:
                try:
                    data = json.loads(match)
                    if isinstance(data, dict) and len(data) > 2:
                        findings.append({
                            "type": "json_in_script",
                            "keys": list(data.keys())[:10],
                            "preview": str(data)[:200]
                        })
                        break
                except:
                    pass
    
    return findings


def analyze_winning_numbers_page():
    """分析winning-numbers页面"""
    print("\n" + "="*70)
    print("分析: CA Lottery Winning Numbers 页面")
    print("="*70)
    
    url = "https://www.calottery.com/winning-numbers"
    html, final_url = fetch_html(url)
    
    if not html:
        print(f"❌ 无法访问: {final_url}")
        return
    
    parser = HTMLParser(html)
    print(f"✅ 成功获取 ({len(html)} 字符)\n")
    
    # 查找所有游戏链接
    game_links = parser.css("a[href*='draw-games']")
    print(f"📋 找到 {len(game_links)} 个游戏链接:")
    for link in game_links[:10]:
        href = link.attributes.get("href", "")
        text = link.text(strip=True)
        print(f"  - {text}: {href}")
    
    # 查找是否有历史数据链接
    history_keywords = ["history", "past", "archive", "previous", "all"]
    history_links = []
    for link in parser.css("a[href]"):
        href = link.attributes.get("href", "").lower()
        text = link.text(strip=True).lower()
        if any(kw in href or kw in text for kw in history_keywords):
            history_links.append({
                "text": link.text(strip=True),
                "href": link.attributes.get("href", "")
            })
    
    if history_links:
        print(f"\n📚 找到 {len(history_links)} 个可能的历史数据链接:")
        for link in history_links[:10]:
            print(f"  - {link['text']}: {link['href']}")
    
    # 查找表格
    tables = parser.css("table")
    print(f"\n📊 找到 {len(tables)} 个表格")
    for i, table in enumerate(tables[:3]):
        rows = table.css("tr")
        print(f"  表格{i+1}: {len(rows)} 行")
        if rows:
            first_row = rows[0]
            cells = [cell.text(strip=True)[:30] for cell in first_row.css("td, th")]
            print(f"    列头: {cells}")


def check_api_endpoints():
    """检查可能的API端点"""
    print("\n" + "="*70)
    print("检查可能的API端点")
    print("="*70)
    
    base_url = "https://www.calottery.com"
    
    # 常见的API路径模式
    api_paths = [
        "/api/v1/draws",
        "/api/draws",
        "/api/v1/winning-numbers",
        "/api/winning-numbers",
        "/api/v1/results",
        "/api/results",
        "/api/v1/games",
        "/data/draws.json",
        "/data/winning-numbers.json",
    ]
    
    found_apis = []
    for path in api_paths:
        url = base_url + path
        try:
            response = httpx.get(url, timeout=5, follow_redirects=True)
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "")
                if "json" in content_type:
                    found_apis.append({
                        "url": url,
                        "status": response.status_code,
                        "content_type": content_type,
                        "size": len(response.text)
                    })
                    print(f"  ✅ {url} - {content_type} ({len(response.text)} 字符)")
                elif response.text[:100].strip().startswith("{"):
                    found_apis.append({
                        "url": url,
                        "status": response.status_code,
                        "content_type": content_type,
                        "size": len(response.text)
                    })
                    print(f"  ✅ {url} - 可能是JSON ({len(response.text)} 字符)")
        except Exception as e:
            pass
    
    if not found_apis:
        print("  ❌ 未找到公开的API端点")
    
    return found_apis


def search_third_party_sources():
    """搜索第三方数据源"""
    print("\n" + "="*70)
    print("搜索第三方数据源")
    print("="*70)
    
    sources = [
        {
            "name": "LottoReport",
            "url": "https://www.lottoreport.com/california.htm",
            "description": "第三方彩票数据网站"
        },
        {
            "name": "Lottery Post",
            "url": "https://www.lotterypost.com/game/131",
            "description": "Powerball数据"
        },
        {
            "name": "USAMega",
            "url": "https://www.usamega.com/mega-millions-history.asp",
            "description": "Mega Millions历史数据"
        },
    ]
    
    results = []
    for source in sources:
        print(f"\n🔍 测试: {source['name']}")
        html, result = fetch_html(source["url"])
        if html:
            parser = HTMLParser(html)
            tables = parser.css("table")
            links = parser.css("a[href]")
            print(f"  ✅ 可访问")
            print(f"     - HTML大小: {len(html)} 字符")
            print(f"     - 表格数量: {len(tables)}")
            print(f"     - 链接数量: {len(links)}")
            results.append({**source, "accessible": True, "tables": len(tables)})
        else:
            print(f"  ❌ 无法访问: {result}")
            results.append({**source, "accessible": False})
    
    return results


def main():
    """主函数"""
    print("="*70)
    print("数据源查找分析")
    print("="*70)
    
    # 1. 分析主页面链接
    print("\n" + "="*70)
    print("1. 分析主页面链接结构")
    print("="*70)
    
    main_url = "https://www.calottery.com/en/draw-games/superlotto-plus"
    html, final_url = fetch_html(main_url)
    
    if html:
        categories = extract_all_links(html, final_url)
        print(f"\n📋 链接分类:")
        for category, links in categories.items():
            if links:
                print(f"  {category}: {len(links)} 个")
                for link in links[:3]:
                    print(f"    - {link['text']}: {link['href']}")
        
        # 查找嵌入数据
        embedded = find_embedded_data(html)
        if embedded:
            print(f"\n📦 找到 {len(embedded)} 个嵌入的JSON数据")
            for data in embedded:
                print(f"  - keys: {data['keys']}")
    
    # 2. 分析winning-numbers页面
    analyze_winning_numbers_page()
    
    # 3. 检查API端点
    apis = check_api_endpoints()
    
    # 4. 搜索第三方数据源
    third_party = search_third_party_sources()
    
    # 总结
    print("\n" + "="*70)
    print("总结")
    print("="*70)
    print(f"✅ 找到 {len(apis)} 个API端点")
    print(f"✅ 测试了 {len(third_party)} 个第三方数据源")
    accessible_third = [s for s in third_party if s.get("accessible")]
    print(f"   - {len(accessible_third)} 个可访问")


if __name__ == "__main__":
    main()

