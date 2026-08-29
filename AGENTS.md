# Project guide

This repository contains two aiogram bots in one process:

- `public_bot/` — show discovery, registration, calendars and feedback.
- `admin_bot/` — shows, attendees, check-in, analytics and access control.
- `db/` — SQLAlchemy models and CRUD operations.
- `scheduler/` — announcements, reminders and post-show feedback.
- `alembic/versions/` — ordered database migrations.

## Environment

- Production Python: 3.13 (`.python-version` and `Dockerfile`).
- Local commands prefer `.venv/bin/python`, then fall back to `python3`.
- Install development dependencies with:
  `.venv/bin/python -m pip install -r requirements-dev.txt`
- Copy `.env.example` to `.env` for local runs. Never commit tokens or secrets.
- Datetimes stored in the database are naive UTC. Convert UI input/output with
  helpers from `time_utils.py`; do not call `datetime.now()` for business logic.

## Required checks

Run these scripts from any directory:

- `./scripts/compile.sh` — compile application, migrations and tests.
- `./scripts/test.sh` — run the pytest suite.
- `./scripts/check.sh` — run compilation and all tests; preferred before handoff.
- A focused test is supported: `./scripts/test.sh tests/test_security.py`.

The scripts keep bytecode outside the repository and fail on the first error.

## Database changes

- Every model/schema change requires a new Alembic migration.
- Keep one linear migration head and verify it with
  `.venv/bin/python -m alembic heads`.
- Apply migrations with `.venv/bin/python -m alembic upgrade head`.
- Migrations must support PostgreSQL and SQLite; use Alembic batch operations
  where SQLite cannot perform an `ALTER` directly.

## Production facts

- The Render service health check is already configured to use `/health`.
- Render runs `python -m alembic upgrade head` in its startup command before
  launching `python main.py`. Do not report either item as missing unless the
  production configuration or `render.yaml` has changed.
- Production already uses a configured external Postgres database. Its URL is
  supplied through Render's `DATABASE_URL`; never request or commit the secret.
- SQLite is not a production runtime. It is retained only in dev dependencies
  for isolated unit tests and cross-dialect migration tests.

## Implementation rules

- Keep Telegram callback payloads within the platform size limit.
- Escape user-provided HTML with `html_utils.h`.
- Enforce organizer ownership through `admin_bot.security`.
- Keep database sessions scoped with `async with` and avoid unbounded `.all()`
  queries in UI and scheduler paths.
- Bound concurrent sends and background work; do not create unbounded task sets.
- Add or update tests for behavior changes, especially permissions, migrations,
  timezone conversion, registration capacity and scheduler idempotency.
- Preserve unrelated working-tree changes; do not rewrite or delete them.
