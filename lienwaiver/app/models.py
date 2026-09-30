"""Database model. Money is stored in integer cents to avoid float and SQLite Decimal issues."""
from __future__ import annotations

import secrets
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def cents_to_decimal(cents: int) -> Decimal:
    return (Decimal(cents) / 100).quantize(Decimal("0.01"))


def decimal_to_cents(value: Decimal | str | float) -> int:
    return int((Decimal(str(value)) * 100).quantize(Decimal("1")))


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    password_hash: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Vendor(Base):
    __tablename__ = "vendors"
    id: Mapped[int] = mapped_column(primary_key=True)
    netsuite_id: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    address1: Mapped[str] = mapped_column(String(200), default="")
    address2: Mapped[str] = mapped_column(String(200), default="")
    city: Mapped[str] = mapped_column(String(100), default="")
    state: Mapped[str] = mapped_column(String(2), default="OH")
    zip: Mapped[str] = mapped_column(String(10), default="")
    contact_name: Mapped[str] = mapped_column(String(128), default="")
    contact_email: Mapped[str] = mapped_column(String(254), default="")
    # previous: waiver for the previous payment gates the next one (N-day window)
    # exchange: every payment needs a received waiver before the vendor is payable
    hold_mode: Mapped[str] = mapped_column(String(16), default="previous")
    return_days: Mapped[int | None] = mapped_column(Integer, nullable=True)  # overrides the default
    on_hold: Mapped[bool] = mapped_column(Boolean, default=False)
    hold_reason: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")

    payments: Mapped[list[Payment]] = relationship(back_populates="vendor")
    waivers: Mapped[list[Waiver]] = relationship(back_populates="vendor")

    @property
    def address_lines(self) -> list[str]:
        lines = [self.address1, self.address2, f"{self.city}, {self.state} {self.zip}".strip(", ")]
        return [l for l in lines if l and l != ","]


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    netsuite_id: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    job_number: Mapped[str] = mapped_column(String(64), default="")
    address1: Mapped[str] = mapped_column(String(200), default="")
    city: Mapped[str] = mapped_column(String(100), default="")
    state: Mapped[str] = mapped_column(String(2), default="OH")
    zip: Mapped[str] = mapped_column(String(10), default="")
    county: Mapped[str] = mapped_column(String(64), default="")
    owner_name: Mapped[str] = mapped_column(String(200), default="")
    gc_name: Mapped[str] = mapped_column(String(200), default="")
    bond_project: Mapped[bool] = mapped_column(Boolean, default=False)
    surety_name: Mapped[str] = mapped_column(String(200), default="")
    bond_number: Mapped[str] = mapped_column(String(64), default="")
    complete: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")

    payments: Mapped[list[Payment]] = relationship(back_populates="project")
    waivers: Mapped[list[Waiver]] = relationship(back_populates="project")

    @property
    def property_address(self) -> str:
        parts = [self.address1, f"{self.city}, {self.state} {self.zip}".strip(", ")]
        return ", ".join(p for p in parts if p and p != ",")


class Payment(Base):
    """One payment to one vendor for one project. A NetSuite payment covering two projects becomes two rows."""

    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("netsuite_id", "project_id", name="uq_payment_ns_project"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    netsuite_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"))
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    payment_date: Mapped[date] = mapped_column(Date)
    amount_cents: Mapped[int] = mapped_column(Integer)
    reference: Mapped[str] = mapped_column(String(64), default="")  # check number or ACH trace
    memo: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    vendor: Mapped[Vendor] = relationship(back_populates="payments")
    project: Mapped[Project] = relationship(back_populates="payments")
    waivers: Mapped[list[Waiver]] = relationship(back_populates="payment")

    @property
    def amount(self) -> Decimal:
        return cents_to_decimal(self.amount_cents)

    @property
    def live_waiver(self) -> Waiver | None:
        for w in self.waivers:
            if w.status != "void":
                return w
        return None


class Waiver(Base):
    __tablename__ = "waivers"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(32), unique=True)
    portal_token: Mapped[str] = mapped_column(String(32), unique=True, default=lambda: secrets.token_urlsafe(12))
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"))
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"), nullable=True)
    waiver_type: Mapped[str] = mapped_column(String(16))  # progress | final
    amount_cents: Mapped[int] = mapped_column(Integer)
    through_date: Mapped[date] = mapped_column(Date)
    retention_cents: Mapped[int] = mapped_column(Integer, default=0)
    disputed_cents: Mapped[int] = mapped_column(Integer, default=0)
    exceptions_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft | sent | received | void
    pdf_unsigned_path: Mapped[str] = mapped_column(String(400), default="")
    pdf_signed_path: Mapped[str] = mapped_column(String(400), default="")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    due_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    received_via: Mapped[str] = mapped_column(String(32), default="")
    void_reason: Mapped[str] = mapped_column(String(200), default="")
    reminder_count: Mapped[int] = mapped_column(Integer, default=0)
    last_reminder_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    vendor: Mapped[Vendor] = relationship(back_populates="waivers")
    project: Mapped[Project] = relationship(back_populates="waivers")
    payment: Mapped[Payment | None] = relationship(back_populates="waivers")
    events: Mapped[list[Event]] = relationship(back_populates="waiver", order_by="Event.at")

    @property
    def amount(self) -> Decimal:
        return cents_to_decimal(self.amount_cents)

    @property
    def retention(self) -> Decimal:
        return cents_to_decimal(self.retention_cents)

    @property
    def disputed(self) -> Decimal:
        return cents_to_decimal(self.disputed_cents)

    def is_overdue(self, today: date | None = None) -> bool:
        today = today or date.today()
        return self.status == "sent" and self.due_at is not None and self.due_at < today

    @property
    def display_status(self) -> str:
        if self.is_overdue():
            return "overdue"
        return self.status

    @property
    def title(self) -> str:
        kind = "Progress" if self.waiver_type == "progress" else "Final"
        return f"Unconditional Waiver and Release of Lien upon {kind} Payment"


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    waiver_id: Mapped[int | None] = mapped_column(ForeignKey("waivers.id"), nullable=True)
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    user: Mapped[str] = mapped_column(String(64), default="system")
    action: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str] = mapped_column(Text, default="")

    waiver: Mapped[Waiver | None] = relationship(back_populates="events")
