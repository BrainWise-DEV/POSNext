"""Lock order and concurrency tests for Price Group."""

import frappe
from frappe.tests import IntegrationTestCase

from pos_next.install import ensure_price_group_custom_fields
from pos_next.tests import price_group_helpers as helpers


class TestPriceGroupConcurrency(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		ensure_price_group_custom_fields(quiet=True)
		self.company = helpers.get_default_company()
		self.uom = helpers.base_uom()

	def test_lock_order_covers_current_and_desired_profiles(self):
		"""Assert full lock sequence: Price Group, current+desired profiles, Price List, managed Item Prices."""
		item1 = helpers.make_test_item("conc1-1", self.uom)
		item2 = helpers.make_test_item("conc1-2", self.uom)
		wh1 = helpers.make_test_warehouse("conc1-1", self.company)
		wh2 = helpers.make_test_warehouse("conc1-2", self.company)
		pos1 = helpers.make_test_pos_profile("conc1-1", self.company, wh1)
		pos2 = helpers.make_test_pos_profile("conc1-2", self.company, wh2)

		pg = helpers.make_price_group(
			"PG-Conc-1",
			items=[
				{"item_code": item1, "rate": 10000},
				{"item_code": item2, "rate": 20000},
			],
			outlets=[{"company": self.company, "warehouse": wh1}],
		)
		pl_name = f"{helpers.MANAGED_PRICE_LIST_PREFIX}{pg.price_group_name}"
		managed_ip_names = frappe.get_all(
			"Item Price",
			filters={"price_list": pl_name, helpers.OWNER_FIELD: pg.name},
			pluck="name",
		)
		self.assertTrue(
			managed_ip_names,
			msg="Fixture produced no managed Item Prices, so the Item Price lock order below would be asserted against an empty list and could not fail",
		)

		# Transfer ownership from current pos1 to desired pos2.
		pg.set("outlets", [{"company": self.company, "warehouse": wh2}])
		lock_log = []
		orig_get_value = frappe.db.get_value

		def logging_get_value(*args, **kwargs):
			if kwargs.get("for_update"):
				doctype = args[0] if args else kwargs.get("doctype")
				row = args[1] if len(args) > 1 else kwargs.get("filters")
				if isinstance(row, dict):
					row = row.get("name")
				lock_log.append((doctype, str(row)))
			return orig_get_value(*args, **kwargs)

		with __import__("unittest").mock.patch("frappe.db.get_value", side_effect=logging_get_value):
			pg.save()

		expected = (
			[("Price Group", pg.name)]
			+ sorted([("POS Profile", pos1), ("POS Profile", pos2)])
			+ [("Price List", pl_name)]
			+ [("Item Price", name) for name in sorted(managed_ip_names)]
		)
		self.assertEqual(
			lock_log,
			expected,
			msg=f"Observed lock order differs from required full sequence. Probe only observes frappe.db.get_value locks; observed {lock_log}, expected {expected}",
		)

	def test_ownership_checked_after_all_locks(self):
		"""Assert each ownership read follows a lock on the exact same (doctype, name) row."""
		item = helpers.make_test_item("conc2", self.uom)
		wh = helpers.make_test_warehouse("conc2", self.company)
		helpers.make_test_pos_profile("conc2", self.company, wh)

		pg = helpers.make_price_group(
			"PG-Conc-2",
			items=[{"item_code": item, "rate": 10000}],
			outlets=[{"company": self.company, "warehouse": wh}],
		)

		events = []
		orig_get_value = frappe.db.get_value
		owner_fields = {helpers.OWNER_FIELD, helpers.PROFILE_PREVIOUS_PRICE_LIST_FIELD}

		def logging_get_value(*args, **kwargs):
			doctype = args[0] if args else kwargs.get("doctype")
			row = args[1] if len(args) > 1 else kwargs.get("filters")
			if isinstance(row, dict):
				row = row.get("name")
			row = str(row)
			fieldname = args[2] if len(args) > 2 else kwargs.get("fieldname")
			fields = fieldname if isinstance(fieldname, list | tuple) else [fieldname]
			if kwargs.get("for_update"):
				events.append(("LOCK", (doctype, row)))
			elif owner_fields.intersection(fields):
				events.append(("READ_OWNER", (doctype, row)))
			return orig_get_value(*args, **kwargs)

		with __import__("unittest").mock.patch("frappe.db.get_value", side_effect=logging_get_value):
			pg.save()

		self.assertTrue(
			any(kind == "LOCK" for kind, _ in events),
			msg=f"Ownership ordering probe recorded no row locks: {events}",
		)
		self.assertTrue(
			any(kind == "READ_OWNER" for kind, _ in events),
			msg=f"Ownership ordering probe recorded no ownership reads: {events}",
		)
		read_doctypes = {dt for kind, (dt, _row) in events if kind == "READ_OWNER"}
		self.assertIn("Price List", read_doctypes, msg=f"Price List ownership read missing: events={events}")
		self.assertIn(
			"POS Profile", read_doctypes, msg=f"POS Profile ownership read missing: events={events}"
		)
		locked = set()
		for kind, row in events:
			if kind == "LOCK":
				locked.add(row)
			else:
				self.assertIn(
					row,
					locked,
					msg=f"Ownership row {row} was read before its exact row lock; events={events}",
				)

	def test_concurrent_claim_yields_one_owner(self):
		"""Primary lock serializes claims; secondary times out, then rejects committed competing owner."""
		suffix = frappe.generate_hash(length=8)

		# Roll back first so the commit below captures only this test's own rows.
		# IntegrationTestCase has no per-test rollback, so a bare commit would also commit
		# whatever uncommitted state earlier tests in this class left behind.
		frappe.db.rollback()

		item = helpers.make_test_item(f"conc3-{suffix}", self.uom)
		wh = helpers.make_test_warehouse(f"conc3-{suffix}", self.company)
		pos = helpers.make_test_pos_profile(f"conc3-{suffix}", self.company, wh)
		pg_a_name = f"PG-Conc-A-{suffix}"
		pg_b_name = f"PG-Conc-B-{suffix}"
		pl_a_name = f"{helpers.MANAGED_PRICE_LIST_PREFIX}{pg_a_name}"
		pl_b_name = f"{helpers.MANAGED_PRICE_LIST_PREFIX}{pg_b_name}"

		frappe.db.commit()

		cleanup_rows = {
			"Price Group": [pg_a_name, pg_b_name],
			"Item Price": [],
			"Price List": [pl_a_name, pl_b_name],
			"POS Profile": [pos],
			"Warehouse": [wh],
			"Item": [item],
		}

		def cleanup():
			with self.primary_connection():
				try:
					frappe.db.rollback()
					for name in list(cleanup_rows["Item Price"]):
						try:
							if frappe.db.exists("Item Price", name):
								frappe.delete_doc("Item Price", name, ignore_permissions=True)
						except Exception:
							pass
					for dt in ("Price List", "Price Group", "POS Profile", "Warehouse", "Item"):
						for name in cleanup_rows[dt]:
							try:
								if frappe.db.exists(dt, name):
									frappe.delete_doc(dt, name, ignore_permissions=True)
							except Exception:
								pass
				finally:
					frappe.db.commit()

		self.addCleanup(cleanup)

		# IntegrationTestCase.secondary_connection() captures frappe.local.db AFTER its
		# first-use frappe.connect(), so its finally-block restores the secondary rather
		# than the primary. Every operation below therefore names its connection
		# explicitly instead of relying on the ambient one.

		# Primary holds the profile row lock and writes group A's marker, uncommitted.
		with self.primary_connection():
			frappe.db.get_value("POS Profile", pos, "modified", for_update=True)
			frappe.db.set_value("POS Profile", pos, helpers.PROFILE_OWNER_FIELD, pg_a_name)

		with self.secondary_connection():
			with self.assertRaises(
				frappe.QueryTimeoutError,
				msg="Secondary claim should time out while primary holds profile lock",
			):
				frappe.db.get_value("POS Profile", pos, "modified", for_update=True, wait=False)

		with self.primary_connection():
			frappe.db.commit()

		with self.secondary_connection():
			# REPEATABLE-READ: end the transaction the failed lock attempt left open so the
			# ownership read below sees group A's now-committed marker.
			frappe.db.rollback()
			with self.assertRaises(
				frappe.ValidationError,
				msg="Secondary Group B claim should be rejected after Group A commits ownership",
			):
				helpers.make_price_group(
					pg_b_name,
					items=[{"item_code": item, "rate": 10000}],
					outlets=[{"company": self.company, "warehouse": wh}],
				)

		with self.primary_connection():
			owner = frappe.db.get_value("POS Profile", pos, helpers.PROFILE_OWNER_FIELD)
			self.assertEqual(owner, pg_a_name, msg=f"Group A should remain sole owner of {pos}, got {owner}")
