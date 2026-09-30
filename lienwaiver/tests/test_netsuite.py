from datetime import date

from app.models import Payment, Project, Vendor
from app.services import sync
from app.services.netsuite import NsBill, NsPayment, NsProject, NsVendor, RestNetSuite, oauth_header


def test_oauth_header_is_deterministic_and_complete():
    h = oauth_header("POST", "https://123.suitetalk.api.netsuite.com/services/rest/query/v1/suiteql?limit=1000&offset=0",
                     account="123", consumer_key="ck", consumer_secret="cs", token="tk", token_secret="ts",
                     nonce="abc", timestamp=1700000000)
    assert h.startswith('OAuth realm="123", ')
    for k in ("oauth_consumer_key=\"ck\"", "oauth_token=\"tk\"", "oauth_signature_method=\"HMAC-SHA256\"",
              "oauth_timestamp=\"1700000000\"", "oauth_nonce=\"abc\"", "oauth_signature="):
        assert k in h
    again = oauth_header("POST", "https://123.suitetalk.api.netsuite.com/services/rest/query/v1/suiteql?limit=1000&offset=0",
                         account="123", consumer_key="ck", consumer_secret="cs", token="tk", token_secret="ts",
                         nonce="abc", timestamp=1700000000)
    assert h == again
    # the query string is part of the signature base
    other = oauth_header("POST", "https://123.suitetalk.api.netsuite.com/services/rest/query/v1/suiteql?limit=1000&offset=1000",
                         account="123", consumer_key="ck", consumer_secret="cs", token="tk", token_secret="ts",
                         nonce="abc", timestamp=1700000000)
    assert other != h


class CannedClient:
    """Answers SuiteQL by matching a fragment of the query."""

    def __init__(self):
        self.patches = []

    def suiteql(self, q):
        if "type = 'VendPymt'" in q:
            return [{"id": 501, "tranid": "5521", "trandate": "2026-09-10", "entity": 77, "memo": "", "foreigntotal": -17393.88}]
        if "previoustransactionlinelink" in q:
            return [{"payment_id": 501, "bill_id": 901, "amount": -8273.88}, {"payment_id": 501, "bill_id": 902, "amount": -9120.00}]
        if "type = 'VendBill' AND t.id IN" in q:
            return [{"id": 901, "tranid": "INV020", "trandate": "2026-09-20", "foreigntotal": 8273.88, "project": 11},
                    {"id": 902, "tranid": "INV021", "trandate": "2026-09-21", "foreigntotal": 9120.00, "project": 12}]
        if "LIKE '%RETAINAGE%'" in q:
            return [{"bill_id": 901, "amount": -919.32}]
        if "FROM vendor v" in q:
            return [{"id": 77, "companyname": "Easy Living Construction", "entityid": "Easy Living", "email": "ap@easyliving.example"}]
        if "vendoraddressbook" in q:
            return [{"vendor_id": 77, "addr1": "1778 Navion Ct", "addr2": None, "city": "Galloway", "state": "OH", "zip": "43119"}]
        if "customrecord_csegnsps_seg_projec" in q:
            return [{"id": 11, "name": "Vision - VC Lane - Batavia Phase 1", "isinactive": "F"},
                    {"id": 12, "name": "Daimler - Chestnut Hill", "isinactive": "F"}]
        if "t.status = 'VendBill:A'" in q:
            return [{"id": 950}, {"id": 951}]
        raise AssertionError("unexpected query: " + q)

    def patch_record(self, record_type, record_id, body):
        self.patches.append((record_type, record_id, body))


def test_rest_adapter_maps_payments_bills_and_retainage():
    ns = RestNetSuite(client=CannedClient())
    pays = ns.payments_since(date(2026, 9, 1))
    assert len(pays) == 1
    p = pays[0]
    assert p.vendor_id == "77" and p.reference == "5521" and p.total_cents == 1739388
    b1, b2 = sorted(p.bills, key=lambda b: b.id)
    assert (b1.invoice_number, b1.net_cents, b1.gross_cents, b1.applied_cents, b1.project_id) == ("INV020", 827388, 919320, 827388, "11")
    assert b2.gross_cents == 912000 and b2.project_id == "12"
    v = ns.vendors(["77"])[0]
    assert v.name == "Easy Living Construction" and v.city == "Galloway"


def test_sync_splits_a_payment_by_project_and_keeps_app_owned_fields(db):
    db.add(Vendor(name="Easy Living Construction", contact_email="dana@easyliving.example", hold_mode="exchange"))
    db.commit()
    ns = RestNetSuite(client=CannedClient())
    res = sync.run_sync(db, adapter=ns, since=date(2026, 9, 1))
    assert res.payments_created == 2 and res.vendors == 1 and res.projects == 2 and not res.errors
    vendor = db.query(Vendor).one()
    assert vendor.netsuite_id == "77" and vendor.address1 == "1778 Navion Ct"
    assert vendor.contact_email == "dana@easyliving.example" and vendor.hold_mode == "exchange"  # not clobbered
    pays = db.query(Payment).order_by(Payment.amount_cents).all()
    assert [p.amount_cents for p in pays] == [827388, 912000]
    assert all(p.netsuite_id == "501" for p in pays)
    assert {p.project.name for p in pays} == {"Vision - VC Lane - Batavia Phase 1", "Daimler - Chestnut Hill"}
    assert pays[0].bills[0].gross_cents == 919320 and pays[0].latest_invoice_date == date(2026, 9, 20)
    # second run updates rather than duplicates
    res2 = sync.run_sync(db, adapter=ns, since=date(2026, 9, 1))
    assert res2.payments_created == 0 and res2.payments_updated == 2 and db.query(Payment).count() == 2


def test_hold_writeback_patches_open_bills(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "netsuite_write_holds", True)
    client = CannedClient()
    ns = RestNetSuite(client=client)
    ns.set_vendor_hold("77", "Easy Living Construction", True, "overdue")
    assert client.patches == [("vendorBill", "950", {"paymentHold": True, "custbody_lien_waiver_hold": True}),
                              ("vendorBill", "951", {"paymentHold": True, "custbody_lien_waiver_hold": True})]
    monkeypatch.setattr(settings, "netsuite_write_holds", False)
    ns.set_vendor_hold("77", "Easy Living Construction", False, "")
    assert len(client.patches) == 2  # dry-run mode does not patch
