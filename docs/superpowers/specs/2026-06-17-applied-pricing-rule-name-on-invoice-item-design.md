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

Display, on each Sales Invoice **item line**, the pricing rule(s) that discounted
that line, formatted as the human-friendly scheme title plus the rule id:

- Promotional-scheme rule: `<Scheme Title> (<RULE-ID>)`
- Standalone pricing rule (no scheme): `<RULE-ID>` (fallback to rule id only)
- Multiple rules on one line: comma-separated.

The field is read-only and available to Desk (and print).

## Non-Goals

- No change to discount math, `ignore_pricing_rule`, or the one-time-offer
  logic (`pos_applied_one_time_rules`, `One Time Customer Offer Usage`).
- No POS frontend (Vue) UI change — this is a Desk/invoice-record feature.
- No backfill of historical invoices (the data was discarded at save time and
  cannot be reconstructed reliably). New invoices only.
- Sales Invoice only. (Sales Order is out of scope; the clearing logic that
  motivates this lives in the Sales Invoice save path.)

## Design

### 1. New custom field: `pos_applied_pricing_rules` on Sales Invoice Item

Add via a new managed custom-field file
`pos_next/pos_next/custom/sales_invoice_item.json`, following the exact shape of
the existing `pos_next/pos_next/custom/sales_invoice.json` (`sync_on_migrate: 1`).

Field properties (mirroring the established `pos_applied_one_time_rules`
conventions, except this one is visible and printable):

| Property | Value |
|---|---|
| `dt` | `Sales Invoice Item` |
| `fieldname` | `pos_applied_pricing_rules` |
| `fieldtype` | `Small Text` |
| `label` | `Applied Pricing Rules` |
| `read_only` | 1 |
| `no_copy` | 1 |
| `hidden` | 0 |
| `print_hide` | 0 |
| `allow_on_submit` | 0 |
| `in_list_view` | 0 |
| `module` | `POS Next` |
| `insert_after` | an existing discount-area field on Sales Invoice Item (e.g. `discount_amount`) |

Exact `insert_after` and `idx` to be finalized against the live Sales Invoice
Item field order during implementation.

### 2. Populate during `update_invoice` (server-side)

In `pos_next/api/invoices.py`, the per-item loop starting at the
`applied_rule_names_seen` collection (~line 830) already extracts each item's
applied rule names immediately before clearing `item.pricing_rules` (~line
888-897). Extend that exact site:

1. **Capture per-item rule names.** Where the code currently does
   `applied_rule_names_seen.update(...)` and then `item.pricing_rules = ""`,
   also keep the list of rule names for *this item* (e.g. a local
   `item_rule_names` list per iteration). Continue updating the union
   `applied_rule_names_seen` as today (still needed for the one-time stamp).

2. **Resolve titles in one batched query.** After the loop (alongside the
   existing one-time stamping block at ~line 899), run a single
   `frappe.get_all("Pricing Rule", filters={"name": ["in", list(applied_rule_names_seen)]}, fields=["name", "promotional_scheme", "title"])`
   and build a `name -> display_label` map. The label's friendly portion is
   chosen by this precedence (first non-empty wins):
   1. The Promotional Scheme's `title`, if `promotional_scheme` is set and that
      scheme has a non-empty title.
   2. The `promotional_scheme` id itself, if set but the scheme has no title.
   3. The Pricing Rule's own `title`, if set.
   4. None of the above → no friendly portion.

   Final format: `"{friendly} ({rule_name})"` when a friendly portion exists,
   otherwise `"{rule_name}"`.
   - Scheme titles: resolve via one additional batched
     `frappe.get_all("Promotional Scheme", ...)` keyed by the distinct
     `promotional_scheme` values (only if any scheme-linked rules exist).

3. **Stamp each item.** Set
   `item.pos_applied_pricing_rules = ", ".join(display_label[n] for n in item_rule_names)`
   (empty string when the item had no applied rules).

Query budget: at most **two** additional `frappe.get_all` calls per invoice
(one for Pricing Rule, one for Promotional Scheme titles), independent of item
count. No per-item queries.

### Data flow

```
apply_offers (earlier call)           update_invoice (save path)
  └─ ERPNext engine returns      →      per-item loop:
     item.pricing_rules                   ├─ read item.pricing_rules
     ("<RULE-ID>,...")                     ├─ item_rule_names = [...]    (NEW: keep per item)
                                           ├─ applied_rule_names_seen.update(...)  (existing)
                                           └─ item.pricing_rules = ""    (existing)
                                         after loop:
                                           ├─ batch-resolve rule -> "Title (RULE-ID)"  (NEW)
                                           ├─ stamp item.pos_applied_pricing_rules     (NEW)
                                           └─ stamp invoice.pos_applied_one_time_rules (existing)
```

### Error handling

- A rule name in `item.pricing_rules` that no longer resolves to a Pricing Rule
  (deleted rule) falls back to the raw rule id as its label. Never throws.
- Title resolution failures degrade to rule id; stamping must never fail the
  sale (consistent with the existing one-time recording philosophy). Wrap the
  resolution/stamp in a guard that logs and leaves the field empty on error.

## Testing

Run on **pos-dev** (has ERPNext data; never `bench run-tests`, use
`bench execute`):

1. **Scheme rule:** Build a cart whose item matches a promotional-scheme price
   rule, run it through the save path, assert the saved item's
   `pos_applied_pricing_rules == "<Scheme Title> (<RULE-ID>)"`.
2. **Standalone rule:** Same with a standalone Pricing Rule (no scheme), assert
   the field equals `"<RULE-ID>"`.
3. **No rule:** Item with no applied rule → field is empty string.
4. **Multiple rules on a line:** assert comma-separated labels.
5. **Deleted rule id:** simulate an unresolved rule name → falls back to id, no
   exception.
6. Migration: `bench --site pos-dev migrate` syncs the new custom field;
   confirm it appears on Sales Invoice Item and is read-only.

## Rollout

- New custom field ships via `custom/sales_invoice_item.json` and is applied by
  `bench migrate` (sync_on_migrate), same mechanism as existing custom fields.
- Backend change is additive; safe to deploy with the migration.
