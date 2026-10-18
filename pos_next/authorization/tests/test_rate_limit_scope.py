# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""How ``request_grant``'s rate-limit bucket is scoped.

``frappe.rate_limiter.rate_limit`` is a no-op when there is no HTTP request
(``if not frappe.request: return fn(...)``), so a normal test can never observe the
decorator at all. These tests instead assert the *identity* the decorator would
compute, mirroring its arithmetic exactly, and assert that the endpoint is wired
with the arguments that produce the intended scope.

The bug being pinned: with no ``key`` the identity is the IP alone, so every till
in a shop — all behind one public address — shared a single budget, and successful
approvals spent it just as fast as wrong PINs.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from pos_next.api import authorization

SHOP_IP = "41.33.7.9"
OTHER_IP = "196.20.1.4"


def rate_limit_identity(key, ip_based, ip, form_dict):
	"""The identity ``frappe.rate_limiter.rate_limit`` builds for a request.

	Mirrors ``frappe/rate_limiter.py`` verbatim::

	    ip = frappe.local.request_ip if ip_based is True else None
	    user_key = frappe.form_dict.get(key, "")
	    identity = None
	    if key and ip_based:
	        identity = ":".join([ip, user_key])
	    identity = identity or ip or user_key
	"""
	ip = ip if ip_based is True else None
	user_key = form_dict.get(key, "") if key else ""

	identity = None
	if key and ip_based:
		identity = ":".join([ip, user_key])

	return identity or ip or user_key


class TestRequestGrantRateLimitScope(FrappeTestCase):
	def setUp(self):
		self.manager = {"approver": "manager@example.com", "action": "Sales Invoice Return"}
		self.supervisor = {"approver": "supervisor@example.com", "action": "Sales Invoice Return"}

	# -- the defect, so a revert is caught -------------------------------------

	def test_ip_only_scoping_shares_one_bucket_across_a_shop(self):
		"""Regression: the old @rate_limit(limit=5, seconds=60) collapsed to the IP."""
		till_a = rate_limit_identity(None, True, SHOP_IP, self.manager)
		till_b = rate_limit_identity(None, True, SHOP_IP, self.supervisor)

		self.assertEqual(till_a, SHOP_IP)
		self.assertEqual(till_a, till_b, "unkeyed rate_limit buckets on IP alone")

	# -- the scope we actually want --------------------------------------------

	def test_composite_scope_separates_approvers_at_the_same_shop(self):
		till_a = rate_limit_identity("approver", True, SHOP_IP, self.manager)
		till_b = rate_limit_identity("approver", True, SHOP_IP, self.supervisor)

		self.assertNotEqual(till_a, till_b)
		self.assertTrue(till_a.startswith(f"{SHOP_IP}:"))

	def test_composite_scope_keeps_the_ip_so_a_stranger_cannot_starve_a_manager(self):
		"""ip_based=False would let anyone anywhere exhaust a named manager's budget."""
		at_shop = rate_limit_identity("approver", True, SHOP_IP, self.manager)
		from_elsewhere = rate_limit_identity("approver", True, OTHER_IP, self.manager)
		self.assertNotEqual(at_shop, from_elsewhere)

		# Dropping the IP is exactly what makes those two collide.
		self.assertEqual(
			rate_limit_identity("approver", False, SHOP_IP, self.manager),
			rate_limit_identity("approver", False, OTHER_IP, self.manager),
		)

	def test_same_approver_on_two_tills_still_shares_a_bucket(self):
		"""Accepted trade-off, documented so it is a decision and not a surprise.

		Tills in one shop share a public IP, so one manager approving from two tills
		lands in one bucket. That is why the ceiling has to sit far above honest use.
		"""
		self.assertEqual(
			rate_limit_identity("approver", True, SHOP_IP, self.manager),
			rate_limit_identity("approver", True, SHOP_IP, dict(self.manager)),
		)

	def test_blank_approver_would_collapse_back_to_the_shop_bucket(self):
		"""Why request_grant refuses an empty approver before doing any work."""
		blank = rate_limit_identity("approver", True, SHOP_IP, {"approver": ""})
		self.assertEqual(blank, f"{SHOP_IP}:")

		result = authorization.request_grant(action="Sales Invoice Return", approver="   ", pin="1234")
		self.assertFalse(result["authorized"])

	# -- the endpoint is wired the way these tests assume ----------------------

	@staticmethod
	def _rate_limit_arguments(fn):
		"""The arguments rate_limit was called with, read off its closure.

		@frappe.whitelist() wraps the rate-limited function, so walk ``__wrapped__``
		until the frame holding the decorator's own parameters comes into view.
		"""
		seen = fn
		while seen is not None:
			freevars = getattr(seen, "__code__", None) and seen.__code__.co_freevars or ()
			if "ip_based" in freevars:
				cells = seen.__closure__ or ()
				return dict(zip(freevars, (c.cell_contents for c in cells), strict=False))
			seen = getattr(seen, "__wrapped__", None)

		raise AssertionError("request_grant is not wrapped by frappe.rate_limiter.rate_limit")


	def test_request_grant_is_wired_with_the_intended_scope(self):
		closure = self._rate_limit_arguments(authorization.request_grant)

		self.assertEqual(closure.get("key"), "approver", "must scope per approver")
		self.assertIs(closure.get("ip_based"), True, "must keep the IP in the identity")
		self.assertEqual(closure.get("seconds"), 60)
		self.assertGreaterEqual(
			closure.get("limit"),
			20,
			"the ceiling must sit above honest trading — it counts successes too",
		)
		self.assertEqual(closure.get("limit"), authorization.RATE_LIMIT_PER_MINUTE)

	def test_successful_approvals_consume_the_same_budget_as_failures(self):
		"""Documents why the ceiling is high: the decorator increments before fn runs.

		If Frappe ever changes to count only failures this test should fail, and the
		ceiling can come back down.
		"""
		import inspect

		from frappe.rate_limiter import rate_limit

		source = inspect.getsource(rate_limit)
		self.assertIn("value = frappe.cache.incrby(cache_key, 1)", source)
		# rindex: the first `return fn(...)` is the early exit for non-HTTP calls.
		self.assertLess(
			source.index("value = frappe.cache.incrby(cache_key, 1)"),
			source.rindex("return fn(*args, **kwargs)"),
			"rate_limit still counts a request before knowing whether it succeeded",
		)
