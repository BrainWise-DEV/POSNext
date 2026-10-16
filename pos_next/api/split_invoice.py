# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Split one POS sale into one Sales Invoice per company.

A branch (nextend Warehouse Group) can hold warehouses of several companies
(PT/CV) while running a single POS Profile. The cashier still rings up one
basket and takes one payment; this module decides which warehouse every row
ships from and bills each company on its own invoice:

* ``plan_sale`` - allocate every row that ships from the branch (session
  warehouse first, then the branch's other warehouses, oldest restock first),
  then group rows per company. A row that needs two warehouses becomes one
  invoice row per warehouse. A branch warehouse the cashier picked by hand is
  drawn first, unless POS Settings.store_stock_first says the session
  warehouse must run out first. ``preview_allocation`` shows the cart the
  same allocation; the sale is refused when it changed since
  (``check_allocation``).
* ``submit_split_sale`` - create every invoice in the request's transaction,
  share the basket discount and the payment between them, and submit them all
  (or keep them all as drafts when a ``pos_next_split_hold`` hook says so).

The cart side stays one row per item + UOM; only the submitted payload is
split here, so promotions keep working on the whole basket.
"""

import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt

from pos_next.api.items import get_session_scope, get_session_stock

# Invoice header keys that must not be copied from the basket to each invoice.
_PER_INVOICE_KEYS = (
	"name",
	"items",
	"payments",
	"discount_amount",
	"additional_discount_percentage",
	"coupon_code",
	"offline_id",
	"grand_total",
	"rounded_total",
	"total",
	"net_total",
	"total_tax",
	"total_discount",
	"change_amount",
	"write_off_amount",
	"paid_amount",
)


def plan_sale(invoice):
	"""Return ``{"groups": [{"company", "items"}], "split": bool}``.

	Groups are in billing order: the POS Profile's company first. ``split`` is
	true when the sale needs more than one invoice or is billed to a company
	other than the POS Profile's - both go through ``submit_split_sale``.
	"""
	profile = frappe.get_cached_doc("POS Profile", invoice.get("pos_profile"))
	items = [dict(row) for row in invoice.get("items") or []]
	expected = invoice.pop("expected_allocation", None)

	# SPG order rows ship from the warehouse the order locked.
	if not invoice.get("custom_pos_order"):
		_allocate_rows(items, profile)
	if expected is not None:
		check_allocation(items, expected)
	for row in items:
		row.pop("warehouse_manual", None)

	company_by_warehouse = dict(
		frappe.get_all(
			"Warehouse",
			filters={"name": ["in", list({row.get("warehouse") for row in items if row.get("warehouse")})]},
			fields=["name", "company"],
			as_list=True,
		)
	)
	base_company = {
		row["custom_addon_key"]: company_by_warehouse.get(row.get("warehouse"))
		for row in items
		if row.get("custom_addon_key")
	}

	grouped = {}
	for row in items:
		# Add on rows carry no stock of their own and always bill with their base.
		company = base_company.get(row.get("custom_addon_parent_key")) or company_by_warehouse.get(
			row.get("warehouse")
		)
		grouped.setdefault(company or profile.company, []).append(row)

	order = sorted(grouped, key=lambda company: company != profile.company)
	groups = [{"company": company, "items": grouped[company]} for company in order]
	split = bool(groups) and (len(groups) > 1 or groups[0]["company"] != profile.company)
	return {"groups": groups, "split": split}


def _allocate_rows(items, profile):
	"""Spread branch rows over the branch warehouses, in place.

	Each row fills from the session warehouse first and spills to the branch's
	other warehouses (oldest restock first). Rows of the same item draw from one
	running balance, so a free-item row cannot reuse stock its paid row took.
	Whatever the branch cannot cover stays on the first warehouse, where the
	usual stock validation reports it.

	The cart keeps one row per item + UOM, so a hand-picked branch warehouse
	cannot pin the whole row - it would carry qty the cashier added from the
	session warehouse too. It only moves to the front of the order, and not
	even that while store_stock_first is on. A hand-picked warehouse outside
	the branch joins the end of the order and supplies whatever the branch
	cannot (its own stock is checked on submit).
	"""
	scope = get_session_scope(profile)
	branch = scope["branch"]
	picked_outside = any(
		cint(row.get("warehouse_manual")) and row.get("warehouse") not in branch for row in items
	)
	if len(branch) < 2 and not picked_outside:
		return

	candidates = [row for row in items if _is_auto_allocated(row, branch)]
	if not candidates:
		return
	candidate_ids = {id(row) for row in candidates}

	item_codes = list({row["item_code"] for row in candidates})
	stock = get_session_stock(item_codes, profile)
	order_by_item = {code: _warehouse_order(code, branch, scope["native"]) for code in item_codes}
	whole_uoms = set(frappe.get_all("UOM", filters={"must_be_whole_number": 1}, pluck="name"))
	store_first = store_stock_first(profile.name)

	remaining = {code: dict((stock.get(code) or {}).get("stock_by_warehouse") or {}) for code in item_codes}
	need = defaultdict(float)
	for row in candidates:
		need[row["item_code"]] += flt(row.get("qty")) * (flt(row.get("conversion_factor")) or 1.0)
	allocated = []
	for row in items:
		if id(row) not in candidate_ids:
			allocated.append(row)
			continue
		order = order_by_item[row["item_code"]]
		picked = row.get("warehouse")
		manual = cint(row.get("warehouse_manual"))
		if manual and picked and picked not in order:
			order = [*order, picked]
			remaining[row["item_code"]].setdefault(picked, need[row["item_code"]])
		if manual and not store_first:
			order = [picked] + [warehouse for warehouse in order if warehouse != picked]
		allocated.extend(_split_row(row, order, remaining[row["item_code"]], whole_uoms))
	# Add ons ship (and bill) with their base row's first chunk.
	base_warehouse = {
		row["custom_addon_key"]: row.get("warehouse") for row in allocated if row.get("custom_addon_key")
	}
	for row in allocated:
		if row.get("custom_addon_parent_key") in base_warehouse:
			row["warehouse"] = base_warehouse[row["custom_addon_parent_key"]]
	items[:] = allocated


@frappe.whitelist()
def preview_allocation(pos_profile, items):
	"""Where ``_allocate_rows`` ships each cart row from, for the cart to show
	before the sale is paid: ``[[{"warehouse", "qty"}, ...], ...]`` per row of
	``items``, in order."""
	profile = frappe.get_cached_doc("POS Profile", pos_profile)
	items = [dict(row, _row=index) for index, row in enumerate(frappe.parse_json(items) or [])]
	result = [[] for _ in items]
	_allocate_rows(items, profile)
	company = dict(
		frappe.get_all(
			"Warehouse",
			filters={"name": ["in", list({row.get("warehouse") for row in items})]},
			fields=["name", "company"],
			as_list=True,
		)
	)
	abbr = dict(frappe.get_all("Company", fields=["name", "abbr"], as_list=True))
	for row in items:
		warehouse = row.get("warehouse")
		result[row["_row"]].append(
			{
				"warehouse": warehouse,
				"qty": flt(row.get("qty")),
				"company": company.get(warehouse),
				"abbr": abbr.get(company.get(warehouse)),
			}
		)
	return result


def check_allocation(items, expected):
	"""Throw unless `items` ship from the warehouses the cart showed.

	``expected`` is ``[[item_code, warehouse, stock_qty], ...]`` from the cart's
	split preview. Stock that moved since the preview changes the allocation;
	the cashier must see that before the sale goes through. Add on rows carry
	no stock and are left out on both sides.
	"""
	actual = defaultdict(float)
	for row in items:
		if not row.get("custom_addon_parent_key"):
			factor = flt(row.get("conversion_factor")) or 1.0
			actual[(row.get("item_code"), row.get("warehouse"))] += flt(row.get("qty")) * factor
	shown = defaultdict(float)
	for item_code, warehouse, qty in frappe.parse_json(expected) or []:
		shown[(item_code, warehouse)] += flt(qty)

	changed = [key for key in actual.keys() | shown.keys() if flt(actual[key] - shown[key], 6)]
	if changed:
		frappe.throw(
			_("Pembagian gudang berubah karena stok berubah: {0}. Periksa keranjang lalu ulangi.").format(
				"; ".join(
					f"{item_code} {warehouse}: {flt(shown[(item_code, warehouse)], 3)} → "
					f"{flt(actual[(item_code, warehouse)], 3)}"
					for item_code, warehouse in changed
				)
			),
			title=_("Alokasi Gudang Berubah"),
		)


def store_stock_first(pos_profile):
	"""POS Settings.store_stock_first: the session warehouse must run out
	before another branch warehouse may supply a row. On unless a POS
	Settings record turns it off."""
	if not pos_profile:
		return True
	value = frappe.db.get_value(
		"POS Settings", {"pos_profile": pos_profile, "enabled": 1}, "store_stock_first"
	)
	return value is None or bool(cint(value))


def _is_auto_allocated(row, branch):
	if row.get("custom_addon_parent_key"):
		return False
	if row.get("batch_no") or row.get("serial_no"):
		return False
	# A warehouse outside the branch only comes in when the cashier picked it.
	return not row.get("warehouse") or row.get("warehouse") in branch or cint(row.get("warehouse_manual"))


def _warehouse_order(item_code, branch, native):
	others = [warehouse for warehouse in branch if warehouse != native]
	try:
		from nextend.warehouse_group import resolve_stock_order

		others = resolve_stock_order(item_code, others)
	except ImportError:
		pass
	return ([native] if native in branch else []) + others


def _split_row(row, warehouses, remaining, whole_uoms):
	"""One row per warehouse that supplies part of `row`, in `warehouses` order."""
	factor = flt(row.get("conversion_factor")) or 1.0
	qty = flt(row.get("qty"))
	if qty <= 0:
		return [row]

	chunks = []
	left = qty
	for warehouse in warehouses:
		if left <= 0:
			break
		available = flt(remaining.get(warehouse)) / factor
		if row.get("uom") in whole_uoms:
			available = int(available)
		take = min(left, available)
		if take <= 0:
			continue
		chunks.append([warehouse, take])
		remaining[warehouse] = flt(remaining.get(warehouse)) - take * factor
		left -= take

	if left > 0:
		if chunks and chunks[0][0] == warehouses[0]:
			chunks[0][1] += left
		else:
			chunks.insert(0, [warehouses[0], left])
		remaining[warehouses[0]] = flt(remaining.get(warehouses[0])) - left * factor

	rows = []
	discount = flt(row.get("discount_amount"))
	for index, (warehouse, chunk_qty) in enumerate(chunks):
		new_row = dict(row, warehouse=warehouse, qty=chunk_qty)
		# discount_amount is the row total here (see update_invoice), not per unit
		new_row["discount_amount"] = discount * chunk_qty / qty
		if index:
			# The add on key must stay unique in an invoice; add ons and the
			# tinting of a tinted base (one machine job) follow the first chunk.
			for field in ("custom_addon_key", "custom_hpp_tinta", "custom_tinting_job"):
				new_row.pop(field, None)
		rows.append(new_row)
	return rows


def submit_split_sale(invoice, data, plan):
	"""Create, pay and submit one invoice per plan group in this transaction.

	Returns the first (primary) invoice's result with every invoice listed
	under ``invoices``, or a hold hook's response when the invoices have to
	wait as drafts.
	"""
	from pos_next.api.invoices import _set_payment_accounts, submit_invoice, update_invoice

	_validate_split_sale(invoice, data, plan)

	groups = plan["groups"]
	split_ref = frappe.generate_hash(length=10)
	header = {key: value for key, value in invoice.items() if key not in _PER_INVOICE_KEYS}
	discounts = _prorate(
		flt(invoice.get("discount_amount")), [_items_net(group["items"]) for group in groups]
	)

	drafts = []
	for index, group in enumerate(groups):
		payload = dict(
			header,
			company=group["company"],
			items=group["items"],
			payments=[],
			discount_amount=discounts[index],
			posa_split_ref=split_ref,
		)
		if index == 0 and invoice.get("coupon_code"):
			payload["coupon_code"] = invoice["coupon_code"]
		drafts.append(update_invoice(json.dumps(payload, default=str)))

	totals = [flt(draft.get("rounded_total")) or flt(draft.get("grand_total")) for draft in drafts]
	payments = _allocate_payments(invoice.get("payments") or [], totals)

	for draft, draft_payments in zip(drafts, payments, strict=True):
		# Not through update_invoice again: it would re-derive row discounts from
		# the saved (per unit) discount_amount and move the totals just shared out.
		doc = frappe.get_doc("Sales Invoice", draft["name"])
		doc.set("payments", draft_payments)
		_set_payment_accounts(doc.payments, doc.company)
		doc.flags.ignore_permissions = True
		doc.save()

	names = [draft["name"] for draft in drafts]
	for hook in frappe.get_hooks("pos_next_split_hold"):
		held = frappe.get_attr(hook)(names, invoice.get("offline_id"))
		if held:
			return dict(held, split_ref=split_ref, invoices=[{"name": name} for name in names])

	results = []
	for index, (name, draft_payments) in enumerate(zip(names, payments, strict=True)):
		child = {
			"doctype": "Sales Invoice",
			"name": name,
			"pos_profile": invoice.get("pos_profile"),
			"payments": draft_payments,
		}
		child_data = {}
		if index == 0:
			# Change and write-off belong to the primary invoice only.
			child_data["change_amount"] = data.get("change_amount") or invoice.get("change_amount")
			child_data["write_off_amount"] = data.get("write_off_amount") or invoice.get("write_off_amount")
			if invoice.get("coupon_code"):
				child["coupon_code"] = invoice["coupon_code"]
		result = submit_invoice(invoice=child, data=child_data)
		result["company"] = groups[index]["company"]
		results.append(result)

	return dict(results[0], split_ref=split_ref, invoices=results)


def _validate_split_sale(invoice, data, plan):
	"""Reject what a split sale does not support yet.

	Open points (credit, loyalty, combined returns) are tracked in nextend's
	planning notes - see pos-multi-company-open-questions.md.
	"""
	companies = ", ".join(group["company"] for group in plan["groups"])

	def get(key):
		return data.get(key) or invoice.get(key)

	if cint(get("is_return")):
		frappe.throw(_("Returns of a split sale are made per invoice."))
	if cint(get("is_credit_sale")) or get("receivable_account"):
		frappe.throw(
			_("This sale is billed to several companies ({0}) and must be paid in full.").format(companies),
			title=_("Split Sale"),
		)
	if flt(get("redeemed_customer_credit")) or get("customer_credit_dict"):
		frappe.throw(
			_("Customer credit cannot pay a sale billed to several companies ({0}).").format(companies),
			title=_("Split Sale"),
		)
	if cint(get("redeem_loyalty_points")) or flt(get("loyalty_points")):
		frappe.throw(
			_("Loyalty points cannot be used on a sale billed to several companies ({0}).").format(companies),
			title=_("Split Sale"),
		)

	paid = sum(flt(payment.get("amount")) for payment in invoice.get("payments") or [])
	if paid <= 0:
		frappe.throw(
			_("This sale is billed to several companies ({0}) and must be paid in full.").format(companies),
			title=_("Split Sale"),
		)


def _items_net(items):
	return sum(flt(row.get("qty")) * flt(row.get("rate")) for row in items)


def _prorate(amount, weights, precision=2):
	"""Split `amount` by `weights`; rounding remainder lands on the first share."""
	total = sum(weights)
	if not amount or not total:
		return [0.0] * len(weights)
	shares = [flt(amount * weight / total, precision) for weight in weights]
	shares[0] = flt(amount - sum(shares[1:]), precision)
	return shares


def _allocate_payments(payments, totals, precision=2):
	"""Payment rows per invoice for one basket payment.

	Every invoice but the first is paid exactly its total, split across payment
	modes in the basket's proportions. The first (primary) invoice takes the
	rest, change included.
	"""
	modes = [p for p in payments if flt(p.get("amount"))]
	per_invoice = [[] for _ in totals]
	left = {index: flt(p.get("amount")) for index, p in enumerate(modes)}

	for invoice_index in range(1, len(totals)):
		shares = _prorate(totals[invoice_index], [flt(p.get("amount")) for p in modes], precision)
		for index, share in enumerate(shares):
			left[index] = flt(left[index] - share, precision)
			if share:
				per_invoice[invoice_index].append(_payment_row(modes[index], share))

	per_invoice[0] = [_payment_row(modes[index], amount) for index, amount in left.items() if amount]
	return per_invoice


def _payment_row(payment, amount):
	return {
		"mode_of_payment": payment.get("mode_of_payment"),
		"amount": amount,
		"type": payment.get("type"),
	}
