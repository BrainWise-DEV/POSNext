# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe


def _get_item_group():
	"""Get the first available Item Group, or create one."""
	name = frappe.db.get_value("Item Group", {}, "name")
	if name:
		return name
	doc = frappe.get_doc({"doctype": "Item Group", "item_group_name": "SYNCTEST Group", "parent_item_group": ""})
	doc.insert(ignore_permissions=True)
	return doc.name


def _get_uom():
	"""Get the first available UOM, or create one."""
	name = frappe.db.get_value("UOM", {}, "name")
	if name:
		return name
	doc = frappe.get_doc({"doctype": "UOM", "uom_name": "SYNCTEST Unit"})
	doc.insert(ignore_permissions=True)
	return doc.name


def _cleanup():
	for name in frappe.get_all("Item", filters={"name": ("like", "SYNCTEST-%")}, pluck="name"):
		frappe.delete_doc("Item", name, force=True, ignore_permissions=True)
	frappe.db.commit()


def test_item_adapter_registered():
	"""ItemAdapter is registered for 'Item'."""
	from pos_next.sync.adapters import item  # triggers registration
	from pos_next.sync import registry
	adapter = registry.get_adapter("Item")
	assert adapter is not None, "Item adapter not registered"
	assert adapter.doctype == "Item"
	print("PASS: test_item_adapter_registered")


def test_item_adapter_apply_creates_item():
	"""apply_incoming creates an Item from payload."""
	_cleanup()
	try:
		from pos_next.sync.adapters.item import ItemAdapter
		adapter = ItemAdapter()
		item_group = _get_item_group()
		uom = _get_uom()

		payload = {
			"name": "SYNCTEST-APPLE",
			"item_code": "SYNCTEST-APPLE",
			"item_name": "Apple",
			"item_group": item_group,
			"stock_uom": uom,
			"is_stock_item": 1,
		}
		result = adapter.apply_incoming(payload, "update")
		assert result == "SYNCTEST-APPLE"
		assert frappe.db.exists("Item", "SYNCTEST-APPLE")
		print("PASS: test_item_adapter_apply_creates_item")
	finally:
		_cleanup()


def test_item_adapter_apply_updates_item():
	"""apply_incoming updates an existing Item."""
	_cleanup()
	try:
		from pos_next.sync.adapters.item import ItemAdapter
		adapter = ItemAdapter()
		item_group = _get_item_group()
		uom = _get_uom()

		payload = {
			"name": "SYNCTEST-BANANA",
			"item_code": "SYNCTEST-BANANA",
			"item_name": "Banana",
			"item_group": item_group,
			"stock_uom": uom,
		}
		adapter.apply_incoming(payload, "update")

		payload["item_name"] = "Banana (Updated)"
		adapter.apply_incoming(payload, "update")

		doc = frappe.get_doc("Item", "SYNCTEST-BANANA")
		assert doc.item_name == "Banana (Updated)"
		print("PASS: test_item_adapter_apply_updates_item")
	finally:
		_cleanup()


def test_item_adapter_serialize():
	"""serialize returns a dict payload."""
	_cleanup()
	try:
		from pos_next.sync.adapters.item import ItemAdapter
		adapter = ItemAdapter()
		item_group = _get_item_group()
		uom = _get_uom()

		doc = frappe.get_doc({
			"doctype": "Item",
			"item_code": "SYNCTEST-SERIALIZE",
			"item_name": "Serialize Test",
			"item_group": item_group,
			"stock_uom": uom,
		})
		doc.insert(ignore_permissions=True)
		doc.reload()

		payload = adapter.serialize(doc)
		assert "name" in payload
		assert isinstance(payload, dict)
		print("PASS: test_item_adapter_serialize")
	finally:
		_cleanup()


def run_all():
	test_item_adapter_registered()
	test_item_adapter_apply_creates_item()
	test_item_adapter_apply_updates_item()
	test_item_adapter_serialize()
	print("\nAll ItemAdapter tests PASSED")
