"""Daily housekeeping: reminders and hold evaluation. Run hourly in-process, once per calendar day."""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Setting
from . import hold, sync, waivers

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


def tick(session_factory) -> None:
    """One scheduler pass: NetSuite sync (if configured), then the daily jobs once per day."""
    db = session_factory()
    try:
        if settings.netsuite_backend == "rest":
            try:
                sync.run_sync(db)
            except Exception:
                db.rollback()
                log.exception("NetSuite sync failed")
        run_daily_once(db)
    finally:
        db.close()


async def scheduler(session_factory, interval_seconds: int | None = None) -> None:
    interval = interval_seconds or max(60, settings.netsuite_sync_minutes * 60)
    while True:
        try:
            await asyncio.to_thread(tick, session_factory)
        except Exception:
            log.exception("scheduler tick failed")
        await asyncio.sleep(interval)
