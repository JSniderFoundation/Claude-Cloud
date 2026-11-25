# Shop Books: free double-entry bookkeeping for a small chocolate shop

A complete double-entry bookkeeping system in **one HTML file** (`index.html`). It has no subscription, no install and no server. Open it in Chrome, Edge, Firefox or Safari. It works offline, and nothing leaves your computer.

## What it does

- **Chart of accounts** for a US boutique chocolate shop. You can rename, renumber, add or deactivate accounts.
- **Quick-entry forms** that post balanced debits and credits for you. They cover daily sales (cash, card and sales tax), card processor payouts (net of fees), cash deposits, gift cards sold and redeemed, corporate/wholesale invoices and payments, refunds, inventory purchases, bills and expenses, paying suppliers (A/P), paying the credit card, paying sales tax, payroll, owner contributions and draws, and transfers.
- **General journal entries** for anything else, such as depreciation, loans and corrections. Every entry must balance.
- **Card processor clearing account.** Card sales sit there until Square, Stripe or Shopify pays out. Fees are recorded automatically.
- **Inventory & cost of goods sold** using the periodic method. Purchases go to inventory. At month end you count what's left, and the difference posts to COGS. An optional count sheet adds up quantity × unit cost.
- **Bank reconciliation** for bank, credit card, cash and clearing accounts. Tick items until the difference is $0.00. Reconciled entries are protected from accidental edits.
- **Reports:** Profit & Loss, P&L by month, Balance Sheet, Trial Balance and General Ledger. Click any account to drill into its transactions. Print or save any report as a PDF.
- **Year-end handled automatically.** Prior-year profit rolls into retained earnings, so no closing entries are needed. You can lock the books through a date after you file taxes.
- **Backup & restore** to a `.json` file, plus a **CSV export** of the journal for your accountant.

## Getting started

1. Save `index.html` somewhere permanent, such as `Documents/Shop Books/`, and open it in your browser. Bookmark it.
2. **Settings & Backup:** enter your shop name and fiscal year start.
3. **Accounts:** adjust names to match your bank, card and processor.
4. **Settings & Backup → Opening balances:** enter what you had on your start date.
5. Want to look around first? Click **Explore with sample data**, then erase it in Settings before entering real books.

## Suggested routine

| When | What |
|---|---|
| Daily, or each day you're open | **Record → Daily sales** from your POS end-of-day summary |
| When payouts arrive | **Record → Card processor payout** (deposit amount + fees) |
| Weekly | Bank the cash (**Cash deposit**), enter bills and purchases, **download a backup** |
| Monthly | **Inventory → Take an inventory count** on the last day, **Reconcile** the bank and credit card, review **Reports** |
| Yearly | Print the P&L and Balance Sheet for your tax preparer, export the CSV, set **Lock books through** to year end |

## Sharing the books between computers with OneDrive (Chrome or Edge)

You can keep your books in a file in your OneDrive folder. Every change is saved to that file automatically, and OneDrive syncs it to your other computer.

1. Put `index.html` in your OneDrive folder too, so both computers open the same app.
2. **On the computer that has your books now:** open Shop Books in Chrome or Edge. Go to **Settings & Backup → Books file (OneDrive) → Create books file…** and save it inside your OneDrive folder, for example `OneDrive/Shop Books/my-shop-books.json`.
3. **On the other computer:** open Shop Books in Chrome or Edge, click **Open existing books file…** (on the welcome screen or in Settings) and pick that same file.
4. Each time you start, the browser asks once for permission to open the file. Click **Allow**, or **Allow on every visit** if it's offered. The header shows `saved to my-shop-books.json` while you're connected.

Good habits:

- Use the books on **one computer at a time**. Before switching, wait for OneDrive to show the file as synced. The OneDrive icon in the taskbar or menu bar shows sync status.
- If the file changed on the other computer while this one also has unsaved changes, Shop Books **stops and asks** which version to keep. It never silently overwrites. It also offers to download this computer's version first.
- If a computer is left open, it checks the file every 30 seconds and when you switch back to the tab. It picks up changes made on the other computer automatically.
- OneDrive keeps version history (right-click the file → **Version history**), which acts as an automatic backup.
- Loading sample data or erasing everything **disconnects** the file first, so neither can touch your real books file.

## Important: backups

Without a linked books file, your books are saved in **this browser's storage on this computer**. They are not in the HTML file itself. That means:

- Clearing browser data, or switching to a different browser or computer, will *not* show your books.
- **Download a backup at least weekly** (Settings & Backup → Download backup) and keep copies in a second place, such as a USB drive or cloud folder. The app reminds you when a backup is overdue.
- To move to a new computer, copy `index.html` and your latest backup over, open the file, then choose **Restore from backup**.
- In Firefox, keep the HTML file in the same folder. Firefox ties saved data to the file's location.

## Notes

- Amounts are stored in whole cents, so there are no rounding drift errors.
- This is a bookkeeping tool, not tax advice. Have your accountant review your chart of accounts and year-end reports.
