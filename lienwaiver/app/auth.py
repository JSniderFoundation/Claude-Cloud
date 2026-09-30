"""Staff login: scrypt password hashes and a signed session cookie."""
from __future__ import annotations

import hashlib
import hmac
import os

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
    return hmac.compare_digest(digest.hex(), digest_hex)


def bootstrap_admin(db: Session) -> None:
    if db.query(User).count() == 0 and settings.admin_password:
        db.add(User(username=settings.admin_user, name=settings.admin_user, password_hash=hash_password(settings.admin_password)))
        db.commit()


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.query(User).filter(User.username == username).one_or_none()
    if user and verify_password(password, user.password_hash):
        return user
    return None


class LoginRequired(HTTPException):
    pass


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    user = db.get(User, user_id) if user_id else None
    if not user:
        raise LoginRequired(status_code=303, headers={"Location": f"/login?next={request.url.path}"})
    return user
