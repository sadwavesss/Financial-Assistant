"""Generator of realistic demo transactions (a student's budget in Minsk).

The data is reproducible (fixed random seed) and labeled: every row carries its true category.
It is used for demonstrations and as a labeled dataset to evaluate the categorizer (stage 4).
Some descriptions intentionally contain no keyword from the default rules ("ИП Петров"),
so that the machine learning component has something to learn beyond the rules.
"""

import calendar
import csv
import datetime as dt
import random
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from app.models import Currency, TransactionType

EXPENSE, INCOME = TransactionType.EXPENSE, TransactionType.INCOME
USD = Currency.USD


@dataclass(frozen=True)
class DemoRow:
    date: dt.date
    type: TransactionType
    amount: Decimal
    currency: Currency
    description: str
    category: str  # ground-truth label


@dataclass(frozen=True)
class Habit:
    """A kind of spending that happens several times a month at varying places and prices."""

    category: str
    descriptions: tuple[str, ...]
    per_month: tuple[int, int]  # min/max number of operations per month
    amount: tuple[float, float]  # min/max amount
    currency: Currency = Currency.BYN
    # Multipliers of the number of operations by month (1-12); missing months = 1.
    season: tuple[tuple[int, float], ...] = ()
    type: TransactionType = EXPENSE


@dataclass(frozen=True)
class Monthly:
    """A regular payment or income on a fixed day of every month."""

    category: str
    type: TransactionType
    description: str
    day: int
    amount: tuple[float, float]
    currency: Currency = Currency.BYN


# Data tables are easier to read in a compact layout, so the formatter is disabled here.
# fmt: off
MONTHLY = (
    Monthly("Зарплата", INCOME, "Заработная плата ООО «Софтлайн»", 5, (2150, 2350)),
    Monthly("Зарплата", INCOME, "Аванс по заработной плате", 20, (900, 1000)),
    Monthly("Стипендия", INCOME, "Стипендия БГУИР", 25, (150, 150)),
    Monthly("Кэшбэк и проценты", INCOME, "Кэшбэк за покупки", 28, (3, 15)),
    Monthly("Жильё и ЖКУ", EXPENSE, "Оплата ЖКУ, ЕРИП", 10, (95, 140)),
    Monthly("Связь и интернет", EXPENSE, "МТС, мобильная связь", 12, (25.90, 25.90)),
    Monthly("Связь и интернет", EXPENSE, "BYFLY Белтелеком", 15, (32.00, 32.00)),
    Monthly("Транспорт", EXPENSE, "Проездной Минсктранс", 1, (45.00, 45.00)),
    Monthly("Подписки и сервисы", EXPENSE, "Яндекс Плюс", 3, (9.99, 9.99)),
    Monthly("Подписки и сервисы", EXPENSE, "OPENAI *CHATGPT SUBSCR", 18, (20.00, 20.00), USD),
    Monthly("Подписки и сервисы", EXPENSE, "APPLE.COM/BILL iCloud", 7, (0.99, 0.99), USD),
)

HABITS = (
    Habit(
        "Продукты",
        ("Евроопт", "EVROOPT MINSK", "Гиппо", "GIPPO TC", "Корона", "Санта, магазин", "Соседи",
         "ГРИН, гипермаркет", "Алми", "Доброном", "ИП Петров, магазин у дома", "ОДО «Фермер»"),
        (12, 18), (8, 95), season=((12, 1.3),),
    ),
    Habit(
        "Кафе и рестораны",
        ("Кофейня «Зерно»", "COFFEE BREAK", "Вкусно и точка", "KFC", "Пицца Темпо",
         "Domino's Pizza", "Суши Весла", "Wolt", "Лидо", "OOO KOFEMANIYA", "Столовая БГУИР"),
        (5, 10), (5, 40), season=((6, 1.3), (7, 1.4), (8, 1.3), (12, 1.4)),
    ),
    Habit(
        "Транспорт",
        ("Яндекс Go, такси", "YANDEX.GO", "Uber", "Атлас, автобус Минск—Гродно"),
        (2, 5), (5, 22),
    ),
    Habit(
        "Здоровье",
        ("Аптека №12", "APTEKA BELFARMACIYA", "ЛОДЭ, медцентр", "Стоматология «Дента»"),
        (1, 2), (8, 120), season=((1, 1.5), (2, 1.5), (11, 1.3)),
    ),
    Habit(
        "Одежда и обувь",
        ("ZARA", "Марко, обувь", "Mark Formelle", "LC Waikiki", "Спортмастер", "ООО «Модный дом»"),
        (0, 2), (40, 220), season=((3, 1.6), (9, 1.8), (12, 1.5)),
    ),
    Habit(
        "Красота и уход",
        ("Мила", "Остров чистоты", "Барбершоп «Борода»", "ИП Сидорова, парикмахер"),
        (1, 2), (10, 60),
    ),
    Habit(
        "Дом и быт",
        ("OMA", "21vek.by", "Электросила", "IKEA"),
        (0, 2), (15, 180),
    ),
    Habit(
        "Маркетплейсы",
        ("Wildberries", "OZON.BY", "Kufar, покупка"),
        (1, 3), (15, 120), season=((11, 1.5), (12, 1.8)),
    ),
    Habit(
        "Маркетплейсы",
        ("AliExpress",),
        (0, 1), (5, 40), Currency.USD, season=((11, 2.0),),
    ),
    Habit(
        "Развлечения и досуг",
        ("Silver Screen, кинотеатр", "Mooon", "Боулинг «Галактика»", "Steam", "Купаловский театр"),
        (1, 3), (10, 60), season=((6, 1.4), (7, 1.5), (8, 1.4), (12, 1.3)),
    ),
    Habit(
        "Образование",
        ("Stepik, онлайн-курс", "Учебник, книжный «Белкнига»", "Coursera"),
        (0, 1), (15, 90), season=((9, 2.0), (2, 1.5)),
    ),
    Habit(
        "Переводы и подарки",
        ("Перевод от Иванова И.", "Подарок от родителей"),
        (0, 1), (50, 300), type=INCOME,
    ),
)
# fmt: on


def generate_demo_rows(
    months: int = 12, seed: int = 42, end: dt.date | None = None
) -> list[DemoRow]:
    """Reproducible operations for `months` full months ending with the month of `end`."""
    rng = random.Random(seed)
    end = end or dt.date.today()
    rows: list[DemoRow] = []
    for year, month in _months_back(end, months):
        last_day = calendar.monthrange(year, month)[1]
        for item in MONTHLY:
            rows.append(
                DemoRow(
                    date=dt.date(year, month, min(item.day, last_day)),
                    type=item.type,
                    amount=_money(rng, item.amount),
                    currency=item.currency,
                    description=item.description,
                    category=item.category,
                )
            )
        for habit in HABITS:
            factor = dict(habit.season).get(month, 1.0)
            for _ in range(round(rng.randint(*habit.per_month) * factor)):
                rows.append(
                    DemoRow(
                        date=dt.date(year, month, rng.randint(1, last_day)),
                        type=habit.type,
                        amount=_money(rng, habit.amount),
                        currency=habit.currency,
                        description=rng.choice(habit.descriptions),
                        category=habit.category,
                    )
                )
    rows = [row for row in rows if row.date <= end]  # no operations in the future
    rows.sort(key=lambda row: (row.date, row.description))
    return rows


def write_demo_csv(rows: list[DemoRow], path: Path, with_categories: bool = True) -> None:
    """Save rows in the application's CSV template (";" separator, UTF-8 with BOM for Excel)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    header = ["Дата", "Тип", "Сумма", "Валюта", "Описание"] + (
        ["Категория"] if with_categories else []
    )
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file, delimiter=";")
        writer.writerow(header)
        for row in rows:
            values = [
                row.date.strftime("%d.%m.%Y"),
                "доход" if row.type is INCOME else "расход",
                f"{row.amount:.2f}".replace(".", ","),
                row.currency.value,
                row.description,
            ]
            writer.writerow(values + ([row.category] if with_categories else []))


def _months_back(end: dt.date, months: int) -> list[tuple[int, int]]:
    """(year, month) pairs of the last `months` months, oldest first, including `end`'s month."""
    index = end.year * 12 + end.month - 1
    return [(i // 12, i % 12 + 1) for i in range(index - months + 1, index + 1)]


def _money(rng: random.Random, bounds: tuple[float, float]) -> Decimal:
    value = Decimal(str(rng.uniform(*bounds)))
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
