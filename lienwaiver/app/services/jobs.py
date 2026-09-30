"""Daily housekeeping: reminders and hold evaluation. Run hourly in-process, once per calendar day."""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from sqlalchemy.orm import Session

from ..models import Setting
from . import hold, waivers

log = logging.getLogger("lienwaiver.jobs")


def run_daily(db: Session, today: date | None = None) -> dict[str, int]:
    today = today or date.today()
    sent = 0
    for w in waivers.reminders_due(db, today):
        try:
            waivers.remind(db, w, today)
            sent += 1
        except Exception:  # keep going; one bad address must not stop the run
            log.exception("reminder failed for %s", w.number)
    db.commit()
    changed = hold.apply_holds(db, today)
    for vendor, decision in changed:
        waivers.notify_ap(db, f"Lien waiver hold {'ON' if decision.on_hold else 'OFF'}: {vendor.name}",
                          decision.reason or "All waivers received. Hold released.")
    return {"reminders": sent, "hold_changes": len(changed)}


def run_daily_once(db: Session) -> bool:
    today = date.today().isoformat()
    marker = db.get(Setting, "_last_daily_run")
    if marker and marker.value == today:
        return False
    result = run_daily(db)
    if marker is None:
        db.add(Setting(key="_last_daily_run", value=today))
    else:
        marker.value = today
    db.commit()
    log.info("daily jobs done: %s", result)
    return True


async def scheduler(session_factory, interval_seconds: int = 3600) -> None:
    while True:
        try:
            db = session_factory()
            try:
                await asyncio.to_thread(run_daily_once, db)
            finally:
                db.close()
        except Exception:
            log.exception("scheduler tick failed")
        await asyncio.sleep(interval_seconds)
