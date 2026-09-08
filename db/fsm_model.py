from sqlalchemy import BigInteger, Column, DateTime, String, Text

from db.base import Base
from db.model_types import utc_default


class FSMStorageRecord(Base):
    """Persistent aiogram FSM data, shared by both bot processes."""

    __tablename__ = "fsm_storage"

    bot_id = Column(BigInteger, primary_key=True)
    chat_id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, primary_key=True)
    thread_id = Column(BigInteger, primary_key=True, default=0)
    business_connection_id = Column(String(128), primary_key=True, default="")
    destiny = Column(String(64), primary_key=True, default="default")
    state = Column(String(256), nullable=True)
    data = Column(Text, nullable=False, default="{}")
    updated_at = Column(DateTime, default=utc_default, onupdate=utc_default, nullable=False)
