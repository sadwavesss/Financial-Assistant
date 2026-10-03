"""Initial set of categories with keyword rules, tuned for Belarusian shops and services.

Keywords are matched against the transaction description in stage 4 (categorization).
Both Cyrillic and Latin spellings are listed because bank statements often use Latin.
"""

from dataclasses import dataclass

from app.models.enums import TransactionType

EXPENSE = TransactionType.EXPENSE
INCOME = TransactionType.INCOME


@dataclass(frozen=True)
class DefaultCategory:
    name: str
    type: TransactionType
    color: str
    keywords: tuple[str, ...] = ()
    # System categories are fallbacks for uncategorized operations and cannot be deleted.
    is_system: bool = False


# Compact layout is easier to read for a data table, so the formatter is disabled here.
# fmt: off
DEFAULT_CATEGORIES: tuple[DefaultCategory, ...] = (
    # --- Expenses ---
    DefaultCategory(
        "Продукты", EXPENSE, "#2e7d32",
        (
            "евроопт", "evroopt", "гиппо", "hippo", "gippo", "корона", "korona", "санта", "santa",
            "соседи", "sosedi", "белмаркет", "belmarket", "грин", "green", "алми", "almi",
            "виталюр", "vitalur", "рублевский", "rublevski", "простор", "prostor",
            "доброном", "dobronom", "копеечка", "kopeechka", "хит экспресс", "hit express",
            "е-доставка", "edostavka", "продукты",
        ),
    ),
    DefaultCategory(
        "Кафе и рестораны", EXPENSE, "#ef6c00",
        (
            "кафе", "cafe", "ресторан", "restaurant", "кофейня", "coffee", "макдональдс",
            "mcdonalds", "вкусно и точка", "kfc", "бургер кинг", "burger king", "пицца", "pizza",
            "domino", "лидо", "lido", "суши", "sushi", "wolt", "яндекс еда", "yandex eda",
            "delivio",
        ),
    ),
    DefaultCategory(
        "Транспорт", EXPENSE, "#1565c0",
        (
            "такси", "taxi", "yandex go", "яндекс go", "uber", "убер", "метрополитен",
            "metro minsk", "минсктранс", "minsktrans", "проездной", "белорусская железная дорога",
            "rw.by", "автобус", "маршрутка", "atlasbus",
        ),
    ),
    DefaultCategory(
        "Автомобиль", EXPENSE, "#455a64",
        (
            "азс", "белоруснефть", "belorusneft", "лукойл", "lukoil", "газпромнефть", "gazpromneft",
            "а-100", "a-100", "топливо", "бензин", "автомойка", "шиномонтаж", "парковка", "parking",
            "автозапчасти",
        ),
    ),
    DefaultCategory(
        "Жильё и ЖКУ", EXPENSE, "#6d4c41",
        (
            "жку", "коммунальные", "квартплата", "аренда квартиры", "энергосбыт", "минскэнерго",
            "электроэнергия", "водоканал", "теплосеть", "газоснабжение", "жэс",
        ),
    ),
    DefaultCategory(
        "Связь и интернет", EXPENSE, "#00838f",
        (
            "мтс", "mts", "a1", "а1", "life:)", "лайф", "byfly", "белтелеком", "beltelecom",
            "интернет",
        ),
    ),
    DefaultCategory(
        "Здоровье", EXPENSE, "#c62828",
        (
            "аптека", "apteka", "белфармация", "лекарства", "поликлиника", "стоматология",
            "медцентр", "лодэ", "lode", "анализы",
        ),
    ),
    DefaultCategory(
        "Одежда и обувь", EXPENSE, "#ad1457",
        (
            "одежда", "обувь", "zara", "h&m", "lc waikiki", "марко", "marko", "mark formelle",
            "conte", "sportmaster", "спортмастер", "befree", "gloria jeans",
        ),
    ),
    DefaultCategory(
        "Красота и уход", EXPENSE, "#8e24aa",
        (
            "мила", "mila", "остров чистоты", "ostrov chistoty", "косметика", "парикмахерская",
            "барбершоп", "barbershop", "салон красоты", "маникюр",
        ),
    ),
    DefaultCategory(
        "Дом и быт", EXPENSE, "#795548",
        (
            "oma", "ома", "21vek", "21 век", "электросила", "мебель", "хозтовары", "ikea",
            "бытовая техника", "5 элемент",
        ),
    ),
    DefaultCategory(
        "Маркетплейсы", EXPENSE, "#f9a825",
        (
            "wildberries", "вайлдберриз", "ozon", "озон", "aliexpress", "алиэкспресс", "kufar",
            "куфар", "joom", "lamoda",
        ),
    ),
    DefaultCategory(
        "Развлечения и досуг", EXPENSE, "#5e35b1",
        (
            "кинотеатр", "silver screen", "mooon", "театр", "концерт", "боулинг", "бильярд",
            "steam", "playstation", "аквапарк", "музей",
        ),
    ),
    DefaultCategory(
        "Подписки и сервисы", EXPENSE, "#3949ab",
        (
            "netflix", "spotify", "youtube premium", "яндекс плюс", "yandex plus", "кинопоиск",
            "kinopoisk", "ivi", "okko", "apple.com", "icloud", "google one", "google play",
            "openai", "chatgpt", "telegram premium",
        ),
    ),
    DefaultCategory(
        "Образование", EXPENSE, "#00695c",
        (
            "обучение", "курсы", "оплата обучения", "университет", "бгу", "бгуир", "учебник",
            "coursera", "udemy", "skillbox", "stepik",
        ),
    ),
    DefaultCategory("Прочие расходы", EXPENSE, "#757575", is_system=True),
    # --- Income ---
    DefaultCategory(
        "Зарплата", INCOME, "#1b5e20",
        ("зарплата", "заработная плата", "аванс", "salary", "премия"),
    ),
    DefaultCategory("Стипендия", INCOME, "#0277bd", ("стипендия",)),
    DefaultCategory(
        "Переводы и подарки", INCOME, "#6a1b9a",
        ("перевод от", "поступление перевода", "подарок"),
    ),
    DefaultCategory(
        "Кэшбэк и проценты", INCOME, "#ff8f00",
        ("кэшбэк", "кешбэк", "cashback", "проценты по вкладу", "капитализация"),
    ),
    DefaultCategory("Прочие доходы", INCOME, "#9e9e9e", is_system=True),
)
# fmt: on
