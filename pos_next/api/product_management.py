import json
import frappe
from frappe import _
from frappe.model.naming import make_autoname
from frappe.utils import cint, flt

from pos_next.api.items import _get_pos_profile_allowed_item_groups


DEFAULT_PAGE_LENGTH = 20
MAX_PAGE_LENGTH = 100
POS_ITEM_CODE_SERIES = "POS-ITEM-.#####"


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
def get_item_groups(pos_profile: str) -> list:
	"""Get leaf item groups allowed for product management in this POS Profile."""
	pos_profile_doc = frappe.get_cached_doc("POS Profile", pos_profile)
	allowed_item_groups = _get_pos_profile_allowed_item_groups(pos_profile_doc)

	filters = {"is_group": 0}
	if allowed_item_groups:
		filters["name"] = ["in", allowed_item_groups]

	return frappe.get_all(
		"Item Group",
		filters=filters,
		fields=["name", "parent_item_group", "is_group"],
		order_by="name asc",
	)


@frappe.whitelist()
def get_products(
	pos_profile: str,
	search_term: str | None = None,
	item_group: str | None = None,
	start: int = 0,
	limit: int = DEFAULT_PAGE_LENGTH,
) -> list:
	"""Get products for management"""
	if not frappe.has_permission("Item", "read"):
		frappe.throw(_("Not permitted to read Item"))

	pos_profile_doc = frappe.get_cached_doc("POS Profile", pos_profile)
	limit_start = max(cint(start), 0)
	page_length = min(max(cint(limit) or DEFAULT_PAGE_LENGTH, 1), MAX_PAGE_LENGTH)

	filters = {"is_sales_item": 1, "disabled": 0}
	allowed_item_groups = _get_pos_profile_allowed_item_groups(pos_profile_doc)
	or_filters = None

	if search_term:
		or_filters = [
			["name", "like", f"%{search_term}%"],
			["item_code", "like", f"%{search_term}%"],
			["item_name", "like", f"%{search_term}%"],
		]

	if item_group:
		if allowed_item_groups and item_group not in allowed_item_groups:
			return []
		filters["item_group"] = item_group
	elif allowed_item_groups:
		filters["item_group"] = ["in", allowed_item_groups]

	items = frappe.get_all(
		"Item",
		filters=filters,
		or_filters=or_filters,
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
		limit_start=limit_start,
		limit_page_length=page_length + 1,
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
	item_name = (data.get("item_name") or "").strip()
	item_group = (data.get("item_group") or "").strip()
	stock_uom = (data.get("stock_uom") or "").strip()

	if not item_name:
		frappe.throw(_("Product Name is required"))
	if not item_group:
		frappe.throw(_("Item Group is required"))
	if not stock_uom:
		frappe.throw(_("UOM is required"))

	is_new = not data.get("item_code")
	permission_type = "create" if is_new else "write"
	if not frappe.has_permission("Item", permission_type):
		frappe.throw(_("Not permitted to {0} Item").format(permission_type))

	pos_profile_doc = frappe.get_cached_doc("POS Profile", pos_profile)
	allowed_item_groups = _get_pos_profile_allowed_item_groups(pos_profile_doc)
	if allowed_item_groups and item_group not in allowed_item_groups:
		frappe.throw(_("Item Group is not allowed for this POS Profile"))

	if is_new:
		item = frappe.new_doc("Item")
		item.item_code = _make_item_code()
		item.item_group = item_group
		item.stock_uom = stock_uom
		item.is_sales_item = 1
		item.is_stock_item = 1
	else:
		item = frappe.get_doc("Item", data.get("item_code"))

	item.item_name = item_name

	item.item_group = item_group

	item.stock_uom = stock_uom

	if "is_stock_item" in data:
		item.is_stock_item = 1 if data.get("is_stock_item") else 0

	if "image" in data and not str(data.get("image") or "").startswith("data:"):
		item.image = data.get("image") or ""

	item.disabled = data.get("disabled", 0)
	_save_uom_conversions(item, data.get("uom_conversions") or [])

	item.save()

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
			if not frappe.has_permission("Item Price", "write"):
				frappe.throw(_("Not permitted to write Item Price"))
			price_doc = frappe.get_doc("Item Price", existing_price)
			price_doc.price_list_rate = new_price
			price_doc.save()
		else:
			if not frappe.has_permission("Item Price", "create"):
				frappe.throw(_("Not permitted to create Item Price"))
			price_doc = frappe.new_doc("Item Price")
			price_doc.item_code = item.name
			price_doc.price_list = price_list
			price_doc.price_list_rate = new_price
			price_doc.selling = 1
			price_doc.save()

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


def _make_item_code() -> str:
	return make_autoname(POS_ITEM_CODE_SERIES)
