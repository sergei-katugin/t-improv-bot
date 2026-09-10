from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from db.base import Base
from db.model_types import utc_default


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    actor_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(64), nullable=False)
    entity_type = Column(String(32), nullable=False)
    entity_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_default, nullable=False)

    actor = relationship("User")

    __table_args__ = (
        Index("ix_audit_logs_created_at", "created_at"),
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
    )
