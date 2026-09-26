# NetSuite Vendor ACH & Approvals — Implementation Plan

**Status:** Draft for review · **Owner:** Finance Systems · **Date:** 2026-09-26

## 1. Scope and constraints

**In scope**

1. Paying vendors by ACH, with NetSuite producing the payment file.
2. Three approval controls:
   - **Vendor bill approval**: bills go through tiered approval before they can be paid.
   - **Payment batch approval**: someone approves the ACH batch before the file is released to the bank.
   - **Vendor bank-detail change approval**: fraud control on changes to vendor banking data.

**Out of scope for this plan:** PO approval, international wires, multi-currency ACH, positive pay for checks.

**Key constraint: production-only account (no sandbox).** Every configuration step and test in NetSuite happens in the live account. The plan handles this by:

- building and testing with NetSuite's "Testing" release and deployment statuses, which only run for the owner;
- using clearly named test vendors and $0.00 prenotes;
- never uploading a file to the bank's *production* channel until the bank has certified it in its test channel;
- keeping all custom objects in an SDF project in this repo, so every change is versioned, reviewed and reversible.

> **Recommendation:** Price a NetSuite sandbox before starting. For a control that moves money, the cost of a sandbox is usually small next to the risk of configuring in production. If a sandbox isn't possible, the safeguards below are the minimum.

## 2. Decision: how ACH files leave NetSuite

| Option | What it is | Pros | Cons | Fit |
|---|---|---|---|---|
| **A. Electronic Bank Payments (EBP) SuiteApp** | Free Oracle SuiteApp. It generates NACHA (CCD/CCD+/PPD/CTX) or bank-specific files from bill payment batches. | Free and widely used. Stores vendor bank details in its own record. Has built-in batch approval routing, prenotes and rollback/reversal. | You still move the file to the bank (manual portal upload at first, SFTP later). You own bank-format maintenance. | **Recommended** |
| B. NetSuite-native payment service (Bill Pay / SuiteBanking-type offering) | A paid Oracle payment service that runs payments for you. | No file handling. Vendor enrollment and remittance are handled for you. | Per-transaction fees, vendor onboarding and dependence on a third party. Less control. | Consider if you don't want to handle files at all |
| C. Custom bank host-to-host / API | SuiteScript or middleware that pushes files straight to the bank by SFTP or API. | Fully automated with no manual upload. | Highest build, security and maintenance cost. Still needs A (or a custom file builder). | Phase 2 enhancement on top of A |

**Recommendation:** Option A (EBP), with manual portal upload at go-live. Add SFTP or host-to-host (Option C) only after 1–2 clean months.

EBP also gives us two of the three approval controls: batch approval, plus a dedicated bank-details record we can put a workflow on.

## 3. Target design

```
Vendor bank details (EBP record) ──► Bank-Detail Approval Workflow ──► Status = Approved ──► Prenote sent / cleared
                                                                                              │
Vendor Bill ──► Bill Approval (SuiteApprovals / approval routing) ──► Approved (payable) ─────┤
                                                                                              ▼
                                         EBP Bill Payment Batch (Pay Bills EFT) ──► Batch Approval Routing
                                                                                              │
                                                              Approved batch ──► NACHA file ──► Bank (portal → later SFTP)
                                                                                              │
                                                              Bank acks / returns / NOCs ──► Returns handling & bank rec
```

### 3.1 Approval design choices

| Control | Mechanism | Why |
|---|---|---|
| Vendor bill approval | **SuiteApprovals SuiteApp** (free, rule-based, multi-level). A custom SuiteFlow workflow is the fallback if the matrix gets too complex. | Configuration instead of code. Handles amount tiers, subsidiary and department rules, delegation and re-approval after edits. |
| Payment batch approval | **EBP batch approval routing** (confirm the exact setting in your installed EBP version) | Native to the payment flow: an unapproved batch cannot produce a file. |
| Bank-detail change | **Custom SuiteFlow workflow** on the EBP entity bank details record, plus a **User Event script** that enforces segregation of duties | No out-of-the-box control exists. A script is needed to block self-approval and to reset approval whenever a bank field is edited. |

### 3.2 Approval matrix (to be filled in by Controller/CFO)

| Bill amount (USD) | Approver 1 | Approver 2 | Notes |
|---|---|---|---|
| 0 – 4,999.99 | Department manager | — | |
| 5,000 – 24,999.99 | Department manager | Controller | |
| ≥ 25,000 | Controller | CFO | |
| Any payment batch | AP Manager | Controller if batch total ≥ $X | The batch creator can never approve their own batch |
| Any bank-detail change | Controller or designee | — | The approver must not be the person who made the change. Out-of-band call-back to the vendor is required. |

Tier boundaries (for example, exactly $5,000.00) are explicit test cases in §6.

## 4. Phased plan and dependencies

### Dependency graph

```
P0 Prereqs & decisions ─┬─► P1 Foundations (roles, SDF repo, CI) ─┬─► P2 Bank-detail control ──┐
                        │                                          ├─► P3 Bill approval ────────┤
                        │                                          │                            ▼
                        └─► P0b Bank onboarding (long lead) ───────┴──────────────► P4 EBP config & batch approval
                                                                                                 │
                                                                                                 ▼
                                                                          P5 E2E test + bank certification
                                                                                                 │
                                                                                                 ▼
                                                                                P6 Go-live & hypercare
```

- **P2 must finish before P4 go-live.** Vendor bank data must never be payable before the approval control exists.
- **P3 must finish before P4 go-live.** Pay Bills must only ever pick up approved bills.
- **P0b (bank) is on the critical path.** Banks typically take 2–6 weeks to set up ACH origination and certify a file. Start it on day 1.
- P2 and P3 can run in parallel.

### P0 — Prerequisites and decisions (week 1)

| # | Task | Owner | Output |
|---|---|---|---|
| 0.1 | Sign off the ACH method (§2) | CFO / Controller | Decision record |
| 0.2 | Sign off the approval matrix (§3.2), including delegates for PTO | Controller | Signed matrix |
| 0.3 | Define segregation of duties: who can create vendors, edit bank details, enter bills, approve bills, create batches, approve batches and upload files | Controller + IT | SoD matrix |
| 0.4 | Decide on a sandbox (buy it, or accept production-only with §5 safeguards) | CFO / IT | Decision |
| 0.5 | Inventory existing vendors paid by check, and collect bank details and signed ACH authorization forms through a secure channel (not email) | AP | Vendor list |

### P0b — Bank onboarding (starts week 1, runs in parallel)

| # | Task | Output |
|---|---|---|
| 0b.1 | Enable ACH origination (credits only) on the operating account | Bank agreement |
| 0b.2 | Get the NACHA spec: Company ID, Immediate Origin/Destination, ODFI routing, SEC code (CCD/CCD+), balanced or unbalanced file, cutoff times, holiday calendar | Bank file spec |
| 0b.3 | Get **test channel** access for file certification | Test credentials |
| 0b.4 | Set up bank-side controls: dual approval for file release in the portal, ACH limits, alerts | Configured portal |
| 0b.5 | Agree on the upload method: portal upload now, SFTP later | Decision |

### P1 — Foundations (week 1–2)

| # | Task | Depends on | Output |
|---|---|---|---|
| 1.1 | Enable features: Approval Routing (Vendor Bills), SuiteFlow, Server/Client SuiteScript, Custom Records, plus whatever else the EBP and SuiteApprovals install pages list | 0.4 | Features on |
| 1.2 | Create or adjust roles to match the SoD matrix (AP Clerk, AP Manager, Controller, Payment Releaser). Remove bank-detail edit rights from AP Clerk. | 0.3 | Roles |
| 1.3 | Scaffold the SDF project in this repo (`suitecloud project:create`, Account Customization Project) with Jest and `@oracle/suitecloud-unit-testing` | — | Repo structure |
| 1.4 | Add GitHub Actions CI: lint, unit tests, `suitecloud project:validate`, NACHA validator tests | 1.3 | CI green |
| 1.5 | Set up token-based auth (TBA) for SDF deploys by a named admin integration user. Store the tokens in a secret store, never in the repo. | 1.1 | Integration record + tokens |
| 1.6 | Baseline saved searches: open bills by approval status, vendors with bank details, and System Notes changes to bank details | 1.1 | Searches |

### P2 — Vendor bank-detail change control (week 2–3)

| # | Task | Depends on | Output |
|---|---|---|---|
| 2.1 | Install the EBP SuiteApp (needed for the bank-details record; its payment features stay unconfigured) | 1.1 | EBP installed |
| 2.2 | Add custom fields to the entity bank details record: `Approval Status` (Pending/Approved/Rejected), `Last Changed By`, `Approved By`, `Approved On`, `Call-back Verified` (checkbox + notes) | 2.1 | Custom fields (SDF) |
| 2.3 | **User Event script** (`beforeSubmit`): whenever a bank field (account number, routing, type) changes, force `Approval Status = Pending`, stamp `Last Changed By`, and make the record inactive or unusable for payment. Block approval if approver = `Last Changed By`. | 2.2 | `ue_bank_detail_control.js` + unit tests |
| 2.4 | **SuiteFlow workflow**: on Pending, email the approver group with an Approve/Reject button. Approval requires `Call-back Verified = T`. On approval, activate the record and trigger a prenote. | 2.3 | Workflow (SDF XML) |
| 2.5 | Scheduled or saved-search alert: daily digest of every bank-detail change, sent to the Controller | 2.2 | Alert |
| 2.6 | Deploy script and workflow in **Testing** status. Run the P2 tests. Then switch to **Released**. | 2.3–2.5 | Tests pass |

### P3 — Vendor bill approval (week 2–4, parallel with P2)

| # | Task | Depends on | Output |
|---|---|---|---|
| 3.1 | Install SuiteApprovals and configure rules from §3.2 (amount tiers, subsidiary, department, delegation) | 1.1, 0.2 | Rules |
| 3.2 | Turn on Vendor Bill approval routing so bills default to *Pending Approval* and can't be paid until approved | 3.1 | Preference set |
| 3.3 | Re-approval on edit: if the amount, vendor or lines change after approval, send the bill back to Pending (a SuiteApprovals setting, or a small UE script if unsupported) | 3.1 | Config/script |
| 3.4 | Decide what to do with existing open bills at cutover (bulk-approve under Controller sign-off, or route them) | 3.2 | Cutover memo |
| 3.5 | Test with test vendors, with rules active only for them or for the test subsidiary where possible. Then widen. | 3.1–3.3 | Tests pass |

### P4 — EBP configuration and batch approval (week 3–5)

| # | Task | Depends on | Output |
|---|---|---|---|
| 4.1 | Create the **company bank details** record with the NACHA template, Company ID and other values from 0b.2, tied to the GL bank account | 2.1, 0b.2 | Company bank record |
| 4.2 | Turn on **batch approval routing** in EBP, with the approver roles from §3.2 | 4.1, 1.2 | Setting |
| 4.3 | Set payment-file controls: file naming, who can generate or download, and cleanup of file cabinet folder permissions (files contain account numbers) | 4.1 | Permissions |
| 4.4 | Enter the test vendors' bank details through the P2 approval flow and send prenotes | P2 done | Prenotes |
| 4.5 | Build the remittance advice email template (vendor notification of payment) | 4.1 | Template |
| 4.6 | Returns handling procedure: R01/R02/R03/R04 returns and NOCs (C01/C02). Update bank details through P2, reverse or void the payment in NetSuite, and re-issue. | 4.1 | Runbook |

### P5 — End-to-end testing and bank certification (week 5–6)

| # | Task | Depends on |
|---|---|---|
| 5.1 | Run the full test catalog (§6) in production using test vendors | P2–P4 |
| 5.2 | Generate a NACHA file and run it through the offline validator (§6.4). Upload to the **bank test channel** and get certification. | 0b.3, 4.1 |
| 5.3 | **Penny test:** one live $0.01 or small real payment to an internal or friendly vendor account, then reconcile | 5.2 |
| 5.4 | UAT sign-off by AP Manager and Controller | 5.1–5.3 |

### P6 — Go-live and hypercare (week 7+)

| # | Task |
|---|---|
| 6.1 | Onboard the first wave of vendors (about 10 highest-volume, low-risk). Prenote each one and wait the bank's required prenote period. |
| 6.2 | First live batch, with the Controller watching every step |
| 6.3 | Daily bank rec of ACH clearing for 30 days, and review of the bank-detail change digest |
| 6.4 | Roll out to the remaining vendors in waves |
| 6.5 | 60-day retrospective: evaluate SFTP or host-to-host automation (Option C) |

## 5. Production-only safeguards

1. **Release status gating.** Deploy SuiteFlow workflows and script deployments in **Testing** status, so they only run for their owner, until tests pass.
2. **Test data isolation.** Prefix test vendors with `ZZTEST-`, point them at a dedicated clearing account or test subsidiary if available, and make them inactive after testing.
3. **No live file before certification.** Only upload to the bank's production channel after the bank certifies the test file, and only after the penny test.
4. **Bank-side dual control** (0b.4) is the backstop if NetSuite controls fail.
5. **Change control.** All custom objects live in SDF in this repo. Changes go through a PR, a reviewer, CI green, then a deploy by the named admin. No ad hoc UI edits to controlled objects after go-live.
6. **Rollback plan.** Every SDF deploy has a documented revert (set the workflow or script to Not Initiating or Not Scheduled, or redeploy the previous tag). EBP batches can be rolled back before the file is sent.

## 6. Test catalog

Legend for **Where**: `CI` = automated in this repo (runs in the cloud) · `NS` = manual or scripted in NetSuite · `BANK` = bank test or live channel.

### 6.1 Vendor bank-detail control (P2)

| ID | Test | Expected | Where |
|---|---|---|---|
| BD-01 | AP Clerk edits a vendor's routing number | Blocked by role permission | NS |
| BD-02 | An authorized user changes the account number | Status → Pending, record unusable for payment, `Last Changed By` stamped | CI (UE unit) + NS |
| BD-03 | The same user tries to approve their own change | Blocked with an error | CI + NS |
| BD-04 | A different approver approves without `Call-back Verified` | Blocked | CI + NS |
| BD-05 | A different approver approves with call-back | Approved, activated, prenote queued | NS |
| BD-06 | Non-bank field edited (for example, the email) | Approval status unchanged | CI + NS |
| BD-07 | Bills for a vendor with Pending bank details | Vendor excluded from the EFT batch | NS |
| BD-08 | CSV import or web services edit of bank details | Same control fires (UE runs on all contexts) | CI + NS |
| BD-09 | Daily digest lists every change, with before and after values from System Notes | Email received | NS |
| BD-10 | Invalid ABA routing number (checksum fails) | Rejected on save | CI + NS |

### 6.2 Vendor bill approval (P3)

| ID | Test | Expected | Where |
|---|---|---|---|
| VB-01 | Bill $4,999.99 | 1 approver (dept manager) | NS (+ CI matrix test) |
| VB-02 | Bill $5,000.00 (boundary) | 2 approvers | NS (+ CI) |
| VB-03 | Bill $25,000.00 (boundary) | Controller + CFO | NS (+ CI) |
| VB-04 | Pending bill in Pay Bills / EFT batch | Not listed | NS |
| VB-05 | Approved bill, then amount edited | Returns to Pending | NS |
| VB-06 | Rejected bill | Not payable, reason captured | NS |
| VB-07 | The bill's creator is also in the approver chain | Skipped or escalated per SoD rule | NS |
| VB-08 | Approver on PTO (delegation) | The delegate receives the task | NS |
| VB-09 | Bill created by CSV import or integration | Enters approval as Pending | NS |
| VB-10 | Audit: System Notes show every approval action with user and timestamp | Present | NS |

### 6.3 Payment batch approval and EBP (P4)

| ID | Test | Expected | Where |
|---|---|---|---|
| PB-01 | Create an EFT batch of approved bills | Batch Pending Approval, no file yet | NS |
| PB-02 | Batch creator tries to approve | Blocked | NS |
| PB-03 | Approver approves | File generated in the restricted folder | NS |
| PB-04 | Approver rejects | No file, bills return to open | NS |
| PB-05 | Batch total over the Controller threshold | Second approval level required | NS |
| PB-06 | Roll back a batch before upload | Payments voided, bills open again | NS |
| PB-07 | Vendor with no or unapproved bank details | Excluded from batch | NS |
| PB-08 | Duplicate-payment check: the same bill in two batches | Not possible | NS |
| PB-09 | Payment date on a bank holiday or weekend | Effective date adjusted or warned | NS + CI (validator) |
| PB-10 | File folder permissions: an AP Clerk tries to open the file | Access denied | NS |
| PB-11 | Remittance email sent to the vendor | Received with the correct invoice list | NS |
| PB-12 | Prenote file for a new vendor | $0 entries with prenote transaction codes (23/33) | NS + CI (validator) |

### 6.4 NACHA file validation (offline, automated)

EBP generates the file. We add an **independent validator** in this repo and run it on every test file (sanitized copies only) before bank upload.

| ID | Check | Where |
|---|---|---|
| NF-01 | Every record is 94 characters. The line count is a multiple of 10 (blocking factor; padded with `9` records). | CI |
| NF-02 | Record order is 1 → (5 → 6/7… → 8)+ → 9 | CI |
| NF-03 | Immediate Origin, Destination and Company ID match the bank spec | CI |
| NF-04 | Batch entry/addenda count, entry hash (sum of RDFI 8-digit routing numbers mod 10¹⁰) and total credits match the entries | CI |
| NF-05 | File control (9) totals equal the sum of batch controls (8) | CI |
| NF-06 | Every RDFI routing number passes the ABA checksum | CI |
| NF-07 | SEC code = CCD, and transaction codes are 22/32 (credits) or 23/33 (prenotes) only. No debits. | CI |
| NF-08 | Effective entry date is a valid business day, not in the past | CI |
| NF-09 | Name fields are uppercase ASCII only (no characters that break bank parsers) | CI |
| NF-10 | Offset entry present or absent according to the bank's balanced or unbalanced requirement | CI |
| NF-11 | The file's total equals the NetSuite batch total (reconciliation) | CI (with an exported batch total) |

### 6.5 End-to-end, security and regression

| ID | Test | Where |
|---|---|---|
| E2E-01 | New vendor → bank details approved → prenote → bill → bill approved → batch → batch approved → file → bank test channel accepted | NS + BANK |
| E2E-02 | Penny test, live, reconciled in bank rec | NS + BANK |
| E2E-03 | Simulated return (R03): runbook followed, payment reversed, vendor flagged | NS |
| E2E-04 | Role review: no single role can change bank details *and* approve bills *and* approve batches | NS (role permission report) |
| E2E-05 | Post-release regression: re-run BD-02/03, VB-02/04 and PB-02/03 after each NetSuite biannual release and each SuiteApp update | NS |
| SEC-01 | No bank data or tokens committed to the repo (secret scan in CI) | CI |

## 7. What can be built and tested from the cloud (Claude Code on the web)

| Work item | From the cloud? | Notes |
|---|---|---|
| This plan, runbooks, approval matrix templates | ✅ Yes | |
| SDF project scaffold, custom fields, workflow XML, roles, saved searches | ✅ Yes | Authored as SDF objects in this repo |
| SuiteScript 2.1 (bank-detail UE script, re-approval script) | ✅ Yes | |
| Unit tests with Jest + `@oracle/suitecloud-unit-testing` (mocked `N/record`, `N/runtime`, etc.) | ✅ Yes | Covers the CI rows in §6 |
| Approval matrix boundary tests (data-driven) | ✅ Yes | |
| NACHA validator + tests on synthetic files | ✅ Yes | Validates real EBP output once you add a *sanitized* sample |
| GitHub Actions CI (lint, tests, `suitecloud project:validate` local validation, secret scan) | ✅ Yes | |
| Connect to your NetSuite account (`suitecloud` deploy, REST/SuiteQL checks) | ⚠️ Blocked right now | The environment's network policy blocks `*.netsuite.com`. It can be allowed, and TBA tokens can be added as environment secrets. **For production-only accounts I'd still recommend that a named admin runs deploys, not the cloud.** |
| Install SuiteApps (EBP, SuiteApprovals), set preferences, set up the company bank record | ❌ No | NetSuite UI admin tasks. I can write the step-by-step click-path runbook. |
| Tests marked NS (workflow behavior, Pay Bills, batch approval, permissions) | ❌ No | Run by you in NetSuite. I can provide scripted test scripts and evidence templates. |
| Bank test-channel upload, prenotes, penny test | ❌ No | Bank portal. Real bank data must never enter this repo. |

Rough split: about **35–40%** of the effort can be built and verified from the cloud (code, config-as-code, unit and file-validation tests, CI, documentation). The remaining **60–65%** is NetSuite UI configuration, in-account testing, bank onboarding and sign-offs, and it has to be done by people with account and bank access.

## 8. Open questions

1. Is this a OneWorld account? How many subsidiaries and operating bank accounts will pay by ACH?
2. Which bank? Does it accept standard NACHA CCD+ with remittance addenda, and is the file balanced or unbalanced?
3. Expected volume: vendors per batch, batches per week?
4. Who are the named approvers and delegates for each tier?
5. Is there an existing vendor bill approval process (email, or the native supervisor limit) that must be migrated?
6. Is a sandbox purchase on the table (§1)?
