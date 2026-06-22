# Backend

E-Invoicing API Publisher — FastAPI backend.

## Prerequisites

- **Python 3.11** (see `.python-version`)
- pip

Install Python 3.11 if needed (macOS + Homebrew):

```bash
brew install python@3.11
python3.11 --version   # should be 3.11.x
```

Check your version:

```bash
python3.11 --version   # should be 3.11.x
```

## Setup

```bash
cd backend

# Create and activate virtual environment (must use 3.11)
python3.11 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Verify
python --version   # should show 3.11.x inside .venv

# Install dependencies
pip install -r requirements.txt
```

## Run

```bash
source .venv/bin/activate
uvicorn app.main:app --reload
```

| URL                        | Description  |
| -------------------------- | ------------ |
| http://127.0.0.1:8000      | Health check |
| http://127.0.0.1:8000/docs | Swagger UI   |

## Adding dependencies

1. Activate the virtual environment.
2. `pip install <package>`
3. Add the package (with pinned version) to `requirements.txt`
4. Commit and open a PR so teammates can `pip install -r requirements.txt`

## Project structure

```
backend/
├── app/
│   ├── main.py          # FastAPI entry point
│   ├── routers/         # API routes
│   ├── schemas/         # Pydantic models
│   └── services/        # Business logic
├── requirements.txt     # Python package dependencies
├── .python-version      # Team Python version (3.11)
└── .gitignore
```

## What goes where

| File               | Purpose                    | Commit to Git? |
| ------------------ | -------------------------- | -------------- |
| `requirements.txt` | Third-party packages       | Yes            |
| `.python-version`  | Python interpreter version | Yes            |
| `.env.example`     | Env var template           | Yes            |
| `.env`             | Local secrets / config     | **No**         |
| `.venv/`           | Local virtual environment  | **No**         |
