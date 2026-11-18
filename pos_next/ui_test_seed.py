# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Seed, tear down and check the data of the UI test plan (F&F, coupons, offers).

Plan: docs/superpowers/plans/2026-11-18-ui-test-plan-ff-coupons-offers.md

	bench --site <site> execute pos_next.ui_test_seed.seed
	bench --site <site> execute pos_next.ui_test_seed.teardown
	bench --site <site> execute pos_next.ui_test_seed.check
	bench --site <site> execute pos_next.ui_test_seed.set_ff --kwargs "{'max_discount_per_order': 50}"
	bench --site <site> execute pos_next.ui_test_seed.reset_ff

Every record this module creates is named ``UIT-…`` (users and emails ``uit-…@….example``),
so teardown deletes only its own records. Rows that cannot take a name (POS Settings,
Pricing Rules) get one through ``insert(set_name=…)`` and are also matched by their link.

The site settings seed changes are recorded in a private File called ``UIT-seed-snapshot.json``
before the first change. A second seed reuses it, so the original values are never
overwritten, and teardown restores them from it.

posnext_promotions is optional: its doctypes and fields are named only as strings, and
its functions are reached through ``frappe.get_attr``. pos_next never imports it.
"""

from __future__ import annotations

import json
import secrets

import frappe
from frappe.utils import cint, cstr, flt, getdate, now_datetime, nowdate
from frappe.utils.nestedset import get_root_of

PREFIX = "UIT-"
EMAIL_PREFIX = "uit-"
PROMOTIONS_APP = "posnext_promotions"

COMPANY_CURRENCY = "SAR"
PRICE_LIST = "UIT-Selling SAR"
ITEM_GROUP = "UIT-Group"
BRAND = "UIT-Brand"
TAX_TITLE = "UIT-VAT 15%"
TAX_RATE = 15

APPROVED_DOMAIN = "uit-ff.example"
USER_DOMAIN = "uit-pos.example"
SNAPSHOT_FILE = "UIT-seed-snapshot.json"

FF_SETTINGS = "Friends and Family Settings"
FF_LEDGER_DOCTYPES = ("Friends and Family Usage", "Friends and Family Usage Total", "Friends and Family Log")

PROFILE_FF = "UIT-FF Profile"
PROFILE_NOFF = "UIT-NOFF Profile"
WALK_IN = "UIT-Walk-in"

# item_code: (price, purpose). None = no Item Price on purpose.
ITEMS = {
	"UIT-A": (100, "Plain F&F line"),
	"UIT-A2": (100, "Second plain line, outside the scoped coupon"),
	"UIT-B": (200, "Under the 20% price rule: F&F 30% wins"),
	"UIT-C": (50, "Under the 40% price rule: the promotion wins"),
	"UIT-EXCL": (80, "Excluded from F&F"),
	"UIT-ODD": (33.33, "Rounding"),
	"UIT-P100": (25, "Under the 100% price rule: becomes a free row"),
	"UIT-BXGY": (60, "Buy 2 get 1 of the same item"),
	"UIT-TRIG": (100, "Trigger of the different-item free item"),
	"UIT-GIFT": (30, "Gift of the free-item and cart-total rules"),
	"UIT-GWP1": (30, "GWP scope item"),
	"UIT-GWP2": (45, "GWP scope item"),
	"UIT-NOPRICE": (None, "No Item Price"),
}

# name: (email, verified, mobile). The shared customer differs from UIT-Verified only in case.
# UIT-OTP1..3 and UIT-Mag are spent by the OTP checks, so the cart checks keep their customers.
CUSTOMERS = {
	"UIT-Verified": (f"{EMAIL_PREFIX}verified@{APPROVED_DOMAIN}", True, None),
	"UIT-Cap": (f"{EMAIL_PREFIX}cap@{APPROVED_DOMAIN}", True, None),
	"UIT-Unverified": (f"{EMAIL_PREFIX}unverified@{APPROVED_DOMAIN}", False, None),
	"UIT-Shared": (f"{EMAIL_PREFIX}verified@{APPROVED_DOMAIN.upper()}", False, None),
	"UIT-OTP1": (f"{EMAIL_PREFIX}otp1@{APPROVED_DOMAIN}", False, None),
	"UIT-OTP2": (f"{EMAIL_PREFIX}otp2@{APPROVED_DOMAIN}", False, None),
	"UIT-OTP3": (f"{EMAIL_PREFIX}otp3@{APPROVED_DOMAIN}", False, None),
	"UIT-Mag": (f"{EMAIL_PREFIX}mag@{APPROVED_DOMAIN}", False, "+442079460958"),
	WALK_IN: (None, False, None),
}

# Pricing Rules (ERPNext). Each is limited to the UIT price list, so it never reaches other carts.
PRICING_RULES = {
	"UIT-PR-B20": {"price": 20, "items": ["UIT-B"]},
	"UIT-PR-C40": {"price": 40, "items": ["UIT-C"]},
	"UIT-PR-P100": {"price": 100, "items": ["UIT-P100"]},
	"UIT-PR-CART5": {"price": 5, "transaction": True, "min_amt": 1000},
	"UIT-PR-BXGY": {"product": True, "items": ["UIT-BXGY"], "same_item": 1, "min_qty": 2, "free_qty": 1},
	"UIT-PR-FREE": {
		"product": True,
		"items": ["UIT-TRIG"],
		"free_item": "UIT-GIFT",
		"min_qty": 1,
		"free_qty": 1,
	},
	"UIT-PR-CART-GIFT": {
		"product": True,
		"transaction": True,
		"min_amt": 500,
		"free_item": "UIT-GIFT",
		"free_qty": 1,
	},
}
# Needs promotions' promotion_type / gwp_paid_qty_basis fields. A free_item is set so that
# ERPNext does not turn it into a same-item rule, which F&F would classify as Buy X Get Y.
GWP_RULE = (
	"UIT-PR-GWP",
	{
		"product": True,
		"items": ["UIT-GWP1", "UIT-GWP2"],
		"free_item": "UIT-GWP1",
		"min_qty": 2,
		"free_qty": 1,
		"mixed_conditions": 1,
		"promotion_type": "GWP",
		"gwp_paid_qty_basis": "Max Price",
	},
)
# The kind promotions' classifier must give each seeded rule (checked after seed).
EXPECTED_KINDS = {
	"UIT-PR-B20": "price",
	"UIT-PR-CART5": "price",
	"UIT-PR-BXGY": "bxgy",
	"UIT-PR-FREE": "free_item",
	"UIT-PR-CART-GIFT": "cart_total_gift",
	"UIT-PR-GWP": "gwp",
}

# POS Coupons (pos_next). A Percentage coupon without max_amount is line-level, else order-level.
COUPONS = {
	"UIT-L10": {"discount_type": "Percentage", "discount_percentage": 10},
	"UIT-L20": {"discount_type": "Percentage", "discount_percentage": 20},
	"UIT-L50": {"discount_type": "Percentage", "discount_percentage": 50},
	"UIT-L100": {"discount_type": "Percentage", "discount_percentage": 100},
	"UIT-O40": {"discount_type": "Amount", "discount_amount": 40},
	"UIT-O100": {"discount_type": "Amount", "discount_amount": 100},
	"UIT-MAX1": {"discount_type": "Percentage", "discount_percentage": 10, "maximum_use": 1},
}
# Need promotions' POS Coupon fields.
PROMOTION_COUPONS = {
	"UIT-SI20": {
		"discount_type": "Percentage",
		"discount_percentage": 20,
		"apply_scope": "Item Code",
		"applicable_items": [{"item_code": "UIT-A"}],
	},
	"UIT-BET": {
		"discount_type": "Percentage",
		"discount_percentage": 30,
		"promotion_conflict": "Better of the two",
	},
}

# F&F Settings scalars the seed sets (caps are non-binding for ordinary carts; checks lower them with set_ff).
FF_VALUES = {
	"enabled": 1,
	"discount_percentage": 30,
	"discount_scope": "Entire Cart",
	"allow_free_gift_with_ff": 0,
	"start_date": None,
	"end_date": None,
	"max_discount_per_order": 500,
	"max_discount_per_customer_month": 2000,
	"on_cap_breach_at_submit": "Allow and log",
	"unclassified_promotion_policy": "Compete",
}
FF_EXCLUDED_ITEMS = ("UIT-EXCL",)

VERIFICATION_FIELDS = ("custom_email_verified", "custom_verified_email")

# Doctypes holding records named UIT-… (checked and deleted by name).
NAMED_MASTER_DOCTYPES = (
	"POS Coupon",
	"Pricing Rule",
	"POS Profile",
	"Customer",
	"Item Price",
	"Item",
	"Price List",
	"Item Group",
	"Brand",
	"Sales Taxes and Charges Template",
)
# Links that identify a UIT test record (the link sweep in teardown and check).
LINK_TARGETS = ("Customer", "POS Profile", "Item", "POS Coupon", "Price List", "Pricing Rule")
# Rows of these doctypes are master data, removed in their own step.
SWEEP_SKIP = frozenset(NAMED_MASTER_DOCTYPES) | {"POS Settings", "User", "Wallet"} | set(FF_LEDGER_DOCTYPES)
# Transactions first: closing shifts before their invoices, returns before originals.
SWEEP_ORDER = (
	"POS Closing Shift",
	"Sales Invoice",
	"Sales Order",
	"Payment Entry",
	"Journal Entry",
	"Wallet Transaction",
	"POS Opening Shift",
)


# ---- helpers ---------------------------------------------------------------


def promotions_installed() -> bool:
	return PROMOTIONS_APP in frappe.get_installed_apps()


def _like(prefix: str = PREFIX) -> list:
	return ["like", f"{prefix}%"]


def _company() -> str:
	companies = frappe.get_all(
		"Company", filters={"default_currency": COMPANY_CURRENCY}, pluck="name", order_by="creation asc"
	)
	if not companies:
		frappe.throw(f"No company with default currency {COMPANY_CURRENCY} on this site.")
	default = frappe.defaults.get_global_default("company")
	return default if default in companies else companies[0]


def _source_profile(company: str) -> frappe._dict:
	"""An existing POS Profile of the company: its warehouse, accounts and payments are copied."""
	name = frappe.db.get_value(
		"POS Profile",
		{"company": company, "disabled": 0, "name": ["not like", f"{PREFIX}%"]},
		"name",
		order_by="creation asc",
	)
	if not name:
		frappe.throw(f"No POS Profile on {company} to copy the warehouse, accounts and payments from.")
	return frappe.get_doc("POS Profile", name)


def _leaf(doctype: str) -> str:
	name = frappe.db.get_value(doctype, {"is_group": 0}, "name", order_by="lft asc")
	if not name:
		frappe.throw(f"No leaf {doctype} on this site.")
	return name


def _insert(values: dict, name: str):
	doc = frappe.get_doc(values)
	doc.flags.ignore_permissions = True
	doc.insert(set_name=name, ignore_permissions=True)
	return doc


def _require_fields(doctype: str, fields) -> None:
	meta = frappe.get_meta(doctype)
	missing = [f for f in fields if not meta.has_field(f)]
	if missing:
		frappe.throw(f"{doctype} has no field {', '.join(missing)}. Migrate the site before seeding.")


def _promotions_fn(path: str):
	return frappe.get_attr(f"{PROMOTIONS_APP}.{path}")


# ---- snapshot of the site settings the seed changes --------------------------------


def _snapshot_name() -> str | None:
	return frappe.db.get_value("File", {"file_name": SNAPSHOT_FILE}, "name")


def _snapshot_content(name: str) -> str:
	content = frappe.get_doc("File", name).get_content()
	return content.decode() if isinstance(content, bytes) else content


def _load_snapshot() -> dict | None:
	name = _snapshot_name()
	return json.loads(_snapshot_content(name)) if name else None


def _save_snapshot(snapshot: dict) -> None:
	content = json.dumps(snapshot, indent=1, sort_keys=True, default=str)
	name = _snapshot_name()
	if name:
		if _snapshot_content(name) == content:
			return
		frappe.delete_doc("File", name, force=True, ignore_permissions=True, delete_permanently=True)
	frappe.get_doc(
		{"doctype": "File", "file_name": SNAPSHOT_FILE, "is_private": 1, "content": content}
	).insert(ignore_permissions=True)


def _ff_settings_image() -> dict:
	return frappe.get_doc(FF_SETTINGS).as_dict(convert_dates_to_str=True, no_nulls=False)


def _restore_ff_settings(image: dict) -> None:
	doc = frappe.get_doc(FF_SETTINGS)
	skip_row = {
		"name",
		"idx",
		"parent",
		"parentfield",
		"parenttype",
		"creation",
		"modified",
		"owner",
		"modified_by",
		"doctype",
	}
	for df in doc.meta.fields:
		if df.fieldtype in ("Table", "Table MultiSelect"):
			doc.set(df.fieldname, [])
			for row in image.get(df.fieldname) or []:
				doc.append(df.fieldname, {k: v for k, v in row.items() if k not in skip_row})
		elif df.fieldtype not in frappe.model.no_value_fields:
			doc.set(df.fieldname, image.get(df.fieldname))
	doc.flags.ignore_validate = True
	doc.save(ignore_permissions=True)


# ---- live pricing rules that would change the test carts ---------------------------------


def _live_rules_touching_uit(company: str) -> list[str]:
	"""Enabled selling rules (not ours, not coupon-based) that a UIT cart would pick up."""
	today = getdate(nowdate())
	rows = frappe.get_all(
		"Pricing Rule",
		filters={
			"disable": 0,
			"selling": 1,
			"coupon_code_based": 0,
			"name": ["not like", f"{PREFIX}%"],
			"title": ["not like", f"{PREFIX}%"],
		},
		fields=["name", "apply_on", "company", "for_price_list", "valid_from", "valid_upto"],
	)
	group_bounds = frappe.db.get_value("Item Group", ITEM_GROUP, ["lft", "rgt"], as_dict=True)
	hits = []
	for row in rows:
		if row.company and row.company != company:
			continue
		if row.for_price_list and row.for_price_list != PRICE_LIST:
			continue
		if (row.valid_from and getdate(row.valid_from) > today) or (
			row.valid_upto and getdate(row.valid_upto) < today
		):
			continue
		if row.apply_on == "Transaction" or _rule_covers_uit(row, group_bounds):
			hits.append(row.name)
	return sorted(hits)


def _rule_covers_uit(row, group_bounds) -> bool:
	if row.apply_on == "Item Code":
		return bool(
			frappe.get_all(
				"Pricing Rule Item Code", filters={"parent": row.name, "item_code": _like()}, limit=1
			)
		)
	if row.apply_on == "Brand":
		return bool(
			frappe.get_all("Pricing Rule Brand", filters={"parent": row.name, "brand": _like()}, limit=1)
		)
	if row.apply_on == "Item Group" and group_bounds:
		groups = frappe.get_all("Pricing Rule Item Group", filters={"parent": row.name}, pluck="item_group")
		for group in groups:
			bounds = frappe.db.get_value("Item Group", group, ["lft", "rgt"], as_dict=True)
			if bounds and bounds.lft <= group_bounds.lft and bounds.rgt >= group_bounds.rgt:
				return True
	return False


# ---- seed ----------------------------------------------------------------


def seed():
	"""Create the UIT test data. Running it again changes nothing."""
	frappe.only_for("System Manager")
	promotions = promotions_installed()
	_require_fields(
		"Customer", (*VERIFICATION_FIELDS, "custom_email_verified_via", "custom_email_verified_on")
	)
	if promotions:
		_require_fields("POS Profile", ("allow_friends_family",))
		_require_fields("Pricing Rule", ("promotion_type", "gwp_paid_qty_basis"))
		_require_fields("POS Coupon", ("apply_scope", "promotion_conflict", "applicable_items"))

	company = _company()
	created: list[str] = []
	passwords: dict[str, str] = {}

	_seed_catalog(company, created)
	_seed_customers(created)
	tax = _seed_tax(company, created)
	users = _seed_users(created, passwords)
	_seed_profiles(company, tax, users, promotions, created)
	_seed_rules(company, promotions, created)
	_seed_coupons(company, promotions, created)

	snapshot = _load_snapshot()
	first_snapshot = snapshot is None
	snapshot = snapshot or {"created_on": str(now_datetime()), "disabled_rules": [], "ff_settings": None}
	if promotions and snapshot.get("ff_settings") is None:
		snapshot["ff_settings"] = _ff_settings_image()
	to_disable = [r for r in _live_rules_touching_uit(company) if r not in snapshot["disabled_rules"]]
	snapshot["disabled_rules"] = sorted(set(snapshot["disabled_rules"]) | set(to_disable))
	# The snapshot is written before any setting changes.
	_save_snapshot(snapshot)

	for rule in to_disable:
		frappe.db.set_value("Pricing Rule", rule, "disable", 1)
		frappe.clear_document_cache("Pricing Rule", rule)
	ff_changed = _seed_ff_settings() if promotions else False

	kinds = _verify_kinds() if promotions else {}
	frappe.db.commit()

	if promotions:
		_promotions_fn("promotions.friends_and_family_eligibility.clear_cache")()
	result = {
		"company": company,
		"promotions_installed": promotions,
		"created": created,
		"disabled_live_rules": to_disable,
		"ff_settings_changed": ff_changed,
		"snapshot_created": first_snapshot,
		"rule_kinds": kinds,
	}
	print(json.dumps(result, indent=1, default=str))
	for user, password in passwords.items():
		print(f"PASSWORD (shown once) {user}: {password}")
	if created or to_disable or ff_changed:
		print("Run `bench --site <site> clear-cache` and reload open POS tabs.")
	return result


def _seed_catalog(company: str, created: list) -> None:
	if not frappe.db.exists("Price List", PRICE_LIST):
		_insert(
			{
				"doctype": "Price List",
				"price_list_name": PRICE_LIST,
				"currency": COMPANY_CURRENCY,
				"selling": 1,
				"enabled": 1,
			},
			PRICE_LIST,
		)
		created.append(f"Price List {PRICE_LIST}")
	if not frappe.db.exists("Item Group", ITEM_GROUP):
		root = get_root_of("Item Group")
		_insert(
			{
				"doctype": "Item Group",
				"item_group_name": ITEM_GROUP,
				"parent_item_group": root,
				"is_group": 0,
			},
			ITEM_GROUP,
		)
		created.append(f"Item Group {ITEM_GROUP}")
	if not frappe.db.exists("Brand", BRAND):
		_insert({"doctype": "Brand", "brand": BRAND}, BRAND)
		created.append(f"Brand {BRAND}")
	for code, (price, purpose) in ITEMS.items():
		if not frappe.db.exists("Item", code):
			# Non-stock items: no stock ledger to create or clean up.
			_insert(
				{
					"doctype": "Item",
					"item_code": code,
					"item_name": code,
					"description": purpose,
					"item_group": ITEM_GROUP,
					"brand": BRAND,
					"stock_uom": "Nos",
					"is_stock_item": 0,
					"is_sales_item": 1,
					"include_item_in_manufacturing": 0,
				},
				code,
			)
			created.append(f"Item {code}")
		price_name = f"{PREFIX}IP-{code}"
		if price is not None and not frappe.db.exists("Item Price", price_name):
			_insert(
				{
					"doctype": "Item Price",
					"item_code": code,
					"price_list": PRICE_LIST,
					"price_list_rate": price,
					"currency": COMPANY_CURRENCY,
					"selling": 1,
				},
				price_name,
			)
			created.append(f"Item Price {price_name}")


def _seed_customers(created: list) -> None:
	group, territory = _leaf("Customer Group"), _leaf("Territory")
	for name, (email, verified, mobile) in CUSTOMERS.items():
		if frappe.db.exists("Customer", name):
			continue
		# No email on insert: ERPNext would create a Contact. It is set below with db.set_value,
		# which also skips the Customer.validate guard on the verification fields.
		_insert(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_type": "Individual",
				"customer_group": group,
				"territory": territory,
			},
			name,
		)
		values = {}
		if email:
			values["email_id"] = email
		if mobile:
			values["mobile_no"] = mobile
		if verified:
			values.update(
				{
					"custom_email_verified": 1,
					"custom_verified_email": email.lower(),
					"custom_email_verified_via": "frappe_email",
					"custom_email_verified_on": now_datetime(),
				}
			)
		if values:
			frappe.db.set_value("Customer", name, values, update_modified=False)
		created.append(f"Customer {name}")


def _seed_tax(company: str, created: list) -> str | None:
	existing = frappe.db.get_value(
		"Sales Taxes and Charges Template", {"title": TAX_TITLE, "company": company}, "name"
	)
	if existing:
		return existing
	account = frappe.db.get_value(
		"Account",
		{"company": company, "account_type": "Tax", "is_group": 0, "disabled": 0},
		"name",
		order_by="lft asc",
	)
	if not account:
		print(f"No Tax account on {company}: the UIT profiles get no tax template.")
		return None
	doc = frappe.get_doc(
		{
			"doctype": "Sales Taxes and Charges Template",
			"title": TAX_TITLE,
			"company": company,
			"taxes": [
				{
					"charge_type": "On Net Total",
					"account_head": account,
					"rate": TAX_RATE,
					"description": TAX_TITLE,
				}
			],
		}
	).insert(ignore_permissions=True)
	created.append(f"Sales Taxes and Charges Template {doc.name}")
	return doc.name


def pos_roles() -> dict:
	"""The cashier and manager roles, read from pos_next's role fixtures and DocType permissions."""
	roles: list[str] = []
	for fixture in frappe.get_hooks("fixtures", app_name="pos_next") or []:
		if isinstance(fixture, dict) and fixture.get("dt") == "Role":
			for field, op, values in fixture.get("filters") or []:
				if field == "role_name" and op == "in":
					roles.extend(values)
	if not roles:
		frappe.throw("pos_next hooks list no Role fixtures.")
	# The cashier sells: create on Sales Invoice (Custom DocPerm fixture).
	cashier = [
		r
		for r in roles
		if frappe.db.exists("Custom DocPerm", {"role": r, "parent": "Sales Invoice", "create": 1})
	]
	# The manager writes the POS Settings verification section (permlevel 1).
	settings_perms = frappe.get_meta("POS Settings").permissions
	manager = [
		r
		for r in roles
		if any(p.role == r and cint(p.permlevel) == 1 and cint(p.write) for p in settings_perms)
	]
	if not cashier or not manager:
		frappe.throw(f"Could not tell the cashier and manager roles apart in {roles}. Is the site migrated?")
	return {"cashier": cashier, "manager": manager}


def _seed_users(created: list, passwords: dict) -> list[str]:
	roles = pos_roles()
	specs = {
		f"{EMAIL_PREFIX}cashier@{USER_DOMAIN}": ("UIT Cashier", roles["cashier"]),
		f"{EMAIL_PREFIX}cashier2@{USER_DOMAIN}": ("UIT Cashier 2", roles["cashier"]),
		f"{EMAIL_PREFIX}manager@{USER_DOMAIN}": (
			"UIT Manager",
			sorted(set(roles["manager"]) | set(roles["cashier"])),
		),
	}
	from frappe.core.doctype.user.user import create_contact
	from frappe.utils.password import update_password

	for email, (first_name, user_roles) in specs.items():
		if frappe.db.exists("User", email):
			continue
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": first_name,
				"user_type": "System User",
				"send_welcome_email": 0,
				"roles": [{"role": role} for role in user_roles],
			}
		).insert(ignore_permissions=True)
		# User.on_update queues this after commit; doing it now keeps a second seed from seeing a new Contact.
		create_contact(user, ignore_mandatory=True)
		password = secrets.token_urlsafe(18) + "aA1!"
		update_password(email, password)
		passwords[email] = password
		created.append(f"User {email}")
	return list(specs)


def _seed_profiles(company: str, tax: str | None, users: list[str], promotions: bool, created: list) -> None:
	source = _source_profile(company)
	for name, allow_ff in ((PROFILE_FF, 1), (PROFILE_NOFF, 0)):
		if not frappe.db.exists("POS Profile", name):
			values = {
				"doctype": "POS Profile",
				"company": company,
				"currency": COMPANY_CURRENCY,
				"selling_price_list": PRICE_LIST,
				"customer": WALK_IN,
				"warehouse": source.warehouse,
				"write_off_account": source.write_off_account,
				"write_off_cost_center": source.write_off_cost_center,
				"cost_center": source.get("cost_center"),
				"update_stock": 0,
				"ignore_pricing_rule": 0,
				"taxes_and_charges": tax,
				"payments": [
					{"mode_of_payment": p.mode_of_payment, "default": p.default} for p in source.payments
				],
				"item_groups": [{"item_group": ITEM_GROUP}],
				# One default profile per user and company (ERPNext).
				"applicable_for_users": [
					{"user": u, "default": 1 if name == PROFILE_FF else 0} for u in users
				],
			}
			if promotions:
				values["allow_friends_family"] = allow_ff
			_insert(values, name)
			created.append(f"POS Profile {name}")
		settings_name = f"{PREFIX}POS Settings {name.removeprefix(PREFIX)}"
		if not frappe.db.exists("POS Settings", {"pos_profile": name}):
			_insert(
				{
					"doctype": "POS Settings",
					"pos_profile": name,
					"enabled": 1,
					# S0: item discount on, rate edit off, invoice discount off, no maximum.
					"allow_user_to_edit_item_discount": 1,
					"allow_user_to_edit_rate": 0,
					"allow_user_to_edit_additional_discount": 0,
					"max_discount_allowed": 0,
					"allow_sales_order": 1,
					"allow_delete_offline_invoice": 1,
					"enable_customer_email_verification": 1,
					"verification_provider": None,
					"otp_ttl_seconds": 900,
					"otp_resend_cooldown": 60,
					"otp_max_sends_per_hour": 5,
				},
				settings_name,
			)
			created.append(f"POS Settings {settings_name}")


def _rule_doc(name: str, spec: dict, company: str) -> dict:
	values = {
		"doctype": "Pricing Rule",
		"title": name,
		"company": company,
		"currency": COMPANY_CURRENCY,
		"for_price_list": PRICE_LIST,
		"selling": 1,
		"buying": 0,
		"apply_on": "Transaction" if spec.get("transaction") else "Item Code",
		"items": [{"item_code": code} for code in spec.get("items") or []],
		"min_qty": spec.get("min_qty", 0),
		"min_amt": spec.get("min_amt", 0),
	}
	if spec.get("product"):
		values.update(
			{
				"price_or_product_discount": "Product",
				"same_item": spec.get("same_item", 0),
				"free_item": spec.get("free_item"),
				"free_qty": spec.get("free_qty", 1),
				"mixed_conditions": spec.get("mixed_conditions", 0),
			}
		)
	else:
		values.update(
			{
				"price_or_product_discount": "Price",
				"rate_or_discount": "Discount Percentage",
				"discount_percentage": spec["price"],
			}
		)
		if spec.get("transaction"):
			values["apply_discount_on"] = "Grand Total"
	for field in ("promotion_type", "gwp_paid_qty_basis"):
		if spec.get(field):
			values[field] = spec[field]
	if frappe.get_meta("Pricing Rule").has_field("pos_only"):
		values["pos_only"] = 1
	return values


def _seed_rules(company: str, promotions: bool, created: list) -> None:
	rules = dict(PRICING_RULES)
	if promotions:
		rules[GWP_RULE[0]] = GWP_RULE[1]
	for name, spec in rules.items():
		if frappe.db.exists("Pricing Rule", name):
			continue
		_insert(_rule_doc(name, spec, company), name)
		created.append(f"Pricing Rule {name}")


def _seed_coupons(company: str, promotions: bool, created: list) -> None:
	coupons = dict(COUPONS)
	if promotions:
		coupons.update(PROMOTION_COUPONS)
	for code, spec in coupons.items():
		if frappe.db.exists("POS Coupon", code):
			continue
		frappe.get_doc(
			{
				"doctype": "POS Coupon",
				"coupon_name": code,
				"coupon_code": code.upper(),
				"coupon_type": "Promotional",
				"company": company,
				"apply_on": "Grand Total",
				**spec,
			}
		).insert(ignore_permissions=True)
		created.append(f"POS Coupon {code}")


def _same(current, wanted) -> bool:
	if not current and not wanted:
		return True
	if isinstance(wanted, int | float):
		return flt(current) == flt(wanted)
	return cstr(current) == cstr(wanted)


def _seed_ff_settings() -> bool:
	"""Set the F&F program. Saves only when something differs (idempotent)."""
	doc = frappe.get_doc(FF_SETTINGS)
	changed = False
	for field, value in FF_VALUES.items():
		if not _same(doc.get(field), value):
			doc.set(field, value)
			changed = True
	domains = {(row.email_domain or "").strip().lower(): row for row in doc.get("approved_domains") or []}
	row = domains.get(APPROVED_DOMAIN)
	if row is None:
		doc.append("approved_domains", {"email_domain": APPROVED_DOMAIN, "enabled": 1})
		changed = True
	elif not cint(row.enabled):
		row.enabled = 1
		changed = True
	excluded = {row.item_code for row in doc.get("excluded_items") or []}
	for code in FF_EXCLUDED_ITEMS:
		if code not in excluded:
			doc.append("excluded_items", {"item_code": code})
			changed = True
	if changed:
		doc.save(ignore_permissions=True)
	return changed


def _verify_kinds() -> dict:
	classify = _promotions_fn("promotions.ff_classifier.classify_promotion")
	kinds = {name: classify(name) for name in EXPECTED_KINDS}
	wrong = {name: kind for name, kind in kinds.items() if kind != EXPECTED_KINDS[name]}
	if wrong:
		frappe.throw(f"Seeded rules classify wrongly for F&F: {wrong}; expected {EXPECTED_KINDS}.")
	return kinds


def reset_ff():
	"""Put F&F Settings back to the seeded values (after a check changed them with set_ff)."""
	frappe.only_for("System Manager")
	if not promotions_installed():
		frappe.throw("posnext_promotions is not installed.")
	changed = _seed_ff_settings()
	frappe.db.commit()
	_promotions_fn("promotions.friends_and_family_eligibility.clear_cache")()
	print(
		"F&F Settings back to the seeded values." if changed else "F&F Settings already at the seeded values."
	)
	return changed


def set_ff(**values):
	"""Change F&F Settings scalars during a run (teardown restores the seeded snapshot)."""
	frappe.only_for("System Manager")
	if not promotions_installed():
		frappe.throw("posnext_promotions is not installed.")
	if not (_load_snapshot() or {}).get("ff_settings"):
		frappe.throw("Run seed first: there is no settings snapshot to restore from.")
	doc = frappe.get_doc(FF_SETTINGS)
	scalars = {
		df.fieldname
		for df in doc.meta.fields
		if df.fieldtype not in (*frappe.model.table_fields, *frappe.model.no_value_fields)
	}
	unknown = set(values) - scalars
	if unknown:
		frappe.throw(f"Not F&F Settings fields: {sorted(unknown)}")
	doc.update(values)
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	_promotions_fn("promotions.friends_and_family_eligibility.clear_cache")()
	print(f"F&F Settings updated: {values}. Reload open POS tabs.")


# ---- the records a run left behind -------------------------------------------------------


def _uit_users() -> list[str]:
	return [
		u
		for u in frappe.get_all("User", filters={"name": _like(EMAIL_PREFIX)}, pluck="name")
		if u.endswith(".example")
	]


def _link_fields() -> list[frappe._dict]:
	"""(doctype, fieldname) of every Link to a UIT target on a normal (not child, not single) doctype."""
	rows = frappe.db.sql(
		"""
		select df.parent as doctype, df.fieldname from `tabDocField` df
		join `tabDocType` dt on dt.name = df.parent
		where df.fieldtype = 'Link' and df.options in %(targets)s and dt.istable = 0 and dt.issingle = 0
		union
		select cf.dt as doctype, cf.fieldname from `tabCustom Field` cf
		join `tabDocType` dt on dt.name = cf.dt
		where cf.fieldtype = 'Link' and cf.options in %(targets)s and dt.istable = 0 and dt.issingle = 0
		""",
		{"targets": LINK_TARGETS},
		as_dict=True,
	)
	return [
		r for r in rows if frappe.db.table_exists(r.doctype) and frappe.db.has_column(r.doctype, r.fieldname)
	]


def _linked_records(skip=SWEEP_SKIP) -> dict[str, set[str]]:
	found: dict[str, set[str]] = {}
	for row in _link_fields():
		if row.doctype in skip:
			continue
		names = frappe.get_all(row.doctype, filters={row.fieldname: _like()}, pluck="name")
		if names:
			found.setdefault(row.doctype, set()).update(names)
	return found


def _named_records() -> dict[str, list[str]]:
	found: dict[str, list[str]] = {}
	for doctype in NAMED_MASTER_DOCTYPES:
		names = set(frappe.get_all(doctype, filters={"name": _like()}, pluck="name"))
		if doctype == "Pricing Rule":
			names |= set(frappe.get_all(doctype, filters={"title": _like()}, pluck="name"))
		if doctype == "Item Price":
			names |= set(frappe.get_all(doctype, filters={"price_list": PRICE_LIST}, pluck="name"))
		if doctype == "Sales Taxes and Charges Template":
			names |= set(frappe.get_all(doctype, filters={"title": _like()}, pluck="name"))
		if names:
			found[doctype] = sorted(names)
	settings = frappe.get_all("POS Settings", filters={"pos_profile": _like()}, pluck="name")
	settings += frappe.get_all("POS Settings", filters={"name": _like()}, pluck="name")
	if settings:
		found["POS Settings"] = sorted(set(settings))
	users = _uit_users()
	if users:
		found["User"] = users
	wallets = (
		frappe.get_all("Wallet", filters={"customer": _like()}, pluck="name")
		if frappe.db.table_exists("Wallet")
		else []
	)
	if wallets:
		found["Wallet"] = wallets
	contacts = _uit_contacts()
	if contacts:
		found["Contact"] = contacts
	files = frappe.get_all("File", filters={"file_name": _like()}, pluck="name")
	if files:
		found["File"] = files
	return found


def _uit_contacts() -> list[str]:
	linked = frappe.get_all(
		"Dynamic Link",
		filters={
			"parenttype": ["in", ["Contact", "Address"]],
			"link_doctype": "Customer",
			"link_name": _like(),
		},
		fields=["parenttype", "parent"],
	)
	names = {r.parent for r in linked if r.parenttype == "Contact"}
	names |= set(frappe.get_all("Contact", filters={"email_id": _like(EMAIL_PREFIX)}, pluck="name"))
	names |= set(frappe.get_all("Contact", filters={"name": _like()}, pluck="name"))
	return sorted(names)


def _uit_addresses() -> list[str]:
	return sorted(
		{
			r.parent
			for r in frappe.get_all(
				"Dynamic Link",
				filters={"parenttype": "Address", "link_doctype": "Customer", "link_name": _like()},
				fields=["parent"],
			)
		}
	)


def _ledger_rows() -> dict[str, int]:
	counts = {}
	for doctype in FF_LEDGER_DOCTYPES:
		if not frappe.db.table_exists(doctype):
			continue
		count = frappe.db.count(doctype, {"customer": _like()})
		if doctype == "Friends and Family Log":
			count += frappe.db.count(
				doctype, {"pos_profile": _like(), "customer": ["not like", f"{PREFIX}%"]}
			)
		if count:
			counts[doctype] = count
	return counts


def check() -> dict:
	"""Teardown isolation check: every UIT record and settings change that is still on the site."""
	leftovers: dict = {}
	named = _named_records()
	if named:
		leftovers["records"] = named
	linked = {dt: sorted(names) for dt, names in _linked_records().items()}
	if linked:
		leftovers["linked"] = linked
	ledger = _ledger_rows()
	if ledger:
		leftovers["ff_ledger_rows"] = ledger
	comments = frappe.db.count("Comment", {"reference_doctype": "Customer", "reference_name": _like()})
	if comments:
		leftovers["comments"] = comments
	gl = frappe.db.count("GL Entry", {"party": _like()})
	if gl:
		leftovers["gl_entries"] = gl
	ple = (
		frappe.db.count("Payment Ledger Entry", {"party": _like()})
		if frappe.db.table_exists("Payment Ledger Entry")
		else 0
	)
	if ple:
		leftovers["payment_ledger_entries"] = ple
	snapshot = _load_snapshot()
	if snapshot:
		leftovers["settings_not_restored"] = {
			"disabled_live_rules": [
				r
				for r in snapshot.get("disabled_rules") or []
				if cint(frappe.db.get_value("Pricing Rule", r, "disable"))
			],
			"ff_settings_snapshot": bool(snapshot.get("ff_settings")),
		}
	if promotions_installed():
		doc = frappe.get_doc(FF_SETTINGS)
		refs = [
			r.email_domain
			for r in doc.get("approved_domains") or []
			if (r.email_domain or "").lower() == APPROVED_DOMAIN
		]
		refs += [
			r.item_code for r in doc.get("excluded_items") or [] if (r.item_code or "").startswith(PREFIX)
		]
		if refs:
			leftovers["ff_settings_uit_rows"] = refs
	result = {"ok": not leftovers, "leftovers": leftovers}
	print(json.dumps(result, indent=1, default=str))
	return result


# ---- teardown ---------------------------------------------------------------


def _sweep_key(item):
	doctype, _names = item
	return (SWEEP_ORDER.index(doctype) if doctype in SWEEP_ORDER else len(SWEEP_ORDER), doctype)


def _remove(doctype: str, name: str, errors: list) -> None:
	try:
		docstatus = cint(frappe.db.get_value(doctype, name, "docstatus"))
		if docstatus == 1:
			doc = frappe.get_doc(doctype, name)
			doc.flags.ignore_permissions = True
			# Every linked UIT document goes too, in SWEEP_ORDER.
			doc.flags.ignore_links = True
			doc.cancel()
		frappe.delete_doc(doctype, name, force=True, ignore_permissions=True, delete_permanently=True)
		frappe.db.commit()
	except Exception as exc:
		frappe.db.rollback()
		errors.append(f"{doctype} {name}: {exc}")


def _ordered_invoices(names) -> list[str]:
	"""Returns first, then newest first, so nothing is cancelled under a document that points at it."""
	rows = frappe.get_all(
		"Sales Invoice", filters={"name": ["in", list(names)]}, fields=["name", "is_return", "creation"]
	)
	rows.sort(key=lambda r: (-cint(r.is_return), -r.creation.timestamp()))
	return [r.name for r in rows]


def teardown():
	"""Delete every UIT record (transactions, then ledgers, then master data) and restore the settings."""
	frappe.only_for("System Manager")
	errors: list[str] = []
	settings = frappe.get_single("Accounts Settings")
	delete_ledger = cint(settings.get("delete_linked_ledger_entries"))
	try:
		# Ledger entries of the cancelled UIT transactions go with them.
		if not delete_ledger:
			frappe.db.set_single_value("Accounts Settings", "delete_linked_ledger_entries", 1)
			# Committed, so a rollback in _remove cannot undo it.
			frappe.db.commit()
		for doctype, names in sorted(_linked_records().items(), key=_sweep_key):
			ordered = _ordered_invoices(names) if doctype == "Sales Invoice" else sorted(names, reverse=True)
			for name in ordered:
				_remove(doctype, name, errors)
	finally:
		if not delete_ledger:
			frappe.db.set_single_value("Accounts Settings", "delete_linked_ledger_entries", 0)
			frappe.db.commit()

	# Usage, usage totals and logs refuse edits through their controllers.
	for doctype in FF_LEDGER_DOCTYPES:
		if frappe.db.table_exists(doctype):
			frappe.db.delete(doctype, {"customer": _like()})
			if doctype == "Friends and Family Log":
				frappe.db.delete(doctype, {"pos_profile": _like()})
	frappe.db.delete("Comment", {"reference_doctype": "Customer", "reference_name": _like()})
	frappe.db.commit()

	restored = _restore_settings()

	named = _named_records()
	for doctype in ("POS Settings", "POS Coupon", "Pricing Rule", "POS Profile", "User", "Wallet", "Contact"):
		for name in named.get(doctype, []):
			_remove(doctype, name, errors)
	for name in _uit_addresses():
		_remove("Address", name, errors)
	for doctype in (
		"Customer",
		"Item Price",
		"Item",
		"Price List",
		"Item Group",
		"Brand",
		"Sales Taxes and Charges Template",
	):
		for name in named.get(doctype, []):
			_remove(doctype, name, errors)
	frappe.db.commit()

	if not errors:
		name = _snapshot_name()
		if name:
			frappe.delete_doc("File", name, force=True, ignore_permissions=True, delete_permanently=True)
		frappe.db.commit()
	if promotions_installed():
		_promotions_fn("promotions.friends_and_family_eligibility.clear_cache")()
	result = {"restored": restored, "errors": errors}
	print(json.dumps(result, indent=1, default=str))
	if errors:
		print(
			"Teardown left records behind; the snapshot file is kept. Fix the errors and run teardown again."
		)
	return result


def _restore_settings() -> dict:
	snapshot = _load_snapshot()
	if not snapshot:
		return {}
	for rule in snapshot.get("disabled_rules") or []:
		if frappe.db.exists("Pricing Rule", rule):
			frappe.db.set_value("Pricing Rule", rule, "disable", 0)
			frappe.clear_document_cache("Pricing Rule", rule)
	if snapshot.get("ff_settings") and promotions_installed():
		_restore_ff_settings(snapshot["ff_settings"])
	frappe.db.commit()
	return {
		"rules_enabled": snapshot.get("disabled_rules") or [],
		"ff_settings": bool(snapshot.get("ff_settings")),
	}
