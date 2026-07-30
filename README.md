# BREAD — E-Invoicing API Publisher

UNSW Capstone 26T2 · Team H19B · BREAD

An API publishing and schema-mapping platform for the e-invoicing ecosystem: OpenAPI submission, validation, lifecycle management, version history, and schema mapping.

## Tech Stack

| Layer | Technology |
| --- | --- |
| Frontend | React 19, TypeScript, Vite, Ant Design, Redux Toolkit |
| Backend | FastAPI, Uvicorn, Pydantic, JWT |
| Database | PostgreSQL 16 |
| Deploy | Docker Compose |

## Project Structure

```
.
├── frontend/          # React frontend
├── backend/           # FastAPI backend
├── DB/                # Database init SQL
├── docker/            # Compose env examples
├── docs/              # Design docs and notes
└── compose.yaml       # Full-stack orchestration
```

## Quick Start (Docker, recommended)

Prerequisites: Docker Desktop / Docker Engine.

```bash
# 1. Configure environment
cp docker/.env.example docker/.env
# Edit docker/.env and set POSTGRES_PASSWORD, DATABASE_URL, JWT_SECRET_KEY

# 2. Start all services
docker compose --env-file docker/.env up --build -d
```

| Service | URL |
| --- | --- |
| Frontend | http://localhost:8080 |
| Backend API | http://localhost:8000 |
| Swagger | http://localhost:8000/docs |
| PostgreSQL | localhost:5432 |

Stop:

```bash
docker compose --env-file docker/.env down
```

The DB init script runs only when the volume is first created (default: `DB/19.7database.sql`).

## Local Development

### Database

Start only Postgres with Compose:

```bash
docker compose --env-file docker/.env up -d db
```

### Backend

See [backend/README.md](backend/README.md). Summary:

```bash
cd backend
python3.11 -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set DATABASE_URL and JWT settings
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Dev server: http://localhost:5173 (CORS is configured for this origin).

## Features

- User registration / login (JWT)
- API submission and OpenAPI validation
- Dashboard: all / my API lists with search
- API detail, lifecycle actions, version history
- Schema mapping edit and validation

## Related Docs

| Doc | Description |
| --- | --- |
| [backend/README.md](backend/README.md) | Backend local setup |
| [frontend/src/apidoc/Frontend_Backend_API_Contract_Updated_With_Token.md](frontend/src/apidoc/Frontend_Backend_API_Contract_Updated_With_Token.md) | Frontend–backend API contract |
| [backend/docs/metadata-validation-rules.md](backend/docs/metadata-validation-rules.md) | Metadata validation rules |
| [docs/](docs/) | Proposal / design PDFs |

## Team

Capstone Project 26T2 · 9900 · H19B · BREAD
