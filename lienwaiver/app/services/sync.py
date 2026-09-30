"""Pull vendor payments (and the vendors, projects and bills they reference) from NetSuite into the app."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Payment, PaymentBill, Project, Setting, Vendor, utcnow
from . import netsuite

log = logging.getLogger("lienwaiver.sync")


@dataclass
class SyncResult:
    payments_created: int = 0
    payments_updated: int = 0
    vendors: int = 0
    projects: int = 0
    skipped_no_project: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        s = (f"{self.payments_created} new payment(s), {self.payments_updated} updated, "
             f"{self.vendors} vendor(s), {self.projects} project(s)")
        if self.skipped_no_project:
            s += f", {self.skipped_no_project} bill(s) skipped with no Project"
        return s


def _setting(db: Session, key: str) -> str | None:
    row = db.get(Setting, key)
    return row.value if row else None


def _set(db: Session, key: str, value: str) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value


def run_sync(db: Session, adapter: netsuite.NetSuiteAdapter | None = None, since: date | None = None) -> SyncResult:
    adapter = adapter or netsuite.get_adapter()
    res = SyncResult()
    if since is None:
        last = _setting(db, "_last_sync_date")
        start = datetime.strptime(settings.netsuite_sync_start, "%Y-%m-%d").date()
        since = max(start, datetime.strptime(last, "%Y-%m-%d").date() - timedelta(days=7)) if last else start

    payments = adapter.payments_since(since)
    vendor_ids = sorted({p.vendor_id for p in payments})
    project_ids = sorted({b.project_id for p in payments for b in p.bills if b.project_id})

    vendors_by_ns = _upsert_vendors(db, adapter.vendors(vendor_ids), res)
    projects_by_ns = _upsert_projects(db, adapter.projects(project_ids), res)

    for p in payments:
        vendor = vendors_by_ns.get(p.vendor_id)
        if vendor is None:
            res.errors.append(f"payment {p.reference or p.id}: vendor {p.vendor_id} not found")
            continue
        by_project: dict[str, list[netsuite.NsBill]] = {}
        for b in p.bills:
            if not b.project_id:
                res.skipped_no_project += 1
                continue
            by_project.setdefault(b.project_id, []).append(b)
        for ns_project_id, bills in by_project.items():
            project = projects_by_ns.get(ns_project_id)
            if project is None:
                res.errors.append(f"payment {p.reference or p.id}: project {ns_project_id} not found")
                continue
            amount = sum(b.applied_cents for b in bills) or sum(b.net_cents for b in bills)
            existing = db.query(Payment).filter(Payment.netsuite_id == p.id, Payment.project_id == project.id).one_or_none()
            new_bills = [PaymentBill(netsuite_id=b.id, invoice_number=b.invoice_number, invoice_date=b.invoice_date,
                                     gross_cents=b.gross_cents, net_cents=b.applied_cents or b.net_cents) for b in bills]
            if existing:
                existing.payment_date, existing.amount_cents, existing.reference, existing.memo = p.date, amount, p.reference, p.memo
                existing.bills = new_bills
                res.payments_updated += 1
            else:
                db.add(Payment(netsuite_id=p.id, vendor_id=vendor.id, project_id=project.id, payment_date=p.date,
                               amount_cents=amount, reference=p.reference, memo=p.memo, bills=new_bills))
                res.payments_created += 1

    _set(db, "_last_sync_date", date.today().isoformat())
    _set(db, "_last_sync_at", utcnow().isoformat(timespec="minutes"))
    _set(db, "_last_sync_result", res.summary() + (f"; errors: {'; '.join(res.errors[:5])}" if res.errors else ""))
    db.commit()
    log.info("sync: %s", res.summary())
    return res


def _upsert_vendors(db: Session, rows: list[netsuite.NsVendor], res: SyncResult) -> dict[str, Vendor]:
    out: dict[str, Vendor] = {}
    for v in rows:
        vendor = db.query(Vendor).filter(Vendor.netsuite_id == v.id).one_or_none()
        if vendor is None:
            vendor = db.query(Vendor).filter(Vendor.name == v.name, Vendor.netsuite_id.is_(None)).one_or_none()
        if vendor is None:
            vendor = Vendor(name=v.name, netsuite_id=v.id)
            db.add(vendor)
        vendor.netsuite_id = v.id
        vendor.name = v.name or vendor.name
        # NetSuite owns the address; the app owns contact, hold mode and everything else
        for f in ("address1", "address2", "city", "state", "zip"):
            if getattr(v, f):
                setattr(vendor, f, getattr(v, f))
        if v.email and not vendor.contact_email:
            vendor.contact_email = v.email
        out[v.id] = vendor
        res.vendors += 1
    db.flush()
    return out


def _upsert_projects(db: Session, rows: list[netsuite.NsProject], res: SyncResult) -> dict[str, Project]:
    out: dict[str, Project] = {}
    for p in rows:
        project = db.query(Project).filter(Project.netsuite_id == p.id).one_or_none()
        if project is None:
            project = db.query(Project).filter(Project.name == p.name, Project.netsuite_id.is_(None)).one_or_none()
        if project is None:
            project = Project(name=p.name, netsuite_id=p.id)
            db.add(project)
        project.netsuite_id = p.id
        project.name = p.name or project.name
        if p.inactive:
            project.active = False
        out[p.id] = project
        res.projects += 1
    db.flush()
    return out


def sync_status(db: Session) -> dict[str, str]:
    return {"at": _setting(db, "_last_sync_at") or "never", "result": _setting(db, "_last_sync_result") or ""}
