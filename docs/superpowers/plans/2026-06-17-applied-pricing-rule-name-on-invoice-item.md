# Applied Pricing Rule Name on Sales Invoice Item — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stamp each Sales Invoice item line with the human-friendly name of the Promotional Scheme / Pricing Rule that discounted it (e.g. `<Scheme Title> (<RULE-ID>)`), so the applied promotion is visible on the saved invoice in Desk.

**Architecture:** POS Next clears `item.pricing_rules` before save to stop ERPNext zeroing the discount, which is why no rule name survives today. We add a read-only custom field `pos_applied_pricing_rules` to Sales Invoice Item, capture each item's applied rule names in the existing per-item loop in `update_invoice` just before they are cleared, resolve those names to friendly labels with at most two batched queries after the loop, and stamp the field per item. No change to discount math or the one-time-offer logic.

**Tech Stack:** Frappe/ERPNext (Python), custom fields via `sync_on_migrate` JSON, `FrappeTestCase` (run with `bench run-tests`-free workflow — these are unit tests executed via the test runner, NOT data-wiping `bench run-tests` against a real site; see Testing Notes).

---

## Testing Notes (read first)

- The project rule is **never run `bench run-tests`** (it wipes data) — but the existing `pos_next/test_promotions.py` is a `FrappeTestCase` suite. Run it the way the repo already runs that suite: against the **pos-dev** test site, scoped to the single module, e.g.:
  ```
  bench --site pos-dev run-tests --module pos_next.test_promotions
  ```
  If the team's convention is to avoid even scoped `run-tests`, drive the new test function directly with `bench --site pos-dev execute pos_next.test_promotions.<helper>` is NOT possible for `FrappeTestCase` methods; instead confirm with the user before running. Default below assumes scoped `run-tests --module pos_next.test_promotions` is acceptable since that file is already a test suite. **Confirm with the user before the first run.**
- All work happens on branch `feat/applied-pricing-rule-name-on-invoice-item` (already based on `community/uat`).

---

## File Structure

- **Create:** `pos_next/pos_next/custom/sales_invoice_item.json` — managed custom-field definition adding `pos_applied_pricing_rules` to Sales Invoice Item (synced by `bench migrate`).
- **Modify:** `pos_next/api/invoices.py` (~lines 829-921, the `update_invoice` per-item loop and the post-loop stamping block) — capture per-item rule names, add a helper to resolve labels, stamp the new field.
- **Modify:** `pos_next/test_promotions.py` — add a test asserting the field is stamped with `Title (RULE-ID)` and is empty when no rule applied.

---

## Task 1: Add the `pos_applied_pricing_rules` custom field on Sales Invoice Item

**Files:**
- Create: `pos_next/pos_next/custom/sales_invoice_item.json`

- [ ] **Step 1: Create the custom-field JSON**

Create `pos_next/pos_next/custom/sales_invoice_item.json` with exactly this content. The field shape mirrors the existing `Sales Invoice-pos_applied_one_time_rules` field in `custom/sales_invoice.json`, but is **visible** (`hidden: 0`) and **printable** (`print_hide: 0`) and `read_only`. `insert_after` is `discount_amount`, an existing field on Sales Invoice Item.

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
   "description": "Promotional Scheme / Pricing Rule(s) applied to this line, formatted as 'Title (RULE-ID)'. Stamped by POS Next at save because item.pricing_rules is cleared to protect the discount.",
   "docstatus": 0,
   "dt": "Sales Invoice Item",
   "fieldname": "pos_applied_pricing_rules",
   "fieldtype": "Small Text",
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
   "label": "Applied Pricing Rules",
   "length": 0,
   "mandatory_depends_on": null,
   "module": "POS Next",
   "name": "Sales Invoice Item-pos_applied_pricing_rules",
   "no_copy": 1,
   "non_negative": 0,
   "options": null,
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

- [ ] **Step 2: Sync the field to the test site**

Run: `bench --site pos-dev migrate`
Expected: completes without error; the new custom field is created.

- [ ] **Step 3: Verify the field exists and is read-only**

Run:
```
bench --site pos-dev execute frappe.client.get_value --kwargs "{'doctype':'Custom Field','filters':{'name':'Sales Invoice Item-pos_applied_pricing_rules'},'fieldname':['fieldname','read_only','hidden','dt']}"
```
Expected output: a dict with `fieldname: pos_applied_pricing_rules`, `read_only: 1`, `hidden: 0`, `dt: Sales Invoice Item`.

- [ ] **Step 4: Commit**

```bash
git add pos_next/pos_next/custom/sales_invoice_item.json
git commit -m "feat: add pos_applied_pricing_rules field to Sales Invoice Item"
```

---

## Task 2: Add a label-resolver helper in invoices.py

**Files:**
- Modify: `pos_next/api/invoices.py` (add a module-level function near `is_one_time_eligible_customer`, ~line 280)

This helper takes the set of applied rule names and returns a `{rule_name: display_label}` map using at most two batched queries. It must never raise.

- [ ] **Step 1: Write the helper**

Add this function in `pos_next/api/invoices.py` immediately after the `is_one_time_eligible_customer` function (which ends at ~line 288). The function uses `frappe`, already imported at the top of the file.

```python
def _resolve_pricing_rule_labels(rule_names):
	"""Map applied Pricing Rule names to friendly display labels.

	Label precedence (first non-empty wins) for the friendly portion:
	  1. The linked Promotional Scheme's title.
	  2. The Promotional Scheme id, if linked but the scheme has no title.
	  3. The Pricing Rule's own title.
	  4. None -> label is just the rule id.

	Final label: "{friendly} ({rule_name})" when a friendly part exists,
	otherwise "{rule_name}". Never raises: any failure yields an empty map so
	stamping degrades to nothing rather than failing the sale.

	Args:
		rule_names: iterable of Pricing Rule names.

	Returns:
		dict[str, str]: rule name -> display label. Names that don't resolve to a
		Pricing Rule still get an entry equal to the raw name.
	"""
	names = sorted({n for n in (rule_names or []) if n})
	if not names:
		return {}

	try:
		rules = frappe.get_all(
			"Pricing Rule",
			filters={"name": ["in", names]},
			fields=["name", "promotional_scheme", "title"],
		)
		scheme_ids = sorted({r.promotional_scheme for r in rules if r.promotional_scheme})
		scheme_titles = {}
		if scheme_ids:
			scheme_titles = {
				s.name: s.title
				for s in frappe.get_all(
					"Promotional Scheme",
					filters={"name": ["in", scheme_ids]},
					fields=["name", "title"],
				)
			}

		labels = {}
		found = set()
		for r in rules:
			found.add(r.name)
			friendly = None
			if r.promotional_scheme:
				friendly = scheme_titles.get(r.promotional_scheme) or r.promotional_scheme
			elif r.title:
				friendly = r.title
			labels[r.name] = f"{friendly} ({r.name})" if friendly else r.name

		# Unresolved names (e.g. deleted rule) fall back to the raw id.
		for n in names:
			if n not in found:
				labels[n] = n
		return labels
	except Exception:
		frappe.log_error(
			title="Applied pricing rule label resolution failed",
			message=frappe.get_traceback(),
		)
		return {}
```

- [ ] **Step 2: Syntax-check the module imports cleanly**

Run: `bench --site pos-dev execute pos_next.api.invoices._resolve_pricing_rule_labels --kwargs "{'rule_names': []}"`
Expected: returns `{}` (empty dict), no error.

- [ ] **Step 3: Commit**

```bash
git add pos_next/api/invoices.py
git commit -m "feat: add _resolve_pricing_rule_labels helper"
```

---

## Task 3: Capture per-item rule names and stamp the field in update_invoice

**Files:**
- Modify: `pos_next/api/invoices.py:829-921`

The per-item loop currently collects only the union `applied_rule_names_seen` and clears `item.pricing_rules`. We add a per-item capture (`item._applied_rule_names`, a transient attribute) inside the loop, then resolve+stamp after the loop.

- [ ] **Step 1: Capture per-item names inside the loop**

In `pos_next/api/invoices.py`, find the block (currently ~lines 888-897):

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
			# Stash this line's applied rule names for post-loop label stamping.
			# Cleared field can't be read back, so we keep them on the row object.
			item._applied_rule_names = item_rule_names
```

- [ ] **Step 2: Stamp the field after the loop**

In the same function, find the post-loop block that currently begins (currently ~line 899):

```python
		if doctype == "Sales Invoice":
			# Only stamp rules we can actually track: an identified, non walk-in
			# customer on a non-return sale (see is_one_time_eligible_customer).
			can_track_one_time = is_one_time_eligible_customer(
```

Insert the following **immediately before** that `if doctype == "Sales Invoice":` line (it runs for every doctype that went through the loop; the field only exists on Sales Invoice Item, but `db_set`/attribute set on the row is harmless for others and the value is only persisted when the parent is a Sales Invoice):

```python
		# Stamp each line with the friendly label(s) of the pricing rule(s) that
		# discounted it, so the applied promotion is visible on the saved invoice
		# (item.pricing_rules was cleared above to protect the discount).
		rule_labels = _resolve_pricing_rule_labels(applied_rule_names_seen)
		for item in invoice_doc.get("items", []):
			names = getattr(item, "_applied_rule_names", None) or []
			item.pos_applied_pricing_rules = (
				", ".join(rule_labels.get(n, n) for n in names) if names else ""
			)

```

- [ ] **Step 3: Verify the module still imports**

Run: `bench --site pos-dev execute pos_next.api.invoices._resolve_pricing_rule_labels --kwargs "{'rule_names': []}"`
Expected: returns `{}`, no error (confirms no syntax error in the edited file).

- [ ] **Step 4: Commit**

```bash
git add pos_next/api/invoices.py
git commit -m "feat: stamp pos_applied_pricing_rules on each invoice item at save"
```

---

## Task 4: Test — applied rule name is stamped, empty when none

**Files:**
- Modify: `pos_next/test_promotions.py` (add a method to `class TestPromotions`)

The existing `_make_rule` creates a **standalone** Pricing Rule with a `title` and no `promotional_scheme`, so per the precedence the label is `"{title} ({rule_name})"`. We assert that, plus the empty-string case for an item with no applicable rule. (Implementation lands in Tasks 1-3, so this test verifies the behavior rather than driving it red-first; if you prefer strict TDD, run Steps before Task 1-3 and confirm it fails on a missing attribute first.)

- [ ] **Step 1: Write the test**

Add this method verbatim inside `class TestPromotions` in `pos_next/test_promotions.py` (e.g. after `test_discount_percentage`). It reuses the file's existing helpers (`_make_rule`, `_cart_payload`, `_line`, `_apply_offers_and_stamp`, `_submit_invoice`, `flt`, `ITEM_A`, `ITEM_B`). `paid_amount` is computed from the stamped payload (the cart's net total) rather than hard-coded.

```python
	def test_applied_pricing_rule_name_stamped(self):
		"""The discounted line records the rule label 'Title (RULE-ID)'; an
		undiscounted line records an empty string."""
		rule = _make_rule(
			"_PNXT_TEST_AppliedName",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			rate_or_discount="Discount Percentage",
			price_or_product_discount="Price",
			discount_percentage=15,
		)
		payload = _cart_payload(
			self.ctx,
			[_line(self.ctx, ITEM_A, qty=1), _line(self.ctx, ITEM_B, qty=1)],
		)
		_apply_offers_and_stamp(payload, [rule])
		paid = sum(flt(i["rate"]) * flt(i["qty"]) for i in payload["items"])
		final = _submit_invoice(self.ctx, payload, paid_amount=paid)

		line_a = next(i for i in final.items if i.item_code == ITEM_A)
		line_b = next(i for i in final.items if i.item_code == ITEM_B)

		expected_label = f"_PNXT_TEST_AppliedName ({rule})"
		self.assertEqual(line_a.pos_applied_pricing_rules, expected_label)
		self.assertEqual((line_b.pos_applied_pricing_rules or ""), "")
		self.assertEqual((line_a.pricing_rules or ""), "")
```

- [ ] **Step 2: Run the test to confirm it passes against the implementation**

(Confirm with the user that scoped `run-tests --module` is acceptable per Testing Notes before running.)

Run: `bench --site pos-dev run-tests --module pos_next.test_promotions --test test_applied_pricing_rule_name_stamped`
Expected: 1 test, PASS.

If it FAILS because `ITEM_B` is unexpectedly discounted by another active rule, change the second line to a third item that no test rule targets, or assert `line_b.pos_applied_pricing_rules` does not contain the test rule id. Inspect with:
`bench --site pos-dev execute frappe.client.get_value --kwargs "{'doctype':'Sales Invoice Item','filters':{'parent':'<inv>','item_code':'<ITEM_B>'},'fieldname':['pos_applied_pricing_rules']}"`

- [ ] **Step 3: Run the full promotions suite to confirm no regression**

Run: `bench --site pos-dev run-tests --module pos_next.test_promotions`
Expected: all existing tests still PASS (the change only adds a field; discount math is untouched).

- [ ] **Step 4: Commit**

```bash
git add pos_next/test_promotions.py
git commit -m "test: assert applied pricing rule name is stamped on invoice item"
```

---

## Task 5: Manual Desk verification

- [ ] **Step 1: Confirm the field renders in Desk**

Open an invoice created by the test (or ring a real POS sale that applies a rule on pos-dev), open the item row in Desk, and confirm the **Applied Pricing Rules** field shows `Title (RULE-ID)` and is read-only.

- [ ] **Step 2: Confirm print behavior (optional)**

If a print format is configured, confirm the field prints only when it has a value (`print_hide_if_no_value: 1`).

- [ ] **Step 3: No commit** (verification only).

---

## Self-Review Checklist (completed by plan author)

- **Spec coverage:** custom field (Task 1), populate at clear-site with batched resolution + precedence (Tasks 2-3), per-item granularity (Task 3 loop), scheme-title+id format with standalone fallback (Task 2 helper + Task 4 assertion), no math/one-time change (Task 3 inserts before the one-time block, leaves it intact), error degradation (Task 2 try/except), tests incl. empty + standalone (Task 4), migration/rollout (Task 1 Step 2). Historical-backfill non-goal: not implemented, by design.
- **Placeholder scan:** the intermediate placeholder line in Task 4 Step 1 is explicitly flagged as "do not keep" and the verbatim full method is provided.
- **Type/name consistency:** `_resolve_pricing_rule_labels` (defined Task 2, used Task 3); field `pos_applied_pricing_rules` (Task 1 JSON, Task 3 stamp, Task 4 assertion); transient `item._applied_rule_names` (set Task 3 Step 1, read Task 3 Step 2) — all consistent.
