# E-Invoicing API Publisher

UNSW Capstone 26T2 · Team H19B

The project is a web application for publishing and validating e-invoicing APIs. It supports REST/OpenAPI and SOAP/WSDL submissions, staged validation, lifecycle and version history, database-backed schema mapping, and connection compatibility checks.

## Technology

| Layer | Technology |
| --- | --- |
| Frontend | React 19, TypeScript, Vite, Ant Design, Redux Toolkit |
| Backend | FastAPI, Uvicorn, Pydantic, psycopg, JWT |
| Database | PostgreSQL 16 |
| Deployment | Docker Compose, Nginx |

## Repository layout

```text
.
├── backend/       FastAPI application, services, and tests
├── DB/            PostgreSQL schema and initialization data
├── docker/        Compose environment template
├── docs/          Project reports and connection-validation examples
├── frontend/      React application and Nginx configuration
└── compose.yaml   Full-stack Docker Compose configuration
```

## Run with Docker Compose

Prerequisites: Docker Desktop or Docker Engine with Compose v2.

1. Create the local environment file.

   PowerShell:

   ```powershell
   Copy-Item docker/.env.example docker/.env
   ```

   macOS/Linux:

   ```bash
   cp docker/.env.example docker/.env
   ```

2. Replace every placeholder password and secret in `docker/.env`. Keep `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, and `DATABASE_URL` consistent. Reserved characters in the database password must be percent-encoded inside `DATABASE_URL`.

3. Build and start the stack from the repository root.

   ```bash
   docker compose --env-file docker/.env up -d --build
   docker compose --env-file docker/.env ps
   ```

4. Open the application.

   | Service | Default address |
   | --- | --- |
   | Web application | <http://localhost:8080> |
   | Backend health response | <http://localhost:8000> |
   | Interactive API documentation | <http://localhost:8000/docs> |
   | PostgreSQL | `localhost:5432` |

Stop the stack without deleting data:

```bash
docker compose --env-file docker/.env down
```

The database initializer, `DB/19.7database.sql`, runs only when the `postgres_data` volume is first created. Running `docker compose --env-file docker/.env down -v` permanently deletes the project database volume and all uploaded or generated records.

> **Deployment note:** the bundled SQL initializer contains demonstration enterprises, API records, and a demonstration user for development and evaluation. Remove demonstration credentials and data, configure production secrets, restrict exposed database/backend ports, and add the required TLS/reverse-proxy controls before an internet-facing deployment.

## Local development

### Database

Create `docker/.env` as described above, then start PostgreSQL:

```bash
docker compose --env-file docker/.env up -d db
```

### Backend

The backend requires Python 3.11 and a local `backend/.env` whose `DATABASE_URL` points to the development PostgreSQL service.

```bash
cd backend
python -m venv .venv
# PowerShell: .\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env`, replace its placeholders, then run:

```bash
python -m uvicorn app.main:app --reload
```

See [backend/README.md](backend/README.md) for backend tests and structure.

### Frontend

The frontend uses Node.js 22, matching its Docker build image.

```bash
cd frontend
npm ci
npm run dev
```

The Vite development server normally opens at <http://localhost:5173>. Its default API base URL is <http://127.0.0.1:8000>; the Compose build instead uses the Nginx `/api/` reverse proxy.

See [frontend/README.md](frontend/README.md) for available scripts and frontend structure.

## Current capabilities

- JWT registration, login, protected routes, and session-expiry handling
- API submission from pasted/uploaded content or a specification URL
- REST/OpenAPI and SOAP/WSDL parsing and three-stage publication validation
- Drafts, enterprise-scoped dashboard lists, search, API detail, withdrawal, and publication lifecycle
- Version creation, update, history, validation results, and specification retrieval
- Persisted API-schema comparison, mapping rules, JSON/XML transform preview, and transform-run evidence
- Persisted source-to-target connection validation with staged compatibility results

## Verification commands

Backend:

```bash
cd backend
python -m pytest -q
```

Frontend:

```bash
cd frontend
npm run lint
npm run build
```

Compose configuration:

```bash
docker compose --env-file docker/.env config --quiet
```

## Documentation

- The running backend's Swagger UI at `/docs` and generated OpenAPI schema at `/openapi.json` are the canonical API reference.
- [Backend guide](backend/README.md)
- [Frontend guide](frontend/README.md)
- [Publication validation rules](backend/docs/metadata-validation-rules.md)
- [Connection-validation source example](docs/connection-validation-source-openapi.json)
- [Connection-validation target example](docs/connection-validation-target-openapi.json)
- `docs/` also contains the original proposal and design report PDFs for project background; they are not deployment instructions.

## Team

Capstone Project 26T2 · 9900 · H19B
