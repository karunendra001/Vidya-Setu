from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, JSON, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String, default="")
    password_hash: Mapped[str] = mapped_column(String)
    # applicant | officer | approver | admin
    role: Mapped[str] = mapped_column(String, default="applicant")


class Scheme(Base):
    """A scheme is DATA: all rules live in `config`."""
    __tablename__ = "schemes"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str] = mapped_column(String)
    config: Mapped[dict] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    scheme_id: Mapped[int] = mapped_column(ForeignKey("schemes.id"))
    form_data: Mapped[dict] = mapped_column(JSON, default=dict)
    # DRAFT | SUBMITTED | DEFICIENT | VERIFIED | REJECTED
    status: Mapped[str] = mapped_column(String, default="DRAFT")
    eligibility: Mapped[dict] = mapped_column(JSON, default=dict)
    officer_note: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"))
    doc_type: Mapped[str] = mapped_column(String)
    filename: Mapped[str] = mapped_column(String)
    path: Mapped[str] = mapped_column(String)
    ocr_data: Mapped[dict] = mapped_column(JSON, default=dict)  # filled later by OCR step
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String)
    entity: Mapped[str] = mapped_column(String)
    entity_id: Mapped[int] = mapped_column(Integer)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)