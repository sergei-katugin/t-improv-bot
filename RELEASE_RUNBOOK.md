# Release runbook

## Before deploying

1. Run `./scripts/release-check.sh` with Python 3.13 and `TEST_POSTGRES_URL`
   pointing to a disposable PostgreSQL database.
2. Confirm that Render has `ADMIN_BOT_TOKEN`, `PUBLIC_BOT_TOKEN`, `DATABASE_URL`,
   `WEBHOOK_SECRET`, `ANNOUNCEMENT_CHANNEL_ID`, `ADMIN_IDS`,
   `PUBLIC_BOT_USERNAME`, and `ADMIN_BOT_USERNAME`. Set optional
   `ERROR_ALERT_CHAT_ID` to receive unhandled-error alerts in Telegram.
3. Open `/ready`; it must return HTTP 200. `/health` is only a process liveness check.
4. Create a test show, register and cancel one viewer, send one announcement,
   connect a registrations chat, and exercise both entrance modes.

## Monitoring

- Alert on HTTP 5xx responses, `/ready` failures, process restarts, and log records
  with level `ERROR`.
- In Render, keep notifications enabled for failed deploys and service crashes.
- Search logs after each deployment for `failed to`, `Unhandled error`, and
  `Readiness database check failed`.
- A registrations-chat delivery failure is also sent directly to the show creator.

## PostgreSQL backup and restore drill

Use the backup controls of the managed PostgreSQL provider. At least monthly:

1. Create an on-demand backup and record its timestamp.
2. Restore it into a new, isolated database — never over production.
3. Set `DATABASE_URL` locally to the restored database and run
   `python -m alembic upgrade head`.
4. Verify counts for `users`, `shows`, `registrations`, and `manual_attendees`.
5. Start the bot against the isolated database without configuring production
   webhooks, inspect several shows, then delete the isolated restore.

Record the date, duration, backup timestamp, row counts, and result of every drill.

## Rollback

Prefer rolling the application back while leaving the database at the newest
migration. Database downgrades require a verified backup and an explicit review;
do not downgrade production automatically.
