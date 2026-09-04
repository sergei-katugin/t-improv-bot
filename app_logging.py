import logging

PROJECT_LOG_PREFIX = "[BOT][T-IMPRO-BOT]"

PROJECT_LOGGER_PREFIXES = (
    "admin_bot",
    "public_bot",
    "scheduler",
    "db",
    "miniapp_api",
    "t_improv_bot",
    "__main__",
    "main",
)

_BASE_LOG_RECORD_FACTORY = logging.getLogRecordFactory()


def _is_project_logger(name: str) -> bool:
    return name.startswith(PROJECT_LOGGER_PREFIXES) or name in {"__main__", "main"}


def project_log_record_factory(name, level, pathname, lineno, msg, args, exc_info, func=None, sinfo=None, **kwargs):
    record = _BASE_LOG_RECORD_FACTORY(name, level, pathname, lineno, msg, args, exc_info, func=func, sinfo=sinfo, **kwargs)
    record.project_prefix = PROJECT_LOG_PREFIX if _is_project_logger(record.name) else ""
    return record


def install_project_logging() -> None:
    global _BASE_LOG_RECORD_FACTORY
    _BASE_LOG_RECORD_FACTORY = logging.getLogRecordFactory()
    logging.setLogRecordFactory(project_log_record_factory)


def get_project_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
