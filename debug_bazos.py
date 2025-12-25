import requests
from bs4 import BeautifulSoup

url = "https://reality.bazos.sk/prenajom/byt/bratislava/"

headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
}

print(f"Fetching: {url}\n")
resp = requests.get(url, headers=headers, timeout=15)
resp.encoding = 'utf-8'

print(f"Status: {resp.status_code}")
print(f"Final URL: {resp.url}")
print(f"Content length: {len(resp.text)} chars\n")

# Сохраняем HTML
with open("debug_bazos.html", "w", encoding="utf-8") as f:
    f.write(resp.text)
print("✅ Saved to debug_bazos.html\n")

soup = BeautifulSoup(resp.text, 'html.parser')

# Анализ структуры
print("="*50)
print("HTML STRUCTURE ANALYSIS")
print("="*50)

# Заголовок страницы
title = soup.find('title')
print(f"\nPage title: {title.get_text() if title else 'N/A'}")

# Все уникальные классы
print("\n--- All unique CSS classes ---")
all_classes = set()
for tag in soup.find_all(class_=True):
    for cls in tag.get('class', []):
        all_classes.add(cls)

for cls in sorted(all_classes):
    print(f"  .{cls}")

# Ищем ссылки на объявления
print("\n--- Links containing '/inzerat/' ---")
links = soup.find_all('a', href=lambda x: x and '/inzerat/' in x)
print(f"Found: {len(links)} links\n")

for i, link in enumerate(links[:10], 1):
    href = link.get('href')
    text = link.get_text(strip=True)[:50]
    parent_class = link.parent.get('class', ['no-class']) if link.parent else ['no-parent']
    print(f"{i}. {text}...")
    print(f"   href: {href}")
    print(f"   parent class: {parent_class}\n")

# Пробуем найти контейнеры объявлений
print("\n--- Searching for listing containers ---")

selectors_to_try = [
    ('div.inzeraty', 'div', {'class_': 'inzeraty'}),
    ('div.inzeratynadpis', 'div', {'class_': 'inzeratynadpis'}),
    ('div.vypis', 'div', {'class_': 'vypis'}),
    ('div.list', 'div', {'class_': 'list'}),
    ('div.maincontent', 'div', {'class_': 'maincontent'}),
    ('table.inzeraty', 'table', {'class_': 'inzeraty'}),
    ('div containing nadpis', 'div', {'class_': 'nadpis'}),
]

for name, tag, attrs in selectors_to_try:
    found = soup.find_all(tag, **attrs)
    if found:
        print(f"✅ {name}: {len(found)} found")
        if found:
            print(f"   First element preview:")
            print(f"   {str(found[0])[:300]}...")
    else:
        print(f"❌ {name}: not found")

# Показываем структуру body
print("\n--- Body direct children ---")
body = soup.find('body')
if body:
    for i, child in enumerate(body.children):
        if hasattr(child, 'name') and child.name:
            classes = child.get('class', [])
            print(f"  <{child.name} class='{' '.join(classes)}'>")