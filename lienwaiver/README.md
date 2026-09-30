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

## Run it with Docker

```bash
cp .env.example .env    # edit it
docker compose up -d --build
```

Data (SQLite database and PDFs) lives in `./data`. Back that folder up.

## Hosting on Render (no office machine needed)

`render.yaml` describes the service: one Docker container, a 5 GB persistent disk at `/data` for the database and
PDFs, health checks, HTTPS. Steps:

1. In Render: **New > Blueprint**, connect the GitHub repo, pick the branch. Render reads `render.yaml`.
2. Fill in the values marked `sync: false`: `ADMIN_PASSWORD`, `BASE_URL` (the service URL Render assigns, or your
   custom domain such as `waivers.millworkandstone.com`), the Graph email values, and later the NetSuite values.
3. Deploy. Open the URL, sign in, go to Settings and check the company details.
4. Optional: add the custom domain under the service's Settings; Render issues the certificate.

Cost is the Starter plan plus the disk, roughly $8 to $10 a month. Backups: Settings > **Download backup** gives a
zip of the database and every PDF; take one weekly until the SharePoint mirror (phase 4) exists.

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

With `NETSUITE_BACKEND=fake` the hold is shown in the app and emailed to `AP_NOTIFY_EMAIL`; AP sets the
Payment Hold in NetSuite by hand. With `rest` and `NETSUITE_WRITE_HOLDS=true` the tool sets **Payment Hold** on
the vendor's open bills itself, and stamps its own checkbox (`NETSUITE_HOLD_FIELD`) so it only ever clears holds
it set. New bills entered while a vendor is on hold are caught at the next sync.

## NetSuite sync

Every `NETSUITE_SYNC_MINUTES` (and from Settings > **Sync now**) the app pulls vendor payments dated on or after
`NETSUITE_SYNC_START`, the bills they were applied to, and the vendors and projects those bills reference. Only
vendors and projects that appear on paid bills are imported, so utilities and office suppliers never show up.

- The **Projects** custom segment (`csegnsps_seg_projec`) is read from the bill header. A bill with no project is
  skipped and counted in the sync result. A payment covering bills on two projects becomes two payments in the app.
- **Invoice amount** = bill total + retainage lines (lines to any account whose name contains
  `NETSUITE_RETAINAGE_MATCH`). **Net amount** = what the payment applied to that bill.
- NetSuite owns vendor names and addresses. The app owns the waiver contact, hold mode and everything about projects
  except the name.

Setting it up in NetSuite (one-time, admin):

1. Enable **Token-Based Authentication** and **REST Web Services** (Setup > Company > Enable Features > SuiteCloud).
2. Create a role *Lien Waiver Integration* with: Vendors (view), Vendor Bills (view, plus edit for phase 3),
   Vendor Payments (view), Custom Segment Projects (view), REST Web Services, Log in using Access Tokens,
   SuiteAnalytics Workbook (needed for SuiteQL). Restrict to the Foundation Millwork and Stone subsidiary.
3. Setup > Integration > Manage Integrations > New: name *Lien Waivers*, tick Token-Based Authentication. Copy the
   consumer key and secret (shown once).
4. Setup > Users/Roles > Access Tokens > New: the integration, a user with the role above. Copy the token id and secret.
5. Put the four values plus the account id in the environment. Set `NETSUITE_BACKEND=rest`, deploy, click Sync now.
6. For phase 3, add a checkbox transaction body field on Vendor Bill with id `custbody_lien_waiver_hold` and set
   `NETSUITE_WRITE_HOLDS=true`.

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
