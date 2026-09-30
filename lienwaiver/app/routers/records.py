"""Projects, vendors, payments and CSV import."""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import Event, Payment, Project, User, Vendor, cents_to_decimal, decimal_to_cents
from ..services import importer
from ..web import flash, render

router = APIRouter(dependencies=[Depends(current_user)])

PROJECT_FIELDS = ["name", "job_number", "netsuite_id", "address1", "city", "state", "zip", "county", "owner_name",
                  "gc_name", "surety_name", "bond_number", "notes"]
VENDOR_FIELDS = ["name", "netsuite_id", "address1", "address2", "city", "state", "zip", "contact_name", "contact_email",
                 "hold_mode", "notes"]


def _apply(obj, form, fields: list[str], checkboxes: list[str]):
    for f in fields:
        if f in form:
            value = str(form.get(f, "")).strip()
            if f == "netsuite_id":
                value = value or None  # unique column: empty must be NULL, not ""
            setattr(obj, f, value)
    for c in checkboxes:
        setattr(obj, c, form.get(c) == "on")


# ---- projects ---------------------------------------------------------------

@router.get("/projects")
def projects(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    request.state.user = user
    rows = db.query(Project).order_by(Project.active.desc(), Project.name).all()
    return render(request, "projects.html", projects=rows)


@router.get("/projects/new")
def project_new(request: Request, user: User = Depends(current_user)):
    request.state.user = user
    return render(request, "project_form.html", p=Project(state="OH", active=True), active="projects")


@router.post("/projects/new")
async def project_create(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    form = await request.form()
    p = Project(name="")
    _apply(p, form, PROJECT_FIELDS, ["bond_project", "complete", "active"])
    if not p.name:
        flash(request, "Name is required.", "error")
        return RedirectResponse("/projects/new", status_code=303)
    db.add(p)
    db.commit()
    flash(request, f"Project {p.name} created.")
    return RedirectResponse(f"/projects/{p.id}", status_code=303)


@router.get("/projects/{project_id}")
def project_detail(request: Request, project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    request.state.user = user
    p = db.get(Project, project_id) or _404()
    coverage = {}
    for pay in p.payments:
        c = coverage.setdefault(pay.vendor_id, {"vendor": pay.vendor, "paid": 0, "waived": 0, "open": 0, "missing": 0})
        c["paid"] += pay.amount_cents
        w = pay.live_waiver
        if w is None:
            c["missing"] += pay.amount_cents
        elif w.status == "received":
            c["waived"] += pay.amount_cents
        else:
            c["open"] += pay.amount_cents
    rows = sorted(coverage.values(), key=lambda c: c["vendor"].name)
    for c in rows:
        for k in ("paid", "waived", "open", "missing"):
            c[k] = cents_to_decimal(c[k])
    return render(request, "project_detail.html", p=p, coverage=rows, active="projects")


@router.get("/projects/{project_id}/edit")
def project_edit(request: Request, project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    request.state.user = user
    p = db.get(Project, project_id) or _404()
    return render(request, "project_form.html", p=p, active="projects")


@router.post("/projects/{project_id}/edit")
async def project_update(request: Request, project_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = db.get(Project, project_id) or _404()
    form = await request.form()
    _apply(p, form, PROJECT_FIELDS, ["bond_project", "complete", "active"])
    db.commit()
    flash(request, "Project saved. Regenerate any draft or sent waivers if the address, owner or bond status changed.")
    return RedirectResponse(f"/projects/{p.id}", status_code=303)


# ---- vendors ----------------------------------------------------------------

@router.get("/vendors")
def vendors(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    request.state.user = user
    rows = db.query(Vendor).order_by(Vendor.on_hold.desc(), Vendor.active.desc(), Vendor.name).all()
    return render(request, "vendors.html", vendors=rows)


@router.get("/vendors/new")
def vendor_new(request: Request, user: User = Depends(current_user)):
    request.state.user = user
    return render(request, "vendor_form.html", v=Vendor(state="OH", hold_mode="previous", active=True), active="vendors")


@router.post("/vendors/new")
async def vendor_create(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    form = await request.form()
    v = Vendor(name="")
    _apply(v, form, VENDOR_FIELDS, ["active"])
    v.return_days = _int_or_none(form.get("return_days"))
    if not v.name:
        flash(request, "Name is required.", "error")
        return RedirectResponse("/vendors/new", status_code=303)
    db.add(v)
    db.commit()
    flash(request, f"Vendor {v.name} created.")
    return RedirectResponse(f"/vendors/{v.id}", status_code=303)


@router.get("/vendors/{vendor_id}")
def vendor_detail(request: Request, vendor_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    request.state.user = user
    v = db.get(Vendor, vendor_id) or _404()
    events = db.query(Event).filter(Event.vendor_id == v.id, Event.waiver_id.is_(None)).order_by(Event.at.desc()).limit(20).all()
    waivers = sorted(v.waivers, key=lambda w: w.created_at, reverse=True)
    return render(request, "vendor_detail.html", v=v, waivers=waivers, events=events, active="vendors")


@router.get("/vendors/{vendor_id}/edit")
def vendor_edit(request: Request, vendor_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    request.state.user = user
    v = db.get(Vendor, vendor_id) or _404()
    return render(request, "vendor_form.html", v=v, active="vendors")


@router.post("/vendors/{vendor_id}/edit")
async def vendor_update(request: Request, vendor_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    v = db.get(Vendor, vendor_id) or _404()
    form = await request.form()
    _apply(v, form, VENDOR_FIELDS, ["active"])
    v.return_days = _int_or_none(form.get("return_days"))
    db.commit()
    flash(request, "Vendor saved.")
    return RedirectResponse(f"/vendors/{v.id}", status_code=303)


# ---- payments and import ----------------------------------------------------

@router.get("/payments/new")
def payment_new(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    request.state.user = user
    return render(request, "payment_form.html", today=date.today(),
                  projects=db.query(Project).filter(Project.active.is_(True)).order_by(Project.name).all(),
                  vendors=db.query(Vendor).filter(Vendor.active.is_(True)).order_by(Vendor.name).all(), active="queue")


@router.post("/payments/new")
async def payment_create(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    form = await request.form()
    try:
        p = Payment(
            vendor_id=int(form.get("vendor_id")),
            project_id=int(form.get("project_id")),
            payment_date=datetime.strptime(str(form.get("payment_date")), "%Y-%m-%d").date(),
            amount_cents=decimal_to_cents(str(form.get("amount")).replace("$", "").replace(",", "")),
            reference=str(form.get("reference", "")).strip(),
            memo=str(form.get("memo", "")).strip(),
        )
        if p.amount_cents <= 0:
            raise ValueError("amount must be positive")
        db.add(p)
        db.commit()
        flash(request, "Payment added. It is now in the queue.")
        return RedirectResponse("/", status_code=303)
    except (TypeError, ValueError, ArithmeticError) as e:
        flash(request, f"Could not add payment: {e}", "error")
        return RedirectResponse("/payments/new", status_code=303)


@router.get("/import")
def import_form(request: Request, user: User = Depends(current_user)):
    request.state.user = user
    return render(request, "import.html", result=None, kind="payments",
                  columns={"vendors": importer.VENDOR_COLUMNS, "projects": importer.PROJECT_COLUMNS, "payments": importer.PAYMENT_COLUMNS})


@router.post("/import")
async def import_run(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    request.state.user = user
    form = await request.form()
    kind = str(form.get("kind", "payments"))
    upload = form.get("file")
    text = (await upload.read()).decode("utf-8-sig") if upload is not None and hasattr(upload, "read") else ""
    fn = {"vendors": importer.import_vendors, "projects": importer.import_projects, "payments": importer.import_payments}.get(kind)
    result = fn(db, text) if fn and text else importer.ImportResult(errors=["No file or unknown type."])
    return render(request, "import.html", result=result, kind=kind,
                  columns={"vendors": importer.VENDOR_COLUMNS, "projects": importer.PROJECT_COLUMNS, "payments": importer.PAYMENT_COLUMNS})


def _404():
    raise HTTPException(404)


def _int_or_none(value) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return max(1, int(text))
    except ValueError:
        return None
