from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..auth import current_user
from ..config import settings as env
from ..db import get_db
from ..models import User
from ..services import company, hold, jobs, netsuite
from ..web import flash, render

router = APIRouter(dependencies=[Depends(current_user)])


@router.get("/settings")
def settings_form(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    request.state.user = user
    fake = netsuite.get_adapter()
    calls = getattr(fake, "calls", [])[-10:]
    return render(request, "settings.html", values=company.get_settings(db), env=env, ns_calls=list(reversed(calls)))


@router.post("/settings")
async def settings_save(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    company.save_settings(db, {k: str(v).strip() for k, v in form.items()})
    flash(request, "Settings saved.")
    return RedirectResponse("/settings", status_code=303)


@router.post("/holds/run")
def holds_run(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    result = jobs.run_daily(db, date.today())
    flash(request, f"Daily jobs ran: {result['reminders']} reminder(s) sent, {result['hold_changes']} hold change(s).")
    return RedirectResponse(request.headers.get("referer", "/"), status_code=303)
