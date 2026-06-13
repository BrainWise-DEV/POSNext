import json
import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def get_product_management_permissions() -> dict:
	"""Return permissions required to show and use POS Product Management."""
	can_read_item = frappe.has_permission("Item", "read")
	can_create_item = frappe.has_permission("Item", "create")
	can_write_item = frappe.has_permission("Item", "write")
	can_read_price = frappe.has_permission("Item Price", "read")
	can_create_price = frappe.has_permission("Item Price", "create")
	can_write_price = frappe.has_permission("Item Price", "write")

	return {
		"read_item": can_read_item,
		"create_item": can_create_item,
		"write_item": can_write_item,
		"read_item_price": can_read_price,
		"create_item_price": can_create_price,
		"write_item_price": can_write_price,
		"can_access": can_read_item and can_read_price and (can_create_item or can_write_item) and (can_create_price or can_write_price),
	}


@frappe.whitelist()
def get_products(pos_profile: str, search_term: str | None = None, item_group: str | None = None) -> list:
	"""Get products for management"""
	if not frappe.has_permission("Item", "read"):
		frappe.throw(_("Not permitted to read Item"))

	pos_profile_doc = frappe.get_cached_doc("POS Profile", pos_profile)

	filters = {"is_sales_item": 1}

	if search_term:
		filters["item_name"] = ["like", f"%{search_term}%"]

	if item_group:
		filters["item_group"] = item_group

	items = frappe.get_all(
		"Item",
		filters=filters,
		fields=[
			"name",
			"item_name",
			"item_group",
			"stock_uom",
			"is_stock_item",
			"image",
			"disabled",
		],
		order_by="creation desc",
		limit=100,
	)
	item_codes = [d.name for d in items]

	if item_codes:
		conversions = frappe.get_all(
			"UOM Conversion Detail",
			filters={"parent": ["in", item_codes]},
			fields=["parent", "uom", "conversion_factor"],
			order_by="idx asc",
		)
		conversion_map = {}
		for row in conversions:
			conversion_map.setdefault(row.parent, []).append(
				{"uom": row.uom, "conversion_factor": row.conversion_factor}
			)
		for item in items:
			item.uom_conversions = conversion_map.get(item.name, [])

	# Fetch prices
	if items and pos_profile_doc.selling_price_list:
		prices = frappe.get_all(
			"Item Price",
			filters={
				"item_code": ["in", item_codes],
				"price_list": pos_profile_doc.selling_price_list,
			},
			fields=["item_code", "price_list_rate"],
		)
		price_map = {p.item_code: p.price_list_rate for p in prices}
		for item in items:
			item.price = price_map.get(item.name, 0.0)
	else:
		for item in items:
			item.price = 0.0

	return items


@frappe.whitelist()
def save_product(pos_profile: str, data: str) -> dict:
	"""Create or update a product for POS"""
	data = json.loads(data)
	is_new = not data.get("item_code")
	permission_type = "create" if is_new else "write"
	if not frappe.has_permission("Item", permission_type):
		frappe.throw(_("Not permitted to {0} Item").format(permission_type))

	pos_profile_doc = frappe.get_cached_doc("POS Profile", pos_profile)

	if is_new:
		item = frappe.new_doc("Item")
		item.item_code = data.get("item_name")
		item.item_group = data.get("item_group") or "Products"
		item.stock_uom = data.get("stock_uom") or "Nos"
		item.is_sales_item = 1
		item.is_stock_item = 1
	else:
		item = frappe.get_doc("Item", data.get("item_code"))

	item.item_name = data.get("item_name")

	if "item_group" in data and data.get("item_group"):
		item.item_group = data.get("item_group")

	if "stock_uom" in data and data.get("stock_uom"):
		item.stock_uom = data.get("stock_uom")

	if "is_stock_item" in data:
		item.is_stock_item = 1 if data.get("is_stock_item") else 0

	if "image" in data and not str(data.get("image") or "").startswith("data:"):
		item.image = data.get("image") or ""

	item.disabled = data.get("disabled", 0)
	_save_uom_conversions(item, data.get("uom_conversions") or [])

	item.save(ignore_permissions=True)

	# Handle Price
	price_list = pos_profile_doc.selling_price_list
	if price_list and "price" in data:
		new_price = flt(data.get("price"))

		# Find existing price
		existing_price = frappe.db.get_value(
			"Item Price",
			{"item_code": item.name, "price_list": price_list},
			"name",
		)

		if existing_price:
			price_doc = frappe.get_doc("Item Price", existing_price)
			price_doc.price_list_rate = new_price
			price_doc.save(ignore_permissions=True)
		else:
			price_doc = frappe.new_doc("Item Price")
			price_doc.item_code = item.name
			price_doc.price_list = price_list
			price_doc.price_list_rate = new_price
			price_doc.selling = 1
			price_doc.save(ignore_permissions=True)

	frappe.db.commit()

	return {"item_code": item.name}


def _save_uom_conversions(item, rows: list) -> None:
	item.set("uoms", [])
	seen = set()
	stock_uom = item.stock_uom
	for row in rows:
		uom = (row.get("uom") or "").strip()
		conversion_factor = flt(row.get("conversion_factor") or 0)
		if not uom or uom == stock_uom or conversion_factor <= 0 or uom in seen:
			continue
		seen.add(uom)
		item.append(
			"uoms",
			{
				"uom": uom,
				"conversion_factor": conversion_factor,
			},
		)
