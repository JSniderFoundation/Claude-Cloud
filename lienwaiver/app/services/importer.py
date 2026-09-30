"""CSV import for vendors, projects and payments (phase 1 stand-in for the NetSuite sync)."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy.orm import Session

from ..models import Payment, Project, Vendor, decimal_to_cents

VENDOR_COLUMNS = ["name", "netsuite_id", "address1", "address2", "city", "state", "zip", "contact_name", "contact_email"]
PROJECT_COLUMNS = ["name", "job_number", "netsuite_id", "address1", "city", "state", "zip", "county", "owner_name",
                   "gc_name", "bond_project", "surety_name", "bond_number"]
PAYMENT_COLUMNS = ["vendor", "project", "date", "amount", "reference", "memo", "netsuite_id"]


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    errors: list[str] = field(default_factory=list)


def _rows(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text))
    return [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()} for row in reader]


def _parse_date(value: str) -> date:
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"unrecognised date {value!r}")


def _truthy(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "y", "t")


def import_vendors(db: Session, text: str) -> ImportResult:
    res = ImportResult()
    for i, row in enumerate(_rows(text), start=2):
        if not row.get("name"):
            res.errors.append(f"line {i}: name is required")
            continue
        vendor = None
        if row.get("netsuite_id"):
            vendor = db.query(Vendor).filter(Vendor.netsuite_id == row["netsuite_id"]).one_or_none()
        if vendor is None:
            vendor = db.query(Vendor).filter(Vendor.name == row["name"]).one_or_none()
        if vendor is None:
            vendor = Vendor(name=row["name"])
            db.add(vendor)
            res.created += 1
        else:
            res.updated += 1
        for col in VENDOR_COLUMNS:
            if col in row and row[col] != "":
                setattr(vendor, col, row[col])
    db.commit()
    return res


def import_projects(db: Session, text: str) -> ImportResult:
    res = ImportResult()
    for i, row in enumerate(_rows(text), start=2):
        if not row.get("name"):
            res.errors.append(f"line {i}: name is required")
            continue
        project = None
        if row.get("netsuite_id"):
            project = db.query(Project).filter(Project.netsuite_id == row["netsuite_id"]).one_or_none()
        if project is None and row.get("job_number"):
            project = db.query(Project).filter(Project.job_number == row["job_number"]).one_or_none()
        if project is None:
            project = db.query(Project).filter(Project.name == row["name"]).one_or_none()
        if project is None:
            project = Project(name=row["name"])
            db.add(project)
            res.created += 1
        else:
            res.updated += 1
        for col in PROJECT_COLUMNS:
            if col in row and row[col] != "":
                setattr(project, col, _truthy(row[col]) if col == "bond_project" else row[col])
    db.commit()
    return res


def find_vendor(db: Session, key: str) -> Vendor | None:
    return (db.query(Vendor).filter(Vendor.netsuite_id == key).one_or_none()
            or db.query(Vendor).filter(Vendor.name == key).one_or_none())


def find_project(db: Session, key: str) -> Project | None:
    return (db.query(Project).filter(Project.netsuite_id == key).one_or_none()
            or db.query(Project).filter(Project.job_number == key).one_or_none()
            or db.query(Project).filter(Project.name == key).one_or_none())


def import_payments(db: Session, text: str) -> ImportResult:
    res = ImportResult()
    for i, row in enumerate(_rows(text), start=2):
        try:
            vendor = find_vendor(db, row.get("vendor", ""))
            project = find_project(db, row.get("project", ""))
            if vendor is None:
                raise ValueError(f"vendor {row.get('vendor')!r} not found")
            if project is None:
                raise ValueError(f"project {row.get('project')!r} not found")
            when = _parse_date(row.get("date", ""))
            cents = decimal_to_cents(row.get("amount", "").replace("$", "").replace(",", ""))
        except (ValueError, ArithmeticError) as e:
            res.errors.append(f"line {i}: {e}")
            continue
        ns_id = row.get("netsuite_id") or None
        existing = None
        if ns_id:
            existing = db.query(Payment).filter(Payment.netsuite_id == ns_id, Payment.project_id == project.id).one_or_none()
        if existing is None and row.get("reference"):
            existing = db.query(Payment).filter(Payment.vendor_id == vendor.id, Payment.project_id == project.id,
                                                Payment.reference == row["reference"]).one_or_none()
        if existing:
            existing.payment_date, existing.amount_cents, existing.memo = when, cents, row.get("memo", "")
            res.updated += 1
        else:
            db.add(Payment(netsuite_id=ns_id, vendor_id=vendor.id, project_id=project.id, payment_date=when,
                           amount_cents=cents, reference=row.get("reference", ""), memo=row.get("memo", "")))
            res.created += 1
    db.commit()
    return res
