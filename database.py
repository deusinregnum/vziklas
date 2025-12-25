import sqlite3
import json
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / 'rentals.db'


def init_db():
    """Инициализация базы данных."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rentals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price INTEGER,
            district TEXT,
            address TEXT,
            rooms TEXT,
            size TEXT,
            description TEXT,
            url TEXT UNIQUE NOT NULL,
            source TEXT,
            available_from TEXT,
            image_url TEXT,
            parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS parse_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            count INTEGER,
            status TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("✅ Database initialized")


def save_rentals(rentals: List[Dict]) -> int:
    """
    Сохраняет объявления в БД.
    Обновляет существующие по URL, добавляет новые.
    Возвращает количество добавленных объявлений.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    added_count = 0
    updated_count = 0
    
    for rental in rentals:
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO rentals 
                (name, price, district, address, rooms, size, description, 
                 url, source, available_from, image_url, parsed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (
                rental['name'],
                rental['price'],
                rental['district'],
                rental['address'],
                rental['rooms'],
                rental['size'],
                rental['description'],
                rental['url'],
                rental['source'],
                rental['available_from'],
                rental['image_url']
            ))
            
            if cursor.rowcount > 0:
                added_count += 1
        except sqlite3.IntegrityError:
            updated_count += 1
        except Exception as e:
            logger.error(f"Error saving rental {rental.get('name', 'Unknown')}: {e}")
    
    conn.commit()
    conn.close()
    
    logger.info(f"📊 Saved: {added_count} new, {updated_count} updated rentals")
    return added_count


def log_parse(count: int, status: str = "success"):
    """Логирует информацию о парсинге."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO parse_log (count, status)
        VALUES (?, ?)
    ''', (count, status))
    
    conn.commit()
    conn.close()
    logger.info(f"✅ Parse log: {count} rentals, status={status}")


def get_all_rentals() -> List[Dict]:
    """Получает все объявления из БД."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM rentals ORDER BY parsed_at DESC')
    rentals = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return rentals


def search_rentals_db(search_type: str, value) -> List[Dict]:
    """Поиск объявлений в БД."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if search_type == 'price':
        min_price, max_price = value
        cursor.execute('''
            SELECT * FROM rentals 
            WHERE price > 0 AND price >= ? AND price <= ?
            ORDER BY price ASC
        ''', (min_price, max_price))
    
    elif search_type == 'district':
        district = value.lower()
        cursor.execute('''
            SELECT * FROM rentals 
            WHERE LOWER(district) LIKE ? OR LOWER(address) LIKE ?
            ORDER BY parsed_at DESC
        ''', (f'%{district}%', f'%{district}%'))
    
    elif search_type == 'keyword':
        keyword = value.lower()
        cursor.execute('''
            SELECT * FROM rentals 
            WHERE LOWER(name) LIKE ? OR LOWER(description) LIKE ?
            ORDER BY parsed_at DESC
        ''', (f'%{keyword}%', f'%{keyword}%'))
    
    else:
        cursor.execute('SELECT * FROM rentals ORDER BY parsed_at DESC')
    
    rentals = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return rentals


def search_rentals_advanced(filters: Dict) -> List[Dict]:
    """
    Поиск с несколькими фильтрами одновременно.
    
    filters = {
        'min_price': 300,
        'max_price': 800,
        'district': 'Bratislava',
        'keyword': 'balkon'
    }
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Строим SQL запрос динамически
    query = 'SELECT * FROM rentals WHERE 1=1'
    params = []
    
    # Фильтр по цене
    if 'min_price' in filters and filters['min_price'] > 0:
        query += ' AND price >= ?'
        params.append(filters['min_price'])
    
    if 'max_price' in filters and filters['max_price'] < 50000:
        query += ' AND price <= ? AND price > 0'
        params.append(filters['max_price'])
    
    # Фильтр по локации
    if 'district' in filters and filters['district']:
        query += ' AND (LOWER(district) LIKE ? OR LOWER(address) LIKE ?)'
        district_pattern = f"%{filters['district'].lower()}%"
        params.extend([district_pattern, district_pattern])
    
    # Фильтр по ключевому слову
    if 'keyword' in filters and filters['keyword']:
        query += ' AND (LOWER(name) LIKE ? OR LOWER(description) LIKE ?)'
        keyword_pattern = f"%{filters['keyword'].lower()}%"
        params.extend([keyword_pattern, keyword_pattern])
    
    # Сортировка
    query += ' ORDER BY price ASC' if 'min_price' in filters else ' ORDER BY parsed_at DESC'
    
    cursor.execute(query, params)
    rentals = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return rentals


def get_districts_db() -> List[str]:
    """Получает список всех районов из БД."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT DISTINCT district FROM rentals 
        WHERE district IS NOT NULL AND district != 'Slovensko'
        ORDER BY district
    ''')
    
    districts = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    return districts


def get_price_range_db() -> Tuple[int, int]:
    """Получает диапазон цен из БД."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT MIN(price), MAX(price) FROM rentals
        WHERE price > 0
    ''')
    
    result = cursor.fetchone()
    conn.close()
    
    if result[0] and result[1]:
        return (int(result[0]), int(result[1]))
    return (0, 0)


def get_rental_by_index(index: int) -> Optional[Dict]:
    """Получает объявление по индексу."""
    rentals = get_all_rentals()
    return rentals[index] if 0 <= index < len(rentals) else None


def clear_old_rentals(days: int = 7):
    """Удаляет объявления старше N дней."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        DELETE FROM rentals 
        WHERE datetime(parsed_at) < datetime('now', '-' || ? || ' days')
    ''', (days,))
    
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    
    logger.info(f"🗑️ Deleted {deleted} old rentals (older than {days} days)")
    return deleted


def get_last_parse_time() -> Optional[datetime]:
    """Получает время последнего парсинга."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT parsed_at FROM parse_log 
        ORDER BY parsed_at DESC LIMIT 1
    ''')
    
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return datetime.fromisoformat(result[0])
    return None


def get_rental_count() -> int:
    """Возвращает общее количество объявлений в БД."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM rentals')
    count = cursor.fetchone()[0]
    
    conn.close()
    return count


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully!")
