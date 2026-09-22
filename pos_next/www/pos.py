import frappe

# Never cache this page: boot carries the session's CSRF token.
no_cache = 1


def get_context(context):
	# Frappe creates the token lazily, and a demo Cashier reaches /pos without the
	# Desk ever asking for one. The boot loop in pos.html puts it on window.
	if frappe.session.user != "Guest":
		context.boot = {**context.boot, "csrf_token": frappe.sessions.get_csrf_token()}
