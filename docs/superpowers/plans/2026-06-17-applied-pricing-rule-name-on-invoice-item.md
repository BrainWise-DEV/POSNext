# Applied Promotional Scheme Link on Sales Invoice Item — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stamp each Sales Invoice item line with a clickable **Link** to the Promotional Scheme that discounted it, so the applied promotion is visible and navigable on the saved invoice in Desk.

**Architecture:** POS Next clears `item.pricing_rules` before save to stop ERPNext zeroing the discount, which is why no rule name survives today. We add a read-only `Link` custom field `pos_applied_promotional_scheme` (→ Promotional Scheme) to Sales Invoice Item, capture each item's applied rule names in the existing per-item loop in `update_invoice` just before they are cleared, resolve those rule names to their parent `promotional_scheme` with ONE batched query after the loop, and stamp the field per item with the first resolved scheme. Standalone rules (no scheme) leave the field blank. No text-formatting helper is needed — a Link renders the scheme natively. No change to discount math or the one-time-offer logic.

**Tech Stack:** Frappe/ERPNext (Python), custom fields via `sync_on_migrate` JSON, `FrappeTestCase`.

---

## Testing Notes (read first)

- Tests run on site **nexus.local** (has erpnext + pos_next installed) via the existing `pos_next/test_promotions.py` suite, scoped to the module:
  ```
  bench --site nexus.local run-tests --module pos_next.test_promotions
  ```
  Run all bench commands from `/home/ubuntu/frappe-bench`.
- All work happens on branch `feat/applied-pricing-rule-name-on-invoice-item`.
- **Data facts confirmed on nexus.local:** `Promotional Scheme` has NO `title` column — its `name` IS the title (`autoname: Prompt`). A `Pricing Rule` carries `promotional_scheme` (the scheme name, possibly null) and `title`. So resolving rule → scheme is a single `Pricing Rule` query; do NOT query `Promotional Scheme` for a `title` (it will raise).

---

## File Structure

- **Create:** `pos_next/pos_next/custom/sales_invoice_item.json` — managed custom-field definition adding the `Link` field `pos_applied_promotional_scheme` to Sales Invoice Item (synced by `bench migrate`).
- **Modify:** `pos_next/api/invoices.py` (~lines 829-921, the `update_invoice` per-item loop and the post-loop stamping block) — capture per-item rule names, resolve to scheme, stamp the new field.
- **Modify:** `pos_next/test_promotions.py` — add a test asserting the field links to the scheme for a scheme rule, and is blank for a standalone rule / no rule.

---

## Task 1: Add the `pos_applied_promotional_scheme` Link field on Sales Invoice Item

**Files:**
- Create: `pos_next/pos_next/custom/sales_invoice_item.json`

- [ ] **Step 1: Create the custom-field JSON**

Create `pos_next/pos_next/custom/sales_invoice_item.json` with exactly this content. It is a read-only `Link` to `Promotional Scheme`, visible (`hidden: 0`) and printable (`print_hide: 0`, `print_hide_if_no_value: 1`), inserted after `discount_amount`.

```json
{
 "custom_fields": [
  {
   "allow_in_quick_entry": 0,
   "allow_on_submit": 0,
   "bold": 0,
   "collapsible": 0,
   "columns": 0,
   "default": null,
   "depends_on": null,
   "description": "Promotional Scheme applied to this line. Stamped by POS Next at save because item.pricing_rules is cleared to protect the discount.",
   "docstatus": 0,
   "dt": "Sales Invoice Item",
   "fieldname": "pos_applied_promotional_scheme",
   "fieldtype": "Link",
   "hidden": 0,
   "idx": 0,
   "ignore_user_permissions": 0,
   "ignore_xss_filter": 0,
   "in_global_search": 0,
   "in_list_view": 0,
   "in_preview": 0,
   "in_standard_filter": 0,
   "is_system_generated": 0,
   "is_virtual": 0,
   "label": "Applied Promotional Scheme",
   "length": 0,
   "mandatory_depends_on": null,
   "module": "POS Next",
   "name": "Sales Invoice Item-pos_applied_promotional_scheme",
   "no_copy": 1,
   "non_negative": 0,
   "options": "Promotional Scheme",
   "permlevel": 0,
   "precision": "",
   "print_hide": 0,
   "print_hide_if_no_value": 1,
   "read_only": 1,
   "report_hide": 0,
   "reqd": 0,
   "search_index": 0,
   "show_dashboard": 0,
   "sort_options": 0,
   "translatable": 0,
   "unique": 0,
   "width": null
  }
 ],
 "custom_perms": [],
 "doctype": "Sales Invoice Item",
 "links": [],
 "property_setters": [],
 "sync_on_migrate": 1
}
```

- [ ] **Step 2: Sync to the test site**

Run: `bench --site nexus.local migrate`
Expected: completes without error.

- [ ] **Step 3: Verify the field**

Run:
```
bench --site nexus.local execute frappe.client.get_value --kwargs "{'doctype':'Custom Field','filters':{'name':'Sales Invoice Item-pos_applied_promotional_scheme'},'fieldname':['fieldname','fieldtype','options','read_only','dt']}"
```
Expected: `{'fieldname':'pos_applied_promotional_scheme','fieldtype':'Link','options':'Promotional Scheme','read_only':1,'dt':'Sales Invoice Item'}`.

- [ ] **Step 4: Commit**

```bash
git add pos_next/pos_next/custom/sales_invoice_item.json
git commit -m "feat: add pos_applied_promotional_scheme Link field to Sales Invoice Item

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Capture per-item rule names and stamp the scheme in update_invoice

**Files:**
- Modify: `pos_next/api/invoices.py:829-921`

The per-item loop currently collects only the union `applied_rule_names_seen` and clears `item.pricing_rules`. We capture per-item names in the loop, then resolve rule → scheme in one query and stamp the Link after the loop.

- [ ] **Step 1: Capture per-item names inside the loop**

In `pos_next/api/invoices.py`, find this block (currently ~lines 888-897):

```python
			if item.get("pricing_rules"):
				if erpnext_get_applied_pricing_rules:
					applied_rule_names_seen.update(
						erpnext_get_applied_pricing_rules(item.pricing_rules) or []
					)
				else:
					applied_rule_names_seen.update(
						r.strip() for r in str(item.pricing_rules).split(",") if r.strip()
					)
				item.pricing_rules = ""
```

Replace it with (captures this item's names before clearing):

```python
			item_rule_names = []
			if item.get("pricing_rules"):
				if erpnext_get_applied_pricing_rules:
					item_rule_names = list(
						erpnext_get_applied_pricing_rules(item.pricing_rules) or []
					)
				else:
					item_rule_names = [
						r.strip() for r in str(item.pricing_rules).split(",") if r.strip()
					]
				applied_rule_names_seen.update(item_rule_names)
				item.pricing_rules = ""
			# Stash this line's applied rule names for post-loop scheme stamping.
			# The cleared field can't be read back, so keep them on the row object.
			item._applied_rule_names = item_rule_names
```

- [ ] **Step 2: Resolve rule → scheme and stamp after the loop**

In the same function, find the post-loop block that currently begins (~line 899):

```python
		if doctype == "Sales Invoice":
			# Only stamp rules we can actually track: an identified, non walk-in
			# customer on a non-return sale (see is_one_time_eligible_customer).
			can_track_one_time = is_one_time_eligible_customer(
```

Insert the following **immediately before** that `if doctype == "Sales Invoice":` line. It runs for any doctype that went through the loop; the field only exists on Sales Invoice Item, but setting the attribute on other rows is harmless and only persists when the parent is a Sales Invoice. The resolve/stamp is guarded so it can never fail the sale.

```python
		# Stamp each line with a Link to the Promotional Scheme that discounted it
		# (item.pricing_rules was cleared above to protect the discount). The applied
		# record is a Pricing Rule; resolve it to its parent promotional_scheme. One
		# batched query, no per-item queries. Standalone rules (no scheme) stay blank.
		try:
			rule_to_scheme = {}
			if applied_rule_names_seen:
				rule_to_scheme = {
					r.name: r.promotional_scheme
					for r in frappe.get_all(
						"Pricing Rule",
						filters={"name": ["in", list(applied_rule_names_seen)]},
						fields=["name", "promotional_scheme"],
					)
					if r.promotional_scheme
				}
			for item in invoice_doc.get("items", []):
				names = getattr(item, "_applied_rule_names", None) or []
				scheme = next((rule_to_scheme[n] for n in names if n in rule_to_scheme), None)
				item.pos_applied_promotional_scheme = scheme or None
		except Exception:
			# Stamping must never fail the sale.
			frappe.log_error(
				title="Applied promotional scheme stamping failed",
				message=frappe.get_traceback(),
			)

```

- [ ] **Step 3: Verify the module imports cleanly**

Run: `bench --site nexus.local execute pos_next.api.invoices.is_one_time_eligible_customer --kwargs "{'customer':'x','default_customer':'y'}"`
Expected: returns `True` (and no syntax/import error — proves the edited file loads).

- [ ] **Step 4: Commit**

```bash
git add pos_next/api/invoices.py
git commit -m "feat: stamp pos_applied_promotional_scheme on each invoice item at save

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Test — scheme link stamped for scheme rule, blank otherwise

**Files:**
- Modify: `pos_next/test_promotions.py` (add a method to `class TestPromotions`)

The existing `_make_rule` creates a **standalone** Pricing Rule (no `promotional_scheme`), so its line must be **blank**. To test the scheme path we create a Promotional Scheme, which generates a child Pricing Rule whose `promotional_scheme` is the scheme name; the discounted line must link to that scheme.

- [ ] **Step 1: Write the test**

Add this method verbatim inside `class TestPromotions` in `pos_next/test_promotions.py` (e.g. after `test_discount_percentage`). It reuses existing helpers (`_cart_payload`, `_line`, `_apply_offers_and_stamp`, `_submit_invoice`, `_resolve_company`, `flt`, `ITEM_A`, `ITEM_B`, `nowdate`) and `frappe`.

```python
	def test_applied_promotional_scheme_stamped(self):
		"""A line discounted by a Promotional Scheme links to that scheme; an
		undiscounted line and a standalone-rule line stay blank."""
		scheme_name = "_PNXT_TEST_Scheme"
		if frappe.db.exists("Promotional Scheme", scheme_name):
			frappe.delete_doc("Promotional Scheme", scheme_name, force=True, ignore_permissions=True)
		scheme = frappe.get_doc(
			{
				"doctype": "Promotional Scheme",
				"__newname": scheme_name,
				"apply_on": "Item Code",
				"selling": 1,
				"company": _resolve_company(),
				"currency": frappe.get_cached_value("Company", _resolve_company(), "default_currency"),
				"valid_from": nowdate(),
				"items": [{"item_code": ITEM_A}],
				"price_discount_slabs": [
					{
						"rate_or_discount": "Discount Percentage",
						"discount_percentage": 15,
						"min_qty": 1,
						"disable": 0,
					}
				],
			}
		).insert(ignore_permissions=True)

		# The scheme generates one or more Pricing Rules linked back to it.
		scheme_rules = frappe.get_all(
			"Pricing Rule", filters={"promotional_scheme": scheme.name}, pluck="name"
		)
		self.assertTrue(scheme_rules, "scheme should generate a Pricing Rule")

		payload = _cart_payload(
			self.ctx,
			[_line(self.ctx, ITEM_A, qty=1), _line(self.ctx, ITEM_B, qty=1)],
		)
		_apply_offers_and_stamp(payload, scheme_rules)
		paid = sum(flt(i["rate"]) * flt(i["qty"]) for i in payload["items"])
		final = _submit_invoice(self.ctx, payload, paid_amount=paid)

		line_a = next(i for i in final.items if i.item_code == ITEM_A)
		line_b = next(i for i in final.items if i.item_code == ITEM_B)

		# ITEM_A was discounted by the scheme -> links to the scheme.
		self.assertEqual(line_a.pos_applied_promotional_scheme, scheme.name)
		# ITEM_B had no applicable rule -> blank.
		self.assertFalse(line_b.pos_applied_promotional_scheme)
		# pricing_rules itself stays cleared (the protective behavior).
		self.assertEqual((line_a.pricing_rules or ""), "")

		frappe.delete_doc("Promotional Scheme", scheme.name, force=True, ignore_permissions=True)
```

- [ ] **Step 2: Run the new test**

Run: `bench --site nexus.local run-tests --module pos_next.test_promotions --test test_applied_promotional_scheme_stamped`
Expected: 1 test, PASS.

Troubleshooting if FAIL:
- If the scheme insert fails on a required field, inspect the Promotional Scheme doctype on nexus.local and add the missing field to the `frappe.get_doc({...})` dict:
  `bench --site nexus.local execute frappe.client.get_value --kwargs "{'doctype':'DocType','filters':{'name':'Promotional Scheme'},'fieldname':['name']}"` then read its meta. Common required fields are already included (apply_on, selling, company, currency, valid_from, items, price_discount_slabs).
- If `line_a.pos_applied_promotional_scheme` is empty, inspect what rule actually applied:
  `bench --site nexus.local execute frappe.client.get_value --kwargs "{'doctype':'Sales Invoice Item','filters':{'parent':'<inv>','item_code':'<ITEM_A>'},'fieldname':['pos_applied_promotional_scheme']}"` and confirm `_apply_offers_and_stamp` set `pricing_rules` on the payload line.

- [ ] **Step 3: Run the full suite for regressions**

Run: `bench --site nexus.local run-tests --module pos_next.test_promotions`
Expected: all existing tests still PASS (the change only adds a field and a stamp; discount math is untouched).

- [ ] **Step 4: Commit**

```bash
git add pos_next/test_promotions.py
git commit -m "test: assert applied promotional scheme is linked on invoice item

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Manual Desk verification

- [ ] **Step 1:** Open an invoice created by the test (or ring a real POS sale that applies a scheme rule on nexus.local), open the item row in Desk, and confirm the **Applied Promotional Scheme** field shows the scheme as a clickable Link and is read-only.
- [ ] **Step 2 (optional):** Confirm print behavior — the field prints only when populated (`print_hide_if_no_value: 1`).
- [ ] **Step 3:** No commit (verification only).

---

## Self-Review Checklist (completed by plan author)

- **Spec coverage:** Link custom field → Promotional Scheme (Task 1); capture per-item names + single-query rule→scheme resolution + per-item stamp, guarded (Task 2); standalone/no-rule blank (Task 2 logic + Task 3 assertions); migration/rollout (Task 1 Steps 2-3). No text helper (removed by design). Non-goals (no math change, SI only, no backfill) preserved — Task 2 inserts before the one-time block and leaves it intact.
- **Placeholder scan:** none — all code blocks are complete and verbatim.
- **Type/name consistency:** field `pos_applied_promotional_scheme` (Task 1 JSON, Task 2 stamp, Task 3 assertion); transient `item._applied_rule_names` (set Task 2 Step 1, read Task 2 Step 2); `applied_rule_names_seen` (existing, still updated). Consistent throughout.
