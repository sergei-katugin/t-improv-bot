import enum
from datetime import datetime

from time_utils import utc_now


def utc_default() -> datetime:
    return utc_now()


class UserRole(str, enum.Enum):
    admin = "admin"
    organizer = "organizer"
    user = "user"
