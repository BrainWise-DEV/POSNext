# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Invoice rows keep what the promotions server reads (Task 8h).

``update_invoice`` blanks ``pricing_rules`` on paid rows (ERPNext would zero their
discount on the next save), but a free row keeps its gift rule names when every
kept name is an existing product-discount Pricing Rule, so the F&F gift policy can
recognise the gift. Names the offer evaluator does not back are dropped, and a
free row the evaluator backs gets the backing rule's name (Task 8i).

Runs on a dev site with:
	bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.api.test_ff_markers'}"
"""

import json
import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import cint, flt, now_datetime

from pos_next.api.invoices import submit_invoice, update_invoice
from pos_next.optional_apps import promotions_installed
from pos_next.test_promotions import (
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

PREFIX = "_PNXT_TEST_FFM_"
CUSTOMER = f"{PREFIX}CUSTOMER"
FNF = "friends_and_family"
FF_SETTINGS = "Friends and Family Settings"
EMAIL_DOMAIN = "ffmarkers.example"


def enable_ff(testcase, customer, email_domain, **values):
	"""Enable F&F for ``customer`` (approved domain + verified email); restored on cleanup."""
	snapshot = frappe.get_doc(FF_SETTINGS).as_dict(convert_dates_to_str=False)
	testcase.addCleanup(_restore_ff_settings, snapshot)
	email = f"customer@{email_domain}"
	frappe.db.set_value(
		"Customer",
		customer,
		{
			"email_id": email,
			"custom_email_verified": 1,
			"custom_verified_email": email,
			"custom_email_verified_on": now_datetime(),
		},
		update_modified=False,
	)
	doc = frappe.get_doc(FF_SETTINGS)
	doc.update(
		{
			"enabled": 1,
			"approved_domains": [{"email_domain": email_domain, "company": "F&F Tests", "enabled": 1}],
			"discount_percentage": 30,
			"discount_scope": "Entire Cart",
			"start_date": None,
			"end_date": None,
			"allow_free_gift_with_ff": 0,
			"applicable_brands": [],
			"applicable_item_groups": [],
			"applicable_items": [],
			"excluded_brands": [],
			"excluded_items": [],
			"excluded_item_groups": [],
			"max_discount_per_order": 0,
			"max_discount_per_customer_month": 0,
			**values,
		}
	)
	doc.save(ignore_permissions=True)  # on_update clears the F&F config cache


def _restore_ff_settings(snapshot):
	doc = frappe.get_doc(FF_SETTINGS)
	skip = ("name", "idx", "parent", "parentfield", "parenttype", "creation", "modified")
	for df in doc.meta.fields:
		if df.fieldtype in ("Table", "Table MultiSelect"):
			rows = snapshot.get(df.fieldname) or []
			doc.set(df.fieldname, [{k: v for k, v in r.items() if k not in skip} for r in rows])
		elif df.fieldtype not in frappe.model.no_value_fields:
			doc.set(df.fieldname, snapshot.get(df.fieldname))
	doc.flags.ignore_validate = True
	doc.save(ignore_permissions=True)


class TestFFMarkers(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not promotions_installed():
			raise unittest.SkipTest("posnext_promotions is not installed")
		cls.ctx = _ctx()
		if not frappe.db.exists("Customer", CUSTOMER):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": CUSTOMER,
					"customer_group": _resolve_customer_group(),
					"territory": _resolve_territory(),
					"customer_type": "Individual",
				}
			).insert(ignore_permissions=True)
		# Scoped to this test's customer so no other sale picks the rules up.
		scope = {"applicable_for": "Customer", "customer": CUSTOMER}
		cls.gift = _make_rule(
			f"{PREFIX}GIFT",
			apply_on="Item Code",
			items=[{"item_code": ITEM_B}],
			price_or_product_discount="Product",
			rate_or_discount="Discount Percentage",
			same_item=0,
			free_item=ITEM_C,
			min_qty=1,
			free_qty=1,
			free_item_uom="Nos",
			free_item_rate=0,
			**scope,
		)
		# On another item: two priority-1 rules on ITEM_B are an ERPNext conflict, and
		# the free-row check (Task 8i) evaluates the paid rows' offers.
		cls.price = _make_rule(
			f"{PREFIX}PRICE",
			apply_on="Item Code",
			items=[{"item_code": ITEM_A}],
			price_or_product_discount="Price",
			rate_or_discount="Discount Percentage",
			discount_percentage=10,
			**scope,
		)

	def setUp(self):
		frappe.set_user("Administrator")

	# ---- helpers -----------------------------------------------------------

	def _payload(self, paid_rules="", free_rules=""):
		paid = _line(self.ctx, ITEM_B)
		paid["pricing_rules"] = paid_rules
		free = _line(self.ctx, ITEM_C, price_list_rate=0)
		free.update({"is_free_item": 1, "pricing_rules": free_rules})
		payload = _cart_payload(self.ctx, [paid, free])
		payload["customer"] = CUSTOMER
		return payload

	def _draft(self, payload):
		draft = update_invoice(json.dumps(payload))
		self.addCleanup(
			frappe.delete_doc, "Sales Invoice", draft["name"], force=True, ignore_permissions=True
		)
		return frappe.get_doc("Sales Invoice", draft["name"])

	@staticmethod
	def _rows(doc, free):
		return [row for row in doc.items if cint(row.is_free_item) == free]

	# ---- update_invoice: pricing_rules on rows ------------------------------

	def test_free_row_keeps_gift_rule_name(self):
		doc = self._draft(self._payload(free_rules=self.gift))
		self.assertEqual([row.pricing_rules for row in self._rows(doc, 1)], [self.gift])

	def test_forged_rule_name_dropped(self):
		forged = f"{PREFIX}NO_SUCH_RULE"
		# Unknown names and non-product (Price) rules are dropped; the real gift rule stays.
		doc = self._draft(self._payload(free_rules=f"{self.gift},{forged},{self.price}"))
		self.assertEqual([row.pricing_rules for row in self._rows(doc, 1)], [self.gift])

		# Only a forged name: the gift is still due for ITEM_B, so its real rule is restored.
		doc = self._draft(self._payload(free_rules=forged))
		self.assertEqual([row.pricing_rules for row in self._rows(doc, 1)], [self.gift])

	def test_non_free_row_rules_still_blanked(self):
		doc = self._draft(self._payload(paid_rules=f"{self.price},{self.gift}", free_rules=self.gift))
		self.assertEqual([row.pricing_rules or "" for row in self._rows(doc, 0)], [""])

	def test_submit_existing_draft_drops_forged_rule_name(self):
		"""submit_invoice on an existing draft applies the same pricing_rules handling."""
		forged = f"{PREFIX}NO_SUCH_RULE"
		payload = self._payload(free_rules=self.gift)
		draft = update_invoice(json.dumps(payload))
		payload.update({"name": draft["name"], "payments": self._payments()})
		payload["items"][0]["pricing_rules"] = self.price
		payload["items"][1]["pricing_rules"] = f"{forged},{self.gift}"
		submit_invoice(invoice=json.dumps(payload), data=json.dumps({}))

		doc = frappe.get_doc("Sales Invoice", draft["name"])
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual([row.pricing_rules for row in self._rows(doc, 1)], [self.gift])
		self.assertEqual([row.pricing_rules or "" for row in self._rows(doc, 0)], [""])

	def _payments(self):
		return [{"mode_of_payment": self.ctx.mode_of_payment, "amount": ITEM_PRICES[ITEM_B]}]

	# ---- cart → invoice: the F&F gift policy sees the gift ------------------

	def test_cart_to_submit_gift_policy(self):
		"""F&F customer, gift rule, gifts not allowed with F&F.

		The POS sends the F&F marker on the trigger line and the gift rule on the free
		row (formatItemsForSubmission). Online, no offer backs the gift (the evaluator
		applies the same policy), so the save is refused (Task 8i, Ruling 58). An
		offline sync is a paid sale: the gift row is kept with its rule name, so the
		policy can record it. That paid half (prices kept and a ``gift_with_fnf`` Paid
		Disagreement) waits for promotions P1 Task 6d.
		"""
		enable_ff(self, CUSTOMER, EMAIL_DOMAIN)
		payload = self._ff_gift_payload()
		with self.assertRaises(frappe.ValidationError):
			update_invoice(json.dumps(payload))

		# An offline sync arrives through submit_invoice with a new offline_id.
		payload = self._ff_gift_payload()
		payload["offline_id"] = f"{PREFIX}OFFLINE_{frappe.generate_hash(length=10)}"
		payload["payments"] = [
			{"mode_of_payment": self.ctx.mode_of_payment, "amount": payload["items"][0]["rate"]}
		]
		result = submit_invoice(invoice=json.dumps(payload), data=json.dumps({}))
		doc = frappe.get_doc("Sales Invoice", result["name"])

		self.assertEqual([row.pricing_rules for row in self._rows(doc, 1)], [self.gift])
		(line_b,) = self._rows(doc, 0)
		self.assertEqual(line_b.posnext_discount_source, FNF)
		self.assertAlmostEqual(flt(line_b.rate), ITEM_PRICES[ITEM_B] * 0.7, places=2)

	def _ff_gift_payload(self):
		payload = self._payload(free_rules=self.gift)
		trigger = payload["items"][0]
		price = ITEM_PRICES[ITEM_B]
		trigger.update(
			{
				"discount_percentage": 30,
				"discount_amount": flt(price * 0.3, 2),
				"rate": flt(price * 0.7, 2),
				"posnext_discount_source": FNF,
			}
		)
		return payload
