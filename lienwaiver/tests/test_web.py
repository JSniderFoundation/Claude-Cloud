from datetime import date

from app.models import Payment, Waiver
from app.services import waivers as svc
from app.services.email import ConsoleBackend


def test_login_required(client):
    client.post("/logout")
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")


def test_full_flow_queue_to_portal(client, db, sample):
    # add a payment through the form
    r = client.post("/payments/new", data={"vendor_id": sample["vendor"].id, "project_id": sample["project"].id,
                                            "payment_date": "2026-09-30", "amount": "$4,500.00", "reference": "CHK 9"},
                    follow_redirects=False)
    assert r.status_code == 303
    pid = db.query(Payment).one().id
    assert "CHK 9" in client.get("/").text

    # generate and send from the queue
    r = client.post("/queue/generate", data={"payment_id": [str(pid)], f"type_{pid}": "progress", "action": "send"},
                    follow_redirects=True)
    assert "Created 1 waiver(s), sent 1" in r.text
    w = db.query(Waiver).one()
    assert w.status == "sent" and len(ConsoleBackend.sent) == 1

    # staff can see both the detail and the PDF
    assert w.number in client.get(f"/waivers/{w.id}").text
    assert client.get(f"/waivers/{w.id}/pdf/unsigned").content.startswith(b"%PDF")

    # vendor portal, no login
    client.post("/logout")
    token = w.portal_token
    assert client.get("/p/not-a-token").status_code == 404
    page = client.get(f"/p/{token}")
    assert page.status_code == 200 and "Upload signed waiver" in page.text
    assert client.get(f"/p/{token}/pdf").content.startswith(b"%PDF")
    r = client.post(f"/p/{token}/upload", files={"signed_pdf": ("signed.pdf", b"%PDF-1.7 signed", "application/pdf")})
    assert "Thank you" in r.text
    db.expire_all()
    w = db.query(Waiver).one()
    assert w.status == "received" and w.received_via == "portal" and w.pdf_signed_path.endswith("-signed.pdf")


def test_csv_import_and_project_coverage(client, db, sample):
    csv = ("vendor,project,date,reference,invoice_number,invoice_date,invoice_amount,net_amount\n"
           "Acme Stone LLC,J1,09/15/2026,ACH 1,INV1,09/01/2026,\"$1,000.00\",900.00\n"
           "Acme Stone LLC,J1,09/15/2026,ACH 1,INV2,09/03/2026,500.00,450.00\n"
           "Nobody,J1,2026-09-15,ACH 2,INV3,09/03/2026,5,5\n")
    r = client.post("/import", data={"kind": "payments"}, files={"file": ("p.csv", csv, "text/csv")})
    assert "Created 1, updated 0, 1 error(s)" in r.text and "line 4: vendor" in r.text and "Nobody" in r.text
    pay = db.query(Payment).one()
    assert pay.amount_cents == 135000 and [b.invoice_number for b in pay.bills] == ["INV1", "INV2"]
    assert pay.latest_invoice_date == date(2026, 9, 3)
    page = client.get(f"/projects/{sample['project'].id}").text
    assert "$1,350.00" in page and "Acme Stone LLC" in page


def test_generate_leaves_draft_when_vendor_has_no_email(client, db, sample):
    sample["vendor"].contact_email = ""
    db.commit()
    db.add(Payment(vendor_id=sample["vendor"].id, project_id=sample["project"].id, payment_date=date(2026, 9, 30),
                   amount_cents=100000, reference="ACH 7"))
    db.commit()
    pid = db.query(Payment).one().id
    r = client.post("/queue/generate", data={"payment_id": [str(pid)], f"type_{pid}": "progress", "action": "send"},
                    follow_redirects=True)
    assert "Created 1 waiver(s), sent 0" in r.text and "left as draft" in r.text and "no contact email" in r.text
    w = db.query(Waiver).one()
    assert w.status == "draft" and w.pdf_unsigned_path.endswith("-unsigned.pdf")
