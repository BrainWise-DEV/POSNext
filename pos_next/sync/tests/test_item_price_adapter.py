# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe


def _cleanup():
	for name in frappe.get_all("Item Price", filters={"item_code": ("like", "SYNCTEST-%")}, pluck="name"):
		frappe.delete_doc("Item Price", name, force=True, ignore_permissions=True)
	for name in frappe.get_all("Item", filters={"name": ("like", "SYNCTEST-%")}, pluck="name"):
		frappe.delete_doc("Item", name, force=True, ignore_permissions=True)
	frappe.db.commit()


def _ensure_test_item():
	"""Create a test item if not exists."""
	if not frappe.db.exists("Item", "SYNCTEST-IP-ITEM"):
		item_group = frappe.db.get_value("Item Group", {}, "name")
		uom = frappe.db.get_value("UOM", {}, "name")
		frappe.get_doc({
			"doctype": "Item",
			"item_code": "SYNCTEST-IP-ITEM",
			"item_name": "IP Test Item",
			"item_group": item_group,
			"stock_uom": uom,
		}).insert(ignore_permissions=True)


def test_item_price_adapter_registered():
	"""ItemPriceAdapter is registered for 'Item Price'."""
	from pos_next.sync.adapters import item_price  # triggers registration
	from pos_next.sync import registry
	adapter = registry.get_adapter("Item Price")
	assert adapter is not None, "Item Price adapter not registered"
	print("PASS: test_item_price_adapter_registered")


def test_item_price_adapter_conflict_key():
	"""Conflict key is composite: (item_code, price_list, uom)."""
	from pos_next.sync.adapters.item_price import ItemPriceAdapter
	adapter = ItemPriceAdapter()
	payload = {"item_code": "ITEM-001", "price_list": "Standard Selling", "uom": "Nos"}
	assert adapter.conflict_key(payload) == ("item_code", "price_list", "uom")
	print("PASS: test_item_price_adapter_conflict_key")


def test_item_price_adapter_apply_by_composite_key():
	"""apply_incoming looks up by composite key, not by name."""
	_cleanup()
	try:
		_ensure_test_item()
		from pos_next.sync.adapters.item_price import ItemPriceAdapter
		adapter = ItemPriceAdapter()

		uom = frappe.db.get_value("UOM", {}, "name")
		currency = frappe.defaults.get_global_default("currency") or "USD"

		payload = {
			"name": "CENTRAL-IP-001",
			"item_code": "SYNCTEST-IP-ITEM",
			"price_list": "Standard Selling",
			"price_list_rate": 100,
			"uom": uom,
			"currency": currency,
		}
		adapter.apply_incoming(payload, "update")
		assert frappe.db.exists("Item Price", {"item_code": "SYNCTEST-IP-ITEM", "price_list": "Standard Selling"})

		# Second apply with updated price — should update, not create duplicate
		payload["price_list_rate"] = 150
		adapter.apply_incoming(payload, "update")
		count = frappe.db.count("Item Price", {"item_code": "SYNCTEST-IP-ITEM", "price_list": "Standard Selling"})
		assert count == 1, f"Expected 1 Item Price, got {count}"

		rate = frappe.db.get_value("Item Price", {"item_code": "SYNCTEST-IP-ITEM", "price_list": "Standard Selling"}, "price_list_rate")
		assert float(rate) == 150.0, f"Expected 150, got {rate}"
		print("PASS: test_item_price_adapter_apply_by_composite_key")
	finally:
		_cleanup()


def run_all():
	test_item_price_adapter_registered()
	test_item_price_adapter_conflict_key()
	test_item_price_adapter_apply_by_composite_key()
	print("\nAll ItemPriceAdapter tests PASSED")
