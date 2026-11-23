# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""POS Coupon usage counts only coupons that end up applied on a submitted sale.

The count moves from submit_invoice (before save) to the Sales/POS Invoice
on_submit hook, so it follows the saved ``coupon_code`` after every validate
hook has run (an F&F engine may clear it), and cancel releases it.

Runs on a dev site with:
	bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.api.test_coupon_usage'}"
"""

import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from pos_next.api import sales_invoice_hooks
from pos_next.api.invoices import submit_invoice, update_invoice
from pos_next.pos_next.doctype.pos_coupon.pos_coupon import (
	COUPON_OVERSHOOT_LOG_TITLE,
	OFFLINE_OVERSHOOT_FIELD,
	_get_customer_coupon_usage_count,
	check_coupon_code,
)
from pos_next.test_promotions import (
	ITEM_C,
	_cart_payload,
	_ctx,
	_line,
	_resolve_customer_group,
	_resolve_territory,
)

COUPON_CODE = "PNXTUSAGE8C"


def _fresh_customer() -> str:
	"""A customer with no coupon history, so per-customer limits start at 0."""
	return (
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": f"_PNXT_8C_{frappe.generate_hash(length=8)}",
				"customer_group": _resolve_customer_group(),
				"territory": _resolve_territory(),
				"customer_type": "Individual",
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def _overshoot_logged(invoice: str, limit: str) -> bool:
	logs = frappe.get_all(
		"Error Log",
		filters={"method": COUPON_OVERSHOOT_LOG_TITLE, "reference_name": invoice},
		pluck="error",
	)
	# Each skipped check is on its own "<check>: <reason>" line
	return any(f"\n{limit}: " in (log or "") for log in logs)


@contextmanager
def _other_connection():
	"""Run frappe calls on a second DB connection (another session), then switch back."""
	from frappe.database import get_db

	conf = frappe.local.conf
	main = frappe.local.db
	other = get_db(
		socket=conf.db_socket,
		host=conf.db_host,
		port=conf.db_port,
		user=conf.db_name,
		password=conf.db_password,
		cur_db_name=conf.db_name,
	)
	other.connect()
	frappe.local.db = other
	try:
		yield other
	finally:
		frappe.local.db = main
		other.close()


def _used() -> int:
	return int(frappe.db.get_value("POS Coupon", {"coupon_code": COUPON_CODE}, "used") or 0)


class TestCouponUsage(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ctx = _ctx()
		existing = frappe.db.get_value("POS Coupon", {"coupon_code": COUPON_CODE}, "name")
		if existing:
			frappe.delete_doc("POS Coupon", existing, force=True, ignore_permissions=True)
		cls.coupon = (
			frappe.get_doc(
				{
					"doctype": "POS Coupon",
					"coupon_name": COUPON_CODE,
					"coupon_code": COUPON_CODE,
					"coupon_type": "Promotional",
					"company": cls.ctx.company,
					"discount_type": "Percentage",
					"discount_percentage": 10,
					"maximum_use": 100,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		name = frappe.db.get_value("POS Settings", {"pos_profile": cls.ctx.pos_profile}, "name")
		if not name:
			name = (
				frappe.get_doc({"doctype": "POS Settings", "pos_profile": cls.ctx.pos_profile})
				.insert(ignore_permissions=True)
				.name
			)
		cls.pos_settings = name
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.db.set_value("POS Settings", cls.pos_settings, OFFLINE_OVERSHOOT_FIELD, None)
		frappe.delete_doc("POS Coupon", cls.coupon, force=True, ignore_permissions=True)
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		frappe.db.set_value(
			"POS Coupon",
			self.coupon,
			{"used": 0, "one_use": 0, "maximum_use": 100, "disabled": 0, "valid_upto": None},
		)
		if frappe.db.has_column("POS Coupon", "maximum_use_per_customer"):
			frappe.db.set_value("POS Coupon", self.coupon, "maximum_use_per_customer", 0)
		# Blank = the field's default ("Allow and log")
		frappe.db.set_value("POS Settings", self.pos_settings, OFFLINE_OVERSHOOT_FIELD, None)

	def _payload(self, customer=None, coupon_code=COUPON_CODE):
		payload = _cart_payload(self.ctx, [_line(self.ctx, ITEM_C)])
		if customer:
			payload["customer"] = customer
		payload["coupon_code"] = coupon_code
		payload["payments"] = [{"mode_of_payment": self.ctx.mode_of_payment, "amount": 20}]
		return payload

	def _sell(self, **kwargs):
		draft = update_invoice(json.dumps(self._payload(**kwargs)))
		submit_invoice(invoice=json.dumps(draft, default=str), data=json.dumps({}))
		return frappe.get_doc("Sales Invoice", draft["name"])

	def _sell_offline_style(self, offline_id=None, **kwargs):
		# The offline sync sends the cart payload itself (coupon_code still set),
		# and submit_invoice drafts it internally.
		payload = self._payload(**kwargs)
		if offline_id:
			payload["offline_id"] = offline_id
		result = submit_invoice(invoice=json.dumps(payload), data=json.dumps({}))
		return frappe.get_doc("Sales Invoice", result["name"])

	def test_usage_counted_once_on_submit(self):
		sale = self._sell()
		self.assertEqual(sale.docstatus, 1)
		self.assertEqual(sale.coupon_code, COUPON_CODE)
		self.assertEqual(_used(), 1)

	def test_usage_not_counted_when_fnf_wins(self):
		original = sales_invoice_hooks.validate

		def validate_then_clear(doc, method=None):
			# Stands in for a later validate hook (F&F) that drops the coupon.
			original(doc, method)
			doc.coupon_code = None

		with patch.object(sales_invoice_hooks, "validate", validate_then_clear):
			sale = self._sell_offline_style()
		self.assertEqual(sale.docstatus, 1)
		self.assertFalse(sale.coupon_code)
		self.assertEqual(_used(), 0)

	def test_usage_released_on_cancel(self):
		sale = self._sell()
		self.assertEqual(_used(), 1)
		sale.flags.ignore_permissions = True
		sale.cancel()
		self.assertEqual(_used(), 0)

	def test_release_never_goes_negative(self):
		sale = self._sell()
		frappe.db.set_value("POS Coupon", self.coupon, "used", 0)
		sale.flags.ignore_permissions = True
		sale.cancel()
		self.assertEqual(_used(), 0)

	def test_failed_submit_does_not_count(self):
		draft = update_invoice(json.dumps(self._payload()))
		frappe.db.commit()
		with patch(
			"pos_next.api.invoices._validate_stock_on_invoice",
			side_effect=frappe.ValidationError("stock check failed"),
		):
			with self.assertRaises(frappe.ValidationError):
				submit_invoice(invoice=json.dumps(draft, default=str), data=json.dumps({}))
		frappe.db.rollback()
		self.assertEqual(frappe.db.get_value("Sales Invoice", draft["name"], "docstatus"), 0)
		self.assertEqual(_used(), 0)

	def test_max_use_per_customer_enforced(self):
		from pos_next.pos_next.doctype.pos_coupon.pos_coupon import _get_per_customer_use_limit

		# maximum_use_per_customer wins; one_use means 1 when it is unset.
		self.assertEqual(_get_per_customer_use_limit(SimpleNamespace(maximum_use_per_customer=2)), 2)
		self.assertEqual(
			_get_per_customer_use_limit(SimpleNamespace(maximum_use_per_customer=0, one_use=1)), 1
		)
		self.assertEqual(_get_per_customer_use_limit(SimpleNamespace(one_use=0)), 0)

		if not frappe.db.has_column("POS Coupon", "maximum_use_per_customer"):
			self.skipTest("maximum_use_per_customer field not installed on this site")
		# Earlier runs leave submitted sales behind: allow exactly one more.
		prior = _get_customer_coupon_usage_count(self.ctx.customer, COUPON_CODE)
		frappe.db.set_value("POS Coupon", self.coupon, "maximum_use_per_customer", prior + 1)
		self._sell()
		result = check_coupon_code(COUPON_CODE, customer=self.ctx.customer, company=self.ctx.company)
		self.assertFalse(result.get("valid"))
		self.assertIsNone(result.get("coupon"))
		# Another customer is unaffected.
		other = check_coupon_code(COUPON_CODE, customer="_PNXT_OTHER_CUSTOMER", company=self.ctx.company)
		self.assertTrue(other.get("valid"))

	def test_last_use_race_rejects_the_online_loser(self):
		frappe.db.set_value("POS Coupon", self.coupon, "maximum_use", 1)
		# Both drafts pass the draft-time check while one use is left.
		first = update_invoice(json.dumps(self._payload()))
		second = update_invoice(json.dumps(self._payload()))
		submit_invoice(invoice=json.dumps(first, default=str), data=json.dumps({}))
		frappe.db.commit()
		self.assertEqual(_used(), 1)

		with self.assertRaisesRegex(frappe.ValidationError, COUPON_CODE):
			submit_invoice(invoice=json.dumps(second, default=str), data=json.dumps({}))
		frappe.db.rollback()
		self.assertEqual(frappe.db.get_value("Sales Invoice", second["name"], "docstatus"), 0)
		self.assertEqual(_used(), 1)

	def _last_message_title(self):
		log = frappe.local.message_log or []
		last = log[-1] if log else {}
		if isinstance(last, str):
			last = json.loads(last)
		return last.get("title")

	def test_used_up_coupon_at_checkout_is_not_applicable(self):
		# D-R3-08: another cashier used the last use between Apply and Checkout
		frappe.db.set_value("POS Coupon", self.coupon, {"used": 1, "maximum_use": 1})
		frappe.local.message_log = []
		with self.assertRaisesRegex(
			frappe.ValidationError, f"^Coupon {COUPON_CODE} has reached its usage limit$"
		) as raised:
			update_invoice(json.dumps(self._payload()))
		# The POS keys on the exception type to drop the coupon, not on the text
		self.assertEqual(type(raised.exception).__name__, "CouponNotApplicableError")
		self.assertEqual(self._last_message_title(), "Coupon Not Applicable")

	def test_used_up_coupon_at_submit_is_not_applicable(self):
		frappe.db.set_value("POS Coupon", self.coupon, "maximum_use", 1)
		first = update_invoice(json.dumps(self._payload()))
		second = update_invoice(json.dumps(self._payload()))
		submit_invoice(invoice=json.dumps(first, default=str), data=json.dumps({}))
		with self.assertRaisesRegex(frappe.ValidationError, "has reached its usage limit") as raised:
			submit_invoice(invoice=json.dumps(second, default=str), data=json.dumps({}))
		self.assertEqual(type(raised.exception).__name__, "CouponNotApplicableError")

	def _offline_id(self):
		return f"pnxt-8c-{frappe.generate_hash(length=10)}"

	def test_offline_sale_over_limit_is_counted_and_logged(self):
		frappe.db.set_value("POS Coupon", self.coupon, {"maximum_use": 1, "used": 1})
		sale = self._sell_offline_style(offline_id=self._offline_id())
		self.assertEqual(sale.docstatus, 1)
		self.assertEqual(sale.coupon_code, COUPON_CODE)
		self.assertEqual(_used(), 2)
		self.assertTrue(_overshoot_logged(sale.name, "maximum_use"))

	def test_offline_sale_over_per_customer_limit_is_counted_and_logged(self):
		customer = _fresh_customer()
		frappe.db.set_value("POS Coupon", self.coupon, "one_use", 1)
		self._sell(customer=customer)
		sale = self._sell_offline_style(offline_id=self._offline_id(), customer=customer)
		self.assertEqual(sale.docstatus, 1)
		self.assertEqual(_used(), 2)
		self.assertTrue(_overshoot_logged(sale.name, "maximum_use_per_customer"))

	def test_offline_sale_over_limit_rejected_when_settings_say_reject(self):
		frappe.db.set_value("POS Settings", self.pos_settings, OFFLINE_OVERSHOOT_FIELD, "Reject")
		frappe.db.set_value("POS Coupon", self.coupon, {"maximum_use": 1, "used": 1})
		frappe.db.commit()
		with self.assertRaises(frappe.ValidationError):
			self._sell_offline_style(offline_id=self._offline_id())
		frappe.db.rollback()
		self.assertEqual(_used(), 1)

	def test_offline_submit_of_saved_draft_rejected_when_settings_say_reject(self):
		# The draft passes while one use is left; a sale takes it; the offline submit is rejected.
		frappe.db.set_value("POS Coupon", self.coupon, "maximum_use", 1)
		draft = update_invoice(json.dumps(self._payload()))
		self._sell()
		frappe.db.set_value("POS Settings", self.pos_settings, OFFLINE_OVERSHOOT_FIELD, "Reject")
		frappe.db.commit()
		with self.assertRaisesRegex(frappe.ValidationError, COUPON_CODE):
			submit_invoice(
				invoice=json.dumps(draft, default=str), data=json.dumps({"offline_id": self._offline_id()})
			)
		frappe.db.rollback()
		self.assertEqual(_used(), 1)

	def test_per_customer_check_sees_sale_committed_after_snapshot(self):
		# B's transaction reads (taking its REPEATABLE READ snapshot) before A
		# submits and commits on another connection. B's per-customer count must
		# still see A's sale, so it has to be a locking read.
		customer = _fresh_customer()
		frappe.db.set_value("POS Coupon", self.coupon, "one_use", 1)
		draft_a = update_invoice(json.dumps(self._payload(customer=customer)))
		draft_b = update_invoice(json.dumps(self._payload(customer=customer)))
		frappe.db.commit()

		# B: open the transaction and take the snapshot.
		frappe.db.sql("select count(*) from `tabSales Invoice`")

		with _other_connection() as other:
			submit_invoice(invoice=json.dumps(draft_a, default=str), data=json.dumps({}))
			other.commit()

		with self.assertRaisesRegex(frappe.ValidationError, customer):
			submit_invoice(invoice=json.dumps(draft_b, default=str), data=json.dumps({}))
		frappe.db.rollback()
		self.assertEqual(frappe.db.get_value("Sales Invoice", draft_a["name"], "docstatus"), 1)
		self.assertEqual(frappe.db.get_value("Sales Invoice", draft_b["name"], "docstatus"), 0)
		self.assertEqual(_used(), 1)

	def test_online_submit_rechecks_validity(self):
		draft = update_invoice(json.dumps(self._payload()))
		frappe.db.set_value("POS Coupon", self.coupon, "disabled", 1)
		frappe.db.commit()
		try:
			with self.assertRaisesRegex(frappe.ValidationError, "disabled"):
				submit_invoice(invoice=json.dumps(draft, default=str), data=json.dumps({}))
			frappe.db.rollback()
		finally:
			frappe.db.set_value("POS Coupon", self.coupon, "disabled", 0)
			frappe.db.commit()
		self.assertEqual(frappe.db.get_value("Sales Invoice", draft["name"], "docstatus"), 0)
		self.assertEqual(_used(), 0)

	def test_offline_sale_with_invalid_coupon_counted_and_logged(self):
		frappe.db.set_value("POS Coupon", self.coupon, "valid_upto", add_days(nowdate(), -1))
		try:
			sale = self._sell_offline_style(offline_id=self._offline_id())
			self.assertEqual(sale.docstatus, 1)
			self.assertEqual(sale.coupon_code, COUPON_CODE)
			self.assertEqual(_used(), 1)
			self.assertTrue(_overshoot_logged(sale.name, "validity"))
		finally:
			frappe.db.set_value("POS Coupon", self.coupon, "valid_upto", None)

	def test_per_customer_race_rejects_the_second_draft(self):
		customer = _fresh_customer()
		frappe.db.set_value("POS Coupon", self.coupon, "one_use", 1)
		# Both drafts pass the draft-time check (the customer has used it 0 times, limit 1).
		first = update_invoice(json.dumps(self._payload(customer=customer)))
		second = update_invoice(json.dumps(self._payload(customer=customer)))
		submit_invoice(invoice=json.dumps(first, default=str), data=json.dumps({}))
		frappe.db.commit()
		with self.assertRaisesRegex(frappe.ValidationError, COUPON_CODE):
			submit_invoice(invoice=json.dumps(second, default=str), data=json.dumps({}))
		frappe.db.rollback()
		self.assertEqual(frappe.db.get_value("Sales Invoice", second["name"], "docstatus"), 0)
		self.assertEqual(_used(), 1)

	def test_code_matched_case_insensitively_and_stored_canonical(self):
		sale = self._sell(coupon_code=COUPON_CODE.lower())
		self.assertEqual(sale.coupon_code, COUPON_CODE)
		self.assertEqual(_used(), 1)
		sale.flags.ignore_permissions = True
		sale.cancel()
		self.assertEqual(_used(), 0)

	def test_returns_do_not_count_toward_per_customer_limit(self):
		from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

		prior = _get_customer_coupon_usage_count(self.ctx.customer, COUPON_CODE)
		sale = self._sell()
		ret = make_sales_return(sale.name)
		# A return can carry the sale's coupon_code (copied from the original).
		ret.coupon_code = COUPON_CODE
		ret.flags.ignore_permissions = True
		ret.insert()
		ret.submit()
		self.assertEqual(ret.coupon_code, COUPON_CODE)
		self.assertEqual(_get_customer_coupon_usage_count(self.ctx.customer, COUPON_CODE), prior + 1)
		# A return neither counts nor releases the coupon's total usage.
		self.assertEqual(_used(), 1)
