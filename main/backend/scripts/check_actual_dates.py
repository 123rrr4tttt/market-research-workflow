"""手动检查实际页面的日期信息"""
import requests
from bs4 import BeautifulSoup
import json
import re
from pathlib import Path
from datetime import datetime
from email.utils import parsedate_to_datetime

def check_page_dates(url):
    """检查页面的所有可能的日期来源"""
    print(f"\n{'='*80}")
    print(f"检查: {url}")
    print('='*80)
    
    results = {
        'url': url,
        'http_headers': {},
        'meta_tags': [],
        'time_tags': [],
        'json_ld': [],
        'text_dates': []
    }
    
    try:
        response = requests.get(url, timeout=10, allow_redirects=True, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        
        # 检查HTTP响应头
        if 'last-modified' in response.headers:
            try:
                last_modified = parsedate_to_datetime(response.headers['last-modified'])
                results['http_headers']['last-modified'] = last_modified.isoformat()
                print(f"✓ HTTP Last-Modified: {last_modified.date()}")
            except Exception as e:
                print(f"✗ HTTP Last-Modified 解析失败: {e}")
        
        if 'date' in response.headers:
            try:
                date_header = parsedate_to_datetime(response.headers['date'])
                results['http_headers']['date'] = date_header.isoformat()
                print(f"✓ HTTP Date: {date_header.date()}")
            except Exception as e:
                print(f"✗ HTTP Date 解析失败: {e}")
        
        # 检查HTML内容
        if 'text/html' in response.headers.get('content-type', ''):
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 检查meta标签
            meta_patterns = [
                ('property', 'article:published_time'),
                ('property', 'og:published_time'),
                ('property', 'article:modified_time'),
                ('name', 'publish-date'),
                ('name', 'pubdate'),
                ('name', 'publication-date'),
                ('name', 'date'),
                ('name', 'DC.date'),
                ('name', 'DC.Date'),
                ('itemprop', 'datePublished'),
                ('itemprop', 'dateModified'),
            ]
            
            for attr, value in meta_patterns:
                meta = soup.find('meta', {attr: value})
                if meta and meta.get('content'):
                    content = meta.get('content')
                    results['meta_tags'].append({attr: value, 'content': content})
                    print(f"✓ Meta {attr}={value}: {content[:50]}")
            
            # 检查time标签
            time_tags = soup.find_all('time')
            for time_tag in time_tags[:5]:
                datetime_attr = time_tag.get('datetime') or time_tag.get('pubdate')
                if datetime_attr:
                    results['time_tags'].append({
                        'datetime': datetime_attr,
                        'text': time_tag.get_text(strip=True)[:50]
                    })
                    print(f"✓ Time tag: datetime={datetime_attr}, text={time_tag.get_text(strip=True)[:50]}")
            
            # 检查JSON-LD
            json_ld_scripts = soup.find_all('script', type='application/ld+json')
            for script in json_ld_scripts[:3]:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict):
                        for key in ['datePublished', 'dateModified', 'publishedTime', 'date']:
                            if key in data:
                                results['json_ld'].append({key: data[key]})
                                print(f"✓ JSON-LD {key}: {data[key]}")
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict):
                                for key in ['datePublished', 'dateModified', 'publishedTime', 'date']:
                                    if key in item:
                                        results['json_ld'].append({key: item[key]})
                                        print(f"✓ JSON-LD {key}: {item[key]}")
                except Exception as e:
                    pass
            
            # 检查文本中的日期
            text_content = soup.get_text(separator=' ', strip=True)
            date_patterns = [
                r'(Published|Last\s+updated?|Updated|Effective|Date|发布日期|最后更新)[:\s]+([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
                r'(Published|Last\s+updated?|Updated|Effective|Date|发布日期|最后更新)[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{4})',
                r'(Published|Last\s+updated?|Updated|Effective|Date|发布日期|最后更新)[:\s]+(\d{4}[/-]\d{1,2}[/-]\d{1,2})',
            ]
            
            for pattern in date_patterns:
                matches = re.findall(pattern, text_content[:3000], re.IGNORECASE)
                for match in matches[:3]:
                    results['text_dates'].append(match)
                    print(f"✓ 文本日期: {match[0]}: {match[1]}")
        
        elif 'application/pdf' in response.headers.get('content-type', ''):
            print("这是PDF文件，无法直接解析HTML内容")
            print(f"✓ Content-Type: application/pdf")
            if 'last-modified' in response.headers:
                print(f"✓ Last-Modified: {response.headers['last-modified']}")
        
    except Exception as e:
        print(f"✗ 错误: {e}")
        results['error'] = str(e)
    
    return results


# 检查几个代表性的链接
urls = [
    "https://ktla.com/news/california/california-lottery-to-introduce-new-mega-millions-with-higher-payouts-better-odds/",
    "https://www.calottery.com/en/faqs",
    "https://jackpocket.com/lottery-results/california",
    "https://static.www.calottery.com/-/media/Project/calottery/PWS/PDFs/Lottery-Retailer-Policies--3-3-14.pdf",
]

all_results = []
for url in urls:
    result = check_page_dates(url)
    all_results.append(result)

# 保存结果
output_path = Path(__file__).with_name("actual_dates_check.json")
with output_path.open('w', encoding='utf-8') as f:
    json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)

print(f"\n\n所有结果已保存到 {output_path}")

