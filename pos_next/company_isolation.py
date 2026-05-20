import frappe


def get_user_companies(user=None):
	"""Return company names the current user is allowed to access.

	Used by `validations.item_query` and any other code that wants to scope a
	query to the user's companies. Empty list means "no company restriction
	derivable for this user" — callers decide whether that should fall through
	to stock permission handling or block the query.
	"""
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
