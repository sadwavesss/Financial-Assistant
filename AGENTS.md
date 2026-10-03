# Notes for coding assistants

## Environment
- Windows; use PowerShell (bash is not available). Python 3.12 in `.venv`.
- The project path contains Cyrillic characters and spaces — always quote paths.
- Do not rewrite files with PowerShell `Set-Content -Encoding UTF8` (it adds a BOM);
  use the editor tools instead.
- Network can be unstable: use `pip install --retries 10 --timeout 60`.
- New dependencies: only versions published at least 7 days ago (`--uploaded-prior-to P7D`);
  pin exact versions in `requirements.txt` / `requirements-dev.txt`.

## Commands
- Init DB (migrations + default categories): `.\.venv\Scripts\python.exe -m app.cli init-db`
- Run app: `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload`
- Tests: `.\.venv\Scripts\python.exe -m pytest`
- Lint: `.\.venv\Scripts\python.exe -m ruff check .`
- Format check: `.\.venv\Scripts\python.exe -m ruff format --check .`
- Migrations: `.\.venv\Scripts\alembic.exe upgrade head`;
  new one: `.\.venv\Scripts\alembic.exe revision --autogenerate -m "..."`

## Conventions
- UI text in Russian; code, identifiers, docstrings and comments in English.
- Layers: `api/` and `web/` (thin HTTP handlers) -> `services/` (business logic) -> `models/`.
  External HTTP APIs live in `integrations/`; shared FastAPI deps in `app/dependencies.py`.
- Business errors: raise `ServiceError` subclasses (`app/services/errors.py`) with Russian
  messages; a global handler turns them into JSON (`/api`) or an HTML error page.
- Tests never use the network: rate sources are replaced by `tests/helpers.FakeRateProvider`
  (fixtures `providers` / `offline_providers`), HTTP parsing is tested with `httpx.MockTransport`.
- Money is stored as `Decimal` / `Numeric(12, 2)`, never `float`.
- Analytics are calculated in BYN; USD operations are converted at the NBRB rate on the operation date.
- Third-party front-end libraries are vendored in `app/static/vendor/` (works offline).

## Workflow
- The project is a coursework split into 3 parts (stages 0–3, 4–6, 7–9).
  Stop after each stage, explain what was done, and wait for the user's approval.
- Verify every stage with pytest + ruff before committing.
- Commit messages: short single line in English, no body and no co-author trailer.
- Remote: https://github.com/sadwavesss/Financial-Assistant.git (branch `main`).
