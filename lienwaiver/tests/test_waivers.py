from datetime import date, timedelta

from pypdf import PdfReader
import io

from app.models import Payment, Vendor
from app.services import hold, waivers
from app.services.email import ConsoleBackend
from app.services.pdf import render_waiver_html, render_waiver_pdf


def _payment(db, sample, project=None, amount=1234567, days_ago=0):
    p = Payment(vendor_id=sample["vendor"].id, project_id=(project or sample["project"]).id,
                payment_date=date.today() - timedelta(days=days_ago), amount_cents=amount, reference="ACH 1")
    db.add(p)
    db.commit()
    return p


def _text(pdf: bytes) -> str:
    return " ".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)


def test_numbering_is_sequential_per_year(db, sample):
    p1, p2 = _payment(db, sample), _payment(db, sample)
    w1 = waivers.create_from_payment(db, p1, "progress", "t")
    w2 = waivers.create_from_payment(db, p2, "final", "t")
    year = date.today().year
    assert (w1.number, w2.number) == (f"LW-{year}-0001", f"LW-{year}-0002")


def test_payment_cannot_have_two_live_waivers(db, sample):
    p = _payment(db, sample)
    w = waivers.create_from_payment(db, p, "progress", "t")
    db.commit()
    try:
        waivers.create_from_payment(db, p, "progress", "t")
        assert False, "expected ValueError"
    except ValueError:
        pass
    waivers.void(db, w, "typo", "t")
    assert waivers.create_from_payment(db, p, "progress", "t").number.endswith("0002")


def test_progress_pdf_without_bond_has_no_bond_language(db, sample):
    p = _payment(db, sample)
    w = waivers.create_from_payment(db, p, "progress", "t")
    db.commit()
    from app.services.company import DEFAULTS
    text = _text(render_waiver_pdf(w, dict(DEFAULTS), "http://x/p/t"))
    assert "Partial Waiver of Lien" in text
    assert "$12,345.67" in text
    assert "Acme Stone LLC" in text and "Riverside Flats" in text and "Owner LLC" in text
    assert "Foundation Millwork and Stone LLC" in text and "ap@millworkandstone.com" in text
    assert "bond" not in text.lower()


def test_final_pdf_on_bond_project_releases_bond_claims(db, sample):
    p = _payment(db, sample, project=sample["bond"])
    w = waivers.create_from_payment(db, p, "final", "t")
    db.commit()
    from app.services.company import DEFAULTS
    html = render_waiver_html(w, dict(DEFAULTS), "http://x/p/t")
    assert "Final Waiver of Lien" in html and "payment bond" in html and "Surety Co" in html and "B-1" in html
    assert "final payment" in html and "through" not in html.split("Dated this")[0].split("certifies")[1]


def test_send_sets_due_date_and_emails_pdf(db, sample):
    p = _payment(db, sample)
    w = waivers.create_from_payment(db, p, "progress", "t")
    waivers.send(db, w, "t", today=date(2026, 9, 30))
    db.commit()
    assert w.status == "sent" and w.due_at == date(2026, 10, 7)  # default 7-day window
    mail = ConsoleBackend.sent[-1]
    assert mail.to == ["pat@acme.example"] and mail.attachments[0].content.startswith(b"%PDF")
    assert "/p/" in mail.body and w.number in mail.subject


def test_vendor_override_return_days(db, sample):
    sample["vendor"].return_days = 3
    p = _payment(db, sample)
    w = waivers.create_from_payment(db, p, "progress", "t")
    waivers.send(db, w, "t", today=date(2026, 9, 30))
    assert w.due_at == date(2026, 10, 3)


def test_receive_clears_hold_and_notifies_ap(db, sample):
    v: Vendor = sample["vendor"]
    p = _payment(db, sample, days_ago=20)
    w = waivers.create_from_payment(db, p, "progress", "t")
    waivers.send(db, w, "t", today=date.today() - timedelta(days=19))
    db.commit()
    hold.apply_holds(db)
    assert v.on_hold and w.number in v.hold_reason
    waivers.receive(db, w, b"%PDF-1.7 signed", "portal", "vendor")
    assert w.status == "received" and not v.on_hold and v.hold_reason == ""
    assert any("received" in m.subject and m.to == ["ap@test.example"] for m in ConsoleBackend.sent)


def test_send_refuses_without_vendor_email(db, sample):
    sample["vendor"].contact_email = ""
    p = _payment(db, sample)
    w = waivers.create_from_payment(db, p, "progress", "t")
    try:
        waivers.send(db, w, "t")
        assert False
    except ValueError as e:
        assert "no contact email" in str(e)
    assert w.status == "draft" and w.due_at is None


def test_receive_rejects_non_pdf(db, sample):
    p = _payment(db, sample)
    w = waivers.create_from_payment(db, p, "progress", "t")
    db.commit()
    try:
        waivers.receive(db, w, b"hello", "portal", "vendor")
        assert False
    except ValueError:
        assert w.status == "draft"


def test_reminder_schedule(db, sample):
    p = _payment(db, sample)
    w = waivers.create_from_payment(db, p, "progress", "t")
    waivers.send(db, w, "t", today=date(2026, 9, 1))  # due 9/8
    db.commit()
    assert waivers.reminders_due(db, date(2026, 9, 3)) == []
    assert waivers.reminders_due(db, date(2026, 9, 5)) == [w]  # 3 days before due
    waivers.remind(db, w, date(2026, 9, 5))
    assert waivers.reminders_due(db, date(2026, 9, 7)) == []
    assert waivers.reminders_due(db, date(2026, 9, 9)) == [w]  # overdue
    waivers.remind(db, w, date(2026, 9, 9))
    assert waivers.reminders_due(db, date(2026, 9, 12)) == []
    assert waivers.reminders_due(db, date(2026, 9, 14)) == [w]  # every 5 days after
