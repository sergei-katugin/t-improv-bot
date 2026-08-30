import os
import sqlite3
import subprocess
import sys

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_has_single_expected_head():
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert scripts.get_heads() == ["0016"]


def test_full_migration_chain_upgrades_empty_sqlite_database(tmp_path):
    database_path = tmp_path / "migration-test.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{database_path}"

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        cwd=os.getcwd(),
        env=env,
        capture_output=True,
        text=True,
    )

    with sqlite3.connect(database_path) as connection:
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    assert version == ("0016",)


def test_timezone_migration_converts_existing_local_show_date(tmp_path):
    database_path = tmp_path / "timezone-migration.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{database_path}"
    command = [sys.executable, "-m", "alembic"]
    subprocess.run(command + ["upgrade", "0013"], check=True, env=env, capture_output=True, text=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO users (telegram_id, role, onboarding_done, created_at) VALUES (?, ?, ?, ?)",
            (1, "user", 0, "2026-01-01 00:00:00"),
        )
        connection.execute(
            "INSERT INTO shows (title, team_name, show_date, location, city, max_seats, "
            "is_active, checkin_enabled, feedback_enabled, creator_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("Summer", "Team", "2026-07-15 19:30:00", "Venue", "Limassol", 10, 1, 0, 0, 1),
        )
        connection.commit()

    subprocess.run(command + ["upgrade", "head"], check=True, env=env, capture_output=True, text=True)
    with sqlite3.connect(database_path) as connection:
        stored = connection.execute("SELECT show_date FROM shows").fetchone()[0]
    assert stored.startswith("2026-07-15 16:30:00")
