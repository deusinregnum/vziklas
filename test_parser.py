import requests
from bs4 import BeautifulSoup

url = "https://reality.bazos.sk/prenajom/byt/bratislava/"
headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

resp = requests.get(url, headers=headers, timeout=15)
resp.encoding = 'utf-8'

print(f"Status: {resp.status_code}")
print(f"URL: {resp.url}")
print("\n" + "="*50)
print("HTML STRUCTURE ANALYSIS")
print("="*50 + "\n")

soup = BeautifulSoup(resp.text, 'html.parser')

# Сохраним HTML для анализа
with open("bazos_page.html", "w", encoding="utf-8") as f:
    f.write(resp.text)
print("HTML saved to bazos_page.html")

# Найдём все классы
all_divs = soup.find_all('div', class_=True)
classes = {}
for div in all_divs:
    for cls in div.get('class', []):
        classes[cls] = classes.get(cls, 0) + 1

print("\nTop CSS classes found:")
for cls, count in sorted(classes.items(), key=lambda x: -x[1])[:30]:
    print(f"  {cls}: {count}")

# Попробуем разные селекторы
print("\n" + "="*50)
print("TRYING DIFFERENT SELECTORS")
print("="*50)

selectors = [
    'div.inzeraty',
    'div.inzeratynadpis', 
    'div.vypis',
    'div.clasified',
    'article',
    'div.box',
    'div.list',
    'table tr',
    'div.inzerat',
    'div[class*="inzer"]',
    'a[href*="/inzerat/"]',
]

for sel in selectors:
    items = soup.select(sel)
    if items:
        print(f"\n✅ '{sel}' found {len(items)} items")
        if len(items) > 0:
            print(f"   First item preview: {str(items[0])[:200]}...")

# Найдём все ссылки на inzerat
print("\n" + "="*50)
print("ALL LISTING LINKS")
print("="*50)

links = soup.find_all('a', href=lambda x: x and '/inzerat/' in x)
print(f"Found {len(links)} listing links")
for link in links[:5]:
    print(f"  - {link.get('href')} : {link.get_text(strip=True)[:50]}")

# Pagination
print("\n" + "="*50)
print("PAGINATION")
print("="*50)
pagination = soup.find_all('a', href=lambda x: x and '/bratislava/' in str(x))
for p in pagination[:10]:
    href = p.get('href')
    text = p.get_text(strip=True)
    if text.isdigit() or 'ďal' in text.lower():
        print(f"  Page: {text} -> {href}")