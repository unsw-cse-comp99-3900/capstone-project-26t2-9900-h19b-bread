# Backend development guide

The backend is a Python 3.11 FastAPI application backed by PostgreSQL. It provides authentication, API submission and validation, lifecycle and version-history operations, schema mapping, and connection validation.

## Prerequisites

- Python 3.11 (also declared in `.python-version`)
- PostgreSQL 16, normally started through the root Compose stack

## Environment setup

From the repository root, start the database after creating `docker/.env` from `docker/.env.example`:

```bash
docker compose --env-file docker/.env up -d db
```

Create the backend environment:

```bash
cd backend
python -m venv .venv
```

Activate it:

```powershell
# PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS/Linux
source .venv/bin/activate
```

Install the pinned dependencies:

```bash
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and replace its placeholders. For a database exposed from the root Compose stack on its default host port, the URL has this form:

```dotenv
DATABASE_URL=postgresql://postgres:your-percent-encoded-password@localhost:5432/bread
JWT_SECRET_KEY=replace-with-a-long-random-secret
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440
```

Do not commit `backend/.env`.

## Run the API

From `backend/` with the virtual environment active:

```bash
python -m uvicorn app.main:app --reload
```

| Address | Purpose |
| --- | --- |
| <http://127.0.0.1:8000> | Health response |
| <http://127.0.0.1:8000/docs> | Swagger UI |
| <http://127.0.0.1:8000/openapi.json> | Generated OpenAPI contract |

The generated OpenAPI document is the canonical endpoint reference. Authentication endpoints are under `/api/v1/auth`; submission, validation, schema-mapping, and connection-validation endpoints are under `/api/v1`; lifecycle and version-history endpoints are under `/api/apis`.

## Run tests

Run the complete backend suite:

```bash
python -m pytest -q
```

Run one area while developing:

```bash
python -m pytest -q tests/test_validation_metadata.py
python -m pytest -q tests/test_schema_mapping_service.py
python -m pytest -q tests/test_connection_validation_service.py
```

## Structure

```text
backend/
├── app/
│   ├── connection_validation/   persisted connection-validation pipeline
│   ├── core/                    database and JWT dependencies
│   ├── lifecycle/               publication state machine and persistence
│   ├── routers/                 FastAPI route modules
│   ├── schemas/                 request and response models
│   ├── services/                validation and schema-mapping logic
│   ├── version_history/         version services and persistence
│   └── main.py                  application entry point
├── docs/                        backend technical references
├── tests/                       unit, contract, router, and acceptance tests
├── Dockerfile
├── requirements.txt
└── .env.example
```

## Dependency changes

1. Activate the backend virtual environment.
2. Install and test the required package.
3. Pin its exact version in `requirements.txt`.
4. Re-run the relevant tests and the complete backend suite.

For the current publication-validation behaviour and error codes, see [docs/metadata-validation-rules.md](docs/metadata-validation-rules.md).
