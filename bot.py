import logging
import os
import sys
from pathlib import Path

# Загрузка .env файла
script_dir = Path(__file__).parent
env_path = script_dir / '.env'

BOT_TOKEN = None

if env_path.exists():
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()
                if key.strip() == 'TELEGRAM_BOT_TOKEN':
                    BOT_TOKEN = value.strip()

if not BOT_TOKEN:
    print("ERROR: TELEGRAM_BOT_TOKEN not found in .env file!")
    print(f"Checked path: {env_path}")
    sys.exit(1)

print(f"✅ Bot token loaded successfully")

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from rental_data import (
    get_rentals, search_rentals, get_rental_details, 
    get_districts, get_price_range, background_parse_rentals, search_rentals_combined
)
from database import init_db, get_rental_count, get_last_parse_time
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния диалога
SEARCH_TYPE, KEYWORD, ADVANCED_SEARCH, MULTI_FILTER_STATE = range(4)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Приветственное сообщение."""
    user = update.effective_user
    rental_count = get_rental_count()
    last_parse = get_last_parse_time()
    
    parse_time_text = "Нет данных"
    if last_parse:
        parse_time_text = last_parse.strftime("%H:%M") if last_parse else "Нет данных"
    
    welcome_text = f"""
🏠 <b>Vitajte v Bratislava Rental Finder!</b> 🏠

Ahoj {user.first_name}! Pomôžem vám nájsť byt v Bratislave z bazos.sk.

<b>� Momentálna stavy:</b>
• 📋 Dostupných: {rental_count} inzerátov
• 🕐 Posledná aktualizácia: {parse_time_text}

<i>Len súkromní vlastníci, bez realitiek!</i>
    """
    
    keyboard = [
        [InlineKeyboardButton("🔍 Vyhľadávanie s filtrami", callback_data="multi_filter_menu")],
        [InlineKeyboardButton("📖 Prehliadať všetky", callback_data="browse")],
        [InlineKeyboardButton("❤️ Obľúbené", callback_data="show_favorites")],
        [InlineKeyboardButton("🔄 Aktualizovať", callback_data="refresh_list")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="HTML")


async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Принудительное обновление данных."""
    await update.message.reply_text(
        "🔄 <b>Aktualizácia dát</b>\n\n"
        "Spúšťam parser... môže to trvať 1-2 minúty.\n"
        "Odoslú vám správu keď bude hotovo.",
        parse_mode="HTML"
    )
    
    try:
        await background_parse_rentals()
        rental_count = get_rental_count()
        await update.message.reply_text(
            f"✅ <b>Hotovo!</b>\n\n"
            f"Načítaných: {rental_count} inzerátov\n\n"
            f"Použite /browse pre zobrazenie.",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error refreshing: {e}")
        await update.message.reply_text(
            f"❌ Chyba pri aktualizácii:\n{str(e)}\n\n"
            "Skúste neskôr."
        )


async def browse(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать все квартиры."""
    # Определяем, это сообщение или callback
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        message = query.message
        edit_message = True
    else:
        message = update.message
        edit_message = False
    
    await message.reply_text("🔄 Načítavam inzeráty z bazos.sk...") if not edit_message else None
    
    rentals = get_rentals()
    
    if not rentals:
        text = "❌ Momentálne nie sú dostupné žiadne inzeráty.\n\nPoužite /refresh pre aktualizáciu."
        if edit_message:
            await query.edit_message_text(text)
        else:
            await message.reply_text(text)
        return
    
    # Сохраняем список в контекст для пагинации
    context.user_data['current_page'] = 0
    context.user_data['rentals_list'] = rentals
    
    await show_rentals_page(update, context, rentals, 0)


async def show_rentals_page(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                           rentals: list, page: int) -> None:
    """Показать страницу с квартирами."""
    items_per_page = 8
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_rentals = rentals[start_idx:end_idx]
    
    keyboard = []
    for rental in page_rentals:
        idx = rentals.index(rental)
        price_text = f"€{rental['price']}" if rental['price'] > 0 else "Cena dohodou"
        rooms_text = rental['rooms'][:10] if rental['rooms'] != "neuvedené" else ""
        
        button_text = f"🏢 {rental['name'][:25]}... | {price_text}"
        if rooms_text:
            button_text = f"🏢 {rental['name'][:20]}... | {rooms_text} | {price_text}"
        
        keyboard.append([InlineKeyboardButton(
            button_text,
            callback_data=f"rental_{idx}"
        )])
    
    # Навигация
    nav_buttons = []
    total_pages = (len(rentals) + items_per_page - 1) // items_per_page
    
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Späť", callback_data=f"page_{page-1}"))
    
    nav_buttons.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
    
    if end_idx < len(rentals):
        nav_buttons.append(InlineKeyboardButton("Ďalej ➡️", callback_data=f"page_{page+1}"))
    
    keyboard.append(nav_buttons)
    keyboard.append([InlineKeyboardButton("🔄 Aktualizovať", callback_data="refresh_list")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        f"🏘️ <b>Inzeráty z bazos.sk</b>\n"
        f"📊 Celkom: {len(rentals)} (bez realitiek)\n"
        f"📄 Strana {page+1} z {total_pages}\n\n"
        f"Kliknite pre detaily:"
    )
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, reply_markup=reply_markup, parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            text, reply_markup=reply_markup, parse_mode="HTML"
        )


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало поиска."""
    keyboard = [
        [InlineKeyboardButton("� Vyhľadávanie s filtrami (Cena + Lokalita)", callback_data="multi_filter_menu")],
        [InlineKeyboardButton("🔤 Podľa kľúčového slova", callback_data="search_keyword")],
        [InlineKeyboardButton("❌ Zrušiť", callback_data="cancel_search")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔍 <b>Vyhľadávanie</b>\n\nPodľa čoho chcete hľadať?",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )
    
    # Inicializujeme фильтры
    context.user_data['search_filters'] = {}
    context.user_data['multi_filters'] = {}
    
    return SEARCH_TYPE


async def district_selected_multi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора района в режиме многофильтра."""
    query = update.callback_query
    await query.answer()
    
    district = query.data.replace('dist_', '')
    context.user_data['multi_filters']['district'] = district
    await show_filter_selection(update, context)
    
    return MULTI_FILTER_STATE


async def multi_filter_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка текстового ввода в режиме многофильтрового поиска."""
    text = update.message.text.strip()
    step = context.user_data.get('filter_step', '')
    
    # Убедимся что фильтры инициализированы
    if 'multi_filters' not in context.user_data:
        context.user_data['multi_filters'] = {}
    
    if not step or step == 'select':
        # Если шаг не установлен, игнорируем
        return MULTI_FILTER_STATE
    
    if step == 'price':
        try:
            min_price = int(text)
            if min_price > 0:
                context.user_data['multi_filters']['min_price'] = min_price
            
            context.user_data['filter_step'] = 'max_price'
            await update.message.reply_text(
                "✅ Мин цена: €{}\n\n".format(min_price if min_price > 0 else "0") +
                "Макс цена (€) или 0 для пропуска:",
                parse_mode="HTML"
            )
            return MULTI_FILTER_STATE
        except ValueError:
            await update.message.reply_text("❌ Укажите число!")
            return MULTI_FILTER_STATE
    
    elif step == 'max_price':
        try:
            max_price = int(text)
            if max_price > 0:
                context.user_data['multi_filters']['max_price'] = max_price
            
            # Возвращаемся в меню
            context.user_data['filter_step'] = 'select'
            await show_filter_selection(update, context)
            return MULTI_FILTER_STATE
        except ValueError:
            await update.message.reply_text("❌ Укажите число!")
            return MULTI_FILTER_STATE
    
    return MULTI_FILTER_STATE


async def search_by_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Поиск по ключевому слову."""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🔤 <b>Vyhľadávanie podľa kľúčového slova</b>\n\n"
        "Zadajte kľúčové slovo (napr. 'balkón', 'parking', 'záhrada'):",
        parse_mode="HTML"
    )
    
    return KEYWORD


async def keyword_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ключевого слова."""
    keyword = update.message.text.strip()
    
    if len(keyword) < 2:
        await update.message.reply_text(
            "❌ Kľúčové slovo musí mať aspoň 2 znaky."
        )
        return KEYWORD
    
    results = search_rentals('keyword', keyword)
    
    if not results:
        await update.message.reply_text(
            f"❌ Nenašli sa žiadne inzeráty s: '{keyword}'"
        )
        return ConversationHandler.END
    
    await show_search_results(update, context, results, f"🔤 Kľúčové slovo: {keyword}")
    
    return ConversationHandler.END


async def multi_filter_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Интерактивное меню для выбора нескольких фильтров."""
    # Инициализируем фильтры правильно
    context.user_data['multi_filters'] = {}
    context.user_data['filter_step'] = 'select'
    
    await show_filter_selection(update, context)
    
    return MULTI_FILTER_STATE


async def show_filter_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать меню выбора фильтров."""
    filters = context.user_data.get('multi_filters', {})
    
    # Создаем текст с выбранными фильтрами
    filter_text = "🔍 <b>Vyhľadávanie s filtrami</b>\n\n"
    
    if 'min_price' in filters or 'max_price' in filters:
        min_p = filters.get('min_price', 0)
        max_p = filters.get('max_price', 50000)
        filter_text += f"💰 Cena: €{min_p}-€{max_p}\n"
    if 'district' in filters:
        filter_text += f"📍 Lokalita: {filters['district']}\n"
    
    if not any(k in filters for k in ['min_price', 'max_price', 'district']):
        filter_text += "Bez filtrů\n"
    
    # Создаем кнопки фильтров
    keyboard = [
        [InlineKeyboardButton("💰 Cena (od-do)", callback_data="set_price_range")],
        [InlineKeyboardButton("📍 Lokalita", callback_data="set_district")],
        [InlineKeyboardButton("🔍 HĽADAJ", callback_data="execute_multi_filter")],
        [InlineKeyboardButton("❌ Zrušiť", callback_data="cancel_multi_filter")],
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                filter_text, reply_markup=reply_markup, parse_mode="HTML"
            )
        except Exception as e:
            if "not modified" not in str(e).lower():
                raise
    else:
        await update.message.reply_text(
            filter_text, reply_markup=reply_markup, parse_mode="HTML"
        )


async def set_price_range(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Установить диапазон цен."""
    query = update.callback_query
    await query.answer()
    
    # Убедимся что фильтры инициализированы
    if 'multi_filters' not in context.user_data:
        context.user_data['multi_filters'] = {}
    
    context.user_data['filter_step'] = 'price'
    
    await query.edit_message_text(
        "💰 <b>Установка цены</b>\n\n"
        "Укажите минимальную цену (€) или напишите 0 для пропуска:",
        parse_mode="HTML"
    )
    
    return MULTI_FILTER_STATE


async def set_district(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Установить локацию."""
    query = update.callback_query
    await query.answer()
    
    # Убедимся что фильтры инициализированы
    if 'multi_filters' not in context.user_data:
        context.user_data['multi_filters'] = {}
    
    context.user_data['filter_step'] = 'district'
    
    districts = get_districts()
    keyboard = [[InlineKeyboardButton(d, callback_data=f"dist_{d}")] for d in districts[:10]]
    keyboard.append([InlineKeyboardButton("« Назад", callback_data="back_to_filters")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📍 <b>Выберите локацию</b>:",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )
    
    return MULTI_FILTER_STATE



async def search_advanced_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало расширенного поиска с несколькими фильтрами."""
    query = update.callback_query
    await query.answer()
    
    # Инициализируем фильтры
    context.user_data['search_filters'] = {}
    
    await query.edit_message_text(
        "⚙️ <b>Покročilé vyhľadávanie</b>\n\n"
        "Nastavit budeme filtre postupně:\n"
        "1️⃣ Cena (voliteľné)\n"
        "2️⃣ Lokalita (voliteľné)\n"
        "3️⃣ Kľúčové slovo (voliteľné)\n\n"
        "Zadajte minimálnu cenu (alebo napíšte 0 pre preskočenie):",
        parse_mode="HTML"
    )
    
    return ADVANCED_SEARCH


async def advanced_search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Obrada rozšíreného hledání."""
    text = update.message.text.strip()
    
    # Určit v kterém kroku jsme
    step = context.user_data.get('advanced_step', 0)
    
    if step == 0:  # Minimálna cena
        try:
            min_price = int(text)
            if min_price > 0:
                context.user_data['search_filters']['min_price'] = min_price
            else:
                context.user_data['search_filters']['min_price'] = 0  # Bez minimálnej ceny
            context.user_data['advanced_step'] = 1
            
            await update.message.reply_text(
                "✅ Cena od: €{}\n\n".format(min_price if min_price > 0 else "Žiadna minimálna") +
                "Zadajte maximálnu cenu (alebo napíšte 0 pre preskočenie):",
                parse_mode="HTML"
            )
            return ADVANCED_SEARCH
        except ValueError:
            await update.message.reply_text("❌ Zadajte číslo!")
            return ADVANCED_SEARCH
    
    elif step == 1:  # Maximálna cena
        try:
            max_price = int(text)
            if max_price > 0:
                context.user_data['search_filters']['max_price'] = max_price
            else:
                context.user_data['search_filters']['max_price'] = 50000  # Bez maximálnej ceny
            context.user_data['advanced_step'] = 2
            
            await update.message.reply_text(
                "✅ Cena do: €{}\n\n".format(max_price if max_price > 0 else "Bez limitu") +
                "Zadajte lokalitu (napr. 'Bratislava') alebo napíšte '-' pre preskočenie:",
                parse_mode="HTML"
            )
            return ADVANCED_SEARCH
        except ValueError:
            await update.message.reply_text("❌ Zadajte číslo!")
            return ADVANCED_SEARCH
    
    elif step == 2:  # Lokalita
        if text != "-":
            context.user_data['search_filters']['district'] = text
        context.user_data['advanced_step'] = 3
        
        await update.message.reply_text(
            "✅ Lokalita: {}\n\n".format(text if text != "-" else "Všetky") +
            "Zadajte kľúčové slovo (napr. 'balkón') alebo napíšte '-' pre vyhľadávanie:",
            parse_mode="HTML"
        )
        return ADVANCED_SEARCH
    
    elif step == 3:  # Kľúčové slovo a spustenie vyhľadávania
        if text != "-":
            context.user_data['search_filters']['keyword'] = text
        
        # Vyhľadávání
        filters = context.user_data.get('search_filters', {})
        results = search_rentals_combined(filters)
        
        if not results:
            await update.message.reply_text(
                "❌ Nenašli sa žiadne inzeráty podľa vašich kritérií."
            )
            return ConversationHandler.END
        
        # Vytvoření textu s použitými filtry
        filter_text = "⚙️ Pokročilé vyhľadávanie:\n"
        if 'min_price' in filters or 'max_price' in filters:
            min_p = filters.get('min_price', 0)
            max_p = filters.get('max_price', 50000)
            filter_text += f"💰 Cena: €{min_p} - €{max_p}\n"
        if 'district' in filters:
            filter_text += f"📍 Lokalita: {filters['district']}\n"
        if 'keyword' in filters:
            filter_text += f"🔤 Slovo: {filters['keyword']}\n"
        filter_text += f"\n📊 Nájdeno: {len(results)} inzerátov"
        
        await show_search_results(update, context, results, filter_text)
        return ConversationHandler.END


async def show_search_results(update: Update, context: ContextTypes.DEFAULT_TYPE,
                             results: list, filter_text: str) -> None:
    """Показать результаты поиска с пагинацией."""
    # Сохраняем результаты для пагинации
    context.user_data['search_results'] = results
    context.user_data['search_filter_text'] = filter_text
    context.user_data['search_page'] = 0
    
    await show_search_results_page(update, context, results, filter_text, 0)


async def show_search_results_page(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                  results: list, filter_text: str, page: int) -> None:
    """Показать страницу результатов поиска с пагинацией."""
    rentals = get_rentals()
    items_per_page = 10
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    page_results = results[start_idx:end_idx]
    
    keyboard = []
    for rental in page_results:
        try:
            idx = rentals.index(rental)
            price_text = f"€{rental['price']}" if rental['price'] > 0 else "Dohodou"
            keyboard.append([InlineKeyboardButton(
                f"🏢 {rental['name'][:25]}... | {price_text}",
                callback_data=f"rental_{idx}"
            )])
        except ValueError:
            continue
    
    # Навигация по результатам
    nav_buttons = []
    total_pages = (len(results) + items_per_page - 1) // items_per_page
    
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Späť", callback_data=f"search_page_{page-1}"))
    
    nav_buttons.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
    
    if end_idx < len(results):
        nav_buttons.append(InlineKeyboardButton("Ďalej ➡️", callback_data=f"search_page_{page+1}"))
    
    keyboard.append(nav_buttons)
    keyboard.append([InlineKeyboardButton("« Späť na zoznam", callback_data="back_to_list")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        f"✅ <b>Výsledky vyhľadávania</b>\n\n"
        f"🔍 {filter_text}\n"
        f"📊 Nájdených: {len(results)} inzerátov\n"
        f"📄 Strana {page+1} z {total_pages}"
    )
    
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text, reply_markup=reply_markup, parse_mode="HTML"
            )
        except Exception as e:
            if "not modified" in str(e).lower():
                await update.callback_query.answer()
            else:
                raise
    else:
        await update.message.reply_text(
            text, reply_markup=reply_markup, parse_mode="HTML"
        )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка нажатий кнопок."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "noop":
        return
    
    if data == "browse":
        rentals = get_rentals()
        context.user_data['rentals_list'] = rentals
        context.user_data['current_page'] = 0
        await show_rentals_page(update, context, rentals, 0)
        return
    
    if data == "cancel_search":
        await query.edit_message_text("❌ Vyhľadávanie zrušené.")
        return
    
    if data == "multi_filter_menu":
        await multi_filter_menu(update, context)
        return
    
    if data == "search_advanced":
        await search_advanced_handler(update, context)
        return
    
    if data == "back_to_filters":
        await show_filter_selection(update, context)
        return
    
    if data == "cancel_multi_filter":
        await query.edit_message_text("❌ Поиск отменен.")
        return
    
    if data == "set_price_range":
        await update.callback_query.answer()
        await set_price_range(update, context)
        return
    
    if data == "set_district":
        await update.callback_query.answer()
        await set_district(update, context)
        return
    
    if data.startswith("dist_"):
        district = data.split("dist_", 1)[1]
        context.user_data['multi_filters']['district'] = district
        await show_filter_selection(update, context)
        return
    
    if data == "execute_multi_filter":
        filters = context.user_data.get('multi_filters', {})
        results = search_rentals_combined(filters)
        
        # Создаем текст с примененными фильтрами
        filter_desc = []
        if 'min_price' in filters:
            filter_desc.append(f"€{filters['min_price']}")
        if 'max_price' in filters:
            filter_desc.append(f"до €{filters['max_price']}")
        if 'district' in filters:
            filter_desc.append(f"в {filters['district']}")
        if 'keyword' in filters:
            filter_desc.append(f"'{filters['keyword']}'")
        
        filter_text = " + ".join(filter_desc) if filter_desc else "Без фильтров"
        
        if results:
            await show_search_results(update, context, results, f"🔍 {filter_text}")
        else:
            await query.edit_message_text(
                f"❌ <b>Результаты не найдены</b>\n\n🔍 {filter_text}",
                parse_mode="HTML"
            )
        return
    
    if data == "back_to_list" or data == "back_to_rentals":
        rentals = get_rentals()
        page = context.user_data.get('current_page', 0)
        await show_rentals_page(update, context, rentals, page)
        return
    
    if data == "show_favorites":
        favorites = context.user_data.get('favorites', [])
        if not favorites:
            await query.edit_message_text("❌ У вас нет сохраненных объявлений")
            return
        rentals = get_rentals()
        favorite_rentals = [r for i, r in enumerate(rentals) if i in favorites]
        if favorite_rentals:
            context.user_data['rentals_list'] = favorite_rentals
            context.user_data['current_page'] = 0
            await show_rentals_page(update, context, favorite_rentals, 0)
        else:
            await query.edit_message_text("❌ Нет сохраненных объявлений")
        return
    
    if data == "refresh_list":
        await query.edit_message_text("🔄 Aktualizujem...")
        rentals = get_rentals(force_refresh=True)
        context.user_data['rentals_list'] = rentals
        context.user_data['current_page'] = 0
        await show_rentals_page(update, context, rentals, 0)
        return
    
    if data.startswith("page_"):
        page = int(data.split("_")[1])
        context.user_data['current_page'] = page
        rentals = context.user_data.get('rentals_list', get_rentals())
        await show_rentals_page(update, context, rentals, page)
        return
    
    if data.startswith("search_page_"):
        page = int(data.split("_")[2])
        results = context.user_data.get('search_results', [])
        filter_text = context.user_data.get('search_filter_text', "")
        await show_search_results_page(update, context, results, filter_text, page)
        return
    
    if data.startswith("rental_"):
        await show_rental_details(update, context, data)
        return
    
    if data.startswith("fav_"):
        await toggle_favorite(update, context, data)
        return


async def show_rental_details(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                              data: str) -> None:
    """Показать детали квартиры."""
    query = update.callback_query
    rentals = get_rentals()
    
    try:
        rental_idx = int(data.split("_")[1])
        rental = rentals[rental_idx]
        
        price_text = f"€{rental['price']}/mesiac" if rental['price'] > 0 else "Cena dohodou"
        
        details_text = f"""
🏢 <b>{rental['name']}</b>

📍 <b>Lokalita:</b> {rental['district']}
🏠 <b>Adresa:</b> {rental['address']}
💰 <b>Cena:</b> {price_text}
🛏️ <b>Izby:</b> {rental['rooms']}
📐 <b>Rozloha:</b> {rental['size']} m²
📅 <b>Dostupné:</b> {rental['available_from']}

<b>Popis:</b>
{rental['description'][:800]}{'...' if len(rental['description']) > 800 else ''}

<i>🔗 Zdroj: {rental['source']}</i>
        """
        
        # Проверяем, в избранном ли
        favorites = context.user_data.get('favorites', [])
        fav_text = "💔 Odstrániť z obľúbených" if rental_idx in favorites else "❤️ Pridať do obľúbených"
        
        keyboard = [
            [InlineKeyboardButton("🔗 Otvoriť na bazos.sk", url=rental['url'])],
            [InlineKeyboardButton(fav_text, callback_data=f"fav_{rental_idx}")],
            [InlineKeyboardButton("« Späť", callback_data="back_to_list")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text=details_text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        
    except (IndexError, ValueError) as e:
        logger.error(f"Error showing rental details: {e}")
        await query.edit_message_text(
            "❌ Chyba pri načítaní detailov. Skúste /browse."
        )


async def toggle_favorite(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                         data: str) -> None:
    """Добавить/удалить из избранного."""
    query = update.callback_query
    
    try:
        rental_idx = int(data.split("_")[1])
        
        if "favorites" not in context.user_data:
            context.user_data["favorites"] = []
        
        if rental_idx in context.user_data["favorites"]:
            context.user_data["favorites"].remove(rental_idx)
            await query.answer("💔 Odstránené z obľúbených")
        else:
            context.user_data["favorites"].append(rental_idx)
            await query.answer("❤️ Pridané do obľúbených!")
        
        # Обновляем сообщение с новой кнопкой
        await show_rental_details(update, context, f"rental_{rental_idx}")
        
    except (ValueError, IndexError) as e:
        logger.error(f"Error toggling favorite: {e}")
        await query.answer("❌ Chyba")


async def favorites(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать избранное."""
    if "favorites" not in context.user_data or not context.user_data["favorites"]:
        await update.message.reply_text(
            "❤️ <b>Vaše obľúbené</b>\n\n"
            "Zatiaľ nemáte žiadne uložené inzeráty.\n"
            "Použite /browse a pridajte si obľúbené!",
            parse_mode="HTML"
        )
        return
    
    rentals = get_rentals()
    keyboard = []
    valid_favorites = []
    
    for fav_idx in context.user_data["favorites"]:
        if fav_idx < len(rentals):
            rental = rentals[fav_idx]
            price_text = f"€{rental['price']}" if rental['price'] > 0 else "Dohodou"
            keyboard.append([InlineKeyboardButton(
                f"❤️ {rental['name'][:25]}... | {price_text}",
                callback_data=f"rental_{fav_idx}"
            )])
            valid_favorites.append(fav_idx)
    
    # Обновляем список избранного (удаляем несуществующие)
    context.user_data["favorites"] = valid_favorites
    
    if not keyboard:
        await update.message.reply_text(
            "❤️ Vaše obľúbené sú prázdne alebo už nie sú dostupné."
        )
        return
    
    keyboard.append([InlineKeyboardButton("🗑️ Vymazať všetky", callback_data="clear_favorites")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"❤️ <b>Vaše obľúbené inzeráty</b>\n\n"
        f"Máte {len(valid_favorites)} uložených:",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Помощь."""
    help_text = """
🆘 <b>Pomocník</b>

<b>Príkazy:</b>
/start - Uvítacia správa
/browse - Zobraziť všetky inzeráty
/search - Vyhľadávanie podľa kritérií
/refresh - Aktualizovať dáta z bazos.sk
/favorites - Vaše uložené inzeráty
/help - Tento pomocník

<b>Ako to funguje:</b>
1. Bot parsuje reality.bazos.sk
2. Automaticky filtruje realitné kancelárie
3. Zobrazuje iba súkromné inzeráty
4. Každý inzerát má priamy odkaz na bazos.sk

<b>Vyhľadávanie:</b>
• 💰 Podľa ceny - zadáte min/max cenu
• 📍 Podľa lokality - vyberiete mestskú časť
• 🔤 Podľa slova - hľadáte v popisoch

<b>Tipy:</b>
• Dáta sa automaticky aktualizujú každých 5 minút
• Použite /refresh pre okamžitú aktualizáciu
• Ukladajte si obľúbené inzeráty ❤️
• Kliknite na "Otvoriť na bazos.sk" pre kontakt

<b>Filtrované kľúčové slová:</b>
<i>reality, r.k., broker, maklér, agentúra, provízia...</i>

Všetky inzeráty sú od súkromných osôb! 🏠
    """
    await update.message.reply_text(help_text, parse_mode="HTML")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена."""
    await update.message.reply_text(
        "❌ Vyhľadávanie zrušené.\n\n"
        "Použite /browse pre zobrazenie inzerátov."
    )
    return ConversationHandler.END


def main() -> None:
    """Запуск бота с фоновым парсингом."""
    # Инициализируем БД
    init_db()
    
    application = Application.builder().token(BOT_TOKEN).build()

    # Создаём планировщик для фонового парсинга
    scheduler = AsyncIOScheduler()
    
    # Добавляем задачу парсинга каждые 3 часа
    scheduler.add_job(
        background_parse_rentals,
        "interval",
        hours=3,
        id="parse_job",
        name="Parse rentals every 3 hours",
        replace_existing=True
    )
    
    # Инициализация при запуске
    async def startup(app):
        logger.info("🤖 Bot starting...")
        rental_count = get_rental_count()
        logger.info(f"✅ БД загружена: {rental_count} объявлений")
        scheduler.start()
        logger.info("✅ Scheduler started (парсинг каждые 3 часа)")
    
    async def shutdown(app):
        logger.info("👋 Bot shutting down...")
        scheduler.shutdown()
        logger.info("✅ Scheduler stopped")
    
    application.post_init = startup
    application.post_stop = shutdown
    
    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("browse", browse))
    application.add_handler(CommandHandler("refresh", refresh))
    application.add_handler(CommandHandler("favorites", favorites))
    application.add_handler(CommandHandler("help", help_command))
    
    # Обработчик поиска (ConversationHandler)
    search_handler = ConversationHandler(
        entry_points=[CommandHandler("search", search)],
        states={
            SEARCH_TYPE: [
                CallbackQueryHandler(search_by_keyword, pattern="^search_keyword$"),
                CallbackQueryHandler(cancel, pattern="^cancel_search$"),
            ],
            KEYWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, keyword_handler)
            ],
            ADVANCED_SEARCH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, advanced_search_handler)
            ],
            MULTI_FILTER_STATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, multi_filter_text_handler),
                CallbackQueryHandler(district_selected_multi, pattern="^dist_")
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    application.add_handler(search_handler)

    # Обработчик кнопок
    application.add_handler(CallbackQueryHandler(button_callback))

    # Запуск
    print("\n" + "="*60)
    print("🤖 BRATISLAVA RENTAL FINDER BOT")
    print("="*60)
    print("📊 Дата: reality.bazos.sk")
    print("🚫 Фильтр: риелторы и агентства исключены")
    print("🔄 Автоматический парсинг: каждые 3 часа")
    print("="*60)
    print("\nBот работает... Нажмите Ctrl+C чтобы остановить\n")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()