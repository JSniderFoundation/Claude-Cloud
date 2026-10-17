# ERP Data Model: Cabinets and Countertops for Multifamily

**Status:** Draft for discussion, nothing built · **Owner:** Finance Systems · **Date:** 2026-10-17

## 1. The business this models

| Item | Answer |
|---|---|
| Who we are | Ohio subcontractor that furnishes and installs cabinets, vanities and countertops in multifamily new construction |
| Customers | Mostly general contractors. Sometimes developers or owners directly. |
| Cabinets | Three sources: imported flat-pack (RTA) assembled by us, domestic pre-assembled bought finished, and a few built in-house |
| Countertops | Fabricated in our own shop from slabs |
| Install | Our own W-2 crews and subcontracted installers |
| Today's systems | NetSuite (GL, AP, projects as a custom segment), INNERGY (BOMs, work orders, inventory), the lien waiver app, Microsoft 365 |
| Goal | Our own ERP as the system of record for CRM, operations and finance, including the general ledger |

This document covers the data structure only: what the system records and how the records connect. Screens, code and hosting come later.

## 2. Design principles

1. **The project is the hub.** One Project record runs from the first lead to the end of warranty. CRM, operations and finance all hang off it.
2. **The unit matrix is the spine.** What goes into each unit type (the takeoff) is entered once, in estimating. It is then reused for the contract, purchasing, production, delivery, install, billing and job cost. This is what sets a multifamily finish business apart from a generic contractor or a cabinet shop, and it is where off-the-shelf systems are weakest.
3. **One party table.** Every company and person is a Party. Customer, vendor, subcontractor and employee are roles. When a GC's project manager moves to another GC, the relationship history moves with them.
4. **Ledgers, not balances.** Money (the GL) and stock (inventory) are append-only ledgers. Balances, on-hand quantities, job cost and AR are derived from them. Posted records are never edited, only reversed.
5. **Documents post, people don't.** Users create business documents such as invoices, bills, receipts and timesheets. A posting engine turns them into journal entries and inventory movements. Manual journal entries are for true adjustments only.
6. **Every cost and revenue line carries the same dimensions:** company, project, cost code, division (cabinets, tops, install) and location. With those, job cost, WIP and margin by product line come out of the system without spreadsheets.
7. **Compliance is data.** Insurance certificates, lien waivers, notices and holds are records with dates, so the system can block a payment or warn about a deadline. The lien waiver app becomes one module of the ERP.
8. **Integrate where the rules aren't ours.** Payroll tax filing, bank feeds, e-signature, tax rates and CAD/nesting software stay in specialist tools. The ERP owns the data they produce.

## 3. Map

```
                    ┌──────────────────────────── CRM ──────────────────────────────┐
  Party ──roles──►  │  Accounts · contacts · activities · bids (one per GC) · estimates │
  (orgs + people)   └───────────────────────────────┬────────────────────────────────┘
                                                    │ award
                                                    ▼
          ┌──────────────────────────────── PROJECT (hub) ─────────────────────────────────┐
          │  Contract · schedule of values · change orders · submittals · finish selections  │
          │                                                                                  │
          │  Buildings ► floors ► units ──is a──► unit type ──► scope lines   ◄── THE SPINE   │
          │                    │                                                             │
          │              releases (groups of units with a need-on-site date)                 │
          └──────┬──────────────────────┬──────────────────────────┬─────────────────────────┘
                 │ demand                │ demand                    │ unit milestones
                 ▼                       ▼                           ▼
     Purchasing & imports         Production                   Field
     POs · deposits · containers  RTA assembly · in-house      Deliveries · install orders ·
     customs · landed cost        cabinets · countertop fab    crews · subs · punch · service
                 │                 slabs · remakes                    │
                 ▼                       │                            │
            Inventory ledger ◄───────────┘                            │
                 │                                                    │
                 ▼                                                    ▼
     ┌───────────────────────────────────── FINANCE ──────────────────────────────────────┐
     │  AP · AR pay apps · retainage · job cost · WIP · GL · cash · tax · assets · payroll │
     └─────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 The spine in detail

```
project ─┬─ building ─ floor ─ unit ─────────────────────── is a ──┐
         │                       │                                  ▼
         ├─ unit_type (A1, B1, B1-M mirrored, B1-ADA) ─┬─ area (kitchen, bath 1, bath 2, laundry)
         │                                             └─ scope_line ──► item (B18 Shaker White,
         │                                                   ▲           quartz top 42 SF, sink…)
         ├─ scope_version: estimate v1, v2 ─► contract ─► revised by each change order
         │
         └─ release (Bldg 2, floors 1–3, need on site Mar 1)
               └─ unit ─► unit_scope_line (scope exploded per physical unit, sourcing decided here)
                              ├─► reservation / po_line         (purchasing)
                              ├─► work_order / countertop_piece (production)
                              ├─► delivery_line                 (logistics)
                              ├─► install_order                 (field)
                              └─► unit_milestone ──► pay app % complete suggestion ──► WIP
```

- **Unit types** are entered at bid time with a planned count. **Physical units** are created at award, once the building plans are final. Mirrored and accessible (ADA/Type A) units are variants of a base unit type, each with its own scope, because handing and counter heights change the cabinet list and the tops.
- Amenity and common spaces (clubhouse kitchen, leasing office, mail room) are units of kind `amenity` with their own unit type. No separate structure is needed.
- **Scope is versioned.** Each estimate revision is a scope version. The winning version becomes the contract baseline. Each executed change order produces a new current version. You can always answer "what did we bid, what did we sign, what are we building now."
- **Sourcing is decided per release, not per estimate.** A scope line says *what* goes in the unit ("B18, Shaker White"). The `unit_scope_line` says *how* it's fulfilled: assembled from imported RTA cartons, bought assembled from a domestic vendor, or built in-house. You can switch a release to domestic when an import container is late without touching the estimate or the contract.

## 4. Conventions (every table)

- `id`, `company_id` (legal entity; one today, but cheap to add now and painful to add later), `created_at`, `created_by`, `updated_at`, `updated_by`.
- `external_ref`: NetSuite and INNERGY ids, for migration and parallel running.
- Money is exact decimal (`numeric(14,2)`), or integer cents as in the lien waiver app. Never float. A `currency` field goes wherever a foreign supplier is involved. Quantities are `numeric(14,4)` with a unit of measure.
- Transaction documents have a header and lines, a `number` from a per-type sequence, and a `status`. They are never deleted, only voided with a reason.
- Master data has an `active` flag instead of being deleted.
- Shared side tables any record can use: `attachment`, `note`, `activity`, `event` (audit trail of who did what and when, with before and after values), `status_history`.

## 5. Entities by domain

Key fields only. Foreign keys are written as the entity name (for example, `project`).

### 5.1 Foundation

| Entity | What it is | Key fields |
|---|---|---|
| company | Legal entity that owns a set of books | name, EIN, address, base currency, fiscal year start |
| user | A login | party (person), email, roles, active |
| role, permission | Access control and segregation of duties | role name; permissions such as create vendor, edit bank details, approve bill, release ACH batch |
| approval_rule | When a document needs approval and by whom | document type, conditions (amount tier, division, project), approver steps, delegate |
| approval | One approval decision | document, step, approver, decision, comment, at |
| sequence | Document numbering | document type, prefix, next number |
| attachment | A file stored once and linked to any record | storage path, filename, category (plan, spec, COI, waiver, photo, DXF, POD), linked record |
| event | Audit trail | record, user, at, action, before, after |

### 5.2 Parties and CRM

| Entity | What it is | Key fields |
|---|---|---|
| party | Any organization or person | kind (org, person), legal name, display name, tax id, phone, website |
| address | An address for a party | party, type (billing, remit-to, ship-to, site), lines, city, state, zip, county |
| party_role | What a party is to us. A party can hold several roles. | party, role (prospect, customer, vendor, subcontractor, employee, developer, architect, designer, property manager, competitor, customs broker, carrier) |
| customer_profile | Terms for a customer | party, payment terms, credit limit, default retainage, billing method (AIA, GC form, Textura, GCPay, Procore), pay app cutoff day, typical days to pay |
| vendor_profile | Terms for a vendor or sub | party, terms, 1099 flag, payment method, country, incoterms, default lead time, waiver hold mode |
| contact_affiliation | A person's role at an organization, with dates | person, organization, title, function (PM, APM, estimator, superintendent, purchasing, AP), start, end, primary |
| activity | Calls, emails, meetings, site visits, bid walks | type, date, owner, parties, project, bid, summary, outcome, next step |
| task | A to-do | assignee, due date, linked record, status |
| spec_package | A developer's standard finish package, reused across their projects | developer, name, door style, finish, quartz color, edge, hardware, sink |

### 5.3 Project and the unit matrix

| Entity | What it is | Key fields |
|---|---|---|
| project | A real development, from lead to end of warranty | name, job number (assigned at award), stage (lead, bidding, awarded, active, closeout, warranty, closed, lost, no-bid), developer, architect, GC (once awarded), site address, county, product type (garden, wrap, podium, mid-rise, senior, student), unit count, lead source, financing type, estimated start and finish, PM, estimator |
| project_compliance | Legal and insurance settings for a project | bond project, surety, bond number, insurance program (standard, OCIP, CCIP), prevailing wage type (none, Davis-Bacon, state), tax treatment, Notice of Commencement date and record number |
| building | A building on the site | project, name, floors, sequence |
| floor | A level in a building | building, level |
| unit_type | A floor plan | project, code, beds, baths, base unit type, variant (standard, mirrored, ADA), template required (or fabricate tops from drawings) |
| unit | A physical unit or amenity space | project, building, floor, number, unit type, kind (dwelling, amenity, common), current status (derived from milestones) |
| area | A room within a unit type | unit type, room (kitchen, bath 1, bath 2, laundry, bar) |
| scope_version | A version of the takeoff | project, number, kind (estimate, contract, revision), bid or change order it came from, planned count per unit type, status (draft, active, superseded) |
| scope_line | One line of the takeoff | scope version, unit type, area, item, quantity, unit of measure. For tops: SF, edge LF, splash LF, cutouts. |
| finish_selection | An approved finish choice | project, category (door style, cabinet finish, hardware, top material, thickness, edge, sink), value or item, applies to (all, a unit type, an area), submittal |
| release | A group of units released to procurement and production | project, name, units, need-on-site date, sourcing default, status (planned, released, procured, in production, delivered, complete) |
| unit_scope_line | Scope exploded per physical unit at release | unit, scope line, item, quantity, sourcing (import RTA, domestic, make), override reason, status, links to reservation, PO line, work order, countertop piece, delivery line, install order |
| milestone_type | Steps every unit passes through | name (cabinets delivered, cabinets installed, top templated, top fabricated, top installed, hardware set, punched, accepted), sequence, division |
| unit_milestone | The unit status board | unit, milestone type, planned date, actual date, completed by (crew or sub), source document |

### 5.4 Estimating and bidding

A single project often has bids out to several GCs. Each bid is its own record; the project is shared.

| Entity | What it is | Key fields |
|---|---|---|
| bid | Our bid to one GC on one project | project, GC, invited date, due date and time, status (invited, declined, in progress, submitted, won, lost), amount, probability, winning competitor, lost reason |
| bid_document | Plans, specs and addenda received | bid, attachment, document type, revision, date |
| estimate | A priced version of a bid | bid, scope version, version number, status, cost basis snapshot (item costs, labor rates, slab yield, freight per container, duty rates), totals |
| estimate_line | A cost and price line | estimate, cost group (cabinet material, cabinet install, top material, top fabrication, top install, freight, duty, bond, general conditions), cost code, quantity, unit cost, markup, price, computed or manual |
| estimate_alternate | Add, deduct or value-engineering options | estimate, description, price change, accepted |
| clarification | Inclusions, exclusions and qualifications | library text (for example, "blocking by others"), and which ones each estimate uses |

### 5.5 Contract, changes and submittals

| Entity | What it is | Key fields |
|---|---|---|
| contract | Our agreement with the GC or owner | project, customer, type (subcontract, purchase order, owner direct), number, executed date, original value, retainage rule (for example 10% until 50% complete, then 5%), payment terms, billing format, insurance requirements, waiver requirements, warranty term, backcharge terms, status |
| sov_line | Schedule of values line for pay apps | contract, line number, description (for example "Bldg 1 cabinets material"), division, scheduled value, retainage %, linked building or release and cost group (so progress can be suggested from unit milestones) |
| change_event | Anything that might change cost or price | project, source (GC directive, RFI, owner upgrade, field condition, our error), status (potential, priced, submitted, approved, rejected), estimated cost and price |
| change_order | An executed change | contract, our number, GC's number, amount, schedule days, executed date; lines with SOV line, price, and budget change by cost code |
| tm_ticket | Time and materials work signed in the field | project, date, labor hours, materials, signed by, change event |
| backcharge | A charge between parties | direction (GC to us, us to sub or vendor), project, party, reason, amount, photos, status, resolution (pay app deduction, credit memo, bill credit) |
| submittal | Shop drawings, samples, product data | project, type, spec section, revision, status (draft, submitted, approved, approved as noted, revise and resubmit, rejected), dates, reviewer, finish selections it covers |
| rfi | A question to the design team | project, question, answer, dates, change event if it costs money |

### 5.6 Catalog and items

| Entity | What it is | Key fields |
|---|---|---|
| item | Anything we buy, make, stock or sell | SKU, description, type (inventory, non-inventory, labor, service), category (base, wall, tall, vanity, filler, panel, molding, RTA carton, slab, sink, hardware, sheet goods, consumable), unit of measure, tracking (none, lot, serial), costing method, division, default accounts |
| cabinet_spec | Cabinet attributes for matching and estimating | item, line or series, door style, finish, construction, width, height, depth, nomenclature (B18, W3030, VSB30), hinge side, finished ends |
| countertop_material | Slab attributes | item, brand, color, price group, thickness (2cm, 3cm), finish, slab size |
| item_vendor | A way to buy an item | item, vendor, vendor SKU, price, currency, minimum order, lead time, carton count, CBM, weight, country of origin, HTS code, effective dates, preferred |
| bom | How an item is made or assembled | parent item, revision, type (RTA assembly, manufacture); components with item, quantity and scrap % |
| routing | Shop steps to make an item | parent item, operations with work center and standard minutes |
| work_center | A shop resource | name (RTA assembly, saw, CNC, edge polisher, cabinet bench, QC), division, labor rate, overhead rate, hours per day |
| item_alternate | Approved substitutes | item, alternate, reason (domestic equivalent of an import SKU), approved for (all, a developer, a project) |
| uom_conversion | Unit conversions | item, from (carton, slab, sheet), to, factor |

An assembled cabinet item can have both a BOM (RTA cartons plus hardware) and an `item_vendor` row (buy it assembled domestically). That is how sourcing becomes a choice per release.

### 5.7 Purchasing and import logistics

| Entity | What it is | Key fields |
|---|---|---|
| material_requirement | Computed demand from released units | item, quantity, need date, project, release, available, reserved, on order, shortfall |
| purchase_order | An order to a vendor | vendor, type (import, domestic, slab, hardware, other), project (most cabinet POs are project-specific), ship-to (warehouse or site), currency, incoterms, terms (for example 30% deposit, balance against bill of lading), status, approval |
| po_line | One line of a PO | item, quantity, price, need date, project, release, cost code, received quantity, billed quantity |
| vendor_deposit | Prepayment on an import PO | PO, amount, paid date, payment, amount applied to bills |
| shipment | A container or truckload | mode (ocean FCL, LCL, truck, LTL), carrier, container number, bill of lading, origin port, ETD, ETA port, ETA warehouse, last free day, customs broker, status (booked, sailed, arrived, released, delivered, empty returned) |
| shipment_line | What's in the shipment | shipment, PO line, quantity, cartons, CBM, weight |
| customs_entry | The customs filing | shipment, entry number, entry date, broker, entered value; lines with HTS code, value, and one or more duty programs (normal duty, Section 301, Section 232, antidumping or countervailing case and rate), plus MPF and HMF fees |
| landed_cost_charge | A cost to spread over a shipment | shipment, type (ocean freight, duty, AD/CVD deposit, MPF, HMF, brokerage, drayage, demurrage, inland freight), vendor bill, amount, allocation basis (value, CBM, weight, quantity) |
| receipt | Goods received | PO or shipment, location, date, received by; lines with PO line, quantity good, quantity damaged, lot or serial (slabs), landed unit cost |
| vendor_claim | Damage, shortage or return claim | vendor or carrier, receipt, lines, photos, amount, status, credit received |

The same cabinet line can carry several duty programs at once, and rates change by proclamation. Duty rates are therefore data with effective dates, never hard-coded, and estimates snapshot the rate they assumed.

### 5.8 Inventory and warehouse

| Entity | What it is | Key fields |
|---|---|---|
| location | A place stock can be | warehouse, zone, bin, type (warehouse, staging, shop, truck, in transit, jobsite) |
| serial | A tracked unit, mainly slabs | item, bundle or lot, length, width, usable area, thickness, cost, photo, status (available, reserved, cut, remnant, scrap), parent serial (remnant lineage), location |
| inventory_txn | The stock ledger | item, serial, location, quantity (+/−), unit cost, type (receipt, transfer, issue to work order, work order output, issue to job, adjustment, count, scrap, return), source document, project, unit |
| cost_layer | Costing for FIFO or average cost | item, location, receipt, quantity remaining, unit cost |
| reservation | Stock held for a job | item or serial, quantity, project, release, units, status |
| inventory_count | A cycle or full count | location, date, lines with counted and system quantities, adjustment posted |

On-hand, available and reserved are views over `inventory_txn` and `reservation`, not stored numbers.

### 5.9 Production

Three flows share one work order structure:

- **RTA assembly.** A batch per release (for example 200 × B18). Consumes cartons and hardware, outputs assembled cabinets. Where RTA cabinets are assembled (warehouse or on site by the installer) is a per-release choice, and the data supports both.
- **In-house cabinets.** A small number of work orders with a BOM and routing.
- **Countertops.** Template, then pieces, then nest on slabs, then cut and fabricate, then QC.

| Entity | What it is | Key fields |
|---|---|---|
| work_order | A production job | type (RTA assembly, manufacture, countertop), item and quantity, or units for tops, project, release, due date, status (planned, released, in progress, complete, closed), BOM and routing snapshot |
| wo_material | Components planned and issued | work order, item, serial, planned quantity, issued quantity |
| wo_operation | Steps planned and done | work order, work center, sequence, standard minutes, actual minutes, status |
| field_measure | Countertop template or field measure | units, area, method (digital template, tape, fab from drawings), scheduled date, actual date, templater, DXF files, issues found (cabinets out of level) |
| countertop_piece | One piece of stone | unit, area, label (K1, K2, V1), material, thickness, length, width, SF, edge LF and profile, splash LF and height, cutouts (sink model, cooktop, faucet holes), seams, DXF, status (designed, nested, cut, fabricated, QC passed, loaded, installed), work order |
| slab_nest | Pieces laid out on a slab | slab serial, pieces, yield %, remnant serial created, file |
| remake | A piece that had to be made again | original piece, reason (mis-measure, fab error, install damage, material defect, change), responsible (us, another trade, vendor), cost, replacement piece, backcharge |
| quality_check | An inspection | work order or piece, checklist, result, photos, inspector |

### 5.10 Field: delivery, install, punch and service

| Entity | What it is | Key fields |
|---|---|---|
| delivery | A trip to the jobsite | project, release, scheduled window, truck and driver or carrier, status (scheduled, loaded, delivered, partial), signed by (GC superintendent), photos; lines with item, unit scope line and quantity |
| crew | An install team | name, type (internal, subcontractor), foreman, members or sub, division |
| install_order | Work assigned to a crew or sub | project, units, areas, scope (cabinet install, RTA assembly on site, top install, hardware, punch), crew or sub, scheduled date, status, completed date |
| subcontract | Our agreement with an install sub | sub, project (or master agreement), value or rate card, retainage %, insurance requirements, status |
| sub_rate | How we pay an install sub | subcontract, basis (per unit type, per cabinet box, per LF, per top SF, per hour, per trip), rate |
| sub_pay_app | A sub's request for payment | sub, subcontract, period; lines with completed install orders × rate, retainage withheld, backcharges, net. Approval creates the vendor bill. |
| time_entry | Hours or piece work by an employee | employee, date, regular and OT hours, pay type (hourly, piece), quantity and piece rate, project, cost code, unit or install order, or work order and operation, approved by |
| daily_log | Field report | project, date, crew, work done, units touched, delays (not ready, damaged by others), photos |
| punch_item | A defect to fix | project, unit, area, source (our pre-punch, GC, owner or architect), description, responsible (us or another trade), crew, status, photos before and after |
| service_ticket | A warranty or service call after turnover | project, unit, reported by (property manager), issue, covered by warranty or billable, visits, cost, status |

### 5.11 Finance

#### General ledger

| Entity | What it is | Key fields |
|---|---|---|
| account | Chart of accounts | number, name, type (asset, liability, equity, revenue, cost of revenue, expense), subtype (bank, AR, AR retainage, inventory, production WIP, contract asset, contract liability, vendor deposits, GRNI, AP, AP retainage, labor clearing, use tax payable), active |
| cost_code | Job cost category | code, name, category (material, labor, subcontract, equipment, freight and duty, other), division |
| division, department | Reporting dimensions | name |
| fiscal_period | Accounting periods | year, period, start, end, status per module (open, soft close, closed) |
| journal_entry | A posted entry | date, period, source (manual, AR, AP, payment, receipt, inventory, payroll, WIP, depreciation), source document, memo, status (draft, posted, reversed), reverses |
| journal_line | One debit or credit | entry, account, debit, credit, project, cost code, division, location, department, party, memo |
| posting_rule | How each document posts | document type, line type, debit account, credit account, dimension mapping |
| gl_budget | Company budget by account | account, period, amount, version |

#### Accounts receivable

| Entity | What it is | Key fields |
|---|---|---|
| pay_application | Monthly progress billing | contract, number, period to, status (pencil draft, submitted, approved, revised, paid), submitted date, approved amount, portal reference |
| pay_app_line | One SOV line on a pay app (AIA G703 columns) | pay application, SOV line, previously completed, completed this period, materials stored, % complete, retainage this period and to date, balance to finish, suggested % from unit milestones |
| ar_invoice | An invoice | customer, project, contract, type (progress, retainage release, T&M, service, other), date, due date, amount, retainage, tax, status; lines with revenue account and dimensions |
| customer_payment | Money received | customer, date, method (check, ACH, joint check), reference, amount; applications to invoices, including retainage |
| credit_memo | A credit to a customer | customer, invoice, reason (backcharge, price change), amount |
| lien_waiver_out | Waivers we give the GC | pay application or payment, type (conditional, unconditional), progress or final, amount, through date, status, signed document |
| notice | Ohio lien notices (R.C. Chapter 1311) | project, type (Notice of Commencement received, Notice of Furnishing served, lien affidavit), party served, date, method, proof, deadline computed from last work date |

#### Accounts payable

| Entity | What it is | Key fields |
|---|---|---|
| vendor_bill | A vendor or sub invoice | vendor, invoice number, date, due date, PO, project, retainage withheld, status (draft, pending approval, approved, on hold, partly paid, paid), hold reasons; lines with item or account, PO line, quantity, amount, project, cost code, division, use tax |
| bill_match | Three-way match | PO line, receipt line, bill line, price variance, quantity variance |
| vendor_payment | Money paid | vendor, date, method (ACH, check, wire, card), bank account, reference, amount, batch, joint check co-payee; applications to bills and deposits |
| payment_batch | An ACH or check run | status, total, approvals, NACHA file |
| vendor_bank_account | Vendor bank details, change-controlled | vendor, routing, account (encrypted), status (pending, approved), changed by, approved by, call-back verified |
| lien_waiver_in | Waivers our subs and suppliers sign | as in the lien waiver app: vendor, project, payment, type, amount, through date, status, PDFs |
| compliance_document | Insurance and paperwork from a party | party, type (general liability, auto, umbrella, workers' comp certificate, W-9, signed subcontract, safety program), project (if specific), effective, expires, limits, additional insured |
| payment_hold | Why a vendor or bill can't be paid | party or bill, reason (waiver overdue, COI expired, dispute, backcharge), set by, set at, released by, released at |

Today's lien waiver app maps directly onto this: its Vendor, Project, Payment, Waiver and Event become `party`/`vendor_profile`, `project`, `vendor_payment`, `lien_waiver_in` and `event`. The ACH plan's bank-detail and batch approvals become `vendor_bank_account`, `payment_batch` and `approval`.

#### Job cost and WIP

| Entity | What it is | Key fields |
|---|---|---|
| job_budget | Budget per project and cost code | project, cost code, original (from the winning estimate), approved changes (from change orders), revised, cost to complete (forecast), forecast at completion, version |
| commitment | Costs we've agreed to but not yet billed (view) | open PO lines and subcontracts by project and cost code: committed, invoiced, remaining |
| job_cost | Actual cost (view) | journal lines with a project and cost code: material issued, labor, subs, freight and duty, equipment |
| labor_burden_rate | Loaded cost of an hour | employee class, period, payroll tax %, Ohio BWC %, benefits %; applied to time entries |
| wip_snapshot | Frozen month-end WIP schedule per project | period, contract value with approved changes, estimated total cost, cost to date, % complete (cost-to-cost), earned revenue, billed to date, over or under billing, gross profit, change from last month (fade) |

#### Payroll (provider-run, ERP-owned data)

| Entity | What it is | Key fields |
|---|---|---|
| employee | A W-2 worker | party, employee number, class (installer, fabricator, assembler, driver, office), crew, hire date, termination date, prevailing wage classification |
| pay_rate | Pay over time | employee, effective date, type (hourly, salary, piece schedule), rate |
| payroll_run | Imported from the payroll provider | period, check date, provider reference; lines with employee, gross, employee taxes, deductions, net, employer taxes |
| certified_payroll | Weekly report for prevailing wage jobs | project, week, built from time entries and payroll lines |

#### Cash, tax and assets

| Entity | What it is | Key fields |
|---|---|---|
| bank_account | Our bank accounts | GL account, bank, last four digits, ACH company id |
| bank_txn | Imported bank feed lines | bank account, date, amount, description, matched to payment, receipt or journal |
| bank_reconciliation | Monthly reconciliation | bank account, period, statement balance, cleared items, difference |
| tax_rate | Ohio sales and use tax by county | jurisdiction, rate, effective dates |
| tax_exemption_certificate | Exemption documentation | project or customer, type, document, expires |
| fixed_asset | CNC, saws, forklifts, trucks | description, cost, in-service date, method, life, location, GL accounts; depreciation schedule |

## 6. One kitchen, end to end

Unit 2-204, type B1-M (mirrored B1), Building 2:

1. **Bid.** Estimating builds the B1 and B1-M scope lines: base and wall cabinets, a vanity, a 42 SF quartz top with one undermount sink cutout. Estimate v2 goes to three GCs as three bids.
2. **Award.** One GC wins the project and awards it to us. Scope v2 becomes the contract baseline. SOV lines are set per building and division, and the job budget by cost code comes from the estimate.
3. **Release.** The GC's look-ahead puts cabinets on Building 2, floors 1 to 3, starting March 1. Release R-2.1 explodes the scope into `unit_scope_line`s for 48 units and computes the material requirement.
4. **Buy.** An import PO for RTA cartons is issued and a 30% deposit is paid. The container ships, then the customs entry posts duty lines. At receipt, freight, duty, brokerage and drayage are allocated across the cartons, and inventory is valued at landed cost and reserved to the project.
5. **Assemble.** An RTA assembly work order turns cartons and hardware into assembled cabinets. Shop time entries carry the labor.
6. **Deliver.** Floor 2's kit ships, and the superintendent signs the POD. Inventory is issued to the job, and the cost lands on the project.
7. **Install.** An install order goes to a sub, who completes it, setting the `cabinets installed` milestone. The sub's pay app becomes a bill with retainage withheld. The lien waiver and COI checks gate the payment.
8. **Tops.** The tops are templated, which creates pieces K1 and K2. They are nested on slab S-1043 (81% yield, remnant S-1043-R1 created), then fabricated, QC'd and installed, setting the `top installed` milestone.
9. **Bill.** On the pay app, the "Bldg 2 cabinets" line suggests its % complete from installed units. If the contract allows, cabinets reserved in the warehouse can be billed as stored materials. The GC approves and the AR invoice posts with retainage. When payment arrives, our waiver goes to the GC.
10. **Close the month.** Job cost is compared with budget and the forecast is updated. The WIP snapshot computes earned revenue and over or under billing, then posts the adjusting entry.
11. **Turnover.** The unit is punched and accepted. The retainage release is invoiced at closeout. Warranty tickets for 2-204 attach to the unit for the warranty term.

## 7. What posts to the GL

| Event | Debit | Credit |
|---|---|---|
| Import deposit paid | Vendor deposits | Cash |
| Goods received | Inventory | GRNI (goods received not invoiced) |
| Supplier bill matched | GRNI, price variance | AP, Vendor deposits (deposit applied) |
| Freight, duty and brokerage bills | Landed cost clearing | AP |
| Landed cost allocated at receipt | Inventory | Landed cost clearing |
| Components issued to a work order | Production WIP | Inventory |
| Shop labor on a work order (burdened) | Production WIP | Labor clearing |
| Work order completed | Inventory (finished) | Production WIP |
| Delivery to site (issue to job) | Job cost: material (project, cost code) | Inventory |
| Payroll imported | Labor clearing | Cash, payroll liabilities |
| Field time distributed (burdened) | Job cost: labor (project, cost code) | Labor clearing |
| Sub bill approved | Job cost: subcontract | AP, AP retainage |
| Use tax on purchases | Inventory or job cost | Use tax payable |
| Pay app approved | AR, AR retainage | Contract revenue |
| Customer payment | Cash | AR or AR retainage |
| Month-end WIP, job overbilled | Contract revenue | Contract liability |
| Month-end WIP, job underbilled | Contract asset | Contract revenue |
| Depreciation | Depreciation expense | Accumulated depreciation |

Whatever is left in labor clearing after distribution is the burden variance, which is reviewed monthly.

## 8. Reports the structure answers

| Report | Built from |
|---|---|
| Pipeline, bid calendar, hit rate by GC | bid, project, activity |
| Backlog (contracted, not yet earned) | contract, change_order, wip_snapshot |
| WIP schedule and profit fade | wip_snapshot by period |
| Job cost vs budget, cost to complete | job_budget, commitment, journal_line |
| Unit status board by building and floor | unit_milestone |
| Container tracker (ETA, last free day, demurrage risk) | shipment |
| Slab inventory, yield, remnant use | serial, slab_nest |
| Remake rate and cost by cause | remake |
| Install productivity (units per crew day, cost per unit by crew or sub) | install_order, time_entry, sub_pay_app |
| Margin by division and by sourcing (import, domestic, make) | journal_line dimensions, unit_scope_line |
| AR aging with retainage, expected pay dates | ar_invoice, customer_profile |
| AP aging and holds | vendor_bill, payment_hold |
| Compliance (COIs expiring, waivers outstanding, notice deadlines) | compliance_document, lien_waiver_in, notice |
| Cash forecast | AR expected dates, AP due, import deposits, payroll |

## 9. Build order (recommendation)

1. **Foundation, parties, project and unit matrix, items.** Everything else depends on these.
2. **CRM and estimating.** This is the biggest gap today and carries no accounting risk. It also creates the scope data every later module reuses.
3. **Operations: purchasing and imports, inventory, production, field.** INNERGY is replaced at this stage.
4. **Finance subledgers: AR pay apps, AP, job cost.** These feed NetSuite with summarized journals while both systems run in parallel.
5. **GL cutover from NetSuite last,** at a fiscal year start, after at least one quarter of parallel running. Payroll processing stays with a provider for good.

Rationale: the GL is the riskiest and least distinctive piece, and NetSuite already does it well. Your advantage is the spine, so build that first and earn the cutover.

## 10. Assumptions and open questions

**Assumptions made in this draft (change any of them):**

- One legal entity today. `company_id` is in place for later.
- Customers are mostly GCs, billed by AIA-style pay apps with retainage.
- Revenue is recognized over time using cost-to-cost, with a monthly WIP schedule. Confirm with your CPA and your bonding company's format.
- Material cost hits the job when it is delivered to site. Until then it is inventory reserved to the job, so it does not inflate % complete.
- Ohio treats construction contractors as the consumer of the materials they install, so tax is mostly paid or accrued as use tax on purchases, with exemptions for some exempt owners. Confirm with your CPA.
- Ohio only. Ohio workers' comp is the state fund (BWC), so it is a burden rate, not an insurance policy.
- None of this is legal or tax advice.

**Open questions:**

1. Do you ever sell material only, with no install (to other contractors, or slab remnants to the public)? That adds a simple sales order flow.
2. Do your GCs let you bill stored materials, for example cabinets in your warehouse, on pay apps?
3. Any prevailing wage or Davis-Bacon jobs (HUD-financed projects often are)? That decides whether certified payroll is needed.
4. How do you pay install subs today: per unit, per box, per LF or SF, or lump sum per building?
5. Which payroll provider do you use?
6. How many warehouse and shop locations?
7. Do you template every top, or fabricate repeat unit types from drawings and field-verify?
8. Will you need more than one legal entity, for example a separate importing company?
