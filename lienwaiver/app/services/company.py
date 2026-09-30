"""Company-level settings stored in the settings table, with defaults."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Setting

DEFAULTS: dict[str, str] = {
    "company_name": "Foundation Millwork and Stone LLC",
    "company_address1": "315 Phillipi Rd, Suite C",
    "company_address2": "Columbus, OH 43228",
    "company_phone": "(614) 274-4700",
    "company_email": "ap@millworkandstone.com",
    "default_return_days": "7",
    "reminder_days_before_due": "3",
    "reminder_every_days_after_due": "5",
    "signer_title_line": "Owner/Partner/President/Co. Officer",
    "important_line": "Important: Future payments will not be released until this form is signed and returned!",
    "email_intro": "Attached is a lien waiver for your recent payment. Please sign it and return it using the link below.",
}


def get_settings(db: Session) -> dict[str, str]:
    values = dict(DEFAULTS)
    for row in db.query(Setting).all():
        values[row.key] = row.value
    return values


def save_settings(db: Session, updates: dict[str, str]) -> None:
    for key, value in updates.items():
        if key not in DEFAULTS:
            continue
        row = db.get(Setting, key)
        if row is None:
            db.add(Setting(key=key, value=value))
        else:
            row.value = value
    db.commit()


def get_int(values: dict[str, str], key: str) -> int:
    try:
        return int(values.get(key, DEFAULTS[key]))
    except ValueError:
        return int(DEFAULTS[key])
