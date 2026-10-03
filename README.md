# Финансовый ассистент

Интеллектуальный ассистент для анализа и прогнозирования личных финансов: учёт доходов и
расходов, импорт операций из файла, автоматическая категоризация, аналитика с графиками,
поиск повторяющихся платежей, прогноз расходов методами машинного обучения и рекомендации
по планированию бюджета.

## Технологии

| Слой | Технология |
|---|---|
| Веб-фреймворк | FastAPI, Uvicorn |
| Интерфейс | Jinja2, Bootstrap 5, Chart.js (локально, без CDN) |
| База данных | SQLAlchemy 2.0, Alembic, SQLite (с возможностью перехода на PostgreSQL) |
| Анализ и ML | pandas, scikit-learn, statsmodels |
| Курсы валют | API Национального банка Республики Беларусь |
| Качество кода | pytest, ruff |

## Структура проекта

```
app/
  main.py          точка входа, сборка приложения
  config.py        настройки (переменные окружения, .env)
  database.py      подключение к БД, сессии
  models/          ORM-модели (таблицы БД)
  api/             REST API (JSON), документация на /docs
  web/             HTML-страницы
  templates/       шаблоны Jinja2
  static/          CSS, JS, сторонние библиотеки (vendor/)
migrations/        миграции схемы БД (Alembic)
data/              файл БД и прочие данные времени выполнения (не хранится в git)
tests/             автоматические тесты
```

## Установка и запуск (Windows, PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env        # при необходимости отредактировать
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

После запуска:

- веб-интерфейс: <http://127.0.0.1:8000>
- документация API (Swagger): <http://127.0.0.1:8000/docs>

## Проверка кода

```powershell
.\.venv\Scripts\python.exe -m pytest            # тесты
.\.venv\Scripts\python.exe -m ruff check .      # линтер
.\.venv\Scripts\python.exe -m ruff format .     # форматирование
```

## Переход на PostgreSQL

Установить драйвер (`pip install "psycopg[binary]"`), указать в `.env`
`DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/finance`
и выполнить `alembic upgrade head`. Код приложения менять не нужно.
