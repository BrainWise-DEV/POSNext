"""Shared test fixtures for the Price Group tests."""

import frappe

from pos_next.price_group_ownership import (
	ITEM_PRICE_OWNER_FIELD,
	MANAGED_PRICE_LIST_PREFIX,
	OWNER_FIELD,
	PRICE_LIST_OWNER_FIELD,
	PROFILE_OWNER_FIELD,
	PROFILE_PREVIOUS_PRICE_LIST_FIELD,
)


def get_default_company() -> str:
	"""Resolve an existing company with a stable sort or create a test company if none exists."""
	company = frappe.db.get_value("Company", {}, "name", order_by="creation asc")
	if company:
		return company
	doc = frappe.get_doc(
		{
			"doctype": "Company",
			"company_name": "_Test POS Next Company",
			"default_currency": "IDR",
			"country": "Indonesia",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def get_second_company() -> str:
	"""Resolve or create a distinct second company."""
	primary = get_default_company()
	companies = frappe.get_all(
		"Company", filters={"name": ("!=", primary)}, pluck="name", order_by="creation asc"
	)
	if companies:
		return companies[0]
	doc = frappe.get_doc(
		{
			"doctype": "Company",
			"company_name": "_Test Second Company",
			"default_currency": get_default_currency(primary),
			"country": "Indonesia",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def get_default_currency(company: str | None = None) -> str:
	"""Derive currency from the resolved company's default_currency."""
	comp = company or get_default_company()
	return frappe.db.get_value("Company", comp, "default_currency") or "IDR"


def ensure_uom(uom_name: str) -> str:
	"""Return uom_name, creating the UOM record if missing."""
	if not frappe.db.exists("UOM", uom_name):
		frappe.get_doc({"doctype": "UOM", "uom_name": uom_name}).insert(ignore_permissions=True)
	return uom_name


def base_uom() -> str:
	"""Return a base UOM existing on site or create fallback."""
	existing = frappe.db.get_value("UOM", {"name": "Nos"}, "name") or frappe.db.get_value(
		"UOM", {}, "name", order_by="creation asc"
	)
	if existing:
		return existing
	return ensure_uom("_Test Base UOM")


def custom_uom() -> str:
	"""Return a secondary UOM distinct from base_uom."""
	base = base_uom()
	existing = frappe.db.get_value("UOM", {"name": ("!=", base)}, "name", order_by="creation asc")
	if existing:
		uom = existing
	else:
		uom = ensure_uom("_Test Custom UOM")
	assert uom != base, f"custom_uom ({uom}) must be distinct from base_uom ({base})"
	return uom


def item_group() -> str:
	"""Return a leaf Item Group, creating one if the site has none."""
	existing = frappe.db.get_value("Item Group", {"is_group": 0}, "name", order_by="creation asc")
	if existing:
		return existing

	parent = frappe.db.get_value("Item Group", {"is_group": 1}, "name", order_by="creation asc")
	if not parent:
		root = frappe.get_doc(
			{"doctype": "Item Group", "item_group_name": "_Test PN Root Group", "is_group": 1}
		)
		root.flags.ignore_mandatory = True
		root.insert(ignore_permissions=True)
		parent = root.name

	group = frappe.get_doc(
		{
			"doctype": "Item Group",
			"item_group_name": "_Test PN Leaf Group",
			"is_group": 0,
			"parent_item_group": parent,
		}
	)
	group.insert(ignore_permissions=True)
	return group.name


def make_test_item(
	suffix: str, stock_uom: str | None = None, *, has_batch_no: int = 0, is_stock_item: int = 0
) -> str:
	"""Create a test Item with resolved leaf Item Group and stock UOM."""
	item_code = f"_Test Item {suffix}"
	if frappe.db.exists("Item", item_code):
		return item_code

	uom = stock_uom or base_uom()
	ensure_uom(uom)
	doc = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": item_code,
			"item_name": item_code,
			"item_group": item_group(),
			"stock_uom": uom,
			"is_stock_item": is_stock_item,
			"has_batch_no": has_batch_no,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def make_test_warehouse(suffix: str, company: str) -> str:
	"""Create a leaf Warehouse linked to the given company."""
	wh_name = f"_Test Warehouse {suffix} - {company[:10]}"
	existing = frappe.db.get_value("Warehouse", {"warehouse_name": wh_name, "company": company}, "name")
	if existing:
		return existing

	parent_wh = frappe.db.get_value(
		"Warehouse", {"is_group": 1, "company": company}, "name", order_by="creation asc"
	)
	doc = frappe.get_doc(
		{
			"doctype": "Warehouse",
			"warehouse_name": wh_name,
			"company": company,
			"is_group": 0,
			"parent_warehouse": parent_wh,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def get_default_cost_center(company: str) -> str:
	"""Resolve a cost center for the company or create fallback."""
	existing = frappe.db.get_value(
		"Cost Center", {"company": company, "is_group": 0}, "name", order_by="creation asc"
	)
	if existing:
		return existing
	parent_cc = frappe.db.get_value(
		"Cost Center", {"company": company, "is_group": 1}, "name", order_by="creation asc"
	)
	doc = frappe.get_doc(
		{
			"doctype": "Cost Center",
			"cost_center_name": f"_Test CC {company[:10]}",
			"company": company,
			"is_group": 0,
			"parent_cost_center": parent_cc,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def get_default_account(company: str, account_type: str = "Expense") -> str:
	"""Resolve an account for the company or create fallback."""
	if account_type == "Expense":
		existing = frappe.db.get_value(
			"Account",
			{
				"company": company,
				"account_type": (
					"in",
					["Expense", "Expense Account", "Indirect Expense", "Cost of Goods Sold"],
				),
				"is_group": 0,
			},
			"name",
			order_by="creation asc",
		) or frappe.db.get_value(
			"Account",
			{"company": company, "root_type": "Expense", "is_group": 0},
			"name",
			order_by="creation asc",
		)
	else:
		existing = frappe.db.get_value(
			"Account",
			{"company": company, "account_type": account_type, "is_group": 0},
			"name",
			order_by="creation asc",
		)

	if not existing:
		existing = frappe.db.get_value(
			"Account", {"company": company, "is_group": 0}, "name", order_by="creation asc"
		)
	return existing


def get_default_mode_of_payment(company: str) -> str:
	"""Resolve an enabled Mode of Payment with an account for company without mutating shared data."""
	mop_list = frappe.get_all(
		"Mode of Payment", filters={"enabled": 1}, pluck="name", order_by="creation asc"
	)
	for mop_name in mop_list:
		has_account = frappe.db.exists("Mode of Payment Account", {"parent": mop_name, "company": company})
		if has_account:
			return mop_name

	# Create a test-owned MOP with an account for this company
	mop_name = f"_Test MOP {company[:10]}"
	if frappe.db.exists("Mode of Payment", mop_name):
		return mop_name

	default_account = frappe.db.get_value(
		"Account",
		{"company": company, "account_type": ("in", ["Cash", "Bank"]), "is_group": 0},
		"name",
		order_by="creation asc",
	) or frappe.db.get_value("Account", {"company": company, "is_group": 0}, "name", order_by="creation asc")

	accounts = []
	if default_account:
		accounts.append({"company": company, "default_account": default_account})

	mop = frappe.get_doc(
		{
			"doctype": "Mode of Payment",
			"mode_of_payment": mop_name,
			"enabled": 1,
			"type": "Cash",
			"accounts": accounts,
		}
	)
	mop.insert(ignore_permissions=True)
	return mop.name


def make_test_pos_profile(suffix: str, company: str, warehouse: str, *, payments=None) -> str:
	"""Create a POS Profile with mandatory payment methods populated."""
	profile_name = f"_Test POS Profile {suffix}"
	if frappe.db.exists("POS Profile", profile_name):
		return profile_name

	if payments is None:
		mop = get_default_mode_of_payment(company)
		payment_rows = [{"mode_of_payment": mop, "default": 1}]
	else:
		payment_rows = payments

	currency = get_default_currency(company)
	write_off_account = get_default_account(company, "Expense")
	write_off_cc = get_default_cost_center(company)
	income_account = (
		frappe.db.get_value(
			"Account",
			{"company": company, "root_type": "Income", "is_group": 0},
			"name",
			order_by="creation asc",
		)
		or write_off_account
	)
	expense_account = write_off_account

	doc = frappe.get_doc(
		{
			"doctype": "POS Profile",
			"name": profile_name,
			"company": company,
			"warehouse": warehouse,
			"currency": currency,
			"payments": payment_rows,
			"write_off_account": write_off_account,
			"write_off_cost_center": write_off_cc,
			"income_account": income_account,
			"expense_account": expense_account,
			"cost_center": write_off_cc,
			"write_off_limit": 1.0,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def make_price_group(name: str, *, items, outlets=(), enabled=1, currency=None):
	"""Create and insert a Price Group document."""
	resolved_currency = currency or get_default_currency()
	doc = frappe.get_doc(
		{
			"doctype": "Price Group",
			"price_group_name": name,
			"enabled": enabled,
			"currency": resolved_currency,
			"items": [
				{
					"item_code": item.get("item_code"),
					"rate": item.get("rate"),
					**({"uom": item["uom"]} if "uom" in item else {}),
				}
				for item in items
			],
			"outlets": [
				{
					"company": outlet.get("company"),
					"warehouse": outlet.get("warehouse"),
				}
				for outlet in outlets
			],
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def make_test_customer(suffix: str) -> str:
	"""Resolve or create a test Customer."""
	cust_name = f"_Test Customer {suffix}"
	if frappe.db.exists("Customer", cust_name):
		return cust_name
	existing = frappe.db.get_value("Customer", {}, "name", order_by="creation asc")
	if existing:
		return existing
	cg = (
		frappe.db.get_value("Customer Group", {"is_group": 0}, "name", order_by="creation asc")
		or "All Customer Groups"
	)
	doc = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": cust_name,
			"customer_group": cg,
			"territory": "All Territories",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def make_test_batch(item_code: str, suffix: str) -> str:
	"""Create a Batch for item_code."""
	batch_id = f"_Test Batch {suffix}"
	if frappe.db.exists("Batch", batch_id):
		return batch_id
	doc = frappe.get_doc(
		{
			"doctype": "Batch",
			"batch_id": batch_id,
			"item": item_code,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def manual_item_price(item_code: str, price_list: str, **overrides) -> str:
	"""Create a manual unmanaged Item Price on the given Price List."""
	stock_uom = frappe.db.get_value("Item", item_code, "stock_uom") or base_uom()
	currency = frappe.db.get_value("Price List", price_list, "currency") or get_default_currency()
	payload = {
		"doctype": "Item Price",
		"item_code": item_code,
		"price_list": price_list,
		"price_list_rate": 100.0,
		"currency": currency,
		"uom": stock_uom,
	}
	payload.update(overrides)
	doc = frappe.get_doc(payload)
	doc.insert(ignore_permissions=True)
	return doc.name
