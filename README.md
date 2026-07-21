# E-Invoice API Ecosystem — API Publisher

A full-stack platform for publishing, validating, and managing enterprise e-invoicing APIs.  
Built with **React + TypeScript (Vite)** on the frontend and **FastAPI (Python 3.11)** on the backend.

---

## Project Structure

```
capstone-project-26t2-9900-h19b-bread/
├── frontend/                  # React + TypeScript (Vite)
│   ├── src/
│   │   ├── pages/             # Route-level page components
│   │   ├── components/        # Shared UI components
│   │   ├── services/          # API call functions
│   │   ├── utils/             # Axios instance, helper utilities
│   │   └── apidoc/            # Frontend–Backend API contract docs
│   ├── package.json
│   └── vite.config.ts
├── backend/                   # FastAPI (Python 3.11)
│   ├── app/
│   │   ├── main.py            # FastAPI entry point
│   │   ├── routers/           # API routes
│   │   ├── schemas/           # Pydantic models
│   │   └── services/          # Business logic
│   ├── requirements.txt
│   └── .python-version
├── 24.6_DATABASE_1stversion.sql  # Database schema + seed data
└── README.md
```

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Node.js | 18 + | Required for frontend |
| npm | 9 + | Comes with Node.js |
| Python | 3.11 | Required for backend |
| Docker Desktop | latest | Required for PostgreSQL |

---

## Quick deployment with Docker (recommended)

Docker Compose runs the complete project with three services:

- `db`: PostgreSQL 16 with a persistent named volume and automatic first-run schema initialization.
- `backend`: FastAPI on the official Python 3.11 image.
- `frontend`: a production Vite build served by Nginx, with `/api` proxied to the backend.

No host Python, virtual environment, Node.js, or local PostgreSQL installation is required.

### Start the complete project

PowerShell:

```powershell
Copy-Item docker/.env.example docker/.env

# Replace POSTGRES_PASSWORD, DATABASE_URL, and JWT_SECRET_KEY in docker/.env.
docker compose --env-file docker/.env up --build --detach
docker compose --env-file docker/.env ps
```

macOS/Linux:

```bash
cp docker/.env.example docker/.env

# Replace POSTGRES_PASSWORD, DATABASE_URL, and JWT_SECRET_KEY in docker/.env.
docker compose --env-file docker/.env up --build --detach
docker compose --env-file docker/.env ps
```

Compose refuses to start if `POSTGRES_PASSWORD`, `DATABASE_URL`, or
`JWT_SECRET_KEY` is missing. Keep the credentials in `DATABASE_URL` aligned with
the `POSTGRES_*` values. URL-encode reserved password characters—for example,
use `%40` for `@`.

Open:

| URL | Service |
|-----|---------|
| `http://localhost:8080` | Frontend |
| `http://localhost:8000` | Backend health response |
| `http://localhost:8000/docs` | Swagger UI |
| `localhost:5432` | PostgreSQL (for local database tools) |

Confirm the backend container uses the required interpreter:

```bash
docker compose --env-file docker/.env exec backend python --version
# Python 3.11.x
```

### Stop, restart, and inspect

```bash
docker compose --env-file docker/.env stop
docker compose --env-file docker/.env start
docker compose --env-file docker/.env logs --follow
docker compose --env-file docker/.env down
```

`down` keeps the PostgreSQL named volume. The SQL file selected by `DB_INIT_SQL`
runs only when PostgreSQL creates a new empty volume. To intentionally rebuild the
database from the selected SQL file, back up required data and then run:

```bash
docker compose --env-file docker/.env down --volumes
docker compose --env-file docker/.env up --build --detach
```

The default schema is the updated `DB/19.7database.sql`, inherited from the
database integration branch. Set `DB_INIT_SQL` in `docker/.env` to another
repository-root SQL file when testing a different schema revision.

For a fresh machine or server, copy/clone the repository, create `docker/.env`,
and run the same `docker compose ... up` command. Application data moves separately:
use `pg_dump`/`pg_restore` or a Docker volume backup when existing PostgreSQL data
must be migrated rather than initialized from SQL.

---

## 1. Database Setup

### Start PostgreSQL with Docker

Make sure Docker Desktop is running, then execute:

```bash
docker run --name sprint1-db \
  -e POSTGRES_PASSWORD=mysecretpassword \
  -p 5432:5432 \
  -d postgres
```

If the container already exists, start it with:

```bash
docker start sprint1-db
```

### Connection Details

| Field | Value |
|-------|-------|
| Database Type | PostgreSQL |
| Host | localhost |
| Port | 5432 |
| Database | postgres |
| Username | postgres |
| Password | mysecretpassword |

Connection string:

```text
postgresql://postgres:mysecretpassword@localhost:5432/postgres
```

### Initialize Schema

1. Open DBeaver and connect using the settings above.
2. Open `24.6_DATABASE_1stversion.sql`.
3. Run the full script (`Alt + X` or **Execute SQL Script**).
4. Confirm the following tables are created:

```text
enterprise · app_user · api_submission · api_version
api_specification · auth_metadata · validation_run
validation_result · schema_mapping
```

---

## 2. Backend Setup & Start

```bash
cd backend

# Create and activate virtual environment (Python 3.11 required)
python3.11 -m venv .venv

# Activate
# macOS / Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start the development server
uvicorn app.main:app --reload
```

The backend will be available at:

| URL | Description |
|-----|-------------|
| `http://127.0.0.1:8000` | API base URL |
| `http://127.0.0.1:8000/docs` | Swagger UI |

---

## 3. Frontend Setup & Start

```bash
cd frontend

# Install dependencies
npm install

# Start the development server
npm run dev
```

The frontend will be available at:

```text
http://localhost:5173
```

> The frontend proxies all API requests to `http://127.0.0.1:8000` by default.  
> To override, set `VITE_API_BASE_URL` in a `.env` file:
>
> ```env
> VITE_API_BASE_URL=http://127.0.0.1:8000
> ```

### Available Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start development server |
| `npm run build` | Production build |
| `npm run lint` | Run ESLint |
| `npm run preview` | Preview production build locally |

---

## 4. API Quick Reference

Full contract: [`frontend/src/apidoc/Frontend_Backend_API_Contract_Updated_With_Token.md`](frontend/src/apidoc/Frontend_Backend_API_Contract_Updated_With_Token.md)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/auth/login` | User login, returns mock token |
| `POST` | `/api/v1/submissions` | Submit API spec + metadata for validation |
| `POST` | `/api/v1/validation/spec` | Validate spec directly (used internally) |

### Sprint 1 Test Credentials

```text
Email:    publisher@example.com
Password: password123
```

---

## 5. Common Issues

### Port 5432 already in use

Map Docker to a different local port:

```bash
docker run --name sprint1-db \
  -e POSTGRES_PASSWORD=mysecretpassword \
  -p 5433:5432 \
  -d postgres
```

Then update the backend database connection to use port `5433`.

### Docker container name already exists

```bash
docker start sprint1-db
# or remove and recreate:
docker rm sprint1-db
```

### Frontend cannot reach backend (CORS / connection refused)

1. Confirm the backend server is running (`uvicorn app.main:app --reload`).
2. Confirm the virtual environment is activated before running uvicorn.
3. Check that `VITE_API_BASE_URL` (if set) matches the actual backend URL.

### Python version mismatch

The backend requires Python 3.11. Check with:

```bash
python --version
```

If the version is wrong, recreate the virtual environment using `python3.11 -m venv .venv`.
