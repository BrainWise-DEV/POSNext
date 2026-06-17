# Show Applied Promotional Scheme / Pricing Rule Name on Sales Invoice Item

**Date:** 2026-06-17
**Status:** Approved design — ready for implementation plan
**Author:** POS Next

## Problem

POS Next computes promotional offers itself via `apply_offers` and saves each
item with `discount_percentage` / `discount_amount` / `rate` already set, paired
with `invoice_doc.ignore_pricing_rule = 1`. To prevent ERPNext's pricing engine
from zeroing the discount on the second save, `update_invoice` **clears**
`item.pricing_rules = ""` before saving (`pos_next/api/invoices.py`, ~line 897).

Consequence: a saved POS Sales Invoice retains **no record** of which Pricing
Rule / Promotional Scheme produced a line's discount. ERPNext's native per-line
"Pricing Rules" field is blank, and `Pricing Rule Detail` is not populated
(the engine is bypassed on save). The only rule name persisted today is
`pos_applied_one_time_rules` (Sales Invoice header), and only for
one-time-per-customer rules.

A representative case: two POS invoices for the same customer both carry a
percentage discount from the same promotional scheme, yet each item row shows
`pricing_rules = ""`. Staff cannot tell from the invoice which promotion applied.

## Goal

Display, on each Sales Invoice **item line**, the Promotional Scheme that
discounted that line, as a **clickable Link** to the Promotional Scheme record.

- Scheme-based rule: links to the scheme (e.g. `15% Discount Iraq Mall`), which
  Frappe renders as the scheme name and lets the user click through to it.
- Standalone pricing rule (no scheme): field stays blank (no scheme to link to).
- Multiple rules on one line: store the first resolved scheme (single value).

The field is read-only and available to Desk (and print). Because the applied
record returned by the engine is a *Pricing Rule*, we resolve each applied rule
to its parent `promotional_scheme` and store that scheme name in the Link.

## Non-Goals

- No change to discount math, `ignore_pricing_rule`, or the one-time-offer
  logic (`pos_applied_one_time_rules`, `One Time Customer Offer Usage`).
- No POS frontend (Vue) UI change — this is a Desk/invoice-record feature.
- No backfill of historical invoices (the data was discarded at save time and
  cannot be reconstructed reliably). New invoices only.
- Sales Invoice only. (Sales Order is out of scope; the clearing logic that
  motivates this lives in the Sales Invoice save path.)

## Design

### 1. New custom field: `pos_applied_promotional_scheme` on Sales Invoice Item

Add via a new managed custom-field file
`pos_next/pos_next/custom/sales_invoice_item.json`, following the shape of the
existing `pos_next/pos_next/custom/sales_invoice.json` (`sync_on_migrate: 1`).

A **Link** field (not text) so the scheme is clickable and navigable in Desk.

| Property | Value |
|---|---|
| `dt` | `Sales Invoice Item` |
| `fieldname` | `pos_applied_promotional_scheme` |
| `fieldtype` | `Link` |
| `options` | `Promotional Scheme` |
| `label` | `Applied Promotional Scheme` |
| `read_only` | 1 |
| `no_copy` | 1 |
| `hidden` | 0 |
| `print_hide` | 0 |
| `allow_on_submit` | 0 |
| `in_list_view` | 0 |
| `module` | `POS Next` |
| `insert_after` | `discount_amount` |

Note: Promotional Scheme is named by its title (`autoname: Prompt`, no separate
`title` column on this ERPNext version), so the Link renders the scheme name
directly. Standalone Pricing Rules have no `promotional_scheme`, so the field is
left blank for them.

### 2. Populate during `update_invoice` (server-side)

In `pos_next/api/invoices.py`, the per-item loop starting at the
`applied_rule_names_seen` collection (~line 830) already extracts each item's
applied rule names immediately before clearing `item.pricing_rules` (~line
888-897). Extend that exact site:

1. **Capture per-item rule names.** Where the code currently does
   `applied_rule_names_seen.update(...)` and then `item.pricing_rules = ""`,
   also keep the list of rule names for *this item* (a local `item_rule_names`
   list per iteration). Continue updating the union `applied_rule_names_seen` as
   today (still needed for the one-time stamp).

2. **Resolve rule → scheme in one batched query.** After the loop (alongside the
   existing one-time stamping block at ~line 899), run a single
   `frappe.get_all("Pricing Rule", filters={"name": ["in", list(applied_rule_names_seen)]}, fields=["name", "promotional_scheme"])`
   and build a `rule_name -> promotional_scheme` map (only rules whose
   `promotional_scheme` is set). No second query and no text formatting — the
   stored value is the scheme name itself.

3. **Stamp each item.** Set `item.pos_applied_promotional_scheme` to the first
   non-empty resolved scheme among `item_rule_names` (single Link value), or
   leave it unset/empty when the item had no scheme-based rule.

Query budget: **one** additional `frappe.get_all` per invoice, independent of
item count. No per-item queries. The `_resolve_pricing_rule_labels` text helper
is NOT used in this design (a Link field renders the scheme natively).

### Data flow

```
apply_offers (earlier call)           update_invoice (save path)
  └─ ERPNext engine returns      →      per-item loop:
     item.pricing_rules                   ├─ read item.pricing_rules
     ("<RULE-ID>,...")                     ├─ item_rule_names = [...]    (NEW: keep per item)
                                           ├─ applied_rule_names_seen.update(...)  (existing)
                                           └─ item.pricing_rules = ""    (existing)
                                         after loop:
                                           ├─ batch-resolve rule -> promotional_scheme  (NEW)
                                           ├─ stamp item.pos_applied_promotional_scheme  (NEW)
                                           └─ stamp invoice.pos_applied_one_time_rules    (existing)
```

### Error handling

- A rule name with no `promotional_scheme` (standalone rule, or a deleted rule
  that doesn't resolve) yields no scheme → the Link is left blank. Never throws.
- The resolve/stamp step must never fail the sale (consistent with the existing
  one-time recording philosophy). Wrap it in a guard that logs and leaves the
  field empty on error.

## Testing

Run on **nexus.local** (has ERPNext data) via the existing `test_promotions.py`
suite, scoped: `bench --site nexus.local run-tests --module pos_next.test_promotions`.

1. **Scheme rule:** Build a cart whose item matches a promotional-scheme price
   rule, run it through the save path, assert the saved item's
   `pos_applied_promotional_scheme == "<Promotional Scheme name>"`.
2. **Standalone rule:** Same with a standalone Pricing Rule (no scheme), assert
   the field is empty/blank.
3. **No rule:** Item with no applied rule → field is blank.
4. Migration: `bench --site nexus.local migrate` syncs the new custom field;
   confirm it appears on Sales Invoice Item as a read-only Link to Promotional
   Scheme.

## Rollout

- New custom field ships via `custom/sales_invoice_item.json` and is applied by
  `bench migrate` (sync_on_migrate), same mechanism as existing custom fields.
- Backend change is additive; safe to deploy with the migration.
