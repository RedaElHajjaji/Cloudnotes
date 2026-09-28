# Database Layer

CloudNotes uses **PostgreSQL** with **SQLAlchemy 2.x (async)** and **Alembic** for migrations. This document explains how the layer is wired together and how to work with it day to day.

## Overview

```
app/
├── db/
│   ├── base.py      # DeclarativeBase + naming conventions + TimestampMixin
│   ├── session.py   # async engine, sessionmaker, get_db() FastAPI dependency
│   └── health.py    # check_database_connection() probe (SELECT 1)
└── models/
    └── user.py      # User ORM model (users table)
migrations/
├── env.py           # async Alembic environment (URL from settings)
└── versions/        # generated migration scripts
alembic.ini         # Alembic configuration (no credentials)
```

## Configuration

The single source of truth is `CLOUDNOTES_DATABASE_URL` (see `.env.example`), consumed through `app/core/config.py`:

```
postgresql+asyncpg://<user>:<password>@<host>:<port>/<database>
```

The application always talks to PostgreSQL through the **asyncpg** driver. Alembic runs online migrations through the same async URL; its offline SQL-rendering mode uses a driver-agnostic `postgresql://` form derived automatically — you never maintain two URLs.

## Engine and sessions

- The **async engine** is created once (`app/db/session.py`) with `pool_pre_ping=True` so stale pooled connections are detected and replaced.
- The engine is attached to `app.state.engine` in the application **lifespan** and disposed on shutdown — no leaked connection pools.
- Request handlers receive a session via the **`get_db` dependency**:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

router = APIRouter()


@router.get("/things")
async def list_things(db: AsyncSession = Depends(get_db)) -> dict[str, str]: ...
```

The dependency always closes the session, even when a handler raises. **Transaction-per-request:** `get_db` commits when the handler returns successfully and rolls back on any exception. Services flush (to obtain IDs and trigger constraint checks) but never commit themselves.

## Models

All models inherit `app/db/base.py:Base`, whose metadata carries deterministic naming conventions (`pk_users`, `ix_users_email`, `fk_…`) so Alembic emits stable, predictable DDL. `TimestampMixin` adds `created_at` / `updated_at` (`timestamptz`, server-side `now()` defaults, `updated_at` also updates on modification).

The initial model is `User` (`users` table):

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | `UUID` | primary key, client-side `uuid4` default |
| `email` | `VARCHAR(255)` | `NOT NULL`, **unique index `ix_users_email`** |
| `password_hash` | `VARCHAR(255)` | `NOT NULL` |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL`, server default `now()` |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL`, server default `now()`, onupdate |

Registration/login endpoints are intentionally **not** implemented yet.

## Migrations

```bash
alembic upgrade head                          # apply all migrations
alembic downgrade -1                          # revert the last one
alembic revision --autogenerate -m "message"  # generate from model changes
alembic check                                 # verify models == migrations (no drift)
alembic current                               # show applied revision
alembic upgrade head --sql                    # offline: print SQL without executing
```

Workflow:

1. Edit/add models under `app/models/` (they are registered via `app/models/__init__.py`).
2. Run `alembic revision --autogenerate -m "..."` against a database that is already at `head`.
3. **Review the generated script** (autogenerate never runs it for you) and adjust if needed.
4. `alembic upgrade head` and run the tests.

Autogenerate connects using `CLOUDNOTES_DATABASE_URL`. Credentials never live in `alembic.ini`.

## Readiness

`GET /ready` and `GET /api/v1/ready` execute a `SELECT 1` through a real engine connection:

- `200 {"status": "ok", "database": true, ...}` — PostgreSQL reachable
- `503 {"status": "unavailable", "database": false, ...}` — the app is up but the database is not usable (the log carries the exception + traceback)

`GET /health` intentionally does **not** touch the database: it answers liveness only.

## Testing

Unit tests (`tests/test_ready.py`) fake the engine — no database needed. Integration tests (`tests/test_db.py`) run real SQL against a migrated database and are **skipped unless** `CLOUDNOTES_TEST_DATABASE_URL` is set:

```bash
# one-off local PostgreSQL
docker run -d --name cloudnotes-pg \
  -e POSTGRES_USER=cloudnotes -e POSTGRES_PASSWORD=cloudnotes -e POSTGRES_DB=cloudnotes \
  -p 5432:5432 postgres:16

export CLOUDNOTES_TEST_DATABASE_URL="postgresql+asyncpg://cloudnotes:cloudnotes@localhost:5432/cloudnotes_test"

pytest              # everything, including DB tests
pytest -m db        # only the DB integration tests
pytest -m "not db"  # unit tests only
```

The fixtures run Alembic `upgrade head` once per session and `downgrade base` afterwards. Each test runs inside a transaction that is **rolled back**, so tests cannot pollute each other or the database. The test URL is passed to Alembic programmatically (`config.attributes["database_url"]`) — never through environment variables or ini files.
