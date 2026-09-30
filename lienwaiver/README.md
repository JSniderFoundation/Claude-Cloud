# Lien Waivers

Creates unconditional lien waiver PDFs for vendor payments, emails them to the vendor with an upload link,
tracks their return, and puts vendors with overdue waivers on payment hold. Built for an Ohio subcontractor
paying its own subs and suppliers. Design and decisions: `../docs/lien-waiver-tool-design.md`.

## Run it locally

```bash
cd lienwaiver
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"            # WeasyPrint needs Pango/Cairo: apt install libpango-1.0-0 libpangoft2-1.0-0
cp .env.example .env               # set SECRET_KEY and ADMIN_PASSWORD at minimum
python -m scripts.seed             # optional demo data (login admin / admin). Wipes data/.
uvicorn app.main:app --reload
```

Open http://localhost:8000. Tests: `pytest`.

## Run it with Docker (recommended for the office machine)

```bash
cp .env.example .env    # edit it
docker compose up -d --build
```

Data (SQLite database and PDFs) lives in `./data`. Back that folder up.

**Public URL for vendors.** Vendor upload links use `BASE_URL`. On an office machine the simplest way to get a
public HTTPS address without opening firewall ports is a Cloudflare Tunnel (free): install `cloudflared`, run
`cloudflared tunnel --url http://localhost:8000` for a quick test, or create a named tunnel on a hostname such
as `waivers.yourcompany.com` and set `BASE_URL` to it. Alternatively any small container host works with the same image.

## Weekly use

1. **Needs waiver** lists every payment without a waiver. Payments come from CSV import or the Add payment form
   until the NetSuite sync is on.
2. Tick the rows, check the type (Progress, or Final when the project is marked complete), click
   **Generate and send selected**. Each vendor gets an email with the PDF and a personal upload link. The
   return clock starts (7 days by default).
3. Vendors upload the signed PDF at the link, or reply by email. Staff can also upload from the waiver page.
4. **Tracking** shows every waiver with Sent / Overdue / Received status. Overdue waivers put the vendor on hold.
   Reminders go out 3 days before due, at due, then every 5 days.
5. **Projects** shows waiver coverage per vendor: paid, waived, waiver out, no waiver.

Voiding a waiver puts its payment back in the queue so a corrected one can be created.

## The hold rule

Each vendor has a mode (Vendors > Edit):

- **Previous payment gates the next** (default): on hold when any *sent* waiver is past its due date.
- **Waiver in exchange for payment**: on hold while any waiver is outstanding at all.

With `NETSUITE_BACKEND=fake` (phase 1) the hold is shown in the app and emailed to `AP_NOTIFY_EMAIL`; AP sets
the Payment Hold in NetSuite by hand. Phase 3 pushes it automatically.

## CSV formats

Header row required, extra columns ignored, existing rows matched by `netsuite_id`, then job number / reference, then name.

| File | Columns |
|---|---|
| vendors | `name, netsuite_id, address1, address2, city, state, zip, contact_name, contact_email` |
| projects | `name, job_number, netsuite_id, address1, city, state, zip, county, owner_name, gc_name, bond_project, surety_name, bond_number` |
| payments | `vendor, project, date, reference, invoice_number, invoice_date, invoice_amount, net_amount, memo, netsuite_id` (one row per invoice paid; rows with the same vendor, project, date and reference become one payment; `amount` may replace the invoice columns for a single lump sum) |

## Email through Microsoft 365

Two options, set by `EMAIL_BACKEND`:

- **`smtp`**: create a mailbox such as `lienwaivers@yourcompany.com`, enable *Authenticated SMTP* for it in the
  Microsoft 365 admin center (Users > Mail > Manage email apps), and put its password (or app password if MFA is on)
  in `SMTP_PASSWORD`. Simplest, but Microsoft is phasing out basic auth for some tenants.
- **`graph`**: register an app in Entra ID, grant it the *Mail.Send* application permission with admin consent, and
  set `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`. Sends as `EMAIL_FROM`. Use an Exchange
  application access policy to restrict the app to that one mailbox.

`console` (default) logs emails instead of sending, for development.

## Layout

```
app/main.py            FastAPI app, session middleware, hourly job scheduler
app/models.py          Vendor, Project, Payment, Waiver, Event, User, Setting
app/services/waivers.py  create / send / remind / receive / void, waiver numbering, portal tokens
app/services/hold.py   the hold rule and NetSuite write-back call
app/services/pdf.py    HTML -> PDF (WeasyPrint), file layout data/pdfs/<project>/<vendor>/
app/services/email.py  console / smtp / graph backends
app/services/netsuite.py  adapter (fake now, REST in phase 2)
app/templates/pdf/waiver.html   the waiver document text
```

The waiver wording follows the company's existing Partial Waiver of Lien form, with a Final variant and bond release
language that appears only on bond projects. Company name, address, phone, email, signer title line and the notice
line are editable under Settings; the text itself lives in `app/templates/pdf/waiver.html`.
