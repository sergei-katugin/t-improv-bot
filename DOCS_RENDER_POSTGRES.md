# Deploying with managed Postgres on Render

This document describes steps to migrate from SQLite to a managed Postgres instance on Render and how to run migrations.

1) Create a managed Postgres instance in Render
   - In the Render dashboard click **New** → **Postgres** → follow the wizard to create a database.
   - Note the connection URL (shown in the dashboard). It will look like:
     `postgres://user:password@host:port/dbname`

2) Build a SQLAlchemy async connection string
   - For SQLAlchemy + asyncpg use this format (in `DATABASE_URL`):
     `postgresql+asyncpg://user:password@host:port/dbname`
   - Set this value in your Service's Environment variables on Render (Dashboard → Your Service → Environment → Environment Variables). Replace the existing `DATABASE_URL`.

3) Make sure `asyncpg` is installed
   - `requirements.txt` already contains `asyncpg` — Render will install it during build.

4) Apply migrations on the remote DB
   - Recommended: run a one-off shell/command in Render and run alembic:
     ```bash
     # from service shell or one-off command in Render
     python -m alembic upgrade head
     ```
   - Alternatively the `main.py` calls `run_migrations()` on startup; ensure the service has permissions and environment configured.

5) Restart the service
   - After setting `DATABASE_URL` and applying migrations, restart your web service.

6) Verify
   - Check logs in Render for DB connection errors.
   - Visit `https://<your-app>.onrender.com/health`.

Notes and recommendations
 - SQLite (`./data/impro.db`) is fine for local development, but **not** for production on Render (ephemeral FS, risk of data loss). Use managed Postgres for persistence and backups.
 - Use Render's backups & follow best practices for credentials (store secrets in Environment variables, do not commit `.env`).
 - For high-concurrency async apps, monitor connection usage and consider a connection pooler if needed.
