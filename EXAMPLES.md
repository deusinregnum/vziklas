# 📖 Примеры использования новой архитектуры

## 1. Инициализация БД

```python
from database import init_db

# Первый запуск - создаст таблицы
init_db()
# Вывод: ✅ Database initialized
```

---

## 2. Парсинг данных

### Фоновый парсинг (автоматически)
```python
import asyncio
from rental_data import background_parse_rentals

async def test():
    await background_parse_rentals()
    # Автоматически сохранит в БД

asyncio.run(test())
```

### Прямой парсинг (для тестирования)
```python
from rental_data import scrape_bazos
from database import save_rentals, log_parse

rentals = scrape_bazos(max_pages=15)
print(f"Распарсено: {len(rentals)} объявлений")

# Сохранить в БД
save_rentals(rentals)

# Залогировать
log_parse(len(rentals), "success")
```

---

## 3. Работа с данными

### Получить все объявления
```python
from rental_data import get_rentals

rentals = get_rentals()
print(f"Загружено: {len(rentals)} объявлений")

for rental in rentals[:5]:
    print(f"🏢 {rental['name']}")
    print(f"   €{rental['price']} | {rental['district']}")
    print()
```

### Получить конкретное объявление
```python
from database import get_rental_by_index

rental = get_rental_by_index(0)
if rental:
    print(f"Название: {rental['name']}")
    print(f"Цена: €{rental['price']}")
    print(f"Описание: {rental['description']}")
    print(f"Ссылка: {rental['url']}")
```

---

## 4. Поиск

### Поиск по цене
```python
from rental_data import search_rentals

# Квартиры от €300 до €800
results = search_rentals('price', (300, 800))
print(f"Найдено: {len(results)} объявлений в диапазоне €300-800")

for r in results[:10]:
    print(f"{r['name']} - €{r['price']}")
```

### Поиск по району
```python
# Только Братислава
bratislava = search_rentals('district', 'Bratislava')
print(f"В Братиславе: {len(bratislava)} объявлений")

# Только Кошице
kosice = search_rentals('district', 'Košice')
print(f"В Кошице: {len(kosice)} объявлений")
```

### Поиск по ключевому слову
```python
# Объявления с "балкон"
balcony = search_rentals('keyword', 'balkon')
print(f"С балконом: {len(balcony)} объявлений")

for r in balcony[:5]:
    print(f"{r['name']}")
```

---

## 5. Статистика БД

### Общая статистика
```python
from database import get_rental_count, get_price_range_db, get_districts_db, get_last_parse_time

count = get_rental_count()
min_price, max_price = get_price_range_db()
districts = get_districts_db()
last_parse = get_last_parse_time()

print(f"📊 Статистика БД:")
print(f"  Всего объявлений: {count}")
print(f"  Диапазон цен: €{min_price} - €{max_price}")
print(f"  Количество районов: {len(districts)}")
print(f"  Последний парсинг: {last_parse}")
```

### Объявления по районам
```python
from rental_data import search_rentals, get_districts

for district in get_districts():
    count = len(search_rentals('district', district))
    print(f"{district}: {count} объявлений")
```

### Распределение цен
```python
from rental_data import get_rentals

rentals = get_rentals()
prices = [r['price'] for r in rentals if r['price'] > 0]

if prices:
    print(f"Минимальная цена: €{min(prices)}")
    print(f"Максимальная цена: €{max(prices)}")
    print(f"Средняя цена: €{sum(prices) // len(prices)}")
    print(f"Медиана: €{sorted(prices)[len(prices)//2]}")
```

---

## 6. SQL запросы напрямую

### Все объявления в диапазоне цен
```python
import sqlite3

conn = sqlite3.connect('rentals.db')
cursor = conn.cursor()

cursor.execute('''
    SELECT name, price, district 
    FROM rentals 
    WHERE price >= 400 AND price <= 900
    ORDER BY price ASC
''')

for row in cursor.fetchall():
    print(f"{row[0]} - €{row[1]} ({row[2]})")

conn.close()
```

### Объявления, обновлённые сегодня
```python
import sqlite3
from datetime import date

conn = sqlite3.connect('rentals.db')
cursor = conn.cursor()

today = date.today()
cursor.execute('''
    SELECT name, price, district, parsed_at
    FROM rentals 
    WHERE DATE(parsed_at) = ?
    ORDER BY parsed_at DESC
''', (today,))

for row in cursor.fetchall():
    print(f"{row[0]} - €{row[1]} ({row[2]}) - {row[3]}")

conn.close()
```

### Статистика по районам
```python
import sqlite3

conn = sqlite3.connect('rentals.db')
cursor = conn.cursor()

cursor.execute('''
    SELECT district, COUNT(*), AVG(price), MIN(price), MAX(price)
    FROM rentals 
    WHERE price > 0
    GROUP BY district
    ORDER BY COUNT(*) DESC
''')

print(f"{'Район':<20} {'Кол-во':<8} {'Средняя':<8} {'Мин':<8} {'Макс':<8}")
print('-' * 60)
for row in cursor.fetchall():
    district, count, avg_price, min_price, max_price = row
    print(f"{district:<20} {count:<8} €{int(avg_price):<7} €{int(min_price):<7} €{int(max_price):<7}")

conn.close()
```

### История парсинга
```python
import sqlite3

conn = sqlite3.connect('rentals.db')
cursor = conn.cursor()

cursor.execute('''
    SELECT parsed_at, count, status
    FROM parse_log
    ORDER BY parsed_at DESC
    LIMIT 10
''')

print(f"{'Дата/время':<20} {'Найдено':<10} {'Статус':<15}")
print('-' * 45)
for row in cursor.fetchall():
    print(f"{row[0]:<20} {row[1]:<10} {row[2]:<15}")

conn.close()
```

---

## 7. Сложные примеры

### Найти самое дешёвое и самое дорогое
```python
from rental_data import get_rentals

rentals = get_rentals()
valid_rentals = [r for r in rentals if r['price'] > 0]

if valid_rentals:
    cheapest = min(valid_rentals, key=lambda x: x['price'])
    most_expensive = max(valid_rentals, key=lambda x: x['price'])
    
    print("💰 САМОЕ ДЕШЁВОЕ:")
    print(f"  {cheapest['name']}")
    print(f"  €{cheapest['price']} | {cheapest['district']}")
    
    print("\n💎 САМОЕ ДОРОГОЕ:")
    print(f"  {most_expensive['name']}")
    print(f"  €{most_expensive['price']} | {most_expensive['district']}")
```

### Объявления в определённом городе со скидкой
```python
from rental_data import get_rentals, get_price_range

rentals = get_rentals()

# Найти 25% квартал от медианы цены
all_prices = [r['price'] for r in rentals if r['price'] > 0]
median = sorted(all_prices)[len(all_prices)//2]
budget = median * 0.75  # 25% дешевле медианы

cheap_rentals = [
    r for r in rentals 
    if r['district'] == 'Bratislava' and 0 < r['price'] < budget
]

print(f"💵 Квартиры в Братиславе дешевле €{budget}:")
for r in cheap_rentals[:5]:
    print(f"  {r['name']} - €{r['price']}")
```

### Экспорт в CSV
```python
import csv
from rental_data import get_rentals

rentals = get_rentals()

with open('rentals_export.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=['name', 'price', 'district', 'rooms', 'size', 'url'])
    writer.writeheader()
    
    for r in rentals:
        writer.writerow({
            'name': r['name'],
            'price': r['price'],
            'district': r['district'],
            'rooms': r['rooms'],
            'size': r['size'],
            'url': r['url']
        })

print(f"✅ Экспортировано {len(rentals)} объявлений в rentals_export.csv")
```

---

## 8. Фоновые задачи в боте

### Добавить собственную задачу в планировщик
```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from rental_data import background_parse_rentals

async def my_custom_task():
    print("🔧 Выполняю собственную задачу...")
    # Ваш код здесь
    pass

# В функции main() бота:
scheduler = AsyncIOScheduler()

# Добавить свою задачу
scheduler.add_job(
    my_custom_task,
    "interval",
    hours=6,
    id="my_job"
)

# Добавить стандартный парсинг
scheduler.add_job(
    background_parse_rentals,
    "interval",
    hours=3,
    id="parse_job"
)

scheduler.start()
```

---

## 9. Мониторинг

### Простой скрипт мониторинга
```python
import asyncio
from database import get_rental_count, get_last_parse_time
from datetime import datetime, timedelta

async def monitor():
    while True:
        count = get_rental_count()
        last_parse = get_last_parse_time()
        
        # Проверить свежесть данных
        if last_parse:
            age = datetime.now() - last_parse
            status = "🟢 Свежие" if age < timedelta(hours=4) else "🟡 Устаревшие"
        else:
            status = "🔴 Нет данных"
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {count} объявлений | {status}")
        
        await asyncio.sleep(300)  # Проверка каждые 5 минут

asyncio.run(monitor())
```

---

## 10. Очистка старых данных

```python
from database import clear_old_rentals, get_rental_count

# Удалить объявления старше 30 дней
before = get_rental_count()
clear_old_rentals(days=30)
after = get_rental_count()

print(f"Удалено {before - after} старых объявлений")
```

---

**Готово! Используйте эти примеры для своего проекта 🚀**
