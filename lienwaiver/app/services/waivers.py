"""Waiver lifecycle: create from a payment, send, remind, receive, void."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Event, Payment, Vendor, Waiver, utcnow
from . import company as company_settings
from . import hold
from .email import Attachment, Mail, send_mail
from .pdf import waiver_pdf_path, write_unsigned_pdf



def portal_url(waiver: Waiver) -> str:
    return f"{settings.base_url}/p/{waiver.portal_token}"


def waiver_from_token(db: Session, token: str) -> Waiver | None:
    if not token or len(token) > 32:
        return None
    return db.query(Waiver).filter(Waiver.portal_token == token).one_or_none()


def next_number(db: Session, today: date | None = None) -> str:
    today = today or date.today()
    prefix = f"LW-{today.year}-"
    last = db.query(func.max(Waiver.number)).filter(Waiver.number.like(prefix + "%")).scalar()
    seq = int(last[len(prefix):]) + 1 if last else 1
    return f"{prefix}{seq:04d}"


def log(db: Session, waiver: Waiver, user: str, action: str, detail: str = "") -> None:
    db.add(Event(waiver_id=waiver.id, vendor_id=waiver.vendor_id, user=user, action=action, detail=detail))


def suggested_type(payment: Payment) -> str:
    return "final" if payment.project.complete else "progress"


def create_from_payment(db: Session, payment: Payment, waiver_type: str, user: str,
                        through_date: date | None = None) -> Waiver:
    if payment.live_waiver is not None:
        raise ValueError(f"Payment {payment.id} already has waiver {payment.live_waiver.number}")
    if waiver_type not in ("progress", "final"):
        raise ValueError("waiver_type must be progress or final")
    waiver = Waiver(
        number=next_number(db),
        vendor=payment.vendor,
        project=payment.project,
        payment=payment,
        waiver_type=waiver_type,
        amount_cents=payment.amount_cents,
        through_date=through_date or payment.latest_invoice_date or payment.payment_date,
        status="draft",
    )
    db.add(waiver)
    db.flush()
    log(db, waiver, user, "created", f"{waiver_type} waiver for payment {payment.reference or payment.id}")
    return waiver


def return_days(db: Session, vendor: Vendor) -> int:
    if vendor.return_days:
        return vendor.return_days
    return company_settings.get_int(company_settings.get_settings(db), "default_return_days")


def regenerate_pdf(db: Session, waiver: Waiver, user: str) -> Path:
    path = write_unsigned_pdf(waiver, company_settings.get_settings(db), portal_url(waiver))
    waiver.pdf_unsigned_path = str(path)
    log(db, waiver, user, "pdf_generated", path.name)
    return path


def _vendor_mail(db: Session, waiver: Waiver, subject: str, intro: str, attach: bool) -> Mail:
    cfg = company_settings.get_settings(db)
    body = (
        f"{waiver.vendor.contact_name or waiver.vendor.name},\n\n"
        f"{intro}\n\n"
        f"Waiver:      {waiver.number} ({'Progress' if waiver.waiver_type == 'progress' else 'Final'})\n"
        f"Project:     {waiver.project.name}\n"
        f"Payment:     ${waiver.amount:,.2f}"
        f"{f' on {waiver.payment.payment_date:%m/%d/%Y}' if waiver.payment else ''}"
        f"{' ref ' + waiver.payment.reference if waiver.payment and waiver.payment.reference else ''}\n"
        f"Return by:   {waiver.due_at:%m/%d/%Y}\n\n"
        f"Sign and return here (no login needed):\n{portal_url(waiver)}\n\n"
        f"You can also reply to this email with the signed copy attached.\n\n"
        f"Thank you,\n{cfg['company_name']} Accounts Payable\n{cfg['company_phone']}  {cfg['company_email']}\n"
    )
    attachments = []
    if attach and waiver.pdf_unsigned_path:
        attachments.append(Attachment(Path(waiver.pdf_unsigned_path).name, Path(waiver.pdf_unsigned_path).read_bytes()))
    return Mail(to=[waiver.vendor.contact_email], subject=subject, body=body, attachments=attachments)


def send(db: Session, waiver: Waiver, user: str, today: date | None = None) -> None:
    """Generate the PDF if needed, email the vendor, move to sent. Also used to resend."""
    if waiver.status in ("received", "void"):
        raise ValueError(f"Waiver {waiver.number} is {waiver.status}")
    if not waiver.vendor.contact_email:
        raise ValueError(f"{waiver.vendor.name} has no contact email. Add one on the vendor page, then send.")
    today = today or date.today()
    if not waiver.pdf_unsigned_path or not Path(waiver.pdf_unsigned_path).exists():
        regenerate_pdf(db, waiver, user)
    first_send = waiver.status == "draft"
    if first_send:
        waiver.sent_at = utcnow()
        waiver.due_at = today + timedelta(days=return_days(db, waiver.vendor))
        waiver.status = "sent"
    cfg = company_settings.get_settings(db)
    mail = _vendor_mail(db, waiver, f"Lien waiver {waiver.number} for {waiver.project.name} - please sign and return",
                        cfg["email_intro"], attach=True)
    send_mail(mail)
    log(db, waiver, user, "sent" if first_send else "resent", f"to {waiver.vendor.contact_email}")


def remind(db: Session, waiver: Waiver, today: date) -> None:
    overdue = waiver.due_at and waiver.due_at < today
    intro = (f"This lien waiver is {'overdue' if overdue else 'due soon'}. Please sign and return it. "
             f"Outstanding waivers can delay future payments.")
    mail = _vendor_mail(db, waiver, f"Reminder: lien waiver {waiver.number} for {waiver.project.name}", intro, attach=True)
    send_mail(mail)
    waiver.reminder_count += 1
    waiver.last_reminder_at = today
    log(db, waiver, "system", "reminder", f"#{waiver.reminder_count}, {'overdue' if overdue else 'due soon'}")


def receive(db: Session, waiver: Waiver, content: bytes, via: str, user: str) -> None:
    if waiver.status == "void":
        raise ValueError("Cannot receive a void waiver")
    if not content.startswith(b"%PDF"):
        raise ValueError("The signed copy must be a PDF")
    path = waiver_pdf_path(waiver, "signed")
    path.write_bytes(content)
    waiver.pdf_signed_path = str(path)
    waiver.status = "received"
    waiver.received_at = utcnow()
    waiver.received_via = via
    log(db, waiver, user, "received", f"via {via}")
    db.commit()
    hold.apply_holds(db, user=user)
    notify_ap(db, f"Signed lien waiver received: {waiver.number}",
              f"{waiver.vendor.name} returned {waiver.number} ({waiver.project.name}, ${waiver.amount:,.2f}) via {via}.\n"
              f"{settings.base_url}/waivers/{waiver.id}")


def void(db: Session, waiver: Waiver, reason: str, user: str) -> None:
    waiver.status = "void"
    waiver.void_reason = reason
    log(db, waiver, user, "void", reason)
    db.commit()
    hold.apply_holds(db, user=user)


def notify_ap(db: Session, subject: str, body: str) -> None:
    if settings.ap_notify_email:
        send_mail(Mail(to=[settings.ap_notify_email], subject=subject, body=body))


def reminders_due(db: Session, today: date) -> list[Waiver]:
    cfg = company_settings.get_settings(db)
    before = company_settings.get_int(cfg, "reminder_days_before_due")
    every = company_settings.get_int(cfg, "reminder_every_days_after_due")
    due: list[Waiver] = []
    for w in db.query(Waiver).filter(Waiver.status == "sent").all():
        if not w.due_at or not w.vendor.contact_email:
            continue
        if w.last_reminder_at == today:
            continue
        if w.due_at < today:
            days_over = (today - w.due_at).days
            last = w.last_reminder_at
            if last is None or last < w.due_at or (today - last).days >= every or days_over == 0:
                due.append(w)
        elif w.reminder_count == 0 and (w.due_at - today).days <= before:
            due.append(w)
    return due
