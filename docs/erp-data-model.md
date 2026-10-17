# ERP Data Model: Cabinets and Countertops for Multifamily

**Status:** Draft for discussion, nothing built · **Owner:** Finance Systems · **Date:** 2026-10-17 (revised with countertop, billing, sub pay and prevailing wage corrections)

## 1. The business this models

| Item | Answer |
|---|---|
| Who we are | Ohio subcontractor that furnishes and installs cabinets, vanities and countertops in multifamily new construction |
| Customers | Mostly general contractors. Sometimes developers or owners directly. |
| Cabinets | Three sources: imported flat-pack (RTA) assembled by us, domestic pre-assembled bought finished, and a few built in-house |
| Countertops | Three sources: precut tops imported finished, cut by the supplier from our shop drawings; tops we fabricate from slabs bought domestically; and tops we fabricate from imported blanks (small slabs). Everything we custom cut is templated. Precut tops are never templated. |
| Install | Our own W-2 crews and subcontracted installers. Subs can be paid per unit, per cabinet box, per LF or SF, or lump sum per building. |
| Stored materials | Billable on some contracts, not all |
| Prevailing wage | None today, but possible. The data model is ready, and that part is built when the first such bid arrives. |
| Today's systems | NetSuite (GL, AP, projects as a custom segment), INNERGY (BOMs, work orders, inventory), the lien waiver app, Microsoft 365 |
| Goal | Our own ERP as the system of record for CRM, operations and finance, including the general ledger |

This document covers the data structure only: what the system records and how the records connect. Screens, code and hosting come later.

## 2. Design principles

1. **The project is the hub.** One Project record runs from the first lead to the end of warranty. CRM, operations and finance all hang off it.
2. **The unit matrix is the spine.** What goes into each unit type (the takeoff) is entered once, in estimating. It is then reused for the contract, purchasing, production, delivery, install, billing, sub pay and job cost. This is what sets a multifamily finish business apart from a generic contractor or a cabinet shop, and it is where off-the-shelf systems are weakest.
3. **One party table.** Every company and person is a Party. Customer, vendor, subcontractor and employee are roles. When a GC's project manager moves to another GC, the relationship history moves with them.
4. **Ledgers, not balances.** Money (the GL) and stock (inventory) are append-only ledgers. Balances, on-hand quantities, job cost and AR are derived from them. Posted records are never edited, only reversed.
5. **Documents post, people don't.** Users create business documents such as invoices, bills, receipts and timesheets. A posting engine turns them into journal entries and inventory movements. Manual journal entries are for true adjustments only.
6. **Every cost and revenue line carries the same dimensions:** company, project, cost code, division (cabinets, tops, install) and location. With those, job cost, WIP and margin by product line come out of the system without spreadsheets.
7. **Compliance is data.** Insurance certificates, lien waivers, notices, certified payroll and holds are records with dates, so the system can block a payment or warn about a deadline. The lien waiver app becomes one module of the ERP.
8. **Integrate where the rules aren't ours.** Payroll tax filing, bank feeds, e-signature, tax rates and CAD/nesting software stay in specialist tools. The ERP owns the data they produce.
9. **Pay once, bill once.** Every sub pay app line and every stored-materials claim points to the record that proves it: a verified unit, a reserved slab, an approved timesheet, or for a lump sum, the % complete suggested from unit milestones. The same record can't be paid or billed twice.

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
          │                    │                      └──► countertop design pieces          │
          │              releases (groups of units with a need-on-site date)                 │
          └──────┬──────────────────────┬──────────────────────────┬─────────────────────────┘
                 │ demand                │ demand                    │ unit milestones
                 ▼                       ▼                           ▼
     Purchasing & imports         Production                   Field
     POs · deposits · containers  RTA assembly · in-house      Templates · deliveries ·
     (RTA, precut tops, blanks) · cabinets · custom tops       install orders · crews · subs ·
     domestic slabs · customs ·   (slabs, blanks) · precut     punch · service
     landed cost                  prep · remakes                      │
                 │                       │                            │
                 ▼                       │                            │
            Inventory ledger ◄───────────┘                            │
                 │   (precut tops go from inventory straight to field)│
                 ▼                                                    ▼
     ┌───────────────────────────────────── FINANCE ──────────────────────────────────────┐
     │  AP · sub pay apps · AR pay apps · stored materials · retainage · job cost · WIP ·   │
     │  GL · cash · tax · assets · payroll                                                  │
     └─────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 The spine in detail

```
project ─┬─ building ─ floor ─ unit ─────────────────────── is a ──┐
         │                       │                                  ▼
         ├─ unit_type (A1, B1, B1-M mirrored, B1-ADA) ─┬─ area (kitchen, bath 1, bath 2, laundry)
         │                                             ├─ scope_line ──► item (B18 Shaker White,
         │                                             │                 kitchen top 42 SF, sink…)
         │                                             └─ countertop_design_piece (K1, K2, V1 from the
         │                                                approved shop drawings; planned source)
         ├─ scope_version: estimate v1, v2 ─► contract ─► revised by each change order
         │
         └─ release (Bldg 2, floors 1–3, need on site Mar 1)
               └─ unit ─► unit_scope_line (scope exploded per physical unit)
                              ├─► reservation / po_line         (purchasing)
                              ├─► stored_material_line          (pay app, where the contract allows)
                              ├─► work_order                    (production)
                              ├─► countertop_piece              (precut: PO line and receipt;
                              │                                  custom: template, nest, work order)
                              ├─► delivery line                 (logistics)
                              ├─► install_order line ──► sub_pay_app line (boxes and LF from the
                              │   (field)                    scope, SF from installed pieces)
                              └─► unit_milestone ──► pay app % complete suggestion ──► WIP
```

- **Unit types** are entered at bid time with a planned count. **Physical units** are created at award, once the building plans are final. Mirrored and accessible (ADA/Type A) units are variants of a base unit type, each with its own scope and its own countertop shop drawings, because handing and counter heights change the cabinet list and the tops. Precut tops are cut from those drawings, so every variant needs its own design pieces.
- Amenity and common spaces are units too: kind `amenity` (clubhouse kitchen) or `common` (leasing office, mail room), each with its own unit type. No separate structure is needed.
- **Scope is versioned.** Each estimate revision is a scope version. The winning version becomes the contract baseline. Each executed change order produces a new current version. You can always answer "what did we bid, what did we sign, what are we building now."
- **Cabinet sourcing is decided per release, not per estimate.** A scope line says *what* goes in the unit ("B18, Shaker White"). The `unit_scope_line` says *how* it's fulfilled: assembled from imported RTA cartons, bought assembled from a domestic vendor, or built in-house. You can switch a release to domestic when an import container is late without touching the estimate or the contract.
- **Top sourcing is planned per design piece and can switch late in one direction only.** Each countertop design piece has a planned source: precut, custom from a domestic slab, or custom from an imported blank. Precut pieces are ordered from the approved shop drawings well ahead of each planned release, against the units of each type in that release (per building; see open question 3). A release or a single piece can switch from precut to custom at short notice, for example when a container is late or a piece doesn't fit. That switch adds a template and fabrication. Switching from custom to precut needs the full import lead time. The actual source lives on each `countertop_piece`, and a unit scope line for tops shows the source derived from its pieces, or "mixed".
- **Templating follows the source.** A countertop area is templated if any of its pieces is custom cut, after the unit's `cabinets installed` milestone. Precut pieces are never templated. No flag on the unit type is needed.
- What drives the planned top source (rules, not fields): the repeat count of the unit type; whether the drawings are approved early enough for the precut lead time; whether the piece fits a blank; which colors each source offers; estimated cost per SF by source; and field risk (ADA, amenity and irregular walls lean custom). The SF of the design pieces in an area should match the scope line SF, which catches takeoff drift.

## 4. Conventions (every table)

- `id`, `company_id` (legal entity; one today, but cheap to add now and painful to add later), `created_at`, `created_by`, `updated_at`, `updated_by`.
- `external_ref`: NetSuite and INNERGY ids, for migration and parallel running.
- Money is exact decimal (`numeric(14,2)`), or integer cents as in the lien waiver app. Never float. A `currency` field goes wherever a foreign supplier is involved. Quantities are `numeric(14,4)` with a unit of measure.
- Transaction documents have a header and lines, a `number` from a per-type sequence, and a `status`. They are never deleted, only voided with a reason.
- Master data has an `active` flag instead of being deleted.
- Side tables any record can use: `attachment`, `note`, `activity`, `event` (audit trail) and `status_history`. All five are defined in 5.1 and 5.2.
- Tables marked **(later)** are defined now, so nothing has to be restructured when they're needed, but they're built only when first needed. For prevailing wage, that is when the first such bid arrives.

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
| attachment | A file stored once and linked to any record | storage path, filename, category (plan, spec, shop drawing, COI, waiver, photo, DXF, POD, bill of sale, inventory listing, certified payroll), linked record |
| note | A comment on any record | linked record, author, text, at |
| event | Audit trail | record, user, at, action, before, after |
| status_history | Every status change on any document | record, from status, to status, user, at, reason |

### 5.2 Parties and CRM

| Entity | What it is | Key fields |
|---|---|---|
| party | Any organization or person | kind (org, person), legal name, display name, tax id, phone, website |
| address | An address for a party | party, type (billing, remit-to, ship-to, site), lines, city, state, zip, county |
| party_role | What a party is to us. A party can hold several roles. | party, role (prospect, customer, vendor, subcontractor, employee, developer, architect, designer, property manager, competitor, customs broker, carrier) |
| customer_profile | Terms for a customer | party, payment terms, credit limit, default retainage, billing method (AIA, GC form, Textura, GCPay, Procore), pay app cutoff day, typical days to pay |
| vendor_profile | Terms for a vendor or sub | party, terms, 1099 flag, payment method, country, incoterms, default lead time, waiver hold mode |
| contact_affiliation | A person's role at an organization, with dates | person, organization, title, function (PM, APM, estimator, superintendent, purchasing, AP), start, end, primary |
| activity | Calls, emails, meetings, site visits, bid walks | type, date, owner, parties, linked record (usually a project or bid), summary, outcome, next step |
| task | A to-do | assignee, due date, linked record, status |
| spec_package | A developer's standard finish package, reused across their projects | developer, name, door style, finish, quartz color, edge, hardware, sink |

### 5.3 Project and the unit matrix

| Entity | What it is | Key fields |
|---|---|---|
| project | A real development, from lead to end of warranty | name, job number (assigned at award), stage (lead, bidding, awarded, active, closeout, warranty, closed, lost, no-bid), developer, architect, GC (once awarded), site address, county, product type (garden, wrap, podium, mid-rise, senior, student), public or private, unit count, lead source, financing type, estimated start and finish, PM, estimator |
| project_compliance | Legal and insurance settings for a project | bond project, surety, bond number, insurance program (standard, OCIP, CCIP), prevailing wage type (none, Davis-Bacon, state, both; none today), tax treatment, Notice of Commencement date and record number |
| building | A building on the site | project, name, floors, sequence |
| floor | A level in a building | building, level |
| unit_type | A floor plan | project, code, beds, baths, base unit type, variant (standard, mirrored, ADA) |
| unit | A physical unit or amenity space | project, building, floor, number, unit type, kind (dwelling, amenity, common), current status (derived from milestones) |
| area | A room within a unit type | unit type, room (kitchen, bath 1, bath 2, laundry, bar) |
| scope_version | A version of the takeoff | project, number, kind (estimate, contract, revision), bids (one or more) or change order it came from, planned count per unit type, status (draft, active, superseded) |
| scope_line | One line of the takeoff | scope version, unit type, area, item, quantity, unit of measure. For tops: SF, edge LF, splash LF, cutouts. |
| countertop_design_piece | One countertop piece as drawn on the approved shop drawings for a unit type | unit type, area, label (K1, K2, V1), revision, quantity per unit, planned source (precut, custom from slab, custom from blank), seams with (the pieces it joins), material, thickness, length, width, SF, edge LF and profile, splash LF and height, cutouts (sink model, cooktop, faucet holes), shop drawing and DXF, shop work needed after receipt (precut only, usually none), submittal, status (draft, submitted, approved, superseded), superseded by, precut item (created when ordered precut) |
| finish_selection | An approved finish choice | project, category (door style, cabinet finish, hardware, top material, thickness, edge, sink), value or item, applies to (all, a unit type, an area), submittal |
| release | A group of units released to procurement and production | project, name, units, need-on-site date, sourcing default per division (cabinets; tops, which otherwise follow the design pieces), status (planned, released, procured, in production, delivered, complete). Planned releases already drive demand for long-lead items such as precut tops. |
| unit_scope_line | Scope exploded per physical unit at release | unit, scope line, item, quantity, sourcing (cabinets: import RTA, domestic, make; tops: derived from its countertop pieces as precut, custom from slab, custom from blank, or mixed), override reason, status, links to reservation, PO line, work order, countertop pieces, delivery line, install order line |
| milestone_type | Steps every unit passes through | name (cabinets delivered, cabinets installed, top templated, top ready, top installed, hardware set, punched, accepted), sequence, division, applies to (all units, units with custom-cut tops, units with precut tops) |
| unit_milestone | The unit status board | unit, milestone type, planned date, actual date, completed by (crew or sub), source document |

`top templated` applies only to units with at least one custom-cut piece. `top ready` means fabricated and QC passed for custom pieces, and received (plus any shop prep) for precut pieces. Each unit's milestones come from its top sources, so the board never waits on a step that won't happen.

### 5.4 Estimating and bidding

A single project often has bids out to several GCs. Each bid is its own record; the project is shared. One scope version can be priced as several estimates, one per bid.

| Entity | What it is | Key fields |
|---|---|---|
| bid | Our bid to one GC on one project | project, GC, invited date, due date and time, status (invited, declined, in progress, submitted, won, lost), amount, probability, winning competitor, lost reason |
| bid_document | Plans, specs and addenda received | bid, attachment, document type, revision, date |
| estimate | A priced version of a bid | bid, scope version, version number, status, totals, cost basis snapshot (see below) |
| estimate_line | A cost and price line | estimate, cost group (cabinet material, cabinet install, top material, top template, top fabrication, top install, freight, duty, bond, general conditions), assumed source (cabinets: import RTA, domestic, make; tops: precut, custom from slab, custom from blank), cost code, quantity, unit cost, markup, price, computed or manual |
| estimate_alternate | Add, deduct or value-engineering options | estimate, description, price change, accepted |
| clarification | Inclusions, exclusions and qualifications | library text (for example "blocking by others", or for precut tops "walls and cabinets built to plan within tolerance"), and which ones each estimate uses |

The cost basis snapshot makes an estimate reproducible. It holds item costs, labor rates, freight per container, the duty rates assumed, and a top cost basis for each source:

- **Precut:** per SF by price group plus cutout charges until shop drawings exist, then price per piece; landed-cost factor; breakage allowance. No yield, template or fabrication cost.
- **Custom from slab:** slab cost per SF and expected yield %.
- **Custom from blank:** landed cost per blank and expected yield %.
- **Custom (both):** fabrication labor per SF, per edge LF and per cutout, plus template cost per area. Yield uses the same definition as `nest`, net of usable remnants.
- **Prevailing wage bids only:** the wage determination and modification used to price labor.

### 5.5 Contract, changes and submittals

| Entity | What it is | Key fields |
|---|---|---|
| contract | Our agreement with the GC or owner | project, customer, type (subcontract, purchase order, owner direct), number, executed date, original value, retainage rule (for example 10% until 50% complete, then 5%), payment terms, billing format, insurance requirements, waiver requirements, stored materials terms (below), warranty term, backcharge terms, status |
| sov_line | Schedule of values line for pay apps | contract, line number, description (for example "Bldg 1 cabinets material"), division, scheduled value, retainage %, stored materials (inherits the contract's value and can only narrow it; defaults to not allowed on install lines), linked building or release and cost group, milestone type that drives the suggested % (defaults by cost group: cabinet lines use `cabinets installed`, top lines `top installed`) |
| change_event | Anything that might change cost or price | project, source (GC directive, RFI, owner upgrade, field condition, shop drawing revision after a precut order, our error), status (potential, priced, submitted, approved, rejected), estimated cost and price |
| change_order | An executed change | contract, our number, GC's number, amount, schedule days, executed date; lines with SOV line, price, and budget change by cost code |
| tm_ticket | Time and materials work signed in the field | project, date, labor hours, materials, signed by, change event |
| backcharge | A charge between parties | direction (GC to us, us to sub or vendor), project, party, source (remake, punch item, service ticket, damage report, GC backcharge passed through), passes through (the GC backcharge this one recovers), reason, amount, photos, status, applications (pay app deduction, sub pay app deduction, credit memo, bill credit, retainage at final; partial allowed), remaining amount |
| submittal | Shop drawings, samples, product data | project, type, spec section, revision, status (draft, submitted, approved, approved as noted, revise and resubmit, rejected), dates, reviewer, finish selections and countertop design pieces it covers |
| rfi | A question to the design team | project, question, answer, dates, change event if it costs money |

**Stored materials are a contract term, not a customer default.** One GC can allow them on one job and not the next. The contract's stored materials terms are:

- allowed: not allowed, on site only, or on and off site
- approved off-site storage locations (our own warehouse counts only if it is listed)
- required backup: bill of sale, insurance certificate naming owner and GC, photos, inventory listing, vendor invoices
- whether GC or architect approval is needed before billing
- valuation basis: landed cost backed by invoices, or scheduled value
- retainage on stored materials, if different from the work retainage
- any cap

**Precut orders wait for final drawings.** A precut PO can be issued only against design pieces whose submittal is approved. "Approved as noted" isn't enough until a new design piece revision includes the notes, because an overseas cut can't be undone. If a shop drawing revision arrives after the precut order is placed, the system raises a change event.

### 5.6 Catalog and items

| Entity | What it is | Key fields |
|---|---|---|
| item | Anything we buy, make, stock or sell | SKU, description, type (inventory, non-inventory, labor, service), category (base, wall, tall, vanity, filler, panel, molding, RTA carton, slab, blank, precut top, sink, hardware, sheet goods, consumable), unit of measure, tracking (none, lot, serial), costing method, division, default accounts |
| cabinet_spec | Cabinet attributes for matching and estimating | item, line or series, door style, finish, construction, width, height, depth, nomenclature (B18, W3030, VSB30), hinge side, finished ends |
| countertop_material | Stone attributes for slab, blank and precut top items | item, brand, color, price group, thickness (2cm, 3cm), finish, nominal size (slabs and blanks) |
| item_vendor | A way to buy an item | item, vendor, vendor SKU, price, currency, minimum order, lead time, carton count, CBM, weight, country of origin, HTS code, effective dates, preferred |
| bom | How an item is made or assembled | parent item, revision, type (RTA assembly, manufacture); components with item, quantity and scrap % |
| routing | Shop steps to make an item | parent item, operations with work center and standard minutes |
| work_center | A shop resource | name (RTA assembly, saw, CNC, edge polisher, cabinet bench, QC), division, labor rate, overhead rate, hours per day |
| item_alternate | Approved substitutes | item, alternate, reason (domestic equivalent of an import SKU; a slab or blank color equivalent to a precut top), approved for (all, a developer, a project) |
| uom_conversion | Unit conversions | item, from (carton, slab, blank, crate, sheet), to, factor |

An assembled cabinet item can have both a BOM (RTA cartons plus hardware) and an `item_vendor` row (buy it assembled domestically). That is how cabinet sourcing becomes a choice per release.

One stone color can exist as a slab item, a blank item, and a precut top item for each design piece. A precut top item is created from an approved design piece, one item per design piece revision, so in practice it is project-specific. `item_alternate` records which slab or blank colors are approved equivalents, so a precut piece can be remade custom only in an approved color. An approved color is not a guaranteed shade match at a seam (see `remake`).

### 5.7 Purchasing and import logistics

| Entity | What it is | Key fields |
|---|---|---|
| material_requirement | Computed demand | item, quantity, need date, project, release, available, reserved, on order, shortfall. Computed from released units, and from planned releases for long-lead items, so precut tops can be ordered as soon as their design pieces are approved. |
| purchase_order | An order to a vendor | vendor, type (import, domestic, hardware, other), project (cabinet and precut POs are project-specific; blank and slab POs can be for stock), ship-to (warehouse or site), currency, incoterms, terms (for example 30% deposit, balance against bill of lading), status, approval |
| po_line | One line of a PO | item, quantity, price, need date, project, unit type and design piece (precut), release (optional; can be assigned later), cost code, received quantity, billed quantity |
| vendor_deposit | Prepayment on an import PO | PO, amount, paid date, payment, amount applied to bills |
| shipment | A container or truckload | mode (ocean FCL, LCL, truck, LTL), carrier, container number, bill of lading, origin port, ETD, ETA port, ETA warehouse, last free day, customs broker, status (booked, sailed, arrived, released, delivered, empty returned) |
| shipment_line | What's in the shipment | shipment, PO line, quantity, cartons or crates, CBM, weight |
| customs_entry | The customs filing | shipment, entry number, entry date, broker, entered value, liquidation date; lines with the shipment lines covered, HTS code, value, one or more duty programs (normal duty, Section 301, Section 232, antidumping or countervailing case and rate), how classification and duty-order scope were determined, plus MPF and HMF fees |
| landed_cost_charge | A cost to spread over a shipment | shipment, type (ocean freight, duty, AD/CVD deposit, MPF, HMF, brokerage, drayage, inland freight, demurrage, detention), vendor bill, estimated or actual, amount, capitalize (yes for freight, duty, fees, brokerage and drayage; no for demurrage and detention), applies to (the whole shipment, or specific customs entry lines), allocation basis (value, CBM, weight, quantity) |
| receipt | Goods received | PO or shipment, location, date, received by; lines with PO line, quantity good, quantity damaged, lot (blanks, precut tops, carton lots) or serial (slabs), landed unit cost |
| vendor_claim | Damage, shortage or return claim | vendor or carrier, receipt, lines, photos, amount, status, credit received |

Precut tops and blanks follow the same import path as RTA cartons: deposit, shipment, customs entry, landed cost. Domestic slabs come in on domestic POs, with bundle and serial captured at receipt.

**Duty.** Several duty programs can apply to the same imported line, and that is true of quartz and stone as well as cabinets. Rates change by proclamation, USTR notice or Commerce review. So duty rates are data with effective dates, never hard-coded, and estimates snapshot the rates they assumed. One container can mix cabinets and tops, so duty assessed on specific entry lines lands only on the goods on those lines. Freight, drayage and brokerage spread across the whole shipment. Classification and duty-order scope are the importer of record's responsibility: the broker files and advises, and Commerce decides scope questions. The model records the result and how it was reached.

**Landed cost.** Landed cost is allocated at receipt, using estimates for bills that haven't arrived. When the actual bills come in, the difference goes to inventory if the goods are still on hand. Otherwise it goes to job cost or a landed cost variance account that is reviewed monthly. Demurrage and detention are not capitalized: they are expensed, or charged to the job that caused the delay. Confirm with your CPA.

### 5.8 Inventory and warehouse

| Entity | What it is | Key fields |
|---|---|---|
| location | A place stock can be | warehouse, zone, bin, type (warehouse, staging, shop, truck, in transit, jobsite, approved off-site storage), project (for a bin set aside for one job) |
| lot | A batch of identical stock: blank crates, precut tops, carton lots | item, lot number, receipt line, customs entry line, shade, landed unit cost, quantity received, status (available, re-inspect, obsolete) |
| serial | A uniquely tracked piece: slabs, and remnants worth keeping | item, bundle, length, width, usable area, thickness, cost, photo, status (available, reserved, cut, remnant, scrap), parent (slab serial, blank lot or precut lot), location |
| inventory_txn | The stock ledger | item, serial, lot, location, quantity (+/−), unit cost, type (receipt, transfer, issue to work order, work order output, issue to job, return from job, adjustment, count, scrap), source document, project, unit |
| cost_layer | Costing for FIFO or average cost | item, location, receipt, quantity remaining, unit cost |
| reservation | Stock held for a job | item, serial or lot, quantity, project, release, units, status (reserved, billed as stored, released, consumed), locked by (the stored materials claim backing it) |
| inventory_count | A cycle or full count | location, date, lines with counted and system quantities, adjustment posted |

On-hand, available, reserved and billed-as-stored are views over `inventory_txn` and `reservation`, not stored numbers.

How stone is tracked:

- **Slabs** are serialized, because each one is unique and gets nested on its own.
- **Blanks** are lot-tracked by default, because they're uniform and many come in each crate. The `lot` keeps shade, landed cost and customs entry together. A blank item can switch to serial tracking through `item.tracking` with no structural change.
- **Precut tops** are lot-tracked items, one per design piece revision. They're interchangeable among units of that type until delivered. A piece returned from a job goes into a re-inspect lot before it can be used again. Stock of a superseded revision shows as obsolete.
- **Remnants** are serials whose parent is a slab serial, a blank lot or a precut lot.

**Stored stock is locked.** A reservation that backs a stored-materials claim is locked. Moving that stock to another project or scrapping it needs approval and a reason, and the stock drops off the next pay app. Issuing it to a work order is allowed: the reservation and the claim pass to the work order and then to its output (see 5.11).

### 5.9 Production

Four flows share one work order structure:

- **RTA assembly.** A batch per release (for example 200 × B18). Consumes cartons and hardware, outputs assembled cabinets. Where RTA cabinets are assembled (warehouse, or on site by the installer) is a per-release choice, and the data supports both.
- **In-house cabinets.** A small number of work orders with a BOM and routing.
- **Custom tops (domestic slab or imported blank).** Pieces are created at release from the design pieces. The field template, taken after cabinets are installed, updates their dimensions. Then they are nested on a slab, blank or remnant, cut, fabricated and QC'd.
- **Precut tops.** No template, nest or fabrication. A work order exists only if the design piece lists shop work (for example faucet holes). It issues the precut item, records the work, and returns it to stock at the higher value. Otherwise pieces go straight from receipt to delivery.

| Entity | What it is | Key fields |
|---|---|---|
| work_order | A production job | type (RTA assembly, manufacture, custom top, precut prep), item and quantity, or units for tops, project, release, due date, status (planned, released, in progress, complete, closed), BOM and routing snapshot |
| wo_material | Components planned and issued | work order, item, serial or lot, planned quantity, issued quantity |
| wo_operation | Steps planned and done | work order, work center, sequence, standard minutes, actual minutes, status |
| field_measure | A countertop template, or an optional cabinet check before precut delivery | purpose (template for custom pieces, cabinet check for precut), units, area, method (digital template, laser, tape), scheduled date (only after `cabinets installed`), actual date, templater, DXF files, result (actual piece dimensions, or pass/fail with deviations from the drawing), issues found (cabinets out of level) |
| countertop_piece | One piece of stone for one unit | unit, area, design piece (optional, for one-offs such as an amenity kitchen), label (K1, K2, V1), source (precut, custom from slab, custom from blank) and override reason, material, thickness, length, width, SF, edge LF and profile, splash LF and height, cutouts, seams, DXF, field measure (custom only), variance from design, precut item and lot (precut) or nest (custom), work order, actual cost, fit result (precut: as-is, field-adjusted, did not fit), status (planned, ordered, received, templated, nested, cut, fabricated, QC passed, loaded, delivered, installed, rejected, void) |
| nest | Pieces laid out on a slab, blank or remnant | material (slab serial, remnant serial, or blank item, lot and number of blanks), pieces, yield % (piece SF ÷ (material SF − usable remnant SF)), remnant serials created, file |
| remake | A piece or seamed group that had to be made again | scope (one piece, or the seamed group), original pieces, reason (mis-measure, fab error, install damage, material defect, change, precut did not fit, supplier cut error, transit damage), responsible (us, another trade, vendor), replacement source, replacement pieces, shade match accepted by (GC or architect, when only one piece of a seamed group is remade from different material), original piece disposition (back to stock, reused on site in another unit, kept as a remnant, scrapped, vendor claim), cost, backcharge, vendor claim |
| quality_check | An inspection | work order, piece, or receipt line (precut tops and blanks checked on arrival against the drawing for size, cutouts, chips and shade), checklist, result, photos, inspector |

**How a remake works.** A remake creates new replacement pieces for the unit. The originals keep their source and go to status `rejected`.

- **Seams decide the scope.** If the replacement's material or lot differs from a piece it seams to, the whole seamed group is remade from one material, unless the GC or architect accepts the match.
- **Precut pieces usually come back custom.** A precut piece that doesn't fit is normally remade from a blank or slab, which requires a template of the area.
- **What happens to the originals:**
  - **Back to stock:** the pieces are trucked to the warehouse, into a re-inspect lot.
  - **Reused on site:** a piece goes straight to another unit of the same type, where it replaces that unit's planned piece, which is voided.

### 5.10 Field: delivery, install, punch and service

| Entity | What it is | Key fields |
|---|---|---|
| delivery | A trip to the jobsite | project, release, scheduled window, truck and driver or carrier (or a sub, when the sub hauls), status (scheduled, loaded, delivered, partial), signed by (GC superintendent), photos; lines with item, lot or serial, unit scope line and quantity |
| crew | An install team | name, type (internal, subcontractor), foreman, members or sub, division |
| install_order | Work assigned to a crew or sub | project, scope (cabinet install, RTA assembly on site, top install, hardware, punch, go-back, service), crew or sub, subcontract (when assigned to a sub), scheduled date, status; lines with unit, areas, status, completed date, verified by (our superintendent), completed by. Verifying a line sets the unit milestone. A unit and scope can be on only one open install order line. |
| subcontract | Our agreement with an install sub | sub, type (master agreement, project), master agreement (a project subcontract copies its lines, which can then change), project, buildings or releases covered, retainage rule, retainage release trigger, payment terms, insurance requirements, committed value (sum of its lines), status |
| subcontract_line | One priced line of a subcontract: a rate or a lump sum | subcontract, line number, scope (cabinet install, RTA assembly on site, top install, hardware, punch, go-back, service, haul, extra work), basis (per unit, per cabinet box, per LF, per countertop SF, per hour, per trip, lump sum), applies to (all, a unit type, amenity or common units, an item category, or a building or release for lump sums), LF measured on (box widths, or LF scope lines), milestone type (drives the suggested % on lump sums), rate or scheduled value, estimated quantity (from the spine; entered by hand for hourly and trip lines), committed amount, retainage override, cost code, change event, effective dates |
| sub_pay_app | A sub's pay request, drafted from verified completed work | sub, subcontract, period, type (progress, retainage release, final), sub's invoice number, status (draft, sent to sub, accepted, disputed, approved, billed, void); lines with subcontract line, source record, unit, quantity (counted from the spine; a manual change needs a reason), rate, amount, retainage; lump-sum lines carry previous %, this period %, to-date % and a suggested %; backcharges deducted; net. Approval creates the vendor bill. |
| time_entry | Hours or piece work by an employee, or hours a sub submits for hourly work | worker kind (employee, sub), employee or sub and worker name, date, regular and OT hours (required on piece work too), pay type (hourly, piece), quantity and piece rate, project, cost code, unit or install order line, or work order and operation, work classification (blank unless the project is prevailing wage), T&M ticket, status (submitted, approved, paid), approved by. Sub entries get no burden and post nothing; they only supply hours to the sub pay app. |
| daily_log | Field report | project, date, crew, work done, units touched, delays (not ready, damaged by others), photos |
| punch_item | A defect to fix | project, unit, area, source (our pre-punch, GC, owner or architect), description, responsible (us or another trade), crew, status, photos before and after |
| service_ticket | A warranty or service call after turnover | project, unit, reported by (property manager), issue, covered by warranty or billable, visits, cost, status |

A precut piece is delivered only after the unit's `cabinets installed` milestone. Whether a cabinet check is used, and whether a failed one blocks delivery, is open question 2. A custom piece is delivered only after QC passes.

**Paying subs.** Each pay app line points to exactly one source record, and the quantity comes from the spine:

| Basis | Pay event (source record) | Quantity measured from |
|---|---|---|
| Per unit (flat or by unit type) | Install order line | 1, with the rate looked up by the unit's unit type |
| Per cabinet box | Install order line | That unit's unit scope lines in the line's areas, item category base, wall, tall or vanity |
| Per LF | Install order line | Box widths from cabinet_spec, or LF scope lines (molding, splash) |
| Per countertop SF | Install order line (top install) | SF of that unit's installed countertop pieces in the line's areas, any source |
| Per trip | A delivery the sub hauled, or a go-back install order | 1 |
| Per hour | Approved sub time entry | Hours |
| Lump sum per building | The subcontract line itself | % complete, suggested from units in the building with the line's milestone done |

Rules:

1. A unit and scope are on only one open install order line.
2. Each measured source record (install order line, hauled delivery or go-back, approved sub time entry) is paid once per subcontract, scope and measure (units, boxes, LF, SF, trips, hours), whichever line prices it. So a box line and a molding-LF line can both pay the same install order line, but two box lines never can. A rate change closes the old line, and the new rate applies to work completed from its effective date. A second completed line for a unit and scope that was already paid is a go-back or a backcharge, not a second full payment. If the unit's scope changes later, only the difference is proposed, tagged with the change event.
3. A unit and scope can't be covered by both a lump sum and a unit rate. Several unit-rate lines can cover the same unit and scope if they measure different things (boxes and molding LF, or top SF and splash LF). Hourly and trip lines are only for work outside the measured scope.
4. A lump sum is paid by % to date and can't pass 100%.

Retainage follows the subcontract's rule line by line. Backcharges are deducted after retainage and can be taken from retainage at final. A mixed subcontract might pay per box for cabinets, per SF for tops, per trip for go-backs, per hour for extra work, and a lump sum for the clubhouse.

### 5.11 Finance

#### General ledger

| Entity | What it is | Key fields |
|---|---|---|
| account | Chart of accounts | number, name, type (asset, liability, equity, revenue, cost of revenue, expense), subtype (bank, AR, AR retainage, inventory, inventory in transit, production WIP, contract asset, contract liability, vendor deposits, vendor claims receivable, GRNI, AP, AP retainage, accrued subcontract cost, landed cost clearing, labor clearing, payroll liabilities, use tax payable, accumulated depreciation, purchase price variance, landed cost variance, duty variance, FX gain/loss), active |
| cost_code | Job cost category | code, name, category (material, labor, subcontract, equipment, freight and duty, backcharges, other), division |
| division, department | Reporting dimensions | name |
| fiscal_period | Accounting periods | year, period, start, end, status per module (open, soft close, closed) |
| journal_entry | A posted entry | date, period, source (manual, AR, AP, payment, receipt, inventory, payroll, WIP, accrual, depreciation), source document, memo, status (draft, posted, reversed), reverses, auto-reverse date |
| journal_line | One debit or credit | entry, account, debit, credit, project, cost code, division, location, department, party, memo |
| posting_rule | How each document posts | document type, line type, debit account, credit account, dimension mapping |
| gl_budget | Company budget by account | account, period, amount, version |

#### Accounts receivable

| Entity | What it is | Key fields |
|---|---|---|
| pay_application | Monthly progress billing | contract, number, period to, status (pencil draft, submitted, approved, revised, paid), submitted date, approved amount, portal reference, stored materials backup (checked against the contract's list), stored materials approval (by whom and when, where required) |
| pay_app_line | One SOV line on a pay app (AIA G703 columns) | pay application, SOV line, previously completed, completed this period, materials stored (sum of its stored material lines, never typed), total completed and stored, % complete, retainage this period and to date, balance to finish, suggested % from unit milestones |
| stored_material_line | One item claimed as stored materials on a pay app line | pay app line, source (reservation, work order, or delivery line with a signed POD), item, serial or lot, quantity, location, units it's for, valuation basis and value, previous line (same stock on the last pay app), status (claimed, GC approved, GC rejected), photos |
| ar_invoice | An invoice | customer, project, contract, type (progress, retainage release, T&M, service, other), date, due date, amount, retainage, tax, status; lines with revenue account and dimensions (a retainage release invoice carries no revenue) |
| customer_payment | Money received | customer, date, method (check, ACH, joint check), reference, amount; applications to invoices, including retainage |
| credit_memo | A credit to a customer | customer, invoice, reason (backcharge, price change), amount |
| lien_waiver_out | Waivers we give the GC | pay application or payment, type (conditional, unconditional), progress or final, amount, through date, status, signed document |
| notice | Ohio lien notices (R.C. Chapter 1311) | project, type (Notice of Commencement received, Notice of Furnishing served, lien affidavit, and public-project notices), party served, first furnished date, last work date, date served, method, proof, deadline (computed per notice type and project type: the Notice of Furnishing runs from first furnishing, the lien affidavit from last work; the periods are data, confirmed with counsel) |

**Stored materials on a pay app.** The system offers only what the contract allows and what is actually held for the project on the period-to date:

- **Off site** (only on contracts that allow on and off site): received stock reserved to the project, in a location the contract approves. Our warehouse counts only if the contract lists it. Lot-tracked stock (blanks, carton lots, precut lots) must first be moved to a bin set aside for the project, so the bill of sale names real goods.
- **In production:** issuing stored stock to a work order passes the reservation and the claim to the work order and then to its output. The claim follows RTA cartons into assembled cabinets, and slabs or blanks into pieces. Remnants either stay reserved to the project or leave the claim.
- **On site:** delivered lines with a signed POD, for units that don't yet have the install milestone for that stock's division (`cabinets installed` for cabinet stock, `top installed` for countertop stock). The stock must still be at the jobsite. A line drops out once its stock is returned from the job, or its countertop piece is rejected or void. A rejected piece reused in another unit moves its listing to that unit.

Goods in transit and vendor deposits don't count. The stock must match the SOV line's building or release and cost group. Precut tops, blanks and slabs qualify under the same rules as cabinets.

The listing is rebuilt for each pay app and frozen on submission. When the unit's install milestone for that division is set, its materials leave stored and show up in completed, so nothing is billed twice. If completed is typed above the milestone suggestion while those units' stock is still listed as stored, submission is blocked until those units' stored lines are removed. Completed plus stored can't exceed the scheduled value. Where the contract or SOV line doesn't allow stored materials, the column stays at zero. A pay app with stored lines can't be submitted until the backup the contract requires is attached and our insurance certificate is current.

#### Accounts payable

| Entity | What it is | Key fields |
|---|---|---|
| vendor_bill | A vendor or sub invoice | vendor, invoice number, date, due date, PO or sub pay app, project, retainage withheld, status (draft, pending approval, approved, on hold, partly paid, paid), hold reasons; lines with item or account, PO line, quantity, amount, project, cost code, division, use tax |
| bill_match | Matching a bill to what was ordered and received | PO line, receipt line or (imports billed against the bill of lading) shipment line, bill line, price variance, quantity variance. For imports, the receipt later confirms quantity and damage. |
| vendor_payment | Money paid | vendor, date, method (ACH, check, wire, card), bank account, reference, amount, batch, joint check co-payee; applications to bills and deposits |
| payment_batch | An ACH or check run | status, total, approvals, NACHA file |
| vendor_bank_account | Vendor bank details, change-controlled | vendor, routing, account (encrypted), status (pending, approved), changed by, approved by, call-back verified |
| lien_waiver_in | Waivers our subs and suppliers sign | as in the lien waiver app: vendor, project, payment, type, amount, through date, status, PDFs |
| compliance_document | Insurance and paperwork, from a party or provided by us | party, direction (received, provided by us), type (general liability, auto, umbrella, workers' comp certificate, property or installation floater, W-9, signed subcontract, safety program), project (if specific), effective, expires, limits, additional insured |
| payment_hold | Why a vendor or bill can't be paid | party or bill, reason (waiver overdue, COI expired, certified payroll missing, dispute, backcharge), set by, set at, released by, released at |

Today's lien waiver app maps directly onto this: its Vendor, Project, Payment, Waiver and Event become `party`/`vendor_profile`, `project`, `vendor_payment`, `lien_waiver_in` and `event`. The ACH plan's bank-detail and batch approvals become `vendor_bank_account`, `payment_batch` and `approval`.

#### Job cost and WIP

| Entity | What it is | Key fields |
|---|---|---|
| job_budget | Budget per project and cost code | project, cost code, original (from the winning estimate), approved changes (from change orders), revised, cost to complete (forecast), forecast at completion, version |
| commitment | Costs we've agreed to but not yet billed (view) | open PO lines (precut POs are large early commitments) and subcontract lines (lump sums, plus rate × estimated quantity) by project and cost code: committed, invoiced, earned not billed (what a draft sub pay app would propose at period end, on every basis), remaining |
| job_cost | Actual cost (view) | journal lines with a project and cost code: material issued, labor, subs, freight and duty, equipment |
| labor_burden_rate | Loaded cost of an hour | employee class, period, payroll tax %, Ohio BWC %, benefits %; applied to employee time entries |
| wip_snapshot | Frozen month-end WIP schedule per project | period, contract value with approved changes, estimated total cost, cost to date, % complete (cost-to-cost), earned revenue, billed to date, stored materials billed (off site and on site), inventory held against stored billing, over or under billing (in total and excluding stored materials), gross profit, change from last month (fade) |

**Billing stored materials doesn't change cost to date.** Stock off site is still our inventory, so % complete doesn't move. The billing shows as overbilling until the stock is delivered to site, which is when its cost hits the job.

Example: a $480,000 contract for 48 units, with $360,000 estimated cost, of which $300,000 is landed material.

| | Pay app 1 | Next month (24 units delivered and installed) |
|---|---|---|
| Billed as stored, off site | $300,000 (all the cabinets, at landed cost) | $150,000 |
| Billed as completed | $0 | $240,000 |
| Cost to date | $0 | $180,000 (50% of estimated cost) |
| Earned revenue | $0 | $240,000 |
| Overbilling | $300,000 | $150,000, exactly the stored balance |

Material delivered to site is already in cost to date, so billing it as on-site stored doesn't create an overbilling. If it is billed at cost, the job shows an underbilling equal to the margin on that material. Whether that margin can be recognized before install is open question 6.

#### Payroll (provider-run, ERP-owned data)

| Entity | What it is | Key fields |
|---|---|---|
| employee | A W-2 worker | party, employee number, class (installer, fabricator, assembler, templater, driver, office), crew, hire date, termination date |
| pay_rate | Pay over time | employee, effective date, type (hourly, salary, piece schedule), rate |
| payroll_run | Imported from the payroll provider | period, check date, provider reference; lines with employee, gross, employee taxes, deductions, net, employer taxes |
| wage_determination **(later)** | Wage rates for a prevailing wage project | project, source (federal Davis-Bacon, Ohio), decision or schedule number, modification number, construction type, county, lock-in date, attachment; lines with classification, base hourly rate, fringe hourly rate, effective date, our employee classes that default to it |
| certified_payroll **(later)** | Weekly certified payroll for a prevailing wage project, from us or from a sub | project, week ending, submitted by (us or a sub), subcontract, payroll number, status (due, received, reviewed, deficient, submitted to GC), no work this week, statement of compliance signed, hours and gross by classification, attachment, reviewed by, submitted to GC date |

**Prevailing wage (none today).**

- **Built now, at almost no cost:** the `project_compliance` switch, a work classification on `time_entry` (blank on ordinary jobs), and the `certified payroll missing` hold reason. Classification sits on each time entry, not just the employee, because one worker can work two classifications in one week. That is the one field that would be costly to add later.
- **Built when the first prevailing wage bid arrives:**
  - `wage_determination`, because the estimate needs its rates to price labor. Its class mapping then fills in the classification on time entries.
  - The `certified_payroll` workflow. On such a job, each party that worked in a given week (us and every install sub) owes a certified payroll for that week. A missing one sets a payment hold on that sub.
- **Deferred to the first job, decided with counsel and the payroll provider:** apprentice ratios, fringe crediting, missing classifications, generating and submitting the report, and whether shop, warehouse and driver work is covered. Each of these adds fields; none restructures anything.

Prevailing wage adds no GL postings. Rate and fringe differences flow through payroll.

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

1. **Bid.** Estimating builds the B1 and B1-M scope lines: base and wall cabinets, a vanity, a 42 SF quartz kitchen top in two pieces with one undermount sink cutout, and a vanity top. No shop drawings exist yet. The kitchen top is priced as precut: per SF by price group plus cutout charges, the landed-cost factor and the duty rates assumed. The vanity top is priced as custom from an imported blank: blank landed cost over expected yield, plus template and fabrication labor. Scope v2 is priced as three estimates, one for each GC's bid.
2. **Award.** One GC wins the project and awards it to us. Scope v2 becomes the contract baseline. SOV lines are set per building and division, and the job budget by cost code comes from the estimate. The contract allows stored materials on and off site, lists our warehouse as approved storage, and requires a bill of sale, photos and an inventory listing. The countertop shop drawings go out as a submittal. On approval they become design pieces K1 and K2 (seamed together, planned precut) and V1 (custom from blank), for B1 and for B1-M separately.
3. **Release.** As soon as K1 and K2 are approved, Building 2's planned release creates precut demand. The GC's look-ahead then puts cabinets on Building 2, floors 1 to 3, starting March 1. Release R-2.1 explodes the scope into `unit_scope_line`s and countertop pieces for 48 units and computes the cabinet material requirement.
4. **Buy.** Two import POs go out, each with a 30% deposit:
   - precut tops: one item per design piece; quantity = the B1-M units in the release plus spares
   - RTA cartons

   Each supplier bills the balance against the bill of lading, and the goods are carried as inventory in transit while the containers are at sea. The customs entries give the cabinet lines and the quartz lines their own duty programs. At receipt, duty lands on the goods it was assessed on, while freight, brokerage and drayage spread across the container. Inventory is valued at landed cost and reserved to the project. Blanks arrive on a separate import PO into stock.
5. **Assemble.** An RTA assembly work order turns cartons and hardware into assembled cabinets. Shop time entries carry the labor.
6. **Deliver.** Floor 2's cabinet kit ships, and the superintendent signs the POD. Inventory is issued to the job, and the cost lands on the project. Tops ship separately later.
7. **Install cabinets.** An install order for floor 2 goes to a sub, one line per unit. When our superintendent verifies 2-204's line, the `cabinets installed` milestone is set. The month's draft sub pay app counts 2-204's boxes from its unit scope lines at the sub's per-box rate. Retainage is withheld, a backcharge for a damaged door is deducted, and approval creates the bill. The lien waiver and COI checks gate the payment.
8. **Tops.**
   - **Kitchen, precut.** No template is needed, so precut K1 and K2 are delivered. At dry fit, K2 misses an out-of-square wall.
   - **Remake.** K1 and K2 meet at a seam, so the remake covers both, from one domestic slab, to keep the seam matched. The kitchen is templated. The replacement K1 and K2 are nested on slab S-1043 (81% yield net of remnant S-1043-R1), fabricated and installed.
   - **What happens to the precut pieces.** They're undamaged, so they go back to the warehouse into a re-inspect lot, and later replace another B1-M unit's pieces.
   - **Vanity, custom.** V1 is templated, nested on one blank from lot B-0312, fabricated, QC'd and installed.
   - **Done.** `top installed` is set when every piece is in. The tops installer's pay line counts the SF of the installed pieces.
9. **Bill.** On the pay app, the "Bldg 2 cabinets" line suggests its % complete from units with `cabinets installed`. Floor 3's cabinets are in the warehouse, received, reserved and set aside in a project bin, so the system offers them as stored materials. Their reservations lock, and the inventory listing and bill of sale print from the stored lines. Units installed this month leave the stored listing and count as completed instead. On a contract that didn't allow stored materials, the column would stay at zero. The GC approves and the AR invoice posts with retainage. When payment arrives, our waiver goes to the GC.
10. **Close the month.** Job cost is compared with budget and the forecast is updated. Completed sub work that hasn't been billed yet is accrued: install lines, hauled trips, approved hours and lump-sum progress. The WIP snapshot computes earned revenue and over or under billing, then posts the adjusting entry, which reverses next month. Floor 3's cabinets are still inventory, not job cost, so their stored billing shows as overbilling until they're delivered to site.
11. **Turnover.** The unit is punched and accepted. The retainage release is invoiced at closeout, which moves AR retainage to AR with no new revenue. The sub's retainage is released against their final waiver. Warranty tickets for 2-204 attach to the unit for the warranty term.

## 7. What posts to the GL

| Event | Debit | Credit |
|---|---|---|
| Import deposit paid | Vendor deposits | Cash |
| Import bill against the bill of lading (goods are ours once loaded, under typical FOB terms) | Inventory in transit | AP, Vendor deposits (deposit applied) |
| Import container received | Inventory | Inventory in transit |
| Domestic goods received (or imports billed after arrival) | Inventory | GRNI (goods received not invoiced) |
| Domestic bill matched | GRNI, price variance | AP, Vendor deposits (if any) |
| Freight, duty, fees and brokerage bills | Landed cost clearing | AP |
| Landed cost allocated at receipt (estimates where bills haven't arrived) | Inventory | Landed cost clearing |
| Landed cost true-up when actual bills differ from estimates | Inventory (goods still on hand), job cost: freight and duty, or landed cost variance | Landed cost clearing (reverse the sides when actual is below estimate) |
| Demurrage and detention | Expense, or job cost when a job caused the delay | AP |
| Duty adjusted when the customs entry liquidates | Job cost: freight and duty (or duty variance if it can't be traced) | AP (reverse the sides for a refund) |
| Vendor claim or bill credit | AP (or vendor claims receivable until credited) | Inventory or job cost, wherever the original cost sits |
| Components issued to a work order (cartons, slabs, blanks, precut tops for prep) | Production WIP | Inventory |
| Work order completed | Inventory (finished) | Production WIP |
| Remnant returned to stock (from a nest, or a rejected precut piece kept as a remnant) | Inventory (remnant) | Production WIP, or job cost: material |
| Delivery to site (issue to job) | Job cost: material (project, cost code) | Inventory |
| Precut piece trucked back to stock after a failed fit | Inventory | Job cost: material |
| Payroll imported | Labor clearing (office payroll straight to expense) | Cash, payroll liabilities |
| Employee time distributed, burdened (field time to jobs, work order time to production, the rest to overhead) | Job cost: labor, production WIP, or overhead | Labor clearing |
| Sub pay app approved | Job cost: subcontract | AP, AP retainage |
| Backcharge deducted on a sub pay app | AP (or AP retainage, when taken from retainage) | Job cost (the project and cost code that carried the repair) |
| Sub retainage released | AP retainage | AP |
| Month-end accrual of completed, unbilled sub work (reverses next period) | Job cost: subcontract | Accrued subcontract cost |
| Use tax on purchases | Inventory or job cost | Use tax payable |
| Pay app approved (including any stored materials) | AR, AR retainage | Contract revenue |
| GC backcharge accepted (pay app deduction, credit memo, or retainage at final) | Job cost: backcharges (or contract revenue, if it is really a price reduction; per CPA) | AR (or AR retainage, when taken from retainage) |
| Retainage release invoiced to the customer | AR | AR retainage |
| Customer payment | Cash | AR or AR retainage |
| Month-end WIP, job overbilled (reverses next period) | Contract revenue | Contract liability |
| Month-end WIP, job underbilled (reverses next period) | Contract asset | Contract revenue |
| Depreciation | Depreciation expense | Accumulated depreciation |

Notes:

- **Labor clearing.** Time not on a job or work order is distributed to overhead. Whatever remains in labor clearing after distribution is the burden variance, which is reviewed monthly.
- **WIP reversal.** The WIP entries reverse on the first day of the next period, so contract asset and contract liability always equal the latest snapshot. Posting only the month's change instead works too.
- **Sub accrual.** The accrual is what a draft sub pay app would propose at period end, on every basis: verified install order lines, hauled deliveries and go-backs, approved sub time entries, and the unbilled increase in suggested % on lump sums. It keeps cost-to-cost % complete current when subs bill late.
- **Precut tops.** They skip production WIP unless they need shop prep, and post from inventory to job cost at delivery. A rejected precut piece that goes straight to another unit on site posts nothing; only its unit link changes. A piece trucked back to the warehouse posts the return.
- **Duty liquidation.** Liquidation usually comes after the goods are installed, so the adjustment goes to job cost, not inventory. This applies to cabinets and stone alike.
- **Remnants.** A remnant is valued either at a share of the slab or blank cost by usable SF, or at zero. Pick one policy with your CPA.
- **Foreign currency.** If an import PO is in a foreign currency, bill match and payment post the realized difference to FX gain/loss.
- **Stored materials.** Billing stored materials moves no stock and posts no cost. Off-site stored stock stays in inventory, so the month-end WIP entry moves that billing to contract liability until the items are delivered to site.

## 8. Reports the structure answers

| Report | Built from |
|---|---|
| Pipeline, bid calendar, hit rate by GC | bid, project, activity |
| Backlog (contracted, not yet earned) | contract, change_order, wip_snapshot |
| WIP schedule and profit fade, with stored materials shown separately | wip_snapshot by period |
| Job cost vs budget, cost to complete | job_budget, commitment, journal_line |
| Unit status board by building and floor (only the milestones each unit's sources need) | unit_milestone |
| Container tracker (ETA, last free day, demurrage risk), with precut ETA compared to cabinets-installed dates by building | shipment, po_line, unit_milestone |
| Stone inventory (slabs, blanks, precut tops on hand by project), yield by source, remnant use | serial, lot, inventory_txn, nest |
| Countertop cost per SF by source, estimate vs actual | countertop_piece, estimate (cost basis snapshot), estimate_line |
| Precut fit rate by project, unit type and supplier, with causes | countertop_piece, remake, quality_check |
| Template backlog (units with cabinets installed and custom pieces not yet templated) | unit_milestone, countertop_piece, field_measure |
| Remake rate and cost by cause, source and responsible party | remake |
| Install productivity (units per crew day, cost per unit by crew or sub, with lump-sum, hourly and trip costs spread to units) | install_order, time_entry, sub_pay_app, subcontract_line |
| Sub work completed but not yet paid; sub retainage held | install_order, delivery, time_entry, sub_pay_app, subcontract_line |
| Margin by division and by source (cabinets: import, domestic, make; tops: precut, slab, blank) | journal_line dimensions, unit_scope_line (cabinets), countertop_piece (tops) |
| Stored materials billed vs held (off site, in production, on site, months since first billed, billed stock moved or damaged) | stored_material_line, reservation, work_order, delivery, unit_milestone |
| AR aging with retainage, expected pay dates | ar_invoice, customer_profile |
| AP aging and holds | vendor_bill, payment_hold |
| Compliance (COIs expiring, waivers outstanding, notice deadlines, certified payroll on prevailing wage jobs) | compliance_document, lien_waiver_in, notice, certified_payroll |
| Cash forecast | ar_invoice, customer_profile (typical days to pay), vendor_bill, vendor_deposit, purchase_order, shipment, payroll_run |

## 9. Build order (recommendation)

1. **Foundation, parties, project and unit matrix (including countertop design pieces), items.** Everything else depends on these.
2. **CRM and estimating.** This is the biggest gap today and carries no accounting risk. It also creates the scope data every later module reuses.
3. **Operations: purchasing and imports (cabinets, precut tops, blanks, domestic slabs), inventory, production, field (templates, install order lines, subcontract lines, employee and sub time entries with the work classification field).** INNERGY is replaced at this stage.
4. **Finance subledgers: AR pay apps with stored materials, AP with sub pay apps, job cost.** These feed NetSuite with summarized journals while both systems run in parallel. Stored materials depend on the reservations, work orders and deliveries built in step 3.
5. **GL cutover from NetSuite last,** at a fiscal year start, after at least one quarter of parallel running. Payroll processing stays with a provider for good.

Prevailing wage (`wage_determination` and the `certified_payroll` workflow) is built when the first prevailing wage bid arrives, not at award. The estimate needs the rates, and the first week of work needs certified payroll from us and from each sub.

Rationale: the GL is the riskiest and least distinctive piece, and NetSuite already does it well. Your advantage is the spine, so build that first and earn the cutover.

## 10. Assumptions and open questions

**Confirmed by you:**

- Tops come from three sources: precut imported, custom from domestic slab, custom from imported blank. Everything custom cut is templated. Precut tops are cut from drawings and never templated.
- Stored materials are billable on some contracts, not all.
- No prevailing wage jobs today, but they're possible.
- Install subs can be paid per unit, per cabinet box, per LF or SF, or lump sum per building.

**Assumptions made in this draft (change any of them):**

- One legal entity today. `company_id` is in place for later.
- Customers are mostly GCs, billed by AIA-style pay apps with retainage.
- Templates are taken in the field after cabinets are installed.
- Subs can also be paid per hour and per trip, and one subcontract can mix bases.
- Revenue is recognized over time using cost-to-cost, with a monthly WIP schedule. Confirm with your CPA and your bonding company's format.
- Material cost hits the job when it is delivered to site. Until then it is inventory reserved to the job, so it doesn't inflate % complete. This holds even when the GC has paid for it as stored materials: the billing sits in overbillings, not cost.
- Stored materials are valued at landed cost, backed by vendor invoices and landed cost charges, unless the contract says otherwise. Our warehouse is approved storage only where a contract lists it.
- Precut tops are ordered per building (planned release) against approved design pieces, not for the whole project in one order. They're interchangeable among units of the same type until delivered.
- Blanks are lot-tracked. Slabs are serialized.
- The ERP drafts each sub pay app from verified completed work. The sub accepts it, or the sub's own invoice is matched to it.
- Duty and wage rates are data with effective dates, never hard-coded.
- Ohio treats construction contractors as the consumer of the materials they install, so tax is mostly paid or accrued as use tax on purchases, with exemptions for some exempt owners. Confirm with your CPA.
- Ohio only. Ohio workers' comp is the state fund (BWC), so it is a burden rate, not an insurance policy.
- None of this is legal, tax or customs advice.

**Open questions (each one changes the data model or how it's set up):**

*Countertops*

1. Do precut suppliers pack and label pieces by unit number, or only by unit type? The draft assumes by unit type. Packing by unit would mean serializing each precut piece to its unit at receipt.
2. Will you check installed cabinets against the drawing before delivering precut tops? If yes, should a failed check block the delivery?
3. Are precut tops ordered per building as the draft assumes, or for the whole project at award?

*Billing and accounting (several are for your CPA)*

4. Does any contract let you bill materials still in transit or at the supplier, such as a container on the water or slabs held at a domestic yard?
5. Does the bill of sale pass title to the owner or GC? If so, should stock billed as stored sit in a separate inventory account?
6. For materials delivered but not yet installed, does your CPA want revenue limited to cost (the ASC 606 uninstalled-materials guidance)? If yes, the WIP snapshot needs an adjustment field.
7. Are remnants carried at a share of cost or at zero?
8. Are import POs priced in US dollars or the supplier's currency?

*Subs and payroll*

9. Do any subcontracts pay the sub only after the GC pays us (pay-when-paid)? If yes, sub pay app lines need a link to the customer payment.
10. Do sub rate cards carry across projects as master agreements, or is every project negotiated?
11. When you pay per LF, is it the sum of box widths or LF scope lines (both modeled), or the wall run measured on plan (which would add an LF field to each area)?
12. Do your own W-2 crews get piece pay on the same bases (per box, per unit, per SF)?
13. Which payroll provider do you use, and can it produce certified payroll reports?

*Company*

14. Do you ever sell material only, with no install (to other contractors, or slab and blank remnants to the public)? That adds a simple sales order flow.
15. How many warehouse and shop locations?
16. Will you need more than one legal entity, for example a separate importing company?
