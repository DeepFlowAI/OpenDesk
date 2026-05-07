# OpenDesk Server

FastAPI backend for OpenDesk.

## Tech Stack

- **Framework**: FastAPI + Python 3.11+
- **ORM**: SQLAlchemy 2.0 (async) + Alembic
- **Database**: PostgreSQL 15+ (asyncpg)
- **Cache**: Redis 7.0+
- **Architecture**: Layered (Router → Service → Repository → Model)

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run dev server (loads .env.dev by default)
uvicorn app.main:app --reload --port 8000

# Run with production config
APP_ENV=production uvicorn app.main:app --port 8000
```

## Database Migrations

Migrations run automatically on startup when `AUTO_MIGRATE=true`.

```bash
# Create a new migration
alembic revision --autogenerate -m "description"

# Run migrations manually
alembic upgrade head

# Rollback one version
alembic downgrade -1
```

## Project Structure

```
server/
├── app/
│   ├── main.py              # FastAPI app creation & lifespan
│   ├── configs/settings.py   # Pydantic Settings
│   ├── routers/v1/           # API routes
│   ├── schemas/              # Pydantic request/response schemas
│   ├── services/             # Business logic layer
│   ├── repositories/         # Data access layer
│   ├── models/               # SQLAlchemy ORM models
│   ├── db/                   # Database & Redis setup
│   ├── core/                 # Exceptions, security
│   ├── enums/                # Enum definitions
│   ├── libs/                 # Utility libraries
│   └── middlewares/          # Custom middleware
├── migrations/               # Alembic migrations
├── tests/                    # Tests
├── alembic.ini
├── requirements.txt
└── .env.dev / .env.production
```
