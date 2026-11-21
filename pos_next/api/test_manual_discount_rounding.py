"""A cashier's discount priced per unit is judged with room for the cent it is rounded to
(G8 round 1, I-1).

The POS sends a cashier's % at 2 decimals and the unit rate rounded to the cent (G8):
50% of 20.01 is 10.00 a unit (Banker's Rounding), 90% of 13.33 is 1.33. The paid-row
check must not read that rounding as a discount above Max Discount, or as a rate edit,
and must still refuse a discount that really is above the limit or a rate really edited.
Read-only: ``_manual_discount_problem`` is called on plain rows, no documents are written.

	bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs "{'module': 'pos_next.api.test_manual_discount_rounding'}"
"""

import unittest

import frappe
from frappe.utils import flt

from pos_next.api import invoices as inv

TOLERANCE = 0.01


def settings(item_discount=1, rate_edit=0, max_discount=0):
	return {
		inv.FIELD_ALLOW_USER_TO_EDIT_ITEM_DISCOUNT: item_discount,
		inv.FIELD_ALLOW_USER_TO_EDIT_RATE: rate_edit,
		inv.FIELD_MAX_DISCOUNT_ALLOWED: max_discount,
	}


def judge(price, rate, percentage, s):
	"""The row's problem as the paid-row check sees it (no offer: all of it is manual)."""
	unexplained = price - rate
	if unexplained <= TOLERANCE:
		return None
	row = frappe._dict(idx=1, item_code="X", rate=rate, discount_percentage=flt(percentage, 2))
	return inv._manual_discount_problem(row, price, unexplained, TOLERANCE, s)


def cart_rate(price, percentage):
	"""The unit rate the POS cart sends for a cashier's % (unitRateLineDiscount)."""
	return flt(price * (1 - percentage / 100), 2)


class TestManualDiscountRounding(unittest.TestCase):
	def test_the_maximum_typed_exactly_is_accepted(self):
		# 50% of 20.01 is 10.00 a unit, 50.02% of the list price once rounded.
		self.assertEqual(cart_rate(20.01, 50), 10.0)
		self.assertIsNone(judge(20.01, 10.0, 50, settings(max_discount=50)))

	def test_above_the_maximum_is_refused(self):
		problem = judge(20.01, cart_rate(20.01, 50.5), 50.5, settings(max_discount=50))
		self.assertIn("maximum allowed discount", problem or "")
		# A cent a unit below the maximum's own rate is still refused.
		self.assertIn("maximum allowed discount", judge(20.01, 9.98, 50.12, settings(max_discount=50)) or "")

	def test_a_high_percentage_is_not_read_as_a_rate_edit(self):
		# 90% of 13.33 is 1.333, sent at 1.33: no rate was edited.
		self.assertEqual(cart_rate(13.33, 90), 1.33)
		self.assertIsNone(judge(13.33, 1.33, 90, settings()))

	def test_a_real_rate_edit_is_still_refused(self):
		# 90% claimed, but the rate is 0.13 a unit lower than 90% gives.
		self.assertIn("rate editing is not allowed", judge(13.33, 1.2, 90, settings()) or "")
		# No % at all: a plain rate edit.
		self.assertIn("rate editing is not allowed", judge(50, 45, 0, settings()) or "")
		# Item discounts off: a cashier % is refused whatever its rounding.
		self.assertIn("item discounts are not allowed", judge(20.01, 10.0, 50, settings(item_discount=0)) or "")

	def test_rounded_rates_are_never_refused_and_over_limit_ones_always_are(self):
		# The review's classes: prices 1.00-200.00, % up to 99, Max = the % typed.
		percentages = (5, 10, 12.5, 15, 100 / 3, 50, 66.67, 75, 90, 95, 99)
		refused, passed_over = [], []
		for cents in range(100, 20001, 37):
			price = cents / 100
			for pct in percentages:
				limit = flt(pct, 2)
				for s in (settings(), settings(max_discount=limit)):
					if judge(price, cart_rate(price, pct), pct, s):
						refused.append((price, pct, s[inv.FIELD_MAX_DISCOUNT_ALLOWED]))
				# Genuinely over: 0.5 points above the limit, and at least two cents a unit.
				over = pct + 0.5
				rate = cart_rate(price, over)
				if cart_rate(price, limit) - rate >= 0.02 and not judge(price, rate, over, settings(max_discount=limit)):
					passed_over.append((price, pct))
		self.assertEqual(refused, [])
		self.assertEqual(passed_over, [])
