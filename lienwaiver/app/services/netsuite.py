"""NetSuite adapter.

FakeNetSuite  - phase 1: records hold calls, returns no data.
RestNetSuite  - phases 2 and 3: SuiteQL reads over the REST API with token-based auth (OAuth 1.0a, HMAC-SHA256),
                and the Payment Hold write-back on vendor bills.

The Projects custom segment (id csegnsps_seg_projec) sits on the bill header, so every bill has one project.
Retainage is booked as a negative expense line to an 'Accounts Payable - Retainage' account, so the bill total is
already net of retainage; the invoice (gross) amount is the total plus the retainage lines.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from ..config import settings

log = logging.getLogger("lienwaiver.netsuite")


@dataclass
class NsVendor:
    id: str
    name: str
    email: str = ""
    address1: str = ""
    address2: str = ""
    city: str = ""
    state: str = ""
    zip: str = ""


@dataclass
class NsProject:
    id: str
    name: str
    inactive: bool = False


@dataclass
class NsBill:
    id: str
    invoice_number: str
    invoice_date: date | None
    net_cents: int  # bill total, already net of retainage
    gross_cents: int  # bill total plus retainage lines
    project_id: str | None
    applied_cents: int = 0  # amount this payment applied to the bill


@dataclass
class NsPayment:
    id: str
    vendor_id: str
    date: date
    reference: str
    memo: str
    total_cents: int
    bills: list[NsBill] = field(default_factory=list)


class NetSuiteAdapter(Protocol):
    def payments_since(self, since: date) -> list[NsPayment]: ...
    def vendors(self, ids: list[str]) -> list[NsVendor]: ...
    def projects(self, ids: list[str]) -> list[NsProject]: ...
    def set_vendor_hold(self, vendor_netsuite_id: str | None, vendor_name: str, on_hold: bool, reason: str) -> None: ...


# ---------------------------------------------------------------------------------------------- fake

@dataclass
class FakeNetSuite:
    calls: list[dict] = field(default_factory=list)

    def payments_since(self, since):
        return []

    def vendors(self, ids):
        return []

    def projects(self, ids):
        return []

    def set_vendor_hold(self, vendor_netsuite_id, vendor_name, on_hold, reason):
        self.calls.append({"netsuite_id": vendor_netsuite_id, "vendor": vendor_name, "on_hold": on_hold, "reason": reason})
        log.info("NetSuite (fake): %s hold for %s (%s): %s", "SET" if on_hold else "CLEAR", vendor_name, vendor_netsuite_id, reason)


# ---------------------------------------------------------------------------------------------- REST

def _pct(s: str) -> str:
    return quote(str(s), safe="-._~")


def oauth_header(method: str, url: str, *, account: str, consumer_key: str, consumer_secret: str, token: str,
                 token_secret: str, nonce: str | None = None, timestamp: int | None = None) -> str:
    """OAuth 1.0a Authorization header for NetSuite TBA (HMAC-SHA256). Query-string params are folded in."""
    base_url, _, query = url.partition("?")
    params = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": nonce or secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA256",
        "oauth_timestamp": str(timestamp or int(time.time())),
        "oauth_token": token,
        "oauth_version": "1.0",
    }
    all_params = dict(params)
    for pair in query.split("&") if query else []:
        k, _, v = pair.partition("=")
        all_params[k] = v
    norm = "&".join(f"{_pct(k)}={_pct(v)}" for k, v in sorted(all_params.items()))
    base = f"{method.upper()}&{_pct(base_url)}&{_pct(norm)}"
    key = f"{_pct(consumer_secret)}&{_pct(token_secret)}"
    sig = base64.b64encode(hmac.new(key.encode(), base.encode(), hashlib.sha256).digest()).decode()
    params["oauth_signature"] = sig
    parts = ", ".join(f'{k}="{_pct(v)}"' for k, v in params.items())
    return f'OAuth realm="{account}", {parts}'


class RestClient:
    def __init__(self):
        acct = settings.netsuite_account
        self.realm = acct.upper().replace("-", "_")
        self.base = f"https://{acct.lower().replace('_', '-')}.suitetalk.api.netsuite.com/services/rest"
        self.http = httpx.Client(timeout=60)

    def _headers(self, method: str, url: str) -> dict[str, str]:
        return {
            "Authorization": oauth_header(method, url, account=self.realm, consumer_key=settings.netsuite_consumer_key,
                                          consumer_secret=settings.netsuite_consumer_secret, token=settings.netsuite_token_id,
                                          token_secret=settings.netsuite_token_secret),
            "Content-Type": "application/json",
            "Prefer": "transient",
        }

    def suiteql(self, q: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            url = f"{self.base}/query/v1/suiteql?limit=1000&offset={offset}"
            r = self.http.post(url, json={"q": q}, headers=self._headers("POST", url))
            if r.status_code >= 400:
                raise RuntimeError(f"SuiteQL {r.status_code}: {r.text[:500]}\n{q}")
            data = r.json()
            rows.extend(data.get("items", []))
            if not data.get("hasMore"):
                return rows
            offset += 1000

    def patch_record(self, record_type: str, record_id: str, body: dict) -> None:
        url = f"{self.base}/record/v1/{record_type}/{record_id}"
        r = self.http.patch(url, json=body, headers=self._headers("PATCH", url))
        if r.status_code >= 400:
            raise RuntimeError(f"PATCH {record_type}/{record_id} {r.status_code}: {r.text[:500]}")


def _cents(v) -> int:
    try:
        return int(round(float(v or 0) * 100))
    except (TypeError, ValueError):
        return 0


def _date(v) -> date | None:
    if not v:
        return None
    s = str(v)[:10]
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            from datetime import datetime

            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _ids(ids: list[str]) -> str:
    return ",".join(str(int(i)) for i in ids) or "0"


class RestNetSuite:
    def __init__(self, client: RestClient | None = None):
        self.client = client or RestClient()
        self.seg = settings.netsuite_project_segment

    # ---- reads

    def payments_since(self, since: date) -> list[NsPayment]:
        sub = f" AND t.subsidiary = {int(settings.netsuite_subsidiary_id)}" if settings.netsuite_subsidiary_id else ""
        pay_rows = self.client.suiteql(
            f"SELECT t.id, t.tranid, t.trandate, t.entity, t.memo, t.foreigntotal "
            f"FROM transaction t WHERE t.type = 'VendPymt' AND t.voided = 'F' AND t.trandate >= TO_DATE('{since:%Y-%m-%d}', 'YYYY-MM-DD'){sub} "
            f"ORDER BY t.trandate, t.id")
        if not pay_rows:
            return []
        pay_ids = [str(r["id"]) for r in pay_rows]
        links = self.client.suiteql(
            f"SELECT l.nextdoc AS payment_id, l.previousdoc AS bill_id, l.foreignamount AS amount "
            f"FROM previoustransactionlinelink l WHERE l.linktype = 'Payment' AND l.nextdoc IN ({_ids(pay_ids)})")
        bill_ids = sorted({str(l["bill_id"]) for l in links})
        bills = self._bills(bill_ids) if bill_ids else {}
        by_payment: dict[str, list[tuple[str, int]]] = {}
        for l in links:
            by_payment.setdefault(str(l["payment_id"]), []).append((str(l["bill_id"]), abs(_cents(l["amount"]))))
        out: list[NsPayment] = []
        for r in pay_rows:
            pid = str(r["id"])
            p = NsPayment(id=pid, vendor_id=str(r["entity"]), date=_date(r["trandate"]) or since,
                          reference=(r.get("tranid") or "ACH").strip(), memo=r.get("memo") or "",
                          total_cents=abs(_cents(r.get("foreigntotal"))))
            for bill_id, applied in by_payment.get(pid, []):
                b = bills.get(bill_id)
                if b is None:
                    continue
                nb = NsBill(**{**b.__dict__, "applied_cents": applied})
                p.bills.append(nb)
            out.append(p)
        return out

    def _bills(self, bill_ids: list[str]) -> dict[str, NsBill]:
        rows = self.client.suiteql(
            f"SELECT t.id, t.tranid, t.trandate, t.foreigntotal, t.{self.seg} AS project "
            f"FROM transaction t WHERE t.type = 'VendBill' AND t.id IN ({_ids(bill_ids)})")
        # retainage lines: negative expense lines to the retainage account, so gross = total + |retainage|
        ret = self.client.suiteql(
            f"SELECT tl.transaction AS bill_id, SUM(tl.foreignamount) AS amount "
            f"FROM transactionline tl JOIN account a ON a.id = tl.expenseaccount "
            f"WHERE tl.transaction IN ({_ids(bill_ids)}) AND tl.mainline = 'F' "
            f"AND (UPPER(a.fullname) LIKE '%{settings.netsuite_retainage_match.upper()}%') GROUP BY tl.transaction")
        retainage = {str(r["bill_id"]): abs(_cents(r["amount"])) for r in ret}
        out: dict[str, NsBill] = {}
        for r in rows:
            bid = str(r["id"])
            net = abs(_cents(r.get("foreigntotal")))
            out[bid] = NsBill(id=bid, invoice_number=r.get("tranid") or "", invoice_date=_date(r.get("trandate")),
                              net_cents=net, gross_cents=net + retainage.get(bid, 0),
                              project_id=str(r["project"]) if r.get("project") else None)
        return out

    def vendors(self, ids: list[str]) -> list[NsVendor]:
        if not ids:
            return []
        rows = self.client.suiteql(
            f"SELECT v.id, v.companyname, v.entityid, v.email FROM vendor v WHERE v.id IN ({_ids(ids)})")
        addr: dict[str, dict] = {}
        try:
            for a in self.client.suiteql(
                    f"SELECT ab.entity AS vendor_id, ea.addr1, ea.addr2, ea.city, ea.state, ea.zip "
                    f"FROM vendoraddressbook ab JOIN vendoraddressbookentityaddress ea ON ea.nkey = ab.addressbookaddress "
                    f"WHERE ab.entity IN ({_ids(ids)}) AND ab.defaultbilling = 'T'"):
                addr[str(a["vendor_id"])] = a
        except RuntimeError as e:  # address tables vary by account; names still sync
            log.warning("vendor address query failed, syncing names only: %s", e)
        out = []
        for r in rows:
            a = addr.get(str(r["id"]), {})
            out.append(NsVendor(id=str(r["id"]), name=(r.get("companyname") or r.get("entityid") or "").strip(),
                                email=r.get("email") or "", address1=a.get("addr1") or "", address2=a.get("addr2") or "",
                                city=a.get("city") or "", state=(a.get("state") or "")[:2], zip=a.get("zip") or ""))
        return out

    def projects(self, ids: list[str]) -> list[NsProject]:
        if not ids:
            return []
        rows = self.client.suiteql(
            f"SELECT id, name, isinactive FROM customrecord_{self.seg} WHERE id IN ({_ids(ids)})")
        return [NsProject(id=str(r["id"]), name=(r.get("name") or "").strip(), inactive=r.get("isinactive") == "T") for r in rows]

    # ---- write-back (phase 3)

    def set_vendor_hold(self, vendor_netsuite_id, vendor_name, on_hold, reason):
        if not vendor_netsuite_id:
            log.warning("Vendor %s has no NetSuite id; hold not pushed", vendor_name)
            return
        if not settings.netsuite_write_holds:
            log.info("NETSUITE_WRITE_HOLDS is off; would %s hold for %s: %s", "SET" if on_hold else "CLEAR", vendor_name, reason)
            return
        hold_field = settings.netsuite_hold_field
        # open bills for the vendor; when clearing, only the ones this tool put on hold
        where = f"t.type = 'VendBill' AND t.entity = {int(vendor_netsuite_id)} AND t.status = 'VendBill:A'"
        if not on_hold:
            where += f" AND t.{hold_field} = 'T'"
        rows = self.client.suiteql(f"SELECT t.id FROM transaction t WHERE {where}")
        for r in rows:
            self.client.patch_record("vendorBill", str(r["id"]), {"paymentHold": on_hold, hold_field: on_hold})
        log.info("NetSuite: %s payment hold on %d bill(s) for %s: %s", "SET" if on_hold else "CLEARED", len(rows), vendor_name, reason)


_fake = FakeNetSuite()


def get_adapter() -> NetSuiteAdapter:
    if settings.netsuite_backend == "rest":
        return RestNetSuite()
    return _fake
