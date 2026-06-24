import enum
from datetime import datetime, timezone
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Enum, ForeignKey,
    Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UserRole(str, enum.Enum):
    admin = "admin"
    organizer = "organizer"
    user = "user"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(64), nullable=True)
    first_name = Column(String(128), nullable=True)
    last_name = Column(String(128), nullable=True)
    role = Column(Enum(UserRole), default=UserRole.user, nullable=False)
    onboarding_done = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    shows_created = relationship("Show", back_populates="creator")
    registrations = relationship("Registration", back_populates="user")


class Show(Base):
    __tablename__ = "shows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(256), nullable=False)
    team_name = Column(String(256), nullable=False)
    show_date = Column(DateTime, nullable=False, index=True)
    location = Column(String(512), nullable=False)
    location_url = Column(String(512), nullable=True)
    city = Column(String(128), nullable=False, index=True)
    poster_text = Column(Text, nullable=True)
    poster_file_id = Column(String(256), nullable=True)
    pub_poster_file_id = Column(String(256), nullable=True)
    max_seats = Column(Integer, nullable=False, default=50)
    is_active = Column(Boolean, default=True, nullable=False)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    creator = relationship("User", back_populates="shows_created")
    registrations = relationship(
        "Registration",
        back_populates="show",
        cascade="all, delete-orphan",
    )
    announcement_logs = relationship(
        "AnnouncementLog",
        back_populates="show",
        cascade="all, delete-orphan",
    )


class Registration(Base):
    __tablename__ = "registrations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    show_id = Column(Integer, ForeignKey("shows.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    attendee_name = Column(String(256), nullable=False)
    is_cancelled = Column(Boolean, default=False, nullable=False)
    registered_at = Column(DateTime, default=_utcnow)
    cancelled_at = Column(DateTime, nullable=True)
    remind_14d = Column(Boolean, default=False, nullable=False)
    remind_7d = Column(Boolean, default=False, nullable=False)
    remind_1d = Column(Boolean, default=True, nullable=False)
    reminded_14d = Column(Boolean, default=False, nullable=False)
    reminded_7d = Column(Boolean, default=False, nullable=False)
    reminded_1d = Column(Boolean, default=False, nullable=False)
    guests = Column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("show_id", "user_id", name="uq_registration_show_user"),
    )

    show = relationship("Show", back_populates="registrations")
    user = relationship("User", back_populates="registrations")


class ManualAttendee(Base):
    __tablename__ = "manual_attendees"

    id = Column(Integer, primary_key=True, autoincrement=True)
    show_id = Column(Integer, ForeignKey("shows.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(256), nullable=False)
    added_at = Column(DateTime, default=_utcnow)

    show = relationship("Show")


class InviteToken(Base):
    __tablename__ = "invite_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(String(64), unique=True, nullable=False, index=True)
    role = Column(Enum(UserRole), default=UserRole.organizer, nullable=False)
    created_at = Column(DateTime, default=_utcnow, nullable=False)
    used_at = Column(DateTime, nullable=True)
    used_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256), nullable=False)
    members = Column(Text, nullable=True)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=_utcnow)

    creator = relationship("User")


class Venue(Base):
    __tablename__ = "venues"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256), nullable=False)
    city = Column(String(128), nullable=False, default="Лимасол")
    maps_url = Column(String(512), nullable=True)
    default_seats = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=_utcnow)


class AnnouncementLog(Base):
    __tablename__ = "announcement_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    show_id = Column(Integer, ForeignKey("shows.id", ondelete="CASCADE"), nullable=False)
    announcement_type = Column(String(32), nullable=False)
    channel_message_id = Column(Integer, nullable=True)
    sent_at = Column(DateTime, default=_utcnow)

    __table_args__ = (
        UniqueConstraint("show_id", "announcement_type", name="uq_announcement_show_type"),
    )

    show = relationship("Show", back_populates="announcement_logs")
