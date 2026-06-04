# EOD Shift Report Print Design

Date: 2026-05-24
App: POS Next
Scope: POS Closing Shift auto-print and Desk reprint for End-of-Day report.

## Problem Statement

Cashiers need a printed EOD report when closing a shift. Currently, shift close does not automatically print this report, and Desk users do not have a dedicated reprint action for submitted closing shifts.

## Goal

Implement EOD report printing for `POS Closing Shift` with:

- Auto-print after successful shift close in POS frontend
- Non-blocking print failure behavior (close succeeds, warning shown, retry path provided)
- Reprint button on submitted `POS Closing Shift` in Desk
- Thermal 80mm print format named `POS Next EOD Report`

## Non-Goals

- No schema changes to `POS Closing Shift` or related doctypes
- No changes to receipt transport beyond existing QZ Tray pipeline
- No changes to `POS Next Receipt` format

## Primary Flow

1. Cashier closes shift in POS.
2. Backend submits `POS Closing Shift`.
3. Frontend resolves returned `closing_shift` name from submit response.
4. Frontend requests print HTML/style via `frappe.www.printview.get_html_and_style`.
5. Frontend sends full HTML document to QZ Tray (`qzPrintHTML`).
6. If printing fails:
   - Shift remains submitted (no rollback)
   - Warning toast appears
   - Dialog stays open with retry button

## Data Sources

- `doc.pos_transactions` child rows (Sales Invoice Reference)
  - rows may contain `sales_invoice` and/or `pos_invoice`
- `doc.payment_reconciliation` rows (POS Closing Shift Detail)
- `doc.taxes` rows (POS Closing Shift Taxes)
- totals on closing doc:
  - `grand_total`, `net_total`, `total_quantity`

## Consolidation Requirement

For closed shifts where ERPNext consolidated POS Invoices into Sales Invoices:

- `get_items_sold(doc)` must follow `POS Invoice.consolidated_invoice`
- If `consolidated_invoice` is set, fetch items from `Sales Invoice Item` with:
  - `parent = consolidated_invoice`
  - `parenttype = "Sales Invoice"`
- Otherwise use:
  - `parent = pos_invoice`
  - `parenttype = "POS Invoice"`

## Backend Components

- New helper module:
  - `pos_next/pos_next/utils/pos_closing_print.py`
  - exposed to Jinja via `hooks.py`
- Jinja method:
  - `get_items_sold(doc)` returning aggregated item rows sorted by amount desc
- Test module:
  - `pos_next/pos_next/utils/tests/test_pos_closing_print.py`

## Print Format

- New print format fixture JSON:
  - `pos_next/pos_next/print_format/pos_next_eod_report/pos_next_eod_report.json`
- Name: `POS Next EOD Report`
- DocType: `POS Closing Shift`
- Thermal styling:
  - 80mm width
  - explicit `direction: ltr` on receipt container and rows
- Sections:
  - Header
  - Session details
  - Sales totals
  - Items sold
  - Taxes
  - Payments
  - Final summary
  - Footer with print timestamp and user

## Desk Integration

File: `pos_next/pos_next/doctype/pos_closing_shift/pos_closing_shift.js`

- On submitted doc (`docstatus === 1`), add button:
  - Label: `Print EOD Report`
  - Group: `Print`
  - Calls `frappe.utils.print` with print format `POS Next EOD Report`

## POS Frontend Integration

Files:

- `POS/src/utils/printInvoice.js`
  - add generic `silentPrintDoc(doctype, name, printFormat)`
- `POS/src/utils/printEod.js`
  - add `printEODReport(closingShiftName)`
- `POS/src/components/ShiftClosingDialog.vue`
  - after successful submit, print EOD
  - if print fails: show warning + keep dialog open with retry action
  - retry success closes dialog and emits `shift-closed`

## Error Handling

- Print errors are non-fatal
- Submit errors remain fatal for closing flow
- Print retry does not resubmit shift

## Acceptance Criteria

- Shift close triggers EOD print via QZ Tray
- Print failure does not block close
- Retry button can print and finish dialog flow
- Desk submitted `POS Closing Shift` supports one-click EOD reprint
- Items sold section works for consolidated and non-consolidated invoices
