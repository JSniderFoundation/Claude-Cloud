import io
import zipfile
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

from ..auth import current_user
from ..config import settings as env
from ..db import get_db
from ..models import User
from ..services import company, hold, jobs, netsuite, sync
from ..web import flash, render

router = APIRouter(dependencies=[Depends(current_user)])


@router.get("/settings")
def settings_form(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    request.state.user = user
    fake = netsuite.get_adapter()
    calls = getattr(fake, "calls", [])[-10:]
    return render(request, "settings.html", values=company.get_settings(db), env=env, ns_calls=list(reversed(calls)),
                  sync_status=sync.sync_status(db))


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


@router.post("/sync/run")
def sync_run(request: Request, db: Session = Depends(get_db)):
    if env.netsuite_backend != "rest":
        flash(request, "NetSuite backend is 'fake'. Set NETSUITE_BACKEND=rest and the token values to sync.", "warn")
        return RedirectResponse("/settings", status_code=303)
    try:
        res = sync.run_sync(db)
        flash(request, "Sync done: " + res.summary(), "ok" if not res.errors else "warn")
        for e in res.errors[:5]:
            flash(request, e, "error")
    except Exception as e:  # surface NetSuite errors to the screen
        db.rollback()
        flash(request, f"Sync failed: {e}", "error")
    return RedirectResponse("/settings", status_code=303)


@router.get("/backup.zip")
def backup(db: Session = Depends(get_db)):
    """Zip of the database and every PDF, for off-site backup."""
    buf = io.BytesIO()
    db_path = env.database_url.replace("sqlite:///", "", 1)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        if Path(db_path).exists():
            z.write(db_path, "lienwaiver.db")
        for p in env.pdf_dir.rglob("*.pdf"):
            z.write(p, str(Path("pdfs") / p.relative_to(env.pdf_dir)))
    buf.seek(0)
    name = f"lienwaiver-backup-{datetime.now():%Y%m%d-%H%M}.zip"
    return StreamingResponse(buf, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})
