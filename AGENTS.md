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
- Demo data: `.\.venv\Scripts\python.exe -m app.cli demo-data [--load] [--months N] [--seed S]`
- Forecast: `python -m app.cli forecast [--granularity week] [--horizon N]`
  (models in `app/ml/forecasting.py`, series and report in `app/services/forecast.py`)
- Categorizer: `python -m app.cli train-categorizer | recategorize | evaluate-categorizer`
  (model and evaluation report are stored in `data/models/`, not in git)
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
- Recommendations: generic engine `services/inference.py` (validated KB schema, forward
  chaining, trace); knowledge base `app/knowledge/recommendation_rules.json` (facts with labels,
  category groups, rules); facts and explanations in `services/recommendations.py`.
  A new fact used by a rule must be added to the KB `facts` (or `category_facts`).
- Categorization code: `services/rule_matcher.py` (symbolic), `ml/text_classifier.py`
  (statistical), `services/categorization.py` (arbiter, trace, training),
  `services/categorization_eval.py` (rules vs ML vs hybrid). Tests use a temporary
  `config.MODELS_DIR` (autouse fixture `isolated_models_dir`).
- Tests never use the network: rate sources are replaced by `tests/helpers.FakeRateProvider`
  (fixtures `providers` / `offline_providers`), HTTP parsing is tested with `httpx.MockTransport`.
- Money is stored as `Decimal` / `Numeric(12, 2)`, never `float`.
- Analytics are calculated in BYN; USD operations are converted at the NBRB rate on the operation date.
- Third-party front-end libraries are vendored in `app/static/vendor/` (works offline).

## Roadmap
The university requires a *hybrid intelligent system* (symbolic + statistical components with
real integration, explainability, step-by-step decision trace, comparison of rules-only /
ML-only / hybrid quality). No LLM in the coursework (user decision; maybe in the diploma).
- Part 1: 0 skeleton, 1 models, 2 transactions + rates, 3 CSV import + demo data generator.
- Part 2: 4 hybrid categorization (keyword rules -> TF-IDF + LogisticRegression -> arbitration
  on low confidence / conflicts, explanation per transaction, evaluation of the 3 variants);
  5 analytics dashboard; 6 recurring payments.
- Part 3: 7 forecasting (baseline / linear regression / Holt, choose by MAE);
  8 knowledge base of production rules + inference engine over ML facts (forecast, analytics)
  with a trace of fired rules; 9 polish.
- The demo data generator produces labeled data (ground-truth categories) used to evaluate
  the categorizer in stage 4.

## Workflow
- The project is a coursework split into 3 parts (stages 0–3, 4–6, 7–9).
  Stop after each stage, explain what was done, and wait for the user's approval.
- Verify every stage with pytest + ruff before committing.
- Commit messages: short single line in English, no body and no co-author trailer.
- Remote: https://github.com/sadwavesss/Financial-Assistant.git (branch `main`).
