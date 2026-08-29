import os


# Application imports happen during test collection. Explicitly allow the
# isolated SQLite engines used by unit and migration tests.
os.environ["ALLOW_SQLITE_FOR_TESTS"] = "true"
