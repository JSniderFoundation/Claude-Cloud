from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import Project, User, Vendor, Waiver
from ..services import waivers as svc
from ..web import flash, render

router = APIRouter(prefix="/waivers", dependencies=[Depends(current_user)])


def _get(db: Session, waiver_id: int) -> Waiver:
    w = db.get(Waiver, waiver_id)
    if w is None:
        raise HTTPException(404)
    return w


@router.get("")
def list_waivers(request: Request, status: str = "", project: int = 0, vendor: int = 0,
                 db: Session = Depends(get_db), user: User = Depends(current_user)):
    request.state.user = user
    q = db.query(Waiver)
    if project:
        q = q.filter(Waiver.project_id == project)
    if vendor:
        q = q.filter(Waiver.vendor_id == vendor)
    rows = q.order_by(Waiver.created_at.desc()).all()
    if status == "overdue":
        rows = [w for w in rows if w.is_overdue()]
    elif status == "open":
        rows = [w for w in rows if w.status in ("draft", "sent")]
    elif status:
        rows = [w for w in rows if w.status == status]
    return render(request, "waivers.html", waivers=rows, status=status, project=project, vendor=vendor,
                  projects=db.query(Project).order_by(Project.name).all(),
                  vendors=db.query(Vendor).order_by(Vendor.name).all())


@router.get("/{waiver_id}")
def detail(request: Request, waiver_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    request.state.user = user
    w = _get(db, waiver_id)
    return render(request, "waiver_detail.html", w=w, portal_url=svc.portal_url(w), active="waivers")


@router.get("/{waiver_id}/pdf/{kind}")
def pdf(waiver_id: int, kind: str, db: Session = Depends(get_db)):
    w = _get(db, waiver_id)
    path = w.pdf_signed_path if kind == "signed" else w.pdf_unsigned_path
    if not path:
        raise HTTPException(404, "No PDF yet")
    return FileResponse(path, media_type="application/pdf", filename=f"{w.number}-{kind}.pdf")


@router.post("/{waiver_id}/send")
def send(request: Request, waiver_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    w = _get(db, waiver_id)
    try:
        svc.send(db, w, user.username)
        db.commit()
        flash(request, f"{w.number} sent to {w.vendor.contact_email or 'nobody (no email on file)'}.",
              "ok" if w.vendor.contact_email else "warn")
    except Exception as e:
        db.rollback()
        flash(request, f"Send failed: {e}", "error")
    return RedirectResponse(f"/waivers/{w.id}", status_code=303)


@router.post("/{waiver_id}/regenerate")
def regenerate(request: Request, waiver_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    w = _get(db, waiver_id)
    svc.regenerate_pdf(db, w, user.username)
    db.commit()
    flash(request, "PDF regenerated.")
    return RedirectResponse(f"/waivers/{w.id}", status_code=303)


@router.post("/{waiver_id}/update")
async def update(request: Request, waiver_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    w = _get(db, waiver_id)
    if w.status == "received":
        flash(request, "A received waiver cannot be edited. Void it and create a new one.", "warn")
        return RedirectResponse(f"/waivers/{w.id}", status_code=303)
    form = await request.form()
    try:
        w.waiver_type = "final" if form.get("waiver_type") == "final" else "progress"
        w.through_date = datetime.strptime(str(form.get("through_date")), "%Y-%m-%d").date()
        w.exceptions_text = str(form.get("exceptions_text", "")).strip()
        svc.log(db, w, user.username, "edited", "type, through date or exceptions changed")
        svc.regenerate_pdf(db, w, user.username)
        db.commit()
        flash(request, "Saved and PDF regenerated." + (" Resend it so the vendor has the new version." if w.status == "sent" else ""))
    except Exception as e:
        db.rollback()
        flash(request, f"Could not save: {e}", "error")
    return RedirectResponse(f"/waivers/{w.id}", status_code=303)


@router.post("/{waiver_id}/receive")
async def receive(request: Request, waiver_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    w = _get(db, waiver_id)
    form = await request.form()
    upload = form.get("signed_pdf")
    content = await upload.read() if upload is not None and hasattr(upload, "read") else b""
    try:
        svc.receive(db, w, content, str(form.get("via") or "upload"), user.username)
        flash(request, f"{w.number} marked received.")
    except ValueError as e:
        db.rollback()
        flash(request, str(e), "error")
    return RedirectResponse(f"/waivers/{w.id}", status_code=303)


@router.post("/{waiver_id}/void")
async def void(request: Request, waiver_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    w = _get(db, waiver_id)
    form = await request.form()
    svc.void(db, w, str(form.get("reason", "")).strip() or "voided", user.username)
    flash(request, f"{w.number} voided. The payment is back in the queue.")
    return RedirectResponse("/", status_code=303)
