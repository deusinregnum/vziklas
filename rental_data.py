import requests
from bs4 import BeautifulSoup
import re
import time
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin
import logging
from database import save_rentals, log_parse, get_all_rentals, search_rentals_db, search_rentals_advanced, get_districts_db, get_price_range_db, get_rental_count

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "https://reality.bazos.sk"
HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}

REALTOR_KEYWORDS = [
    'real', 's.r.o', 'r.k.', 'remax', 'century', 'broker', 
    'sprostredkov', 'maklér', 'makler', 'agency', 'agentúr',
    'herrys', 'lexxus', 'expat', 'bonreality', 'provízi', 
    'v zastúpení', 'vo výhradnom', 'exkluzívne', 'impulz real',
    'adomis', 'foryou', 'ponúkame vám', 'legend.sk', 'zara reality'
]


def is_realtor(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(k.lower() in t for k in REALTOR_KEYWORDS)


def extract_price(text: str) -> int:
    if not text:
        return 0
    text = re.sub(r'\s+', '', text)
    m = re.search(r'(\d+)', text)
    if m:
        p = int(m.group(1))
        return p if 100 <= p <= 50000 else 0
    return 0


def extract_rooms(text: str) -> str:
    if not text:
        return "neuvedené"
    t = text.lower()
    if 'garsón' in t or 'garson' in t:
        return "garsónka"
    m = re.search(r'(\d)[,.]?5?\s*-?\s*izb', t)
    return f"{m.group(1)}-izbový" if m else "neuvedené"


def extract_size(text: str) -> str:
    m = re.search(r'(\d+)\s*m[²2]', text or '')
    return m.group(1) if m else "neuvedené"


def extract_district(text: str) -> str:
    if not text:
        return "Slovensko"
    t = text.lower()
    districts = {
        'bratislava': 'Bratislava', 'košice': 'Košice', 'kosice': 'Košice',
        'žilina': 'Žilina', 'prešov': 'Prešov', 'nitra': 'Nitra',
        'trnava': 'Trnava', 'trenčín': 'Trenčín', 'martin': 'Martin',
        'poprad': 'Poprad', 'zvolen': 'Zvolen', 'petržalka': 'Petržalka',
        'ružinov': 'Ružinov', 'michalovce': 'Michalovce',
    }
    for k, v in districts.items():
        if k in t:
            return v
    return "Slovensko"


def scrape_bazos(max_pages: int = 20) -> List[Dict]:
    all_rentals = []
    seen = set()
    session = requests.Session()
    session.headers.update(HEADERS)
    
    # ПРАВИЛЬНЫЙ URL: /prenajmu/byt/ (не /prenajom/byt/)
    base_url = "https://reality.bazos.sk/prenajmu/byt/"
    
    logger.info(f"Starting scraper, base URL: {base_url}")
    
    for page in range(max_pages):
        # Пагинация: /prenajmu/byt/, /prenajmu/byt/20/, /prenajmu/byt/40/
        url = base_url if page == 0 else f"{base_url}{page * 20}/"
        
        logger.info(f"Page {page + 1}: {url}")
        
        try:
            resp = session.get(url, timeout=15)
            resp.encoding = 'utf-8'
            
            if resp.status_code != 200:
                logger.error(f"HTTP {resp.status_code}, stopping")
                break
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            listings = soup.find_all('div', class_='inzeraty')
            
            if not listings:
                logger.info("No listings found, stopping")
                break
            
            count = 0
            for listing in listings:
                h2 = listing.find('h2', class_='nadpis')
                if not h2:
                    continue
                
                link = h2.find('a')
                if not link:
                    continue
                
                href = link.get('href', '')
                title = link.get_text(strip=True)
                
                if not href or not title:
                    continue
                
                full_url = urljoin(BASE_URL, href)
                if full_url in seen:
                    continue
                
                # Цена
                price = 0
                price_div = listing.find('div', class_='inzeratycena')
                if price_div:
                    price = extract_price(price_div.get_text())
                
                # Описание
                desc = ""
                popis = listing.find('div', class_='popis')
                if popis:
                    desc = popis.get_text(strip=True)
                
                # Локация
                loc = ""
                lok_div = listing.find('div', class_='inzeratylok')
                if lok_div:
                    loc = lok_div.get_text(strip=True).replace('\n', ', ')
                
                full_text = f"{title} {desc} {loc}"
                
                # Фильтр риелторов
                if is_realtor(full_text):
                    continue
                
                # Изображение
                img_url = None
                img = listing.find('img', class_='obrazek')
                if img:
                    img_url = img.get('src')
                
                rental = {
                    'name': title,
                    'price': price,
                    'district': extract_district(full_text),
                    'address': loc or "Slovensko",
                    'rooms': extract_rooms(full_text),
                    'size': extract_size(full_text),
                    'description': desc[:800] if desc else title,
                    'url': full_url,
                    'source': 'bazos.sk',
                    'available_from': 'Ihneď',
                    'image_url': img_url,
                }
                
                seen.add(full_url)
                all_rentals.append(rental)
                count += 1
            
            logger.info(f"  -> Added {count}, total: {len(all_rentals)}")
            
            if count == 0:
                logger.info("No new listings, stopping")
                break
            
            time.sleep(1)
            
        except Exception as e:
            logger.error(f"Error: {e}")
            break
    
    logger.info(f"DONE: {len(all_rentals)} rentals")
    return all_rentals


def get_rentals(force_refresh: bool = False) -> List[Dict]:
    """Получает объявления из БД (парсинг происходит по расписанию из бота)."""
    return get_all_rentals()


def search_rentals(search_type: str, value) -> List[Dict]:
    """Поиск в БД вместо прямого парсинга."""
    return search_rentals_db(search_type, value)


def search_rentals_combined(filters: Dict) -> List[Dict]:
    """Поиск с несколькими фильтрами одновременно."""
    return search_rentals_advanced(filters)


def get_rental_details(index: int) -> Optional[Dict]:
    """Получает деталь объявления из БД."""
    rentals = get_all_rentals()
    return rentals[index] if 0 <= index < len(rentals) else None


def get_districts() -> List[str]:
    """Получает список районов из БД."""
    return get_districts_db()


def get_price_range() -> Tuple[int, int]:
    """Получает диапазон цен из БД."""
    return get_price_range_db()


async def background_parse_rentals():
    """
    Функция для фонового парсинга (вызывается каждые 3 часа).
    Эта функция выполняется в фоне и не блокирует бота.
    """
    logger.info("🔄 Starting scheduled parse...")
    try:
        rentals = scrape_bazos(max_pages=15)
        if rentals:
            save_rentals(rentals)
            log_parse(len(rentals), "success")
            logger.info(f"✅ Successfully parsed and saved {len(rentals)} rentals")
        else:
            log_parse(0, "no_new_rentals")
            logger.warning("⚠️ No rentals found during parse")
    except Exception as e:
        logger.error(f"❌ Error during scheduled parse: {e}")
        log_parse(0, "error")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("BAZOS.SK SCRAPER TEST (Direct Parse)")
    print("="*60)
    
    rentals = scrape_bazos(max_pages=15)
    
    print(f"\nParsed: {len(rentals)} rentals")
    
    if rentals:
        print("\nSaving to database...")
        save_rentals(rentals)
        log_parse(len(rentals), "test")
        
        from database import get_all_rentals, get_price_range_db, get_districts_db
        all_rentals = get_all_rentals()
        print(f"\nTotal in DB: {len(all_rentals)} rentals")
        print(f"Price: €{get_price_range_db()[0]} - €{get_price_range_db()[1]}")
        print(f"Districts: {', '.join(get_districts_db()[:10])}")
        print("\nFirst 5 listings:")
        for i, r in enumerate(all_rentals[:5], 1):
            print(f"\n{i}. {r['name'][:55]}...")
            print(f"   €{r['price']} | {r['rooms']} | {r['district']}")
            print(f"   {r['url']}")
