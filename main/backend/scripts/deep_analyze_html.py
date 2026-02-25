#!/usr/bin/env python3
"""
深度分析网页结构，查找所有可提取的信息和其他数据源
"""

import httpx
from selectolax.parser import HTMLParser
import re
from urllib.parse import urljoin, urlparse
import json


def fetch_html_direct(url: str):
    """直接获取HTML"""
    try:
        response = httpx.get(url, timeout=30, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        response.raise_for_status()
        return response.text, response.url
    except Exception as e:
        raise RuntimeError(f"Failed to fetch {url}: {e}")


def analyze_page_structure(url: str, name: str):
    """深度分析页面结构"""
    print("\n" + "="*70)
    print(f"深度分析: {name}")
    print(f"URL: {url}")
    print("="*70)
    
    try:
        html, final_url = fetch_html_direct(url)
        parser = HTMLParser(html)
        
        print(f"✅ HTML大小: {len(html)} 字符")
        print(f"   最终URL: {final_url}\n")
        
        # 1. 查找所有可能包含数据的元素
        print("🔍 查找数据相关元素:")
        
        # 查找所有包含数字的元素
        all_text = parser.body.text()
        dollar_amounts = re.findall(r'\$[\d,]+(?:\.\d+)?\s*(?:million|billion|M|B|K)?', all_text, re.IGNORECASE)
        if dollar_amounts:
            unique_amounts = sorted(set(dollar_amounts), key=lambda x: len(x), reverse=True)[:15]
            print(f"  💰 美元金额: {len(unique_amounts)} 个唯一值")
            print(f"     示例: {unique_amounts[:5]}")
        
        # 查找日期
        dates = re.findall(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}\b', all_text)
        if dates:
            unique_dates = list(set(dates))[:10]
            print(f"  📅 日期: {len(unique_dates)} 个唯一值")
            print(f"     示例: {unique_dates[:3]}")
        
        # 2. 查找所有链接（寻找历史数据、API等）
        print("\n🔗 查找相关链接:")
        all_links = parser.css("a[href]")
        relevant_links = []
        
        keywords = [
            "history", "past", "archive", "results", "draw", 
            "previous", "winning", "numbers", "api", "json",
            "data", "export", "download", "report", "summary"
        ]
        
        for link in all_links:
            href = link.attributes.get("href", "")
            text = link.text(strip=True).lower()
            href_lower = href.lower()
            
            if any(keyword in href_lower or keyword in text for keyword in keywords):
                try:
                    full_url = urljoin(str(final_url), str(href))
                    relevant_links.append({
                        "text": link.text(strip=True)[:50],
                        "href": href,
                        "full_url": full_url
                    })
                except Exception:
                    pass
        
        if relevant_links:
            print(f"  找到 {len(relevant_links)} 个相关链接:")
            for link in relevant_links[:10]:
                print(f"    - {link['text']}: {link['href']}")
                print(f"      → {link['full_url']}")
        else:
            print("  ❌ 未找到相关链接")
        
        # 3. 查找JSON数据（可能嵌入在页面中）
        print("\n📦 查找JSON数据:")
        json_patterns = [
            r'<script[^>]*>[\s\S]*?({[\s\S]*?})[\s\S]*?</script>',
            r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
            r'window\.__DATA__\s*=\s*({.+?});',
            r'data:\s*({.+?})',
        ]
        
        found_json = False
        for pattern in json_patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            for match in matches[:3]:
                try:
                    data = json.loads(match)
                    if isinstance(data, dict) and len(data) > 0:
                        print(f"  ✅ 找到JSON数据 (key数量: {len(data)})")
                        print(f"     顶层keys: {list(data.keys())[:10]}")
                        found_json = True
                        break
                except:
                    pass
            if found_json:
                break
        
        if not found_json:
            print("  ❌ 未找到JSON数据")
        
        # 4. 查找可能的API端点
        print("\n🌐 查找API端点:")
        api_patterns = [
            r'["\']([^"\']*api[^"\']*)["\']',
            r'["\']([^"\']*json[^"\']*)["\']',
            r'fetch\(["\']([^"\']+)["\']',
            r'\.get\(["\']([^"\']+)["\']',
            r'url:\s*["\']([^"\']+)["\']',
        ]
        
        api_endpoints = set()
        for pattern in api_patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            for match in matches:
                if any(kw in match.lower() for kw in ["api", "json", "data", "draw", "result"]):
                    try:
                        full_url = urljoin(str(final_url), str(match))
                        if full_url.startswith("http"):
                            api_endpoints.add(full_url)
                    except Exception:
                        pass
        
        if api_endpoints:
            print(f"  找到 {len(api_endpoints)} 个可能的API端点:")
            for endpoint in sorted(api_endpoints)[:10]:
                print(f"    - {endpoint}")
        else:
            print("  ❌ 未找到API端点")
        
        # 5. 查找表格结构
        print("\n📊 查找表格:")
        tables = parser.css("table")
        print(f"  找到 {len(tables)} 个表格")
        for i, table in enumerate(tables[:5]):
            thead = table.css_first("thead")
            tbody = table.css_first("tbody")
            if thead:
                headers = [th.text(strip=True) for th in thead.css("th, td")]
                print(f"  表格{i+1}列头: {headers}")
            if tbody:
                rows = tbody.css("tr")
                print(f"    行数: {len(rows)}")
                if rows:
                    first_row = rows[0]
                    cells = [cell.text(strip=True)[:30] for cell in first_row.css("td, th")]
                    print(f"    第一行: {cells}")
        
        # 6. 查找meta标签和data属性
        print("\n🏷️  查找meta标签和data属性:")
        meta_tags = parser.css("meta[property], meta[name]")
        relevant_meta = []
        for meta in meta_tags[:10]:
            prop = meta.attributes.get("property") or meta.attributes.get("name")
            content = meta.attributes.get("content", "")
            if any(kw in content.lower() for kw in ["draw", "jackpot", "winner", "number"]):
                relevant_meta.append(f"{prop}: {content[:50]}")
        
        if relevant_meta:
            print(f"  找到相关meta标签:")
            for meta in relevant_meta:
                print(f"    - {meta}")
        
        data_attrs = parser.css("[data-*]")
        if data_attrs:
            data_keys = set()
            for elem in data_attrs[:20]:
                for attr in elem.attributes:
                    if attr.startswith("data-"):
                        data_keys.add(attr)
            if data_keys:
                print(f"  找到data属性: {sorted(data_keys)[:10]}")
        
        # 7. 查找可能的URL模式（历史数据）
        print("\n🔍 查找URL模式:")
        url_patterns = set()
        for link in all_links:
            href = link.attributes.get("href", "")
            if any(kw in href.lower() for kw in ["draw", "result", "history", "past"]):
                # 提取URL模式
                parts = href.split("/")
                if len(parts) > 2:
                    pattern = "/".join(parts[:3]) + "/..."
                    url_patterns.add(pattern)
        
        if url_patterns:
            print(f"  可能的URL模式:")
            for pattern in sorted(url_patterns)[:10]:
                print(f"    - {pattern}")
        
        return {
            "url": final_url,
            "relevant_links": relevant_links,
            "api_endpoints": list(api_endpoints),
            "tables_count": len(tables),
        }
        
    except Exception as e:
        print(f"❌ 分析失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def search_alternative_sources():
    """搜索其他数据源"""
    print("\n" + "="*70)
    print("搜索其他数据源")
    print("="*70)
    
    sources = [
        {
            "name": "CA Lottery Winning Numbers",
            "url": "https://www.calottery.com/winning-numbers",
        },
        {
            "name": "CA Lottery All Games",
            "url": "https://www.calottery.com/en/draw-games",
        },
        {
            "name": "CA Lottery News/Releases",
            "url": "https://www.calottery.com/news-releases",
        },
    ]
    
    results = []
    for source in sources:
        print(f"\n🔍 测试: {source['name']}")
        try:
            result = analyze_page_structure(source["url"], source["name"])
            if result:
                results.append({**source, **result})
        except Exception as e:
            print(f"  ⚠️  跳过: {e}")
    
    return results


def main():
    """主函数"""
    print("="*70)
    print("深度网页结构分析 - 查找所有数据源")
    print("="*70)
    
    # 分析主页面
    main_pages = [
        ("CA SuperLotto Plus", "https://www.calottery.com/en/draw-games/superlotto-plus"),
        ("CA Powerball", "https://www.calottery.com/en/draw-games/powerball"),
        ("CA Mega Millions", "https://www.calottery.com/en/draw-games/mega-millions"),
    ]
    
    main_results = []
    for name, url in main_pages:
        result = analyze_page_structure(url, name)
        if result:
            main_results.append({**{"name": name, "url": url}, **result})
    
    # 搜索其他数据源
    alt_results = search_alternative_sources()
    
    # 总结
    print("\n" + "="*70)
    print("分析总结")
    print("="*70)
    
    print("\n📋 主页面发现:")
    for result in main_results:
        print(f"  {result['name']}:")
        print(f"    - 相关链接: {len(result.get('relevant_links', []))} 个")
        print(f"    - API端点: {len(result.get('api_endpoints', []))} 个")
        print(f"    - 表格: {result.get('tables_count', 0)} 个")
    
    print("\n📋 其他数据源发现:")
    for result in alt_results:
        print(f"  {result['name']}:")
        print(f"    - URL: {result['url']}")
        print(f"    - 相关链接: {len(result.get('relevant_links', []))} 个")
        print(f"    - API端点: {len(result.get('api_endpoints', []))} 个")
        print(f"    - 表格: {result.get('tables_count', 0)} 个")


if __name__ == "__main__":
    main()

