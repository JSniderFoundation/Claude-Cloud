from datetime import date, timedelta

from app.models import Vendor, Waiver
from app.services.hold import evaluate

TODAY = date(2026, 9, 30)


def w(status, due_days=None, number="LW-2026-0001"):
    return Waiver(number=number, status=status, due_at=TODAY + timedelta(days=due_days) if due_days is not None else None,
                  waiver_type="progress", amount_cents=100, through_date=TODAY, vendor_id=1, project_id=1)


def test_previous_mode_holds_only_when_past_due():
    v = Vendor(name="A", hold_mode="previous")
    assert not evaluate(v, [w("sent", 3)], TODAY).on_hold
    assert not evaluate(v, [w("sent", 0)], TODAY).on_hold  # due today is not late yet
    d = evaluate(v, [w("sent", -1)], TODAY)
    assert d.on_hold and "LW-2026-0001" in d.reason and "overdue" in d.reason


def test_previous_mode_ignores_drafts_received_and_void():
    v = Vendor(name="A", hold_mode="previous")
    assert not evaluate(v, [w("draft"), w("received", -30, "LW-2"), w("void", -30, "LW-3")], TODAY).on_hold


def test_exchange_mode_holds_on_any_outstanding():
    v = Vendor(name="A", hold_mode="exchange")
    assert evaluate(v, [w("draft")], TODAY).on_hold
    assert evaluate(v, [w("sent", 5)], TODAY).on_hold
    assert not evaluate(v, [w("received", -5)], TODAY).on_hold


def test_reason_lists_every_blocking_waiver():
    v = Vendor(name="A", hold_mode="previous")
    d = evaluate(v, [w("sent", -2, "LW-2026-0002"), w("sent", -9, "LW-2026-0001"), w("sent", 4, "LW-2026-0003")], TODAY)
    assert d.reason == "2 overdue waiver(s): LW-2026-0001, LW-2026-0002"
