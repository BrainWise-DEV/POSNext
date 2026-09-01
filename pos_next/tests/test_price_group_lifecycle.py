"""Lifecycle and contract tests for Price Group.

Pins the enabled, disabled, ownership, and deletion contracts of the feature.
"""

from pathlib import Path

import frappe
from frappe.tests import IntegrationTestCase

from pos_next.install import ensure_price_group_custom_fields
from pos_next.tests import price_group_helpers as helpers


class TestPriceGroupLifecycle(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		ensure_price_group_custom_fields(quiet=True)
		self.company = helpers.get_default_company()
		self.currency = helpers.get_default_currency(self.company)
		self.uom = helpers.base_uom()
		self.custom_uom = helpers.custom_uom()

	def test_enable_creates_marked_price_list(self):
		"""Save enabled Price Group: assert Price List PG-<name> created with correct values and owner marker."""
		item = helpers.make_test_item("life1", self.uom)
		pg = helpers.make_price_group("PG-Life-1", items=[{"item_code": item, "rate": 10000}])
		pl_name = f"{helpers.MANAGED_PRICE_LIST_PREFIX}{pg.price_group_name}"

		self.assertTrue(frappe.db.exists("Price List", pl_name), msg=f"Price List {pl_name} was not created")
		pl = frappe.get_doc("Price List", pl_name)
		self.assertEqual(pl.selling, 1, msg=f"Price List {pl_name} selling should be 1")
		self.assertEqual(pl.buying, 0, msg=f"Price List {pl_name} buying should be 0")
		self.assertEqual(pl.enabled, 1, msg=f"Price List {pl_name} enabled should be 1")
		self.assertEqual(
			pl.currency,
			self.currency,
			msg=f"Price List currency should match company currency {self.currency}",
		)
		self.assertEqual(
			getattr(pl, helpers.PRICE_LIST_OWNER_FIELD, None),
			pg.name,
			msg=f"Price List {pl_name} owner marker {helpers.PRICE_LIST_OWNER_FIELD} should equal {pg.name}",
		)

	def test_new_managed_price_list_does_not_become_global_default(self):
		"""Clear Selling Settings.selling_price_list in singles and defaults, create group, assert setting remains empty."""
		frappe.db.set_single_value("Selling Settings", "selling_price_list", None)
		frappe.defaults.clear_default("selling_price_list", parent="__default")

		item = helpers.make_test_item("life2", self.uom)
		pg = helpers.make_price_group("PG-Life-2", items=[{"item_code": item, "rate": 15000}])
		pl_name = f"{helpers.MANAGED_PRICE_LIST_PREFIX}{pg.price_group_name}"

		current_single = frappe.db.get_single_value("Selling Settings", "selling_price_list")
		rows = frappe.db.sql(
			"""select defvalue from tabDefaultValue
			   where parent = '__default' and defkey = 'selling_price_list'"""
		)
		current_default = rows[0][0] if rows else None

		self.assertFalse(
			current_single,
			msg=f"Selling Settings.selling_price_list should remain empty, but became {current_single!r}",
		)
		self.assertNotEqual(
			current_single,
			pl_name,
			msg=f"Selling Settings.selling_price_list was claimed by the managed list {pl_name}",
		)
		self.assertFalse(
			current_default,
			msg=f"tabDefaultValue leaked: {current_default!r}",
		)
		self.assertNotEqual(
			current_default,
			pl_name,
			msg=f"tabDefaultValue was claimed by the managed list {pl_name}",
		)

	def test_existing_selling_default_survives_managed_price_list_creation(self):
		"""A pre-existing Selling default is restored, not blanked, after a managed list is created."""
		existing_pl = (
			frappe.db.get_value("Price List", {"selling": 1, "enabled": 1}, "name") or "Standard Selling"
		)
		frappe.db.set_single_value("Selling Settings", "selling_price_list", existing_pl)
		frappe.db.set_default("selling_price_list", existing_pl)

		item = helpers.make_test_item("life2b", self.uom)
		pg = helpers.make_price_group("PG-Life-2B", items=[{"item_code": item, "rate": 15000}])
		pl_name = f"{helpers.MANAGED_PRICE_LIST_PREFIX}{pg.price_group_name}"

		current_single = frappe.db.get_single_value("Selling Settings", "selling_price_list")
		rows = frappe.db.sql(
			"""select defvalue from tabDefaultValue
			   where parent = '__default' and defkey = 'selling_price_list'"""
		)
		current_default = rows[0][0] if rows else None

		self.assertEqual(
			current_single,
			existing_pl,
			msg=f"Selling Settings.selling_price_list should remain {existing_pl!r}, got {current_single!r}",
		)
		self.assertNotEqual(current_single, pl_name)
		self.assertEqual(
			current_default,
			existing_pl,
			msg=f"tabDefaultValue should remain {existing_pl!r}, got {current_default!r}",
		)
		self.assertNotEqual(current_default, pl_name)

	def test_managed_item_price_identity_is_item_and_uom(self):
		"""Two items generate marked rows with distinct (item_code, uom) identity."""
		item1 = helpers.make_test_item("life3-1", self.uom)
		item2 = helpers.make_test_item("life3-2", self.custom_uom)
		pg = helpers.make_price_group(
			"PG-Life-3",
			items=[
				{"item_code": item1, "rate": 12000},
				{"item_code": item2, "rate": 18000},
			],
		)
		pl_name = f"{helpers.MANAGED_PRICE_LIST_PREFIX}{pg.price_group_name}"

		rows = frappe.get_all(
			"Item Price",
			filters={"price_list": pl_name, helpers.ITEM_PRICE_OWNER_FIELD: pg.name},
			fields=["item_code", "uom"],
		)
		self.assertEqual(
			len(rows), 2, msg=f"Expected exactly 2 marked Item Price rows on {pl_name}, got {len(rows)}"
		)
		identities = {(r.item_code, r.uom) for r in rows}
		self.assertEqual(
			len(identities), 2, msg=f"Expected 2 distinct (item_code, uom) identities, got {identities}"
		)
		self.assertIn(
			(item1, self.uom), identities, msg=f"Expected identity ({item1}, {self.uom}) in {identities}"
		)
		self.assertIn(
			(item2, self.custom_uom),
			identities,
			msg=f"Expected identity ({item2}, {self.custom_uom}) in {identities}",
		)

	def test_rate_change_updates_managed_row_only(self):
		"""Rate change in Price Group updates only changed row, leaving other rows on the same Price List untouched."""
		item1 = helpers.make_test_item("life4-1", self.uom)
		item2 = helpers.make_test_item("life4-2", self.uom)
		item3 = helpers.make_test_item("life4-3", self.uom)

		pg = helpers.make_price_group(
			"PG-Life-4",
			items=[
				{"item_code": item1, "rate": 10000},
				{"item_code": item2, "rate": 20000},
			],
		)
		pl_name = f"{helpers.MANAGED_PRICE_LIST_PREFIX}{pg.price_group_name}"

		# Manual unmarked row on the same managed list
		manual_ip = helpers.manual_item_price(item3, pl_name, price_list_rate=30000)

		ip2_name = frappe.db.get_value("Item Price", {"price_list": pl_name, "item_code": item2}, "name")
		ip2_rate = frappe.db.get_value("Item Price", ip2_name, "price_list_rate")
		ip2_modified = frappe.db.get_value("Item Price", ip2_name, "modified")
		snapshot_unchanged_marked = (ip2_name, ip2_rate, ip2_modified)

		manual_rate = frappe.db.get_value("Item Price", manual_ip, "price_list_rate")
		manual_modified = frappe.db.get_value("Item Price", manual_ip, "modified")
		snapshot_manual = (manual_ip, manual_rate, manual_modified)

		# Mutate rate of item1
		pg.items[0].rate = 15000
		pg.save()

		# Changed item rate updated
		ip1_rate = frappe.db.get_value(
			"Item Price", {"price_list": pl_name, "item_code": item1}, "price_list_rate"
		)
		self.assertEqual(ip1_rate, 15000, msg=f"Item 1 rate should be updated to 15000, got {ip1_rate}")

		# Unchanged marked row identical
		current_unchanged_marked = (
			ip2_name,
			frappe.db.get_value("Item Price", ip2_name, "price_list_rate"),
			frappe.db.get_value("Item Price", ip2_name, "modified"),
		)
		self.assertEqual(
			current_unchanged_marked,
			snapshot_unchanged_marked,
			msg=f"Unchanged marked row on same Price List was modified: {current_unchanged_marked} != {snapshot_unchanged_marked}",
		)

		# Manual row identical
		current_manual = (
			manual_ip,
			frappe.db.get_value("Item Price", manual_ip, "price_list_rate"),
			frappe.db.get_value("Item Price", manual_ip, "modified"),
		)
		self.assertEqual(
			current_manual,
			snapshot_manual,
			msg=f"Manual row on same Price List was modified: {current_manual} != {snapshot_manual}",
		)

	def test_removed_item_deletes_only_marked_row(self):
		"""Removing an item from child table deletes only its marked row, preserving manual and scoped rows."""
		item1 = helpers.make_test_item("life5-1", self.uom)
		item2 = helpers.make_test_item("life5-2", self.uom)
		item3 = helpers.make_test_item("life5-3", self.uom)
		cust = helpers.make_test_customer("life5")

		pg = helpers.make_price_group(
			"PG-Life-5",
			items=[
				{"item_code": item1, "rate": 10000},
				{"item_code": item2, "rate": 20000},
			],
		)
		pl_name = f"{helpers.MANAGED_PRICE_LIST_PREFIX}{pg.price_group_name}"

		manual_ip = helpers.manual_item_price(item3, pl_name, price_list_rate=30000)
		scoped_ip = helpers.manual_item_price(item2, pl_name, customer=cust, price_list_rate=25000)
		manual_modified_before = frappe.db.get_value("Item Price", manual_ip, "modified")
		scoped_modified_before = frappe.db.get_value("Item Price", scoped_ip, "modified")

		# Remove item2 from Price Group
		pg.items = [pg.items[0]]
		pg.save()

		# Marked row for item2 is gone
		marked_item2_exists = frappe.db.exists(
			"Item Price",
			{"price_list": pl_name, helpers.OWNER_FIELD: pg.name, "item_code": item2},
		)
		self.assertFalse(marked_item2_exists, msg=f"Marked row for removed item2 still exists on {pl_name}")

		# Manual and scoped rows still exist with unchanged modified
		self.assertTrue(
			frappe.db.exists("Item Price", manual_ip), msg=f"Manual row {manual_ip} should survive"
		)
		self.assertEqual(
			frappe.db.get_value("Item Price", manual_ip, "modified"),
			manual_modified_before,
			msg=f"Manual row {manual_ip} modified timestamp changed",
		)
		self.assertTrue(
			frappe.db.exists("Item Price", scoped_ip), msg=f"Scoped row {scoped_ip} should survive"
		)
		self.assertEqual(
			frappe.db.get_value("Item Price", scoped_ip, "modified"),
			scoped_modified_before,
			msg=f"Scoped row {scoped_ip} modified timestamp changed",
		)

	def test_manual_unmarked_price_survives(self):
		"""Unmarked manual Item Price on managed Price List survives sync operations."""
		item1 = helpers.make_test_item("life6-1", self.uom)
		item2 = helpers.make_test_item("life6-2", self.uom)
		pg = helpers.make_price_group("PG-Life-6", items=[{"item_code": item1, "rate": 10000}])
		pl_name = f"{helpers.MANAGED_PRICE_LIST_PREFIX}{pg.price_group_name}"

		manual_ip = helpers.manual_item_price(item2, pl_name, price_list_rate=50000)

		pg.save()

		self.assertTrue(
			frappe.db.exists("Item Price", manual_ip), msg=f"Manual row {manual_ip} was deleted on save"
		)
		owner_val = frappe.db.get_value("Item Price", manual_ip, helpers.ITEM_PRICE_OWNER_FIELD)
		self.assertFalse(
			owner_val, msg=f"Manual row {manual_ip} should not have owner marker set, got {owner_val}"
		)

	def test_scoped_and_null_uom_prices_survive(self):
		"""Customer-, batch-, date-, and packing-unit-scoped and NULL-UOM rows survive sync untouched."""
		item1 = helpers.make_test_item("life7-1", self.uom, has_batch_no=1, is_stock_item=1)
		item2 = helpers.make_test_item("life7-2", self.uom)
		pg = helpers.make_price_group("PG-Life-7", items=[{"item_code": item1, "rate": 10000}])
		pl_name = f"{helpers.MANAGED_PRICE_LIST_PREFIX}{pg.price_group_name}"

		cust = helpers.make_test_customer("life7")
		batch = helpers.make_test_batch(item1, "life7")

		scoped_customer = helpers.manual_item_price(item1, pl_name, customer=cust)
		scoped_batch = helpers.manual_item_price(item1, pl_name, batch_no=batch)
		scoped_date = helpers.manual_item_price(
			item1, pl_name, valid_from="2026-01-01", valid_upto="2026-12-31"
		)
		scoped_packing = helpers.manual_item_price(item1, pl_name, packing_unit=10)

		# NULL-UOM row scoped to item2 so check_duplicates does not collide with managed item1 row
		null_uom_ip = helpers.manual_item_price(item2, pl_name, price_list_rate=33000)
		frappe.db.set_value("Item Price", null_uom_ip, "uom", None, update_modified=False)

		scoped_rows = [scoped_customer, scoped_batch, scoped_date, scoped_packing, null_uom_ip]
		snapshots = {
			ip: (
				frappe.db.get_value("Item Price", ip, "price_list_rate"),
				frappe.db.get_value("Item Price", ip, "modified"),
				frappe.db.get_value("Item Price", ip, helpers.OWNER_FIELD),
			)
			for ip in scoped_rows
		}

		pg.save()

		for ip in scoped_rows:
			self.assertTrue(frappe.db.exists("Item Price", ip), msg=f"Scoped row {ip} should survive save")
			current = (
				frappe.db.get_value("Item Price", ip, "price_list_rate"),
				frappe.db.get_value("Item Price", ip, "modified"),
				frappe.db.get_value("Item Price", ip, helpers.OWNER_FIELD),
			)
			self.assertEqual(
				current,
				snapshots[ip],
				msg=f"Scoped row {ip} (rate, modified, owner) changed after save: {current} != {snapshots[ip]}",
			)

		self.assertIsNone(
			frappe.db.get_value("Item Price", null_uom_ip, "uom"),
			msg=f"NULL-UOM row {null_uom_ip} UOM should remain None",
		)

	def test_invalid_item_uom_fails_before_mutation(self):
		"""Missing UOM conversion detail raises validation error while Price List/Profile remain unchanged."""
		item = helpers.make_test_item("life8", self.uom)
		wh = helpers.make_test_warehouse("life8", self.company)
		pos = helpers.make_test_pos_profile("life8", self.company, wh)

		pl_name = f"{helpers.MANAGED_PRICE_LIST_PREFIX}PG-Life-8"

		profile_pl_before = frappe.db.get_value("POS Profile", pos, "selling_price_list")
		profile_owner_before = frappe.db.get_value("POS Profile", pos, helpers.PROFILE_OWNER_FIELD)

		# Remove the conversion row Frappe auto-creates for the stock UOM, so the resolved UOM has none.
		frappe.db.delete(
			"UOM Conversion Detail",
			{"parenttype": "Item", "parent": item, "uom": self.uom},
		)

		with self.assertRaisesRegex(
			frappe.ValidationError,
			r"Conversion Factor for UOM .* does not exist for Item",
			msg="Expected controller validation error for missing UOM conversion",
		):
			helpers.make_price_group(
				"PG-Life-8",
				items=[{"item_code": item, "rate": 10000}],
				outlets=[{"company": self.company, "warehouse": wh}],
			)

		self.assertFalse(
			frappe.db.exists("Price List", pl_name),
			msg=f"Price List {pl_name} should not be created on validation failure",
		)
		self.assertEqual(
			frappe.db.get_value("POS Profile", pos, "selling_price_list"),
			profile_pl_before,
			msg=f"POS Profile {pos} price list should remain {profile_pl_before!r}",
		)
		self.assertEqual(
			frappe.db.get_value("POS Profile", pos, helpers.PROFILE_OWNER_FIELD),
			profile_owner_before,
			msg=f"POS Profile {pos} owner marker should remain {profile_owner_before!r}",
		)

	def test_stock_uom_change_moves_managed_identity(self):
		"""Spec 8.6: after an Item stock-UOM change, the next save moves the managed row's identity."""
		item = helpers.make_test_item("life9", self.uom)
		pg = helpers.make_price_group("PG-Life-9", items=[{"item_code": item, "rate": 10000}])
		pl_name = f"{helpers.MANAGED_PRICE_LIST_PREFIX}{pg.price_group_name}"

		old_ip = frappe.db.get_value(
			"Item Price", {"price_list": pl_name, "item_code": item, "uom": self.uom}, "name"
		)
		self.assertIsNotNone(old_ip, msg=f"Old Item Price for ({item}, {self.uom}) was not created")

		item_doc = frappe.get_doc("Item", item)
		item_doc.stock_uom = self.custom_uom
		item_doc.save()

		pg.reload()
		pg.save()

		self.assertEqual(
			frappe.db.get_value("Price Group Item", pg.items[0].name, "uom"),
			self.custom_uom,
			msg="Child row UOM should be re-derived from the Item's new stock UOM",
		)
		new_ip = frappe.db.get_value(
			"Item Price", {"price_list": pl_name, "item_code": item, "uom": self.custom_uom}, "name"
		)
		self.assertIsNotNone(new_ip, msg=f"New Item Price for ({item}, {self.custom_uom}) was not created")
		self.assertFalse(
			frappe.db.exists("Item Price", old_ip), msg=f"Old Item Price {old_ip} should be deleted"
		)

	def test_delete_succeeds_after_item_stock_uom_change(self):
		"""A stock-UOM change must not make an existing Price Group undeletable."""
		item = helpers.make_test_item("life9b", self.uom)
		pg = helpers.make_price_group("PG-Life-9B", items=[{"item_code": item, "rate": 10000}])

		item_doc = frappe.get_doc("Item", item)
		item_doc.stock_uom = self.custom_uom
		item_doc.save()

		pg.delete()

		self.assertFalse(
			frappe.db.exists("Price Group", pg.name),
			msg=f"Price Group {pg.name} should be successfully deleted after stock UOM change",
		)

	def test_outlet_claim_marks_profile_and_saves_previous(self):
		"""Claiming an outlet marks the POS Profile with owner and saves its previous price list."""
		wh = helpers.make_test_warehouse("life10", self.company)
		pos = helpers.make_test_pos_profile("life10", self.company, wh)

		frappe.db.set_value("POS Profile", pos, "selling_price_list", "Standard Selling")

		pg = helpers.make_price_group(
			"PG-Life-10",
			items=[{"item_code": helpers.make_test_item("life10", self.uom), "rate": 10000}],
			outlets=[{"company": self.company, "warehouse": wh}],
		)
		pl_name = f"{helpers.MANAGED_PRICE_LIST_PREFIX}{pg.price_group_name}"

		pos_doc = frappe.get_doc("POS Profile", pos)
		self.assertEqual(
			pos_doc.selling_price_list,
			pl_name,
			msg=f"POS Profile {pos} price list should be updated to {pl_name}",
		)
		self.assertEqual(
			getattr(pos_doc, helpers.PROFILE_OWNER_FIELD, None),
			pg.name,
			msg=f"POS Profile {pos} owner marker should equal {pg.name}",
		)
		self.assertEqual(
			getattr(pos_doc, helpers.PROFILE_PREVIOUS_PRICE_LIST_FIELD, None),
			"Standard Selling",
			msg=f"POS Profile {pos} previous price list should be preserved as 'Standard Selling'",
		)

	def test_reclaim_does_not_overwrite_stored_previous(self):
		"""Re-saving a Price Group retains original stored previous price list on claimed profile and keeps owner marker."""
		wh = helpers.make_test_warehouse("life11", self.company)
		pos = helpers.make_test_pos_profile("life11", self.company, wh)
		frappe.db.set_value("POS Profile", pos, "selling_price_list", "Standard Selling")

		pg = helpers.make_price_group(
			"PG-Life-11",
			items=[{"item_code": helpers.make_test_item("life11", self.uom), "rate": 10000}],
			outlets=[{"company": self.company, "warehouse": wh}],
		)

		pg.save()

		prev_pl = frappe.db.get_value("POS Profile", pos, helpers.PROFILE_PREVIOUS_PRICE_LIST_FIELD)
		self.assertEqual(
			prev_pl,
			"Standard Selling",
			msg=f"POS Profile {pos} previous price list was overwritten on re-save",
		)
		owner = frappe.db.get_value("POS Profile", pos, helpers.PROFILE_OWNER_FIELD)
		self.assertEqual(owner, pg.name, msg=f"POS Profile {pos} owner marker was cleared on re-save")

	def test_outlet_removal_restores_owned_profile(self):
		"""Removing an outlet from Price Group restores POS Profile's previous price list and clears marker."""
		wh = helpers.make_test_warehouse("life12", self.company)
		pos = helpers.make_test_pos_profile("life12", self.company, wh)
		frappe.db.set_value("POS Profile", pos, "selling_price_list", "Standard Selling")

		pg = helpers.make_price_group(
			"PG-Life-12",
			items=[{"item_code": helpers.make_test_item("life12", self.uom), "rate": 10000}],
			outlets=[{"company": self.company, "warehouse": wh}],
		)

		pg.outlets = []
		pg.save()

		pos_doc = frappe.get_doc("POS Profile", pos)
		self.assertEqual(
			pos_doc.selling_price_list,
			"Standard Selling",
			msg=f"POS Profile {pos} price list was not restored",
		)
		self.assertFalse(
			getattr(pos_doc, helpers.PROFILE_OWNER_FIELD, None),
			msg=f"POS Profile {pos} owner marker was not cleared",
		)
		self.assertFalse(
			getattr(pos_doc, helpers.PROFILE_PREVIOUS_PRICE_LIST_FIELD, None),
			msg=f"POS Profile {pos} previous price list field was not cleared",
		)

	def test_cross_group_claim_is_rejected(self):
		"""Group B cannot claim an outlet whose POS Profile is already owned by Group A."""
		wh = helpers.make_test_warehouse("life13", self.company)
		helpers.make_test_pos_profile("life13", self.company, wh)

		helpers.make_price_group(
			"PG-Life-13A",
			items=[{"item_code": helpers.make_test_item("life13A", self.uom), "rate": 10000}],
			outlets=[{"company": self.company, "warehouse": wh}],
		)

		with self.assertRaises(
			frappe.ValidationError, msg="Group B should be rejected when claiming outlet owned by Group A"
		):
			helpers.make_price_group(
				"PG-Life-13B",
				items=[{"item_code": helpers.make_test_item("life13B", self.uom), "rate": 20000}],
				outlets=[{"company": self.company, "warehouse": wh}],
			)

	def test_no_pos_profile_sets_outlet_status_without_throwing(self):
		"""When no POS Profile matches company/warehouse, outlet status is 'No POS Profile' in DB without raising."""
		wh = helpers.make_test_warehouse("life14", self.company)

		pg = helpers.make_price_group(
			"PG-Life-14",
			items=[{"item_code": helpers.make_test_item("life14", self.uom), "rate": 10000}],
			outlets=[{"company": self.company, "warehouse": wh}],
		)

		self.assertEqual(len(pg.outlets), 1, msg="Expected 1 outlet row on Price Group")
		db_status = frappe.db.get_value("Price Group Outlet", pg.outlets[0].name, "status")
		db_pos_profile = frappe.db.get_value("Price Group Outlet", pg.outlets[0].name, "pos_profile")
		self.assertEqual(
			db_status,
			"No POS Profile",
			msg=f"Database outlet status should be 'No POS Profile', got '{db_status}'",
		)
		self.assertFalse(
			db_pos_profile, msg=f"Database outlet pos_profile should be empty, got '{db_pos_profile}'"
		)

	def test_warehouse_company_mismatch_is_rejected(self):
		"""Warehouse company mismatch is rejected with ValidationError."""
		comp_b = helpers.get_second_company()
		wh_b = helpers.make_test_warehouse("life15", comp_b)

		with self.assertRaisesRegex(
			frappe.ValidationError,
			r"belongs to company",
			msg="Expected ValidationError for warehouse company mismatch",
		):
			helpers.make_price_group(
				"PG-Life-15",
				items=[{"item_code": helpers.make_test_item("life15", self.uom), "rate": 10000}],
				outlets=[{"company": self.company, "warehouse": wh_b}],
			)

	def test_duplicate_item_is_rejected(self):
		"""Duplicate item in child items table is rejected with ValidationError."""
		item = helpers.make_test_item("life16", self.uom)
		with self.assertRaisesRegex(
			frappe.ValidationError,
			r"Duplicate item",
			msg="Expected ValidationError for duplicate child items",
		):
			helpers.make_price_group(
				"PG-Life-16",
				items=[
					{"item_code": item, "rate": 10000},
					{"item_code": item, "rate": 20000},
				],
			)

	def test_non_positive_rate_is_rejected(self):
		"""Rate <= 0 is rejected with ValidationError."""
		item = helpers.make_test_item("life17", self.uom)
		with self.assertRaisesRegex(
			frappe.ValidationError,
			r"Rate must be greater than zero",
			msg="Expected ValidationError for non-positive rate",
		):
			helpers.make_price_group(
				"PG-Life-17",
				items=[{"item_code": item, "rate": 0}],
			)

	def test_duplicate_outlet_is_rejected(self):
		"""Duplicate company/warehouse outlet row is rejected with ValidationError."""
		wh = helpers.make_test_warehouse("life18", self.company)
		with self.assertRaisesRegex(
			frappe.ValidationError,
			r"Duplicate outlet",
			msg="Expected ValidationError for duplicate outlets",
		):
			helpers.make_price_group(
				"PG-Life-18",
				items=[{"item_code": helpers.make_test_item("life18", self.uom), "rate": 10000}],
				outlets=[
					{"company": self.company, "warehouse": wh},
					{"company": self.company, "warehouse": wh},
				],
			)

	# --- Disable and Delete Tests ---

	def test_disable_restores_profiles_and_clears_markers(self):
		"""Disabling Price Group restores linked POS Profile previous list and clears owner markers."""
		wh = helpers.make_test_warehouse("life19", self.company)
		pos = helpers.make_test_pos_profile("life19", self.company, wh)
		frappe.db.set_value("POS Profile", pos, "selling_price_list", "Standard Selling")

		pg = helpers.make_price_group(
			"PG-Life-19",
			items=[{"item_code": helpers.make_test_item("life19", self.uom), "rate": 10000}],
			outlets=[{"company": self.company, "warehouse": wh}],
		)

		pg.enabled = 0
		pg.save()

		pos_doc = frappe.get_doc("POS Profile", pos)
		self.assertEqual(
			pos_doc.selling_price_list,
			"Standard Selling",
			msg=f"POS Profile {pos} price list was not restored on disable",
		)
		self.assertFalse(
			getattr(pos_doc, helpers.PROFILE_OWNER_FIELD, None),
			msg=f"POS Profile {pos} owner marker was not cleared on disable",
		)

	def test_disable_disables_price_list_and_skips_item_price_writes(self):
		"""Disabling Price Group disables Price List and skips Item Price updates, keeping timestamps intact."""
		item = helpers.make_test_item("life20", self.uom)
		pg = helpers.make_price_group("PG-Life-20", items=[{"item_code": item, "rate": 10000}])
		pl_name = f"{helpers.MANAGED_PRICE_LIST_PREFIX}{pg.price_group_name}"

		ip_name = frappe.db.get_value("Item Price", {"price_list": pl_name, "item_code": item}, "name")
		ip_modified_before = frappe.db.get_value("Item Price", ip_name, "modified")

		pg.enabled = 0
		pg.save()

		pl_enabled = frappe.db.get_value("Price List", pl_name, "enabled")
		self.assertEqual(pl_enabled, 0, msg=f"Price List {pl_name} was not disabled")

		ip_modified_after = frappe.db.get_value("Item Price", ip_name, "modified")
		self.assertEqual(
			ip_modified_before,
			ip_modified_after,
			msg=f"Item Price {ip_name} modified timestamp changed: {ip_modified_before} -> {ip_modified_after}",
		)

	def test_reenable_after_disable_restores_managed_prices(self):
		"""Re-enabling disabled Price Group restores Price List enabled state and retains active managed prices without recreation."""
		item = helpers.make_test_item("life21", self.uom)
		pg = helpers.make_price_group("PG-Life-21", items=[{"item_code": item, "rate": 10000}])
		pl_name = f"{helpers.MANAGED_PRICE_LIST_PREFIX}{pg.price_group_name}"

		ip_name = frappe.db.get_value("Item Price", {"price_list": pl_name, "item_code": item}, "name")
		ip_rate_before = frappe.db.get_value("Item Price", ip_name, "price_list_rate")
		ip_creation_before = frappe.db.get_value("Item Price", ip_name, "creation")

		pg.enabled = 0
		pg.save()

		self.assertTrue(
			frappe.db.exists("Item Price", ip_name),
			msg=f"Item Price {ip_name} was deleted while Price Group was disabled",
		)

		pg.enabled = 1
		pg.save()

		pl_enabled = frappe.db.get_value("Price List", pl_name, "enabled")
		self.assertEqual(pl_enabled, 1, msg=f"Price List {pl_name} was not re-enabled")

		self.assertTrue(
			frappe.db.exists("Item Price", ip_name),
			msg=f"Item Price {ip_name} was deleted/recreated on re-enable",
		)
		ip_rate_after = frappe.db.get_value("Item Price", ip_name, "price_list_rate")
		ip_creation_after = frappe.db.get_value("Item Price", ip_name, "creation")
		owner = frappe.db.get_value("Item Price", ip_name, helpers.OWNER_FIELD)
		self.assertEqual(
			ip_rate_after, ip_rate_before, msg=f"Item Price {ip_name} rate changed after re-enable"
		)
		self.assertEqual(
			ip_creation_after,
			ip_creation_before,
			msg=(
				f"Item Price {ip_name} creation timestamp changed "
				f"({ip_creation_before} -> {ip_creation_after}), so the row was deleted on disable "
				"and re-inserted on re-enable instead of being retained"
			),
		)
		self.assertEqual(owner, pg.name, msg=f"Item Price {ip_name} owner marker was lost after re-enable")

	def test_delete_restores_profiles_and_keeps_price_list(self):
		"""Deleting Price Group restores profiles, keeps Price List (disabled), deletes marked rows, preserves unmanaged."""
		wh = helpers.make_test_warehouse("life22", self.company)
		pos = helpers.make_test_pos_profile("life22", self.company, wh)
		frappe.db.set_value("POS Profile", pos, "selling_price_list", "Standard Selling")

		item = helpers.make_test_item("life22", self.uom)
		pg = helpers.make_price_group(
			"PG-Life-22",
			items=[{"item_code": item, "rate": 10000}],
			outlets=[{"company": self.company, "warehouse": wh}],
		)
		pl_name = f"{helpers.MANAGED_PRICE_LIST_PREFIX}{pg.price_group_name}"

		manual_ip = helpers.manual_item_price(helpers.make_test_item("life22-manual", self.uom), pl_name)

		pg.delete()

		pos_doc = frappe.get_doc("POS Profile", pos)
		self.assertEqual(
			pos_doc.selling_price_list,
			"Standard Selling",
			msg=f"POS Profile {pos} price list was not restored after delete",
		)

		self.assertTrue(
			frappe.db.exists("Price List", pl_name),
			msg=f"Price List {pl_name} was deleted after Price Group delete",
		)
		pl_enabled = frappe.db.get_value("Price List", pl_name, "enabled")
		self.assertEqual(pl_enabled, 0, msg=f"Price List {pl_name} should be disabled after delete")

		marked_ip_exists = frappe.db.exists("Item Price", {"price_list": pl_name, "item_code": item})
		self.assertFalse(marked_ip_exists, msg=f"Marked Item Price row for {item} still exists on {pl_name}")

		self.assertTrue(
			frappe.db.exists("Item Price", manual_ip), msg=f"Manual Item Price {manual_ip} was deleted"
		)

	def test_delete_keeps_price_list_and_preserves_unmarked_rows(self):
		"""Deleting Price Group succeeds: keeps disabled Price List, preserves unmanaged rows, removes marked rows."""
		item = helpers.make_test_item("life23", self.uom)
		pg = helpers.make_price_group("PG-Life-23", items=[{"item_code": item, "rate": 10000}])
		pl_name = f"{helpers.MANAGED_PRICE_LIST_PREFIX}{pg.price_group_name}"

		manual_ip = helpers.manual_item_price(
			helpers.make_test_item("life23-manual", self.uom), pl_name, price_list_rate=45000
		)
		manual_rate = frappe.db.get_value("Item Price", manual_ip, "price_list_rate")
		manual_modified = frappe.db.get_value("Item Price", manual_ip, "modified")

		pg.delete()

		# Price List exists and disabled
		self.assertTrue(
			frappe.db.exists("Price List", pl_name), msg=f"Price List {pl_name} should be kept after delete"
		)
		pl_enabled = frappe.db.get_value("Price List", pl_name, "enabled")
		self.assertEqual(pl_enabled, 0, msg=f"Price List {pl_name} should be disabled")

		# Manual unmarked row still exists with unchanged rate and modified
		self.assertTrue(
			frappe.db.exists("Item Price", manual_ip), msg=f"Manual Item Price {manual_ip} should survive"
		)
		self.assertEqual(
			frappe.db.get_value("Item Price", manual_ip, "price_list"),
			pl_name,
			msg=f"Manual Item Price {manual_ip} price_list should still resolve to {pl_name}",
		)
		self.assertEqual(
			frappe.db.get_value("Item Price", manual_ip, "price_list_rate"),
			manual_rate,
			msg=f"Manual Item Price {manual_ip} rate changed after delete",
		)
		self.assertEqual(
			frappe.db.get_value("Item Price", manual_ip, "modified"),
			manual_modified,
			msg=f"Manual Item Price {manual_ip} modified timestamp changed after delete",
		)

		# All marked Item Prices for this group are gone
		marked_rows = frappe.get_all(
			"Item Price", filters={"price_list": pl_name, helpers.OWNER_FIELD: pg.name}
		)
		self.assertEqual(
			len(marked_rows), 0, msg=f"Marked Item Price rows remain after delete: {marked_rows}"
		)

	def test_controller_source_has_no_force_delete(self):
		"""Source contract check: the PriceGroup doctype package and ownership module must not use force=True in delete_doc."""
		app_path = Path(frappe.get_app_path("pos_next"))
		search_paths = [
			app_path / "pos_next" / "doctype" / "price_group",
			app_path / "price_group_ownership.py",
		]

		checked_files = 0
		target_needle = "force" + "=True"
		for target in search_paths:
			if target.is_dir():
				for py_file in target.rglob("*.py"):
					source = py_file.read_text()
					if py_file.name == "test_price_group_lifecycle.py":
						source = source.split("def test_controller_source_has_no_force_delete")[0]
					self.assertNotIn(
						target_needle,
						source,
						msg=f"force=True found in {py_file}",
					)
					checked_files += 1
			elif target.is_file():
				source = target.read_text()
				if target.name == "test_price_group_lifecycle.py":
					source = source.split("def test_controller_source_has_no_force_delete")[0]
				self.assertNotIn(
					target_needle,
					source,
					msg=f"force=True found in {target}",
				)
				checked_files += 1

		self.assertTrue(
			checked_files > 0, msg=f"No python source files found in target search paths: {search_paths}"
		)

	def test_delete_fails_before_mutation_when_price_list_owned_by_other_group(self):
		"""Delete blocks, mutating nothing, when the managed Price List belongs to another group."""
		item = helpers.make_test_item("life25", self.uom)
		wh = helpers.make_test_warehouse("life25", self.company)
		pos = helpers.make_test_pos_profile("life25", self.company, wh)

		pg = helpers.make_price_group(
			"PG-Life-25",
			items=[{"item_code": item, "rate": 10000}],
			outlets=[{"company": self.company, "warehouse": wh}],
		)
		pl_name = f"{helpers.MANAGED_PRICE_LIST_PREFIX}{pg.price_group_name}"

		# Snapshot BEFORE attempt
		pl_enabled_before = frappe.db.get_value("Price List", pl_name, "enabled")
		self.assertEqual(frappe.db.get_value("Price List", pl_name, helpers.PRICE_LIST_OWNER_FIELD), pg.name)

		ip_rows_before = {
			(
				r.name,
				r.price_list_rate,
				frappe.db.get_value("Item Price", r.name, "modified"),
			)
			for r in frappe.get_all(
				"Item Price", filters={"price_list": pl_name}, fields=["name", "price_list_rate"]
			)
		}

		pos_pl_before = frappe.db.get_value("POS Profile", pos, "selling_price_list")
		pos_owner_before = frappe.db.get_value("POS Profile", pos, helpers.PROFILE_OWNER_FIELD)
		pos_prev_before = frappe.db.get_value("POS Profile", pos, helpers.PROFILE_PREVIOUS_PRICE_LIST_FIELD)

		frappe.db.set_value("Price List", pl_name, helpers.PRICE_LIST_OWNER_FIELD, "OtherGroup")

		with self.assertRaisesRegex(
			frappe.ValidationError,
			r"already exists and is owned by OtherGroup",
			msg="Expected ValidationError when deleting Price Group with Price List owned by another group",
		):
			pg.delete()

		# Snapshots unchanged
		self.assertEqual(frappe.db.get_value("Price List", pl_name, "enabled"), pl_enabled_before)
		self.assertEqual(
			frappe.db.get_value("Price List", pl_name, helpers.PRICE_LIST_OWNER_FIELD), "OtherGroup"
		)

		ip_rows_after = {
			(
				r.name,
				r.price_list_rate,
				frappe.db.get_value("Item Price", r.name, "modified"),
			)
			for r in frappe.get_all(
				"Item Price", filters={"price_list": pl_name}, fields=["name", "price_list_rate"]
			)
		}
		self.assertEqual(ip_rows_after, ip_rows_before)

		self.assertEqual(frappe.db.get_value("POS Profile", pos, "selling_price_list"), pos_pl_before)
		self.assertEqual(
			frappe.db.get_value("POS Profile", pos, helpers.PROFILE_OWNER_FIELD), pos_owner_before
		)
		self.assertEqual(
			frappe.db.get_value("POS Profile", pos, helpers.PROFILE_PREVIOUS_PRICE_LIST_FIELD),
			pos_prev_before,
		)
		self.assertTrue(frappe.db.exists("Price Group", pg.name))

	def test_delete_succeeds_when_foreign_owned_profile_is_only_desired(self):
		"""Deleting a group must not be blocked by a profile another group owns and this one merely desires."""
		wh = helpers.make_test_warehouse("life26", self.company)

		# Create Group B before any matching POS Profile exists, so creation-time desired-profile
		# validation (which still runs on save) has nothing to collide with.
		pg_b = helpers.make_price_group(
			"PG-Life-26B",
			items=[{"item_code": helpers.make_test_item("life26", self.uom), "rate": 10000}],
			outlets=[{"company": self.company, "warehouse": wh}],
		)

		# A POS Profile now appears for the same outlet, already owned by another group.
		# Group B never claimed it via save, so it is only ever DESIRED, never OWNED, by B.
		pos = helpers.make_test_pos_profile("life26", self.company, wh)
		frappe.db.set_value("POS Profile", pos, helpers.PROFILE_OWNER_FIELD, "PG-A")
		frappe.db.set_value("POS Profile", pos, "selling_price_list", "PG-PG-A")

		pos_pl_before = frappe.db.get_value("POS Profile", pos, "selling_price_list")
		pos_owner_before = frappe.db.get_value("POS Profile", pos, helpers.PROFILE_OWNER_FIELD)
		pos_prev_before = frappe.db.get_value("POS Profile", pos, helpers.PROFILE_PREVIOUS_PRICE_LIST_FIELD)
		pos_modified_before = frappe.db.get_value("POS Profile", pos, "modified")

		pg_b.delete()

		self.assertFalse(frappe.db.exists("Price Group", pg_b.name))
		self.assertEqual(frappe.db.get_value("POS Profile", pos, "selling_price_list"), pos_pl_before)
		self.assertEqual(
			frappe.db.get_value("POS Profile", pos, helpers.PROFILE_OWNER_FIELD), pos_owner_before
		)
		self.assertEqual(
			frappe.db.get_value("POS Profile", pos, helpers.PROFILE_PREVIOUS_PRICE_LIST_FIELD),
			pos_prev_before,
		)
		self.assertEqual(frappe.db.get_value("POS Profile", pos, "modified"), pos_modified_before)
