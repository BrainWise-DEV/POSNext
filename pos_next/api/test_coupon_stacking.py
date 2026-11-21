# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""An "Add on top" POS Coupon stacked on a promoted line, end to end (G5, D-R2-15).

The POS sends the stacked line at the offer-priced rate minus the coupon. The server
explains that rate (``_coupon_line_rates`` prices the coupon on the server's own offer
pricing), stores the coupon-only part in ``posnext_coupon_share`` (recomputed on every
validate, never the client's) and counts only that part against the coupon's limits.

Needs ``Sales Invoice Item.posnext_coupon_share`` (posnext_promotions), so it runs on
pos-dev with both worktrees on PYTHONPATH:

	bench --site pos-dev execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.api.test_coupon_stacking'}"
"""

import json

import frappe
from frappe.utils import flt, nowdate

from pos_next.api.test_discount_enforcement import CUSTOMER, DiscountEnforcementCase
from pos_next.api.test_ff_markers import enable_ff
from pos_next.test_promotions import ITEM_A, ITEM_C, ITEM_PRICES, _make_rule

PREFIX = "_PNXT_G5_"
SHARE = "posnext_coupon_share"
REPLACED = "posnext_fnf_replaced_discount"
EMAIL_DOMAIN = "g5stack.example"


class TestCouponStacking(DiscountEnforcementCase):
	@classmethod
	def setUpClass(cls):
		# Registered first, so it runs after FrappeTestCase's rollback: a coupon submit
		# commits (usage counter), so what this class wrote may outlive the rollback.
		cls.addClassCleanup(cls._forget)
		cls.created_settings = None
		super().setUpClass()
		if not frappe.db.exists("POS Settings", {"pos_profile": cls.ctx.pos_profile}):
			cls.created_settings = (
				frappe.get_doc({"doctype": "POS Settings", "pos_profile": cls.ctx.pos_profile})
				.insert(ignore_permissions=True)
				.name
			)

	@classmethod
	def _forget(cls):
		"""Drop this class's POS Settings and its ``_PNXT_G5_`` Error Logs, if a commit kept them."""
		if cls.created_settings and frappe.db.exists("POS Settings", cls.created_settings):
			frappe.delete_doc("POS Settings", cls.created_settings, force=True, ignore_permissions=True)
		frappe.db.delete("Error Log", {"error": ["like", f"%{PREFIX}%"]})
		frappe.db.commit()

	def setUp(self):
		super().setUp()
		if not frappe.get_meta("Sales Invoice Item").has_field(SHARE):
			self.skipTest("Sales Invoice Item.posnext_coupon_share is not migrated on this site")
		# The coupon's share is the only explanation left for the cashier.
		self._pos_settings(allow_user_to_edit_item_discount=0)

	# ---- fixtures ----------------------------------------------------------

	def _rule(self, percentage, item=ITEM_A):
		name = _make_rule(
			f"{PREFIX}PROMO_{item}_{percentage}",
			apply_on="Item Code",
			items=[{"item_code": item}],
			price_or_product_discount="Price",
			rate_or_discount="Discount Percentage",
			discount_percentage=percentage,
			applicable_for="Customer",
			customer=CUSTOMER,
		)
		self.addCleanup(frappe.delete_doc, "Pricing Rule", name, force=True, ignore_permissions=True)
		return name

	def _coupon(self, percentage=10, max_amount=10, conflict="Add on top", suffix="ADD"):
		code = f"{PREFIX}{suffix}"
		existing = frappe.db.get_value("POS Coupon", {"coupon_code": code}, "name")
		if existing:
			frappe.delete_doc("POS Coupon", existing, force=True, ignore_permissions=True)
		coupon = frappe.get_doc(
			{
				"doctype": "POS Coupon",
				"coupon_name": code,
				"coupon_code": code,
				"coupon_type": "Promotional",
				"company": self.ctx.company,
				"discount_type": "Percentage",
				"discount_percentage": percentage,
				"max_amount": max_amount,
				"apply_on": "Net Total",
				"apply_scope": "All Eligible Items",
				"promotion_conflict": conflict,
				"maximum_use": 100,
			}
		).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "POS Coupon", coupon.name, force=True, ignore_permissions=True)
		return code

	def _coupon_row_payload(self, code, rate, qty=2, item=ITEM_A, rule=None, **row):
		"""The cart's stacked coupon line as ``formatItemsForSubmission`` sends it."""
		payload = self._payload(
			rate,
			discount_percentage=0,
			item=item,
			qty=qty,
			pricing_rules=rule or "",
			discount_source="coupon",
			posnext_coupon_code=code,
			**row,
		)
		line = payload["items"][0]
		line["discount_amount"] = flt(flt(line["price_list_rate"]) - rate, 6)
		payload["coupon_code"] = code
		return payload

	def _submitted(self, payload, offline=False):
		doc = self._submit(payload, offline=offline)
		self.addCleanup(self._discard, doc.name)
		return doc

	def _discard(self, name):
		for ret in frappe.get_all("Sales Invoice", filters={"return_against": name}, pluck="name"):
			self._discard(ret)
		if not frappe.db.exists("Sales Invoice", name):
			return
		doc = frappe.get_doc("Sales Invoice", name)
		if doc.docstatus == 1:
			doc.flags.ignore_permissions = True
			doc.cancel()
		frappe.delete_doc("Sales Invoice", name, force=True, ignore_permissions=True)

	def _cart_snapshot(self, customer, item, qty, rule):
		"""The signed snapshot the cart holds for an F&F line over ``rule`` (apply_offers)."""
		payload = self._payload(ITEM_PRICES[item], item=item, qty=qty)
		payload["customer"] = customer
		payload["items"][0]["pricing_rules"] = rule
		apply_offers = frappe.get_attr("posnext_promotions.api.offers.apply_offers")
		line = apply_offers(json.dumps(payload))["items"][0]
		self.assertEqual(line.get("discount_source"), "friends_and_family", line)
		self.assertTrue(line.get(REPLACED), line)
		return line[REPLACED]

	# ---- stacked line on a promotion (non-F&F customer) ----------------------

	def test_stacked_line_saved_with_its_coupon_share(self):
		# 50 - 20% promo = 40, + 10% "Add on top" = 36 (4 coupon per unit, x2 = 8 <= max 10).
		rule = self._rule(20)
		code = self._coupon()
		doc = self._draft(self._coupon_row_payload(code, 36, rule=rule))
		row = doc.items[0]
		self.assertEqual(flt(row.rate), 36)
		self.assertEqual(row.posnext_coupon_code, code)
		self.assertAlmostEqual(flt(row.get(SHARE)), 4)
		# Deeper than promotion + coupon is still a manual discount.
		self.assertRefused(self._coupon_row_payload(code, 35, rule=rule), "rate editing is not allowed")

	def test_stacked_line_paid_submit_keeps_the_share(self):
		rule = self._rule(20)
		code = self._coupon()
		doc = self._submitted(self._coupon_row_payload(code, 36, rule=rule))
		self.assertEqual(doc.docstatus, 1)
		self.assertAlmostEqual(flt(doc.items[0].get(SHARE)), 4)

	def test_client_share_is_overwritten(self):
		rule = self._rule(20)
		code = self._coupon(max_amount=0)
		payload = self._coupon_row_payload(code, 36, rule=rule, **{SHARE: 0.01})
		plain = dict(payload["items"][0])
		plain.update(
			{
				"item_code": ITEM_C,
				"price_list_rate": 20,
				"rate": 18,
				"discount_amount": 2,
				"pricing_rules": "",
				SHARE: 999,
			}
		)
		payload["items"].append(plain)
		doc = self._draft(payload)
		self.assertAlmostEqual(flt(doc.items[0].get(SHARE)), 4)
		# A plain coupon line: the share is its whole coupon discount, as before.
		self.assertAlmostEqual(flt(doc.items[1].get(SHARE)), 2)

	def test_untagged_row_share_is_zero(self):
		payload = self._payload(50, **{SHARE: 7})
		doc = self._draft(payload)
		self.assertEqual(flt(doc.items[0].get(SHARE)), 0)

	def test_offline_sync_recomputes_the_share(self):
		rule = self._rule(20)
		code = self._coupon()
		doc = self._submitted(self._coupon_row_payload(code, 36, rule=rule, **{SHARE: 9}), offline=True)
		self.assertEqual(doc.docstatus, 1)
		self.assertAlmostEqual(flt(doc.items[0].get(SHARE)), 4)

	def test_offline_sync_kept_when_the_promotion_is_gone(self):
		# G5 review I-1: rung up offline at 23:50 (ITEM_A x2 at 50, 20% promo, 10% "Add on
		# top" with max 10, paid 72); the promo is disabled before the sale syncs. The server
		# can no longer see the promotion, so the share is the whole 14 a unit (28 > 10):
		# kept and logged, never stranded in the offline queue.
		rule = self._rule(20)
		code = self._coupon()
		payload = self._coupon_row_payload(code, 36, rule=rule)
		payload["posting_time"] = "23:50:00"
		frappe.db.set_value("Pricing Rule", rule, "disable", 1)
		doc = self._submitted(payload, offline=True)
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(flt(doc.paid_amount), 72)
		self.assertAlmostEqual(flt(doc.items[0].get(SHARE)), 14)
		logs = frappe.get_all(
			"Error Log",
			filters={"method": "POS Coupon check kept on offline sync", "error": ["like", f"%{code}%"]},
			pluck="error",
		)
		self.assertTrue(logs)
		self.assertIn("exceeds its limit of 10", logs[0])
		for text in ('"limit": 10', '"share": 14', '"promotion": 0'):
			self.assertIn(text, logs[0])

	# ---- returns -------------------------------------------------------------

	def _return_of(self, original, **row_values):
		from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

		ret = make_sales_return(original.name)
		for row in ret.items:
			row.update(row_values)
		ret.payments = []
		ret.flags.ignore_permissions = True
		ret.insert()
		return ret

	def test_return_copies_the_share(self):
		rule = self._rule(20)
		code = self._coupon()
		original = self._submitted(self._coupon_row_payload(code, 36, rule=rule))
		ret = self._return_of(original, qty=-1, **{SHARE: 50})
		row = ret.items[0]
		self.assertEqual(flt(row.qty), -1)
		self.assertAlmostEqual(flt(row.get(SHARE)), 4)  # the original's, never the client's
		self.assertFalse(row.get("posnext_coupon_code"))
		ret.flags.ignore_permissions = True
		ret.submit()
		self.assertEqual(ret.docstatus, 1)

		# A sale saved before the field (its row holds the column default, 0): its return
		# keeps 0 and validates as before.
		frappe.db.set_value("Sales Invoice Item", original.items[0].name, SHARE, 0, update_modified=False)
		older = self._return_of(original, qty=-1)
		self.assertEqual(flt(older.items[0].get(SHARE)), 0)

	# ---- F&F customer: the signed snapshot -----------------------------------

	def _fnf_stack(self):
		"""F&F 30% over a 25% promo; promo 12.5 + 10% of 37.5 = 16.25 a unit (32.5%) beats F&F."""
		enable_ff(self, CUSTOMER, EMAIL_DOMAIN)
		rule = self._rule(25)
		code = self._coupon()
		snapshot = self._cart_snapshot(CUSTOMER, ITEM_A, 2, rule)
		return rule, code, snapshot

	def test_fnf_stacked_line_with_the_signed_snapshot(self):
		rule, code, snapshot = self._fnf_stack()
		doc = self._submitted(self._coupon_row_payload(code, 33.75, rule=rule, **{REPLACED: snapshot}))
		self.assertEqual(doc.docstatus, 1)
		self.assertAlmostEqual(flt(doc.items[0].get(SHARE)), 3.75)

	def test_forged_snapshot_is_refused(self):
		rule, code, snapshot = self._fnf_stack()
		forged = json.loads(snapshot)
		forged["data"]["discount_percentage"] = 90
		forged["data"]["discount_amount"] = 90
		payload = self._coupon_row_payload(code, 33.75, rule=rule, **{REPLACED: json.dumps(forged)})
		doc = self._draft(payload)
		# The forged 90% promotion is not believed: the share is re-derived on server data.
		self.assertAlmostEqual(flt(doc.items[0].get(SHARE)), 3.75)
		self.assertFalse(doc.items[0].get(REPLACED))

	def test_same_coupon_snapshot_does_not_stack(self):
		# M-A: a signed snapshot whose discount is this same coupon is no promotion under it.
		code = self._coupon(percentage=40, max_amount=0)
		qty, price = 2, 20
		ctx = frappe._dict(customer=CUSTOMER, posting_date=nowdate(), pos_profile=self.ctx.pos_profile)
		sign = frappe.get_attr("posnext_promotions.promotions.ff_snapshot.sign")
		snapshot = sign(
			frappe._dict(item_code=ITEM_C, qty=qty, price_list_rate=price),
			{
				"discount_source": "coupon",
				"discount_percentage": 40,
				"discount_amount": 16,
				"rate": price,
				"pricing_rules": "",
				"posnext_coupon_code": code,
				"coupon_code": code,
				"is_already_discounted": 0,
			},
			doc=ctx,
		)
		doc = self._draft(self._coupon_row_payload(code, 12, qty=qty, item=ITEM_C, **{REPLACED: snapshot}))
		self.assertAlmostEqual(flt(doc.items[0].get(SHARE)), 8)
