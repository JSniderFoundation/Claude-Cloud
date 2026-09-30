"""The payment-hold rule.

previous mode: the waiver for the previous payment gates the next one. A vendor goes on hold when any
               sent waiver is past its due date.
exchange mode: every payment needs its waiver back before the vendor is payable again. A vendor goes on
               hold when any waiver is outstanding (draft or sent), due date or not.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from ..models import Event, Vendor, Waiver
from . import netsuite


@dataclass
class HoldDecision:
    on_hold: bool
    reason: str


def evaluate(vendor: Vendor, waivers: list[Waiver], today: date) -> HoldDecision:
    live = [w for w in waivers if w.status in ("draft", "sent")]
    if vendor.hold_mode == "exchange":
        blocking = live
    else:
        blocking = [w for w in live if w.status == "sent" and w.due_at is not None and w.due_at < today]
    if not blocking:
        return HoldDecision(False, "")
    numbers = ", ".join(sorted(w.number for w in blocking))
    kind = "outstanding" if vendor.hold_mode == "exchange" else "overdue"
    return HoldDecision(True, f"{len(blocking)} {kind} waiver(s): {numbers}")


def apply_holds(db: Session, today: date | None = None, user: str = "system") -> list[tuple[Vendor, HoldDecision]]:
    """Re-evaluate every active vendor and push changes to NetSuite. Returns the vendors whose state changed."""
    today = today or date.today()
    adapter = netsuite.get_adapter()
    changed: list[tuple[Vendor, HoldDecision]] = []
    for vendor in db.query(Vendor).filter(Vendor.active.is_(True)).all():
        decision = evaluate(vendor, vendor.waivers, today)
        if decision.on_hold != vendor.on_hold or decision.reason != vendor.hold_reason:
            flipped = decision.on_hold != vendor.on_hold
            vendor.on_hold = decision.on_hold
            vendor.hold_reason = decision.reason
            if flipped:
                adapter.set_vendor_hold(vendor.netsuite_id, vendor.name, decision.on_hold, decision.reason)
                db.add(Event(vendor_id=vendor.id, user=user, action="hold_on" if decision.on_hold else "hold_off",
                             detail=decision.reason or "All waivers received"))
                changed.append((vendor, decision))
    db.commit()
    return changed
