# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""The F&F comparison evidence survives the POS submit (UI test D-10).

The POS route: the payment dialog saves the cart as an unpaid draft
(``update_invoice``), then submits that draft by name with the payments
(``submit_invoice``), sending its rows as ``formatItemsForSubmission`` does: the
server-signed ``posnext_fnf_replaced_discount`` is never sent.

	bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.api.test_fnf_submit_evidence'}"
"""

import json
import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from pos_next.api import invoices
from pos_next.api.invoices import submit_invoice, update_invoice
from pos_next.api.test_ff_markers import enable_ff
from pos_next.optional_apps import promotions_installed
from pos_next.test_promotions import (
	CUSTOMER,
	ITEM_A,
	ITEM_B,
	ITEM_C,
	ITEM_PRICES,
	_cart_payload,
	_ctx,
	_line,
	_make_rule,
	_resolve_customer_group,
	_resolve_territory,
)

PREFIX = "_PNXT_F5_"
FNF = invoices.FNF_DISCOUNT_SOURCE
REPLACED = "posnext_fnf_replaced_discount"
LOG = "Friends and Family Log"


class TestFnfSubmitEvidence(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not promotions_installed():
			raise unittest.SkipTest("posnext_promotions is not installed")
		cls.ctx = _ctx()

	def setUp(self):
		frappe.set_user("Administrator")
		token = frappe.generate_hash(length=8).lower()
		self.customer = (
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": f"{PREFIX}{token}",
					"customer_group": _resolve_customer_group(),
					"territory": _resolve_territory(),
					"customer_type": "Individual",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		enable_ff(self, self.customer, f"f5{token}.example")

	def _rule(self, item_code, pct):
		name = _make_rule(
			f"{PREFIX}{item_code}_{pct}",
			apply_on="Item Code",
			items=[{"item_code": item_code}],
			rate_or_discount="Discount Percentage",
			discount_percentage=pct,
		)
		self.addCleanup(frappe.delete_doc, "Pricing Rule", name, force=True, ignore_permissions=True)
		return name

	def _discard(self, name):
		if not frappe.db.exists("Sales Invoice", name):
			return
		doc = frappe.get_doc("Sales Invoice", name)
		if doc.docstatus == 1:
			doc.flags.ignore_permissions = True
			doc.cancel()
		frappe.delete_doc("Sales Invoice", name, force=True, ignore_permissions=True)

	def _pos_sale(self, line):
		"""Payment open (unpaid draft), then the paid by-name submit with the cart rows."""
		payload = _cart_payload(self.ctx, [line])
		payload["customer"] = self.customer
		draft = update_invoice(json.dumps(dict(payload, payments=[])))
		self.addCleanup(self._discard, draft["name"])
		# The cart adopts the draft's prices (adoptServerDraft); it never sends the
		# signed replaced-discount field back.
		row = next(r for r in draft["items"] if not r.get("is_free_item"))
		sent = dict(line)
		for key in ("rate", "discount_percentage", "discount_amount", "posnext_discount_source"):
			sent[key] = row.get(key)
		if row.get("posnext_discount_source") != FNF:
			sent["pricing_rules"] = line.get("pricing_rules")
		amount = flt(draft["grand_total"]) or flt(sent["rate"]) * flt(sent["qty"])
		invoice = dict(
			payload,
			name=draft["name"],
			items=[sent],
			payments=[{"mode_of_payment": self.ctx.mode_of_payment, "amount": flt(draft.get("rounded_total") or amount)}],
		)
		result = submit_invoice(invoice=json.dumps(invoice, default=str), data=json.dumps({}))
		return draft, frappe.get_doc("Sales Invoice", result["name"])

	def test_fnf_win_keeps_the_signed_replaced_discount(self):
		"""(a) F&F 30% beats a 20% rule: the saved row keeps the signed replaced discount."""
		rule = self._rule(ITEM_B, 20)
		line = _line(self.ctx, ITEM_B)
		price = ITEM_PRICES[ITEM_B]
		line.update(
			{
				"rate": price * 0.8,
				"discount_percentage": 20,
				"discount_amount": price * 0.2,
				"pricing_rules": rule,
			}
		)
		draft, doc = self._pos_sale(line)
		row = doc.items[0]
		self.assertEqual(row.posnext_discount_source, FNF, draft["items"])
		self.assertEqual(flt(row.rate), price * 0.7)
		self.assertTrue(row.get(REPLACED), "the submitted F&F row lost its signed replaced discount")
		self.assertEqual(row.get(REPLACED), draft["items"][0].get(REPLACED))
		# Still a valid signature for the submitted row (string path: no promotions import).
		verify = frappe.get_attr("posnext_promotions.promotions.ff_snapshot.verify")
		data = verify(row, row.get(REPLACED), doc=doc)
		self.assertIsNotNone(data, "the carried snapshot does not verify on the submitted row")
		self.assertEqual(flt(data["discount_percentage"]), 20)

	def test_snapshot_not_carried_to_a_changed_row(self):
		"""A row that is not the stored F&F row (other qty) gets no snapshot."""
		rule = self._rule(ITEM_B, 20)
		line = _line(self.ctx, ITEM_B)
		price = ITEM_PRICES[ITEM_B]
		line.update({"rate": price * 0.8, "discount_percentage": 20, "discount_amount": price * 0.2, "pricing_rules": rule})
		payload = _cart_payload(self.ctx, [line])
		payload["customer"] = self.customer
		draft = update_invoice(json.dumps(dict(payload, payments=[])))
		self.addCleanup(self._discard, draft["name"])
		self.assertTrue(draft["items"][0].get(REPLACED))
		doc = frappe.get_doc("Sales Invoice", draft["name"])
		doc.update({"items": [dict(line, qty=2, rate=price * 0.7, posnext_discount_source=FNF)]})
		invoices._carry_fnf_snapshots(doc, invoices._stored_fnf_snapshots(frappe.get_doc("Sales Invoice", draft["name"])))
		self.assertFalse(doc.items[0].get(REPLACED))

	def _promotion_win(self):
		rule = self._rule(ITEM_C, 40)
		line = _line(self.ctx, ITEM_C)
		price = ITEM_PRICES[ITEM_C]
		line.update(
			{
				"rate": price * 0.6,
				"discount_percentage": 40,
				"discount_amount": price * 0.4,
				"pricing_rules": rule,
			}
		)
		_draft, doc = self._pos_sale(line)
		row = doc.items[0]
		self.assertNotEqual(row.posnext_discount_source, FNF)
		self.assertEqual(flt(row.rate), price * 0.6)
		return rule, doc, row

	def test_promotion_win_keeps_its_rule_tag(self):
		"""(b1) A 40% rule beats F&F 30%: the submitted row carries the rule the server's
		own evaluation applied (Ruling 137), written at before_submit, and keeps its rate."""
		rule, doc, row = self._promotion_win()
		self.assertEqual(invoices._rule_names(row.pricing_rules or ""), [rule])
		stored = frappe.db.get_value("Sales Invoice Item", row.name, ["pricing_rules", "rate"], as_dict=True)
		self.assertEqual(stored.pricing_rules, rule)
		self.assertEqual(flt(stored.rate), ITEM_PRICES[ITEM_C] * 0.6)
		self.assertEqual(flt(doc.outstanding_amount), 0)

	def _desk_copy(self, doc, amend):
		"""What Desk's Amend (after Cancel) or Duplicate inserts: frappe.copy_doc."""
		if amend:
			doc.reload()
			doc.flags.ignore_permissions = True
			doc.cancel()
		copy = frappe.copy_doc(doc)
		if amend:
			copy.amended_from = doc.name
		copy.docstatus = 0
		copy.insert(ignore_permissions=True)
		self.addCleanup(self._discard, copy.name)
		return copy

	def test_desk_amend_keeps_the_promotion_price(self):
		"""N-1 (Ruling 140): Amend a cancelled POS sale on Desk, save twice, submit: the
		row stays at 12 and the invoice is fully paid."""
		_rule, doc, _row = self._promotion_win()
		price = ITEM_PRICES[ITEM_C]
		copy = self._desk_copy(doc, amend=True)
		copy.save(ignore_permissions=True)
		copy.save(ignore_permissions=True)
		copy.submit()
		copy.reload()
		self.assertEqual(flt(copy.items[0].rate), price * 0.6)
		self.assertEqual(flt(copy.outstanding_amount), 0)
		self.assertFalse(copy.items[0].pricing_rules)

	def test_desk_duplicate_keeps_the_promotion_price(self):
		_rule, doc, _row = self._promotion_win()
		copy = self._desk_copy(doc, amend=False)
		copy.save(ignore_permissions=True)
		copy.reload()
		self.assertEqual(flt(copy.items[0].rate), ITEM_PRICES[ITEM_C] * 0.6)
		self.assertFalse(copy.items[0].pricing_rules)

	def test_non_pos_desk_invoice_keeps_its_rule(self):
		"""A Desk (non-POS) invoice that ERPNext prices from its rule is left alone."""
		rule = self._rule(ITEM_C, 40)
		doc = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": self.ctx.company,
				"customer": self.customer,
				"currency": self.ctx.currency,
				"selling_price_list": self.ctx.price_list,
				"items": [{"item_code": ITEM_C, "qty": 1, "uom": "Nos", "warehouse": self.ctx.warehouse}],
			}
		).insert(ignore_permissions=True)
		self.addCleanup(self._discard, doc.name)
		doc.save(ignore_permissions=True)
		doc.reload()
		self.assertEqual(invoices._rule_names(doc.items[0].pricing_rules or ""), [rule])
		self.assertEqual(flt(doc.items[0].rate), ITEM_PRICES[ITEM_C] * 0.6)

	def test_pos_draft_keeps_its_gift_tag(self):
		"""A POS draft's BXGY gift row keeps its rule through update_invoice and submit
		(8q's tag judge reads it): pos_next API saves are never blanked."""
		gift = _make_rule(
			f"{PREFIX}GIFT",
			apply_on="Item Code",
			items=[{"item_code": ITEM_B}],
			price_or_product_discount="Product",
			rate_or_discount="Discount Percentage",
			same_item=0,
			free_item=ITEM_A,
			min_qty=1,
			free_qty=1,
			free_item_uom="Nos",
			free_item_rate=0,
			applicable_for="Customer",
			customer=CUSTOMER,
		)
		self.addCleanup(frappe.delete_doc, "Pricing Rule", gift, force=True, ignore_permissions=True)
		free = _line(self.ctx, ITEM_A, price_list_rate=0)
		free.update({"is_free_item": 1, "pricing_rules": gift})
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_B), free])
		payload["customer"] = CUSTOMER
		draft = update_invoice(json.dumps(payload))
		self.addCleanup(self._discard, draft["name"])
		stored = frappe.get_doc("Sales Invoice", draft["name"])
		self.assertEqual([r.pricing_rules for r in stored.items if r.is_free_item], [gift])
		paid = [{"mode_of_payment": self.ctx.mode_of_payment, "amount": ITEM_PRICES[ITEM_B]}]
		submit_invoice(invoice=json.dumps(dict(payload, name=draft["name"], payments=paid)), data=json.dumps({}))
		done = frappe.get_doc("Sales Invoice", draft["name"])
		self.assertEqual(done.docstatus, 1)
		self.assertEqual([r.pricing_rules for r in done.items if r.is_free_item], [gift])

	def test_smaller_manual_discount_not_tagged_with_the_offer(self):
		"""N-2: a row discounted less than the offer gives is not stamped with its rule."""
		self._rule(ITEM_C, 40)
		price = ITEM_PRICES[ITEM_C]
		line = _line(self.ctx, ITEM_C)
		line.update({"rate": price * 0.9, "discount_percentage": 10, "discount_amount": price * 0.1})
		payload = _cart_payload(self.ctx, [line])
		payload["customer"] = self.customer
		payload["payments"] = [{"mode_of_payment": self.ctx.mode_of_payment, "amount": price * 0.9}]
		result = submit_invoice(invoice=json.dumps(payload), data=json.dumps({}))
		self.addCleanup(self._discard, result["name"])
		row = frappe.get_doc("Sales Invoice", result["name"]).items[0]
		self.assertEqual(flt(row.rate), price * 0.9)
		self.assertFalse(row.pricing_rules)

	def test_rule_tag_on_the_create_path(self):
		"""A paid submit with no stored draft (submit_invoice creates it) is tagged too."""
		rule = self._rule(ITEM_C, 40)
		price = ITEM_PRICES[ITEM_C]
		line = _line(self.ctx, ITEM_C)
		line.update({"rate": price * 0.6, "discount_percentage": 40, "discount_amount": price * 0.4, "pricing_rules": rule})
		payload = _cart_payload(self.ctx, [line])
		payload["customer"] = self.customer
		payload["payments"] = [{"mode_of_payment": self.ctx.mode_of_payment, "amount": price * 0.6}]
		result = submit_invoice(invoice=json.dumps(payload), data=json.dumps({}))
		self.addCleanup(self._discard, result["name"])
		row = frappe.get_doc("Sales Invoice", result["name"]).items[0]
		self.assertEqual(row.pricing_rules, rule)

	def test_client_rule_name_never_stored(self):
		"""A name the server's evaluation did not apply is never written: an unpaid-rule
		row priced at list carries none, and a forged name on a manual row is dropped."""
		decoy = self._rule(ITEM_B, 20)
		price = ITEM_PRICES[ITEM_C]
		line = _line(self.ctx, ITEM_C)
		line.update({"pricing_rules": decoy})
		payload = _cart_payload(self.ctx, [line])
		payload["customer"] = self.customer
		payload["payments"] = [{"mode_of_payment": self.ctx.mode_of_payment, "amount": price}]
		result = submit_invoice(invoice=json.dumps(payload), data=json.dumps({}))
		self.addCleanup(self._discard, result["name"])
		row = frappe.get_doc("Sales Invoice", result["name"]).items[0]
		self.assertFalse(row.pricing_rules)

	@unittest.expectedFailure
	def test_promotion_win_logs_comparison_lost(self):
		"""(b2) The line the promotion won has a Comparison Lost log.

		Open (posnext_promotions): a paid save is frozen (``_freeze_paid_invoice``), so the
		submit has no F&F decision and ``log_invoice_submit`` logs only the F&F rows."""
		_rule, doc, row = self._promotion_win()
		logged = frappe.get_all(
			LOG,
			filters={
				"reference_name": doc.name,
				"item_code": row.item_code,
				"log_type": "Comparison Lost",
				"creation": [">=", doc.creation],
			},
			pluck="name",
		)
		self.assertTrue(logged, "no Comparison Lost log for the line the promotion won")
