# Production Postgres on Render

Production already uses an external Postgres database configured through the
Render `DATABASE_URL` environment variable. Do not put the URL in this repository
or send it through chat.

The application expects an async SQLAlchemy URL:
`postgresql+asyncpg://user:password@host:port/database`.

The Render startup command applies `python -m alembic upgrade head` before
launching `python main.py`. The service health check is `/health`.

After a deployment:

1. Check the Render logs for a successful migration and database connection.
2. Open `https://<your-app>.onrender.com/health`.
3. Exercise one read and one write through the bot when a schema migration was
   included in the release.

Notes and recommendations
- SQLite is test-only and is installed only by `requirements-dev.txt`.
- Keep credentials in Render environment variables and enable database backups.
- Monitor pool usage before increasing application concurrency.
