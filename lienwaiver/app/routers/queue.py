"""Home page: payments that still need a waiver, generated and sent in one click."""
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import Payment, User, Vendor, Waiver
from ..services import waivers as svc
from ..web import flash, render

router = APIRouter(dependencies=[Depends(current_user)])


def _needs_waiver(db: Session) -> list[Payment]:
    rows = db.query(Payment).order_by(Payment.payment_date.desc(), Payment.id.desc()).all()
    return [p for p in rows if p.live_waiver is None]


@router.get("/")
def queue(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    request.state.user = user
    today = date.today()
    sent = db.query(Waiver).filter(Waiver.status == "sent").all()
    stats = {
        "needs": 0,
        "sent": len([w for w in sent if not w.is_overdue(today)]),
        "overdue": len([w for w in sent if w.is_overdue(today)]),
        "held": db.query(Vendor).filter(Vendor.on_hold.is_(True)).count(),
    }
    payments = _needs_waiver(db)
    stats["needs"] = len(payments)
    held = db.query(Vendor).filter(Vendor.on_hold.is_(True)).order_by(Vendor.name).all()
    return render(request, "queue.html", payments=payments, stats=stats, held=held,
                  suggested={p.id: svc.suggested_type(p) for p in payments}, active="queue")


@router.post("/queue/generate")
async def generate(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    form = await request.form()
    action = form.get("action", "send")
    ids = [int(x) for x in form.getlist("payment_id")]
    if not ids:
        flash(request, "Select at least one payment.", "warn")
        return RedirectResponse("/", status_code=303)
    made, sent, failed = 0, 0, []
    for pid in ids:
        payment = db.get(Payment, pid)
        if payment is None or payment.live_waiver is not None:
            continue
        wtype = str(form.get(f"type_{pid}", "progress"))
        try:
            waiver = svc.create_from_payment(db, payment, wtype, user.username)
            svc.regenerate_pdf(db, waiver, user.username)
            db.commit()
            made += 1
        except Exception as e:  # report per row, keep going
            db.rollback()
            failed.append(f"{payment.vendor.name} {payment.amount:,.2f}: {e}")
            continue
        if action == "send":
            try:
                svc.send(db, waiver, user.username)
                db.commit()
                sent += 1
            except Exception as e:  # the draft stays; the send can be retried from the waiver page
                db.rollback()
                failed.append(f"{waiver.number} left as draft: {e}")
    msg = f"Created {made} waiver(s)" + (f", sent {sent}" if action == "send" else " as drafts") + "."
    flash(request, msg, "ok" if not failed else "warn")
    for f in failed:
        flash(request, f, "error")
    return RedirectResponse("/waivers?status=draft" if action != "send" or sent < made else "/", status_code=303)
