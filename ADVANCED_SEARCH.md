# 🔍 Документация - Расширенный поиск (Multiple Filters)

## 📋 Что добавлено

Теперь бот может применять **несколько фильтров одновременно**:
- 💰 **Цена** (от и до)
- 📍 **Локация** (город/район)
- 🔤 **Ключевое слово** (в названии или описании)

Все три фильтра работают вместе (И-логика), а не отдельно!

---

## 🔧 Технические изменения

### 1. database.py - Новая функция поиска

```python
def search_rentals_advanced(filters: Dict) -> List[Dict]:
    """
    Поиск с несколькими фильтрами одновременно.
    
    filters = {
        'min_price': 300,      # Минимальная цена
        'max_price': 800,      # Максимальная цена
        'district': 'Bratislava',  # Город/район
        'keyword': 'balkon'    # Ключевое слово
    }
    """
```

Использует SQL `WHERE` с AND логикой:
```sql
SELECT * FROM rentals 
WHERE price >= 300 AND price <= 800
  AND (LOWER(district) LIKE '%bratislava%' OR LOWER(address) LIKE '%bratislava%')
  AND (LOWER(name) LIKE '%balkon%' OR LOWER(description) LIKE '%balkon%')
ORDER BY price ASC
```

### 2. rental_data.py - Новая функция-обёртка

```python
def search_rentals_combined(filters: Dict) -> List[Dict]:
    """Поиск с несколькими фильтрами одновременно."""
    return search_rentals_advanced(filters)
```

### 3. bot.py - Новый формат поиска

**Добавлен новый статус диалога:**
```python
ADVANCED_SEARCH = 5  # Состояние для расширенного поиска
```

**Новое меню поиска:**
```
🔍 Вихъдавание

💰 По цене
📍 По локации
🔤 По ключевому слову
⚙️ Покршцилé вихъдавание (НОВОЕ)
❌ Отмена
```

**Новые обработчики:**
- `search_advanced_handler()` - запускает расширенный поиск
- `advanced_search_handler()` - обрабатывает ввод с 4 шагами:
  1. Минимальная цена
  2. Максимальная цена
  3. Локация
  4. Ключевое слово

---

## 🎮 Как использовать (для пользователя)

### Команда запуска
```
/search
```

### Выбор типа поиска
```
🔍 Вихъдавание

💰 Podľa ceny
📍 Podľa lokality
🔤 Podľa kľúčového slova
⚙️ Pokročilé vyhľadávanie  ← НОВОЕ
❌ Zrušiť
```

### Пример использования расширенного поиска

```
Пользователь: /search
Бот: Выберите тип поиска... (показать меню)

Пользователь: ⚙️ Pokročilé vyhľadávanie
Бот: Zadajte minimálnu cenu (alebo napíšte 0 pre preskočenie):

Пользователь: 400
Бот: Zadajte maximálnu cenu (alebo napíšte 0 pre preskočenie):

Пользователь: 900
Бот: Zadajte lokalitu (napr. 'Bratislava') alebo napíšte '-' pre preskočenie:

Пользователь: Bratislava
Бот: Zadajte kľúčové slovo (napr. 'balkón') alebo napíšte '-' pre vyhľadávanie:

Пользователь: balkon
Бот: 
📊 Pokročilé vyhľadávanie:
💰 Cena: €400 - €900
📍 Lokalita: Bratislava
🔤 Slovo: balkon

📊 Nájdeno: 12 inzerátov

[Список найденных объявлений]
```

### Пропуск фильтра

Пользователь может пропустить любой фильтр, введя `-`:

```
Минимальная цена: 0 (пропуск)
Максимальная цена: 1000
Локация: - (пропуск)
Ключевое слово: - (пропуск)

Результат: все объявления до €1000, без фильтра по локации и слову
```

---

## 📊 SQL запросы

### Пример 1: Цена + Город

```sql
SELECT * FROM rentals 
WHERE price > 0 AND price >= 400 AND price <= 900
  AND (LOWER(district) LIKE '%bratislava%' OR LOWER(address) LIKE '%bratislava%')
ORDER BY price ASC
```

### Пример 2: Все фильтры

```sql
SELECT * FROM rentals 
WHERE price > 0 AND price >= 400 AND price <= 900
  AND (LOWER(district) LIKE '%bratislava%' OR LOWER(address) LIKE '%bratislava%')
  AND (LOWER(name) LIKE '%balkon%' OR LOWER(description) LIKE '%balkon%')
ORDER BY price ASC
```

### Пример 3: Только локация и слово

```sql
SELECT * FROM rentals 
WHERE (LOWER(district) LIKE '%bratislava%' OR LOWER(address) LIKE '%bratislava%')
  AND (LOWER(name) LIKE '%balkon%' OR LOWER(description) LIKE '%balkon%')
ORDER BY parsed_at DESC
```

---

## 🔄 Поток данных

```
Пользователь: /search → search()
                          ↓
                    Выбрать тип поиска
                          ↓
    Нажать "⚙️ Покршцилé"
                          ↓
            search_advanced_handler()
                          ↓
         Шаг 1: Минимальная цена
                          ↓
         advanced_search_handler() [step=0]
                          ↓
         Шаг 2: Максимальная цена
                          ↓
         advanced_search_handler() [step=1]
                          ↓
         Шаг 3: Локация
                          ↓
         advanced_search_handler() [step=2]
                          ↓
         Шаг 4: Ключевое слово
                          ↓
         advanced_search_handler() [step=3]
                          ↓
         search_rentals_combined(filters) → search_rentals_advanced()
                          ↓
               Результаты из БД
                          ↓
         show_search_results()
```

---

## 💾 Сохранение фильтров

Фильтры сохраняются в `context.user_data`:

```python
context.user_data['search_filters'] = {
    'min_price': 400,
    'max_price': 900,
    'district': 'Bratislava',
    'keyword': 'balkon'
}
```

---

## 🧪 Примеры использования (для разработчиков)

### Прямое использование функции

```python
from rental_data import search_rentals_combined

filters = {
    'min_price': 300,
    'max_price': 800,
    'district': 'Bratislava'
}

results = search_rentals_combined(filters)
print(f"Найдено: {len(results)} объявлений")

for rental in results:
    print(f"  {rental['name']} - €{rental['price']}")
```

### Только цена и город

```python
filters = {
    'min_price': 400,
    'max_price': 1000,
    'district': 'Košice'
}

results = search_rentals_combined(filters)
```

### Только ключевое слово

```python
filters = {
    'keyword': 'terasa'
}

results = search_rentals_combined(filters)
```

---

## ✨ Преимущества

✅ Комбинирование фильтров (И-логика)  
✅ Пропуск ненужных фильтров (-)  
✅ Интуитивный пошаговый интерфейс  
✅ Быстрый поиск в БД (< 1 сек)  
✅ Все фильтры применяются одновременно  
✅ Сортировка по цене или дате  

---

## 🐛 Тестирование

```bash
# Проверить что функция работает
python3 -c "
from rental_data import search_rentals_combined
filters = {'min_price': 300, 'max_price': 800, 'district': 'Bratislava'}
results = search_rentals_combined(filters)
print(f'✅ Найдено {len(results)} объявлений')
"
```

---

**Готово! Расширенный поиск полностью интегрирован! 🚀**
