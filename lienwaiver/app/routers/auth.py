from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..auth import authenticate
from ..db import get_db
from ..web import render

router = APIRouter()


@router.get("/login")
def login_form(request: Request, next: str = "/"):
    return render(request, "login.html", next=next, error=None)


@router.post("/login")
async def login(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    user = authenticate(db, str(form.get("username", "")).strip(), str(form.get("password", "")))
    if not user:
        return render(request, "login.html", next=form.get("next", "/"), error="Wrong username or password.")
    request.session["user_id"] = user.id
    target = str(form.get("next") or "/")
    return RedirectResponse(target if target.startswith("/") else "/", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
