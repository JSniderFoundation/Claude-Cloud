"""Public vendor page: download the waiver, upload the signed copy. No login; the URL carries a signed token."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import waivers as svc
from ..web import render

router = APIRouter(prefix="/p")


def _waiver(db: Session, token: str):
    w = svc.waiver_from_token(db, token)
    if w is None:
        raise HTTPException(404, "This link is not valid.")
    return w


@router.get("/{token}")
def portal(request: Request, token: str, db: Session = Depends(get_db)):
    w = _waiver(db, token)
    return render(request, "portal.html", w=w, token=token, error=None)


@router.get("/{token}/pdf")
def portal_pdf(token: str, db: Session = Depends(get_db)):
    w = _waiver(db, token)
    if not w.pdf_unsigned_path:
        raise HTTPException(404)
    return FileResponse(w.pdf_unsigned_path, media_type="application/pdf", filename=f"{w.number}.pdf")


@router.post("/{token}/upload")
async def portal_upload(request: Request, token: str, db: Session = Depends(get_db)):
    w = _waiver(db, token)
    if w.status != "sent":
        return render(request, "portal.html", w=w, token=token, error=None)
    form = await request.form()
    upload = form.get("signed_pdf")
    content = await upload.read() if upload is not None and hasattr(upload, "read") else b""
    if len(content) > 20 * 1024 * 1024:
        return render(request, "portal.html", w=w, token=token, error="File is larger than 20 MB.")
    try:
        svc.receive(db, w, content, "portal", f"vendor:{w.vendor.name}")
    except ValueError as e:
        db.rollback()
        return render(request, "portal.html", w=w, token=token, error=str(e))
    return render(request, "portal.html", w=w, token=token, error=None, done=True)
