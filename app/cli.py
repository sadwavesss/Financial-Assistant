"""Command-line utilities: `python -m app.cli <command> [options]` (see `--help`)."""

import argparse
import datetime as dt
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import BASE_DIR, DATA_DIR
from app.database import SessionLocal
from app.dependencies import get_rate_providers
from app.importers import get_importer
from app.services.analytics import Granularity
from app.services.categories import seed_default_categories
from app.services.categorization import recategorize_all, train_classifier
from app.services.categorization_eval import SCENARIO_LABELS, VARIANT_LABELS, evaluate
from app.services.demo_data import generate_demo_rows, write_demo_csv
from app.services.forecast import build_forecast
from app.services.imports import run_import

DEFAULT_DEMO_FILE = DATA_DIR / "samples" / "demo_transactions.csv"


def init_db(_args: argparse.Namespace) -> None:
    """Apply all migrations and create the default categories on an empty database."""
    command.upgrade(Config(str(BASE_DIR / "alembic.ini")), "head")
    with SessionLocal() as db:
        created = seed_default_categories(db)
    if created:
        print(f"База данных готова. Создано стартовых категорий: {created}.")
    else:
        print("База данных готова. Категории уже существуют, стартовый набор не добавлялся.")


def demo_data(args: argparse.Namespace) -> None:
    """Generate a demo CSV file and optionally import it into the database."""
    rows = generate_demo_rows(months=args.months, seed=args.seed, end=args.end)
    write_demo_csv(rows, args.output, with_categories=not args.without_categories)
    print(f"Сгенерировано операций: {len(rows)} за {args.months} мес. → {args.output}")
    if not args.load:
        return

    with SessionLocal() as db:
        for providers in get_rate_providers():
            report = run_import(db, args.output.read_bytes(), get_importer("csv"), providers)
    print(
        f"Импортировано: {report.created}, дубликатов пропущено: {report.duplicates}, "
        f"ошибок: {len(report.errors)}."
    )
    for error in report.errors[:10]:
        print(f"  строка {error.line}: {error.message}")


def train_categorizer(_args: argparse.Namespace) -> None:
    with SessionLocal() as db:
        classifier = train_classifier(db)
    info = classifier.info
    print(f"Модель обучена: {info.samples} операций, {info.classes} категорий ({info.trained_at}).")


def recategorize(_args: argparse.Namespace) -> None:
    with SessionLocal() as db:
        report = recategorize_all(db)
    print(
        f"Обработано: {report.processed}, изменилась категория: {report.changed}, "
        f"требуют проверки: {report.needs_review}."
    )


def evaluate_categorizer(args: argparse.Namespace) -> None:
    with SessionLocal() as db:
        report = evaluate(db, seed=args.seed)
    print(f"Размеченных операций: {report.samples}, seed={report.seed}")
    for scenario in report.scenarios:
        print(
            f"\n{SCENARIO_LABELS[scenario.scenario]} "
            f"(обучение {scenario.train_size}, тест {scenario.test_size})"
        )
        print(f"{'Вариант':16}{'Точность':>10}{'Покрытие':>10}{'Точн.покр.':>12}{'Macro-F1':>10}")
        for v in scenario.variants:
            print(
                f"{VARIANT_LABELS[v.variant]:16}{v.accuracy:>10.3f}{v.coverage:>10.3f}"
                f"{v.precision_covered:>12.3f}{v.macro_f1:>10.3f}"
            )


def forecast_expenses(args: argparse.Namespace) -> None:
    with SessionLocal() as db:
        report = build_forecast(db, Granularity(args.granularity), args.horizon)
    result = report.result
    print(f"Бэктест на {result.test_points} последних периодах ({len(report.history)} в истории):")
    print(f"{'Модель':26}{'MAE, BYN':>10}{'MAPE':>8}")
    for score in result.scores:
        mape = f"{score.mape:.1%}" if score.mape is not None else "—"
        mark = "  ← выбрана" if score is result.best else ""
        print(f"{score.label:26}{score.mae:>10.2f}{mape:>8}{mark}")
    print("\nПрогноз (80% интервал):")
    for point in report.points:
        print(f"  {point.label:12}{point.value:>10.2f}  [{point.lower:.2f} … {point.upper:.2f}]")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Финансовый ассистент")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init-db", help="применить миграции и создать стартовые категории")
    init.set_defaults(handler=init_db)

    demo = subparsers.add_parser("demo-data", help="сгенерировать демо-операции (CSV)")
    demo.add_argument("--months", type=int, default=12, help="за сколько месяцев (по умолчанию 12)")
    demo.add_argument("--seed", type=int, default=42, help="зерно генератора для воспроизводимости")
    demo.add_argument(
        "--end",
        type=dt.date.fromisoformat,
        default=None,
        help="последний день периода, ГГГГ-ММ-ДД (по умолчанию сегодня)",
    )
    demo.add_argument("--output", type=Path, default=DEFAULT_DEMO_FILE, help="путь к CSV-файлу")
    demo.add_argument(
        "--without-categories", action="store_true", help="не записывать столбец «Категория»"
    )
    demo.add_argument("--load", action="store_true", help="сразу импортировать файл в базу данных")
    demo.set_defaults(handler=demo_data)

    train = subparsers.add_parser("train-categorizer", help="обучить ML-модель категоризации")
    train.set_defaults(handler=train_categorizer)

    recat = subparsers.add_parser(
        "recategorize", help="перекатегоризировать операции без ручной категории"
    )
    recat.set_defaults(handler=recategorize)

    evaluation = subparsers.add_parser(
        "evaluate-categorizer", help="сравнить: только правила / только ML / гибрид"
    )
    evaluation.add_argument("--seed", type=int, default=42, help="зерно разбиения на выборки")
    evaluation.set_defaults(handler=evaluate_categorizer)

    fc = subparsers.add_parser("forecast", help="прогноз расходов и сравнение моделей")
    fc.add_argument("--granularity", choices=["month", "week"], default="month")
    fc.add_argument("--horizon", type=int, default=None, help="число периодов вперёд")
    fc.set_defaults(handler=forecast_expenses)
    return parser


def main(argv: list[str] | None = None) -> None:
    # Russian output must be readable even when stdout is redirected to a file on Windows.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    args.handler(args)


if __name__ == "__main__":
    main()
