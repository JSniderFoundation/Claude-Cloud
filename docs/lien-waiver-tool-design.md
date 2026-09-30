# Lien Waiver Tool — Design

**Status:** Phases 1 to 3 built (`lienwaiver/`), NetSuite connection pending credentials · **Owner:** Finance Systems · **Date:** 2026-09-30

## 1. What we are building

A small tool that, for every payment we make to one of our subs or suppliers, produces an **unconditional lien waiver PDF**, gets it to the vendor, records when the signed copy comes back, and puts the vendor on **payment hold in NetSuite** while a waiver is outstanding.

**Context from discovery**

| Item | Answer |
|---|---|
| Who we are | Subcontractor (countertops and cabinets) on multifamily new builds |
| Who signs | Our subs and suppliers (one tier below us) |
| State | Ohio, all projects |
| Waiver types | Unconditional Progress, Unconditional Final |
| Signature | Any method: wet, scanned, or e-signed. No notary. |
| Trigger | One waiver per vendor payment |
| System of record | NetSuite (vendors, projects, bills, payments) |
| Volume | About 6 waivers per week |
| Tracking | Per-project grid plus "what's missing before I can pay" view |
| Hold | Missing waiver puts the vendor on payment hold in NetSuite |
| PDF storage | Somewhere safe and easy |
| Template | A company template is coming. Draft from a standard Ohio form until then. |

**Not in scope now:** waivers we sign for our GCs, lower tiers below our subs, e-signature integration, other states.

### Ohio notes

- Ohio has **no statutory lien waiver form** (Ohio's mechanics' lien law is R.C. Chapter 1311). Any clear form works, so the company template can be used as-is once we have it.
- Ohio does not require notarization of lien waivers.
- Because the waiver is unconditional, its wording states the vendor **has been paid** the stated amount. That drives the timing decision in §2.
- This design is not legal advice. Have counsel read the final template text once before go-live.

## 2. Decisions

**Made 2026-09-30:**

| # | Decision |
|---|---|
| D1 | Standalone app with NetSuite sync (option A). |
| D2 | Waiver for the previous payment gates the next one, 7-day return window. The exchange pattern stays available per vendor. |
| D3 | Projects are the custom segment `csegnsps_seg_projec` on the bill header. The app holds the property address, owner, GC and bond details. Retainage is a negative line to the AP Retainage account, so bill total is net. |
| D4 | Microsoft 365 for email and file mirroring. |
| D5 | Hosting: no office machine is available, so the app runs on Render (Docker service with a persistent disk, `lienwaiver/render.yaml`). |
| D6 | Bond claim language only on projects flagged as bond projects. |

The original options, for the record:


### D1. Where the tool lives: standalone app, or inside NetSuite

| | A. Standalone web app + NetSuite sync (**recommended**) | B. Built inside NetSuite |
|---|---|---|
| Creating waivers | Fast, purpose-built screens. Select rows, one click, PDFs and emails go out. | NetSuite forms and Advanced PDF templates. Works, slower to use. |
| Tracking | Dashboard designed for exactly this. | Saved searches and dashboard reminders. |
| Payment hold | Written back to NetSuite by API (§4.3). | Native: a workflow flips the flag. |
| NetSuite footprint | One integration record, one optional custom field. | Custom record, scripts, workflow, PDF template, all deployed to the **production-only** account. |
| Build and test | Can be built and demoed with sample data now, then pointed at NetSuite. | Can only be tested in production with test vendors. |
| Hosting | Needs a place to run (§6). | None extra. |
| Vendor return path | Vendor gets an upload link. No login. | Vendor replies by email. Someone attaches the file by hand. |

Recommendation: **A.** It is the only option that is "quick and convenient" for the person creating six waivers a week, and it keeps almost everything out of the production NetSuite account.

### D2. When the waiver is signed relative to the payment

Unconditional only means the vendor signs a statement that they have been paid. Two workable patterns:

| Pattern | How it works | Hold rule | Trade-off |
|---|---|---|---|
| **P1. Waiver for the previous payment gates the next one** (**recommended**) | We pay. The waiver for that payment goes out with the remittance. The vendor signs and returns it. If it is not back within N days, the vendor's next bills are held. | Vendor has any waiver in *Sent* older than N days → hold | Legally clean: the vendor only ever signs for money they have received. The first payment is never gated. |
| P2. Waiver in exchange for payment | Waiver goes out when the bill is approved. Payment is released only after the signed waiver is back. | Bill has no *Received* waiver → hold | Every payment is covered, including the first. The vendor signs "paid" before they are paid, which some vendors refuse. |

Both are supported by the same data model. Recommendation: **P1 with N = 10 days**, and P2 available per vendor for anyone with a history of problems.

### D3. How projects appear in NetSuite

The tool needs to know, for each vendor bill, which project it belongs to. To confirm: is the project a **Project/Job record**, a **Class**, a **Department**, a **Location**, or a **custom segment**, and is it set at the bill header or per line? Owner name, GC name and property address are also needed on the waiver. If those are not on the NetSuite project record, the tool holds them (§3.1).

### D4. Email and file storage platform

Microsoft 365 or Google Workspace? Determines how emails go out (SMTP or Graph/Gmail API) and where the PDF folder is mirrored (SharePoint/OneDrive or Drive). See §5.

### D5. Hosting

A container on a small cloud host, or a machine in the office. See §6.

## 3. Design (Option A)

```
                      ┌────────────────────────────────────────────────┐
  NetSuite            │  Lien Waiver app                                │
  ┌────────────┐ pull │  ┌──────────┐   ┌───────────┐   ┌───────────┐  │
  │ Vendors    │─────►│  │ Sync     │──►│ Waiver    │──►│ PDF       │──┼──► email + upload link ──► Vendor
  │ Projects   │      │  │ (SuiteQL)│   │ queue &   │   │ generator │  │                              │
  │ Bills      │      │  └──────────┘   │ tracking  │   └───────────┘  │                              │
  │ Bill pmts  │◄─────┼──────────────── │           │◄─────────────────┼── signed PDF uploaded ◄──────┘
  └────────────┘ hold │   write-back    └───────────┘                  │
                      │                       │                        │
                      │            PDF store (app) ──► mirror folder   │
                      └────────────────────────────────────────────────┘
```

### 3.1 Data model

| Entity | Key fields | Source |
|---|---|---|
| **Vendor** | NetSuite id, legal name, address, waiver contact name + email, hold mode (P1/P2), N-day override, `on_hold` | NetSuite, plus contact and settings kept in the app |
| **Project** | NetSuite id, name, job number, property address, owner name, GC name, active | NetSuite, plus owner/GC/address in the app if NetSuite lacks them (D3) |
| **Payment** | NetSuite bill payment id, vendor, date, amount, check/ACH ref, bills paid, project(s) | NetSuite |
| **Waiver** | id, vendor, project, payment, type (Progress/Final), amount, through date, exceptions text, status, `pdf_unsigned`, `pdf_signed`, `sent_at`, `due_at`, `received_at`, `received_via`, `void_reason` | App |
| **Event** | waiver, timestamp, user, action | App (audit trail) |

Waiver status: `Draft → Sent → Received`, or `Void`. `Overdue` is derived: `Sent` and past `due_at`.

One payment that covers bills on two projects produces two waivers, one per project, since the waiver is tied to the property.

### 3.2 The waiver document

Unconditional waiver, Ohio. Progress and Final share one layout. Fields:

- Claimant (vendor) legal name and address
- Customer: our company name
- Project name, job number, property address, owner name, general contractor name
- Payment amount, payment date, check or ACH reference
- Progress: work through date. Final: statement that all labor, materials and lower-tier parties are paid in full.
- Progress exceptions: retention withheld, disputed amounts, unbilled change orders (optional lines)
- Waiver and release of mechanics' lien rights, bond claim rights, and any claim against the owner, GC, customer or property for labor, materials or equipment furnished through the through date, in consideration of the payment named
- Signature block: company, signature, printed name, title, date. No notary block.
- Footer: waiver id and a QR code or short link to the upload page

Generated from an HTML template and rendered to PDF. When the company template arrives, its wording replaces the draft text and the layout is matched. Legal text is reviewed once by counsel.

### 3.3 Screens

1. **Needs waiver** (the home page). Rows pulled from NetSuite: every vendor payment with no waiver yet. Columns: vendor, project, amount, date, ref, suggested type. Select all or some, pick Progress or Final where the default is wrong, click **Generate and send**. PDFs are created, emails go out, rows move to *Sent*. This is the whole weekly job in one screen.
2. **Tracking**. Grid of all waivers, filter by project, vendor, status. Overdue rows in red. Vendors currently on hold listed at the top. Click a row to open it.
3. **Waiver detail**. Unsigned PDF, signed PDF (if back), timeline, buttons: resend, mark received (upload), void, regenerate.
4. **Project view**. All vendors on the project with waiver coverage: paid to date, waived to date, gap.
5. **Vendor view**. Contact, hold mode, outstanding waivers, hold status, history.
6. **Vendor upload page** (public, tokenized link, no login). Shows the unsigned PDF and an upload box. Upload marks the waiver *Received* and notifies AP.
7. **Settings**. Company details, template text, default N days, sender email, mirror folder, NetSuite connection test.

### 3.4 Convenience details

- Type defaults to Progress. Final is suggested when the project is marked complete or the vendor's contract value is fully paid.
- Vendor contact email is remembered after the first send.
- Reminder email at due date minus 3 days and at due date, then every 5 days.
- Signed PDFs can also arrive by email reply: an inbox rule forwards to the app, which matches the waiver id in the subject or footer. Phase 2.
- Everything the tool does is logged on the waiver timeline.

## 4. NetSuite integration

### 4.1 Auth and access

- One **Integration record** with Token-Based Authentication, one integration role limited to: Vendors (view), Projects/Jobs (view), Vendor Bills (view, edit of the hold field only), Vendor Payments (view). Tokens live in the app's secret store, never in the repo.
- Read via **SuiteQL** over the REST API. Write via REST record update.

### 4.2 Reads (every 15 minutes and on demand)

| Query | Purpose |
|---|---|
| Vendors (active, with address) | Vendor list |
| Projects (active) | Project list |
| Vendor payments since last sync, with applied bills and each bill's project | Feed the *Needs waiver* queue |
| Open vendor bills by vendor | Know what to hold |

### 4.3 Payment hold write-back

NetSuite vendor bills have a **Payment Hold** checkbox. Bills with it set are excluded from Pay Bills and from EBP batches. The hold rule runs after every sync and every status change:

1. Evaluate each vendor against its hold mode (D2).
2. If the vendor should be on hold and is not: set Payment Hold on all their open bills, stamp a custom bill field `Lien Waiver Hold = T` (so the tool never clears a hold that AP set for another reason), set `on_hold` in the app, email AP.
3. If the vendor should be off hold and is on: clear Payment Hold only on bills where `Lien Waiver Hold = T`, then clear the flag.
4. New bills for a vendor on hold get the hold at the next sync.

Optional later: a NetSuite saved search "Bills on lien waiver hold" on the AP dashboard, and a vendor-record checkbox for visibility.

Fits the ACH plan in `netsuite-vendor-ach-approvals-plan.md`: held bills never reach the EBP batch, so no extra control is needed in that flow.

## 5. Storage and email

- PDFs live in the app's storage under `/{project}/{vendor}/{waiver-id}-unsigned.pdf` and `-signed.pdf`, backed up nightly.
- The same tree is mirrored to a shared folder (SharePoint/OneDrive or Google Drive, per D4) so anyone can browse without the app.
- Phase 3 option: attach the signed PDF to the vendor payment in NetSuite through a small RESTlet, so it is visible from the payment record.
- Outgoing email from a dedicated mailbox such as `lienwaivers@company.com`, via SMTP or the platform API.

## 6. Stack and hosting

- **Python 3.12, FastAPI, SQLite** (Postgres later if ever needed), **Jinja2** HTML templates, **WeasyPrint** for PDF, **HTMX** for the front end. One process, one container.
- Login for staff (a handful of users), token links for vendors.
- Hosting options: a small container host (Fly.io, Azure Container Apps, Render) for about $10 to $20 a month, or Docker on an office server. Needs a public HTTPS URL for vendor upload links.
- Tests: unit tests for the hold rule and PDF fields, a fake NetSuite adapter for local runs and CI.

## 7. Phases

| Phase | Delivers | Depends on |
|---|---|---|
| **1. Create** | App with vendors, projects and payments entered by hand or CSV. Generate PDFs in batch, email them, track Sent/Received/Overdue, manual upload of signed copies, vendor upload link. Runs locally or hosted. | Template text (draft or company's) |
| **2. NetSuite read** | Sync vendors, projects and payments. *Needs waiver* queue fills itself. | D3, integration record |
| **3. Hold write-back** | Automatic Payment Hold per D2. Custom bill field. AP notifications. | Phase 2, custom field in NetSuite |
| **4. Polish** | Reminders, email-reply capture, mirror folder, PDF attached to the NetSuite payment, project coverage report. | Phase 3 |

Phase 1 can be built and demoed with sample data immediately.

## 8. Open questions

1. D1 through D5 above.
2. Do payments ever cover bills from more than one project? (Determines how often one payment yields two waivers.)
3. Who at the vendor signs: is one contact per vendor enough, or per project?
4. Should AP be able to override a hold in the app, or only in NetSuite?
5. Do you want the waiver to also release **bond** claims, or lien rights only? (Common on multifamily where a payment bond exists.)
