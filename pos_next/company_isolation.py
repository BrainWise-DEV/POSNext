import frappe

def get_user_companies(user=None):
	"""Return company names the current user is allowed to access."""
	user = user or frappe.session.user

	if user == "Administrator":
		return []

	companies = set()

	default_company = frappe.defaults.get_user_default("company", user=user)
	if default_company:
		companies.add(default_company)

	for company in frappe.get_all(
		"User Permission",
		filters={"user": user, "allow": "Company"},
		pluck="for_value",
	):
		if company:
			companies.add(company)

	employee_company = frappe.db.get_value(
		"Employee",
		{"user_id": user, "status": "Active"},
		"company",
	)
	if employee_company:
		companies.add(employee_company)

	return sorted(companies)


def _build_company_condition(doctype, user=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return ""

	companies = get_user_companies(user)
	if not companies:
		return "1=0"

	companies_sql = ", ".join(frappe.db.escape(company) for company in companies)
	return f"`tab{doctype}`.`custom_company` IN ({companies_sql})"


def _has_company_permission(doc, user=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return True

	companies = set(get_user_companies(user))
	if not companies:
		return False

	return doc.get("custom_company") in companies


def customer_permission_query_conditions(user):
	return _build_company_condition("Customer", user)


def supplier_permission_query_conditions(user):
	return _build_company_condition("Supplier", user)


def item_group_permission_query_conditions(user):
	return _build_company_condition("Item Group", user)


def customer_group_permission_query_conditions(user):
	return _build_company_condition("Customer Group", user)


def supplier_group_permission_query_conditions(user):
	return _build_company_condition("Supplier Group", user)


def brand_permission_query_conditions(user):
	return _build_company_condition("Brand", user)


def price_list_permission_query_conditions(user):
	return _build_company_condition("Price List", user)


def customer_has_permission(doc, user=None, permission_type=None):
	return _has_company_permission(doc, user)


def supplier_has_permission(doc, user=None, permission_type=None):
	return _has_company_permission(doc, user)


def item_group_has_permission(doc, user=None, permission_type=None):
	return _has_company_permission(doc, user)


def customer_group_has_permission(doc, user=None, permission_type=None):
	return _has_company_permission(doc, user)


def supplier_group_has_permission(doc, user=None, permission_type=None):
	return _has_company_permission(doc, user)


def brand_has_permission(doc, user=None, permission_type=None):
	return _has_company_permission(doc, user)


def price_list_has_permission(doc, user=None, permission_type=None):
	return _has_company_permission(doc, user)
