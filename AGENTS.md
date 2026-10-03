# Notes for coding assistants

## Environment
- Windows; use PowerShell (bash is not available). Python 3.12 in `.venv`.
- The project path contains Cyrillic characters and spaces — always quote paths.
- Network can be unstable: use `pip install --retries 10 --timeout 60`.
- New dependencies: only versions published at least 7 days ago (`--uploaded-prior-to P7D`);
  pin exact versions in `requirements.txt` / `requirements-dev.txt`.

## Commands
- Run app: `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload`
- Tests: `.\.venv\Scripts\python.exe -m pytest`
- Lint: `.\.venv\Scripts\python.exe -m ruff check .`
- Format check: `.\.venv\Scripts\python.exe -m ruff format --check .`
- Migrations: `.\.venv\Scripts\alembic.exe upgrade head`;
  new one: `.\.venv\Scripts\alembic.exe revision --autogenerate -m "..."`

## Conventions
- UI text in Russian; code, identifiers, docstrings and comments in English.
- Layers: `api/` and `web/` (thin HTTP handlers) -> `services/` (business logic) -> `models/`.
- Money is stored as `Decimal` / `Numeric(12, 2)`, never `float`.
- Analytics are calculated in BYN; USD operations are converted at the NBRB rate on the operation date.
- Third-party front-end libraries are vendored in `app/static/vendor/` (works offline).

## Workflow
- The project is a coursework split into 3 parts (stages 0–3, 4–6, 7–9).
  Stop after each stage, explain what was done, and wait for the user's approval.
- Verify every stage with pytest + ruff before committing.
