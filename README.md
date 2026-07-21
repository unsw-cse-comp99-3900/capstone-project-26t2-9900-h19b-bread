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
│   │   ├── store/             # Redux store (auth, authors, …)
│   │   ├── utils/             # Axios instance, helpers
│   │   └── apidoc/            # Frontend–Backend API contract docs
│   ├── Dockerfile
│   └── package.json
├── backend/                   # FastAPI (Python 3.11)
│   ├── app/
│   │   ├── main.py            # FastAPI entry point
│   │   ├── core/              # DB, security, config
│   │   ├── routers/           # API routes
│   │   ├── schemas/           # Pydantic models
│   │   └── services/          # Business logic
│   ├── .env.example
│   ├── Dockerfile
│   └── requirements.txt
├── DB/
│   └── 19.7database.sql       # Current schema + seed (default init)
├── docker/
│   └── .env.example           # Compose secrets / ports
├── compose.yaml               # db + backend + frontend
└── README.md
```

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Node.js | 18 + | Local frontend only |
| npm | 9 + | Comes with Node.js |
| Python | 3.11 | Local backend only |
| Docker Desktop | latest | Required for PostgreSQL / full deploy |

---

## Two ways to run

| Mode | What runs in Docker | What runs on host | Best for |
|------|---------------------|-------------------|----------|
| **A. Full Docker** | db + backend + frontend | nothing | Demo / shared server |
| **B. Local dev** | db only | backend + frontend | Daily development |

Both modes use the same schema file: `DB/19.7database.sql` (first volume init only).

---

## A. Full Docker deploy

Compose starts three services:

- `db` — PostgreSQL 16, named volume, auto-init from `DB_INIT_SQL`
- `backend` — FastAPI (Python 3.11 image)
- `frontend` — Vite production build behind Nginx (`/api` proxied to backend)

No host Python/Node/PostgreSQL install is required.

### 1. Create env file

PowerShell:

```powershell
Copy-Item docker/.env.example docker/.env
```

macOS/Linux:

```bash
cp docker/.env.example docker/.env
```

Edit `docker/.env` and set real values for at least:

- `POSTGRES_PASSWORD`
- `DATABASE_URL` (must match `POSTGRES_*`; use host `db` inside Compose)
- `JWT_SECRET_KEY`

Compose refuses to start if those are missing. URL-encode reserved password characters (e.g. `@` → `%40`).

Default ports / DB:

| Variable | Default | Meaning |
|----------|---------|---------|
| `POSTGRES_DB` | `bread` | Database name |
| `POSTGRES_USER` | `postgres` | DB user |
| `POSTGRES_PORT` | `5432` | Host port for Postgres |
| `BACKEND_PORT` | `8000` | Host port for API |
| `APP_PORT` | `8080` | Host port for UI |
| `DB_INIT_SQL` | `DB/19.7database.sql` | Init script (empty volume only) |

### 2. Build and start

```bash
docker compose --env-file docker/.env up --build --detach
docker compose --env-file docker/.env ps
```

Open:

| URL | Service |
|-----|---------|
| `http://localhost:8080` | Frontend |
| `http://localhost:8000` | Backend |
| `http://localhost:8000/docs` | Swagger UI |
| `localhost:5432` | PostgreSQL (GUI tools) |

Confirm Python version in the backend container:

```bash
docker compose --env-file docker/.env exec backend python --version
# Python 3.11.x
```

### 3. Stop / restart / logs

```bash
docker compose --env-file docker/.env stop
docker compose --env-file docker/.env start
docker compose --env-file docker/.env logs --follow
docker compose --env-file docker/.env down
```

`down` keeps the Postgres volume. Init SQL runs only on a **new empty volume**.

To wipe data and re-init from SQL (destructive):

```bash
docker compose --env-file docker/.env down --volumes
docker compose --env-file docker/.env up --build --detach
```

To try another schema file, set `DB_INIT_SQL` in `docker/.env`, then recreate the volume as above.

---

## B. Local development (backend + frontend on host, DB in Docker)

Use this when you want hot reload while still using the Compose Postgres.

### 1. Start only the database

From the repository root, with `docker/.env` already configured (same as section A):

```bash
docker compose --env-file docker/.env up db --detach
docker compose --env-file docker/.env ps
```

Wait until `db` is healthy. First start creates volume and loads `DB/19.7database.sql`.

Connection from the **host**:

| Field | Value |
|-------|-------|
| Host | `localhost` |
| Port | `5432` (or `POSTGRES_PORT` in `docker/.env`) |
| Database | `bread` |
| Username | `postgres` |
| Password | value of `POSTGRES_PASSWORD` |

Example URL (replace password):

```text
postgresql://postgres:<password>@localhost:5432/bread
```

Optional: open the same URL in DBeaver to inspect tables. Schema details: [`DB/readme.md`](DB/readme.md).

### 2. Backend (host)

```bash
cd backend

# Python 3.11 required
python3.11 -m venv .venv

# Activate
# macOS / Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

pip install -r requirements.txt

# Create backend/.env from the example
# PowerShell: Copy-Item .env.example .env
# bash:       cp .env.example .env
```

Edit `backend/.env` so it points at the **host-mapped** Docker DB (not hostname `db`):

```env
DATABASE_URL=postgresql://postgres:<password>@localhost:5432/bread
JWT_SECRET_KEY=<replace-with-a-long-random-secret>
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440
```

Keep `DATABASE_URL` credentials aligned with `docker/.env` `POSTGRES_*` values.

Start:

```bash
uvicorn app.main:app --reload
```

| URL | Description |
|-----|-------------|
| `http://127.0.0.1:8000` | API base |
| `http://127.0.0.1:8000/docs` | Swagger UI |

### 3. Frontend (host)

```bash
cd frontend
npm install
npm run dev
```

UI: `http://localhost:5173`

Axios defaults to `http://127.0.0.1:8000`. Override with `frontend/.env` if needed:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

| Command | Description |
|---------|-------------|
| `npm run dev` | Dev server |
| `npm run build` | Production build |
| `npm run lint` | ESLint |
| `npm run preview` | Preview production build |

---

## Test credentials

Seed user in `DB/19.7database.sql`:

```text
Email:    publisher@example.com
Password: password123
```

Passwords are stored as **SHA-256 hex** (see backend auth). The seed currently inserts a placeholder hash (`hashed_password_here`). After DB init, fix it once:

```sql
UPDATE app_user
SET password_hash = 'ef92b778bafe771e89245b89ecbc08a44a4e166c06659911881f383d4473e94f'
WHERE email = 'publisher@example.com';
```

Or register a new account via the UI / `POST /api/v1/auth/register`.

---

## API quick reference

Full contract: [`frontend/src/apidoc/Frontend_Backend_API_Contract_Updated_With_Token.md`](frontend/src/apidoc/Frontend_Backend_API_Contract_Updated_With_Token.md)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/auth/login` | Login, returns JWT |
| `POST` | `/api/v1/auth/register` | Register + token |
| `GET` | `/api/v1/submissions` | List submissions |
| `POST` | `/api/v1/submissions` | Submit API for validation |
| `GET` | `/api/v1/submissions/authors` | Author filter list |

---

## Common issues

### Port 5432 already in use

Set `POSTGRES_PORT=5433` in `docker/.env`, then for local backend use:

```env
DATABASE_URL=postgresql://postgres:<password>@localhost:5433/bread
```

### Frontend cannot reach backend

1. Confirm uvicorn is running.
2. Confirm `VITE_API_BASE_URL` matches the backend URL.
3. In full Docker mode, open `http://localhost:8080` (not the Vite port).

### Login fails for seed user

Run the `UPDATE app_user ...` statement in the credentials section, or register a new user.

### Init SQL did not run

Init runs only on a new empty volume. Recreate with `down --volumes` (destructive) if you need a clean schema load.

### Python version mismatch

```bash
python --version
```

Recreate the venv with Python 3.11 if needed: `python3.11 -m venv .venv`.
