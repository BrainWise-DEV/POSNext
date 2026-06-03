"""Desk setup for Nexus POS Manager: module profile + DocPerm sync."""

import frappe

MODULE_PROFILE_NAME = "Nexus POS Manager"
MANAGER_ROLE = "Nexus POS Manager"

# Frappe CRM (crm/api/session.py) only allows these roles for app + SPA access.
MANAGER_CRM_ACCESS_ROLES = ("Sales Manager", "Sales User")

# ERPNext module names (not display labels). POS Next is required for the POSNext workspace.
MANAGER_ALLOWED_MODULES = frozenset({
	"Stock",       # Inventory
	"Accounts",    # Accounting
	"CRM",         # ERPNext CRM (optional, when used alongside Frappe CRM)
	"FCRM",        # Frappe CRM app (crm)
	"Lead Syncing",  # Frappe CRM lead sync (crm)
	"HR",          # Frappe HR / hrms (when installed)
	"Payroll",     # Frappe HR / hrms (when installed)
	"POS Next",
})

# Clone DocPerm from these roles so allow_modules includes modules in Desk + app tiles.
MANAGER_MODULE_ACCESS = (
	("CRM", "Sales User"),
	("FCRM", "Sales User"),
	("Lead Syncing", "Sales Manager"),
	("HR", "HR User"),
	("Payroll", "HR Manager"),
)

# DocTypes outside the modules above that gate app access (e.g. hrms app tile).
MANAGER_EXTRA_DOCTYPE_ACCESS = (
	("Employee", "HR User"),  # required for hrms check_app_permission
)

# Custom DocPerm parents where Sales Manager perms are cloned for Nexus POS Manager.
MANAGER_CUSTOM_DOCPERM_PARENTS = (
	"POS Closing Entry",
	"POS Opening Entry",
	"Territory",
	"Customer",
	"Sales Invoice Item",
)

# POS Next doctypes/reports that define permissions in JSON (not Custom DocPerm).
def _clear_module_profile_lock(doc):
	"""Remove a stale file lock left by a failed Module Profile save."""
	import hashlib

	from frappe.utils import file_lock

	signature = hashlib.sha224(
		f"{doc.doctype}:{doc.name or MODULE_PROFILE_NAME}".encode(),
		usedforsecurity=False,
	).hexdigest()
	if file_lock.lock_exists(signature):
		file_lock.delete_lock(signature)


MANAGER_PERMISSION_DOCTYPES = (
	"POS Settings",
	"POS Opening Shift",
	"POS Closing Shift",
	"POS Offer",
	"POS Coupon",
	"Brainwise Branding",
	"Referral Code",
	"Sales vs Shifts Report",
	"Cashier Performance Report",
	"Payments and Cash Control Report",
	"Inventory Impact and Fast Movers Report",
	"Offline Sync and System Health Report",
)


def setup_manager_module_profile(quiet=False):
	"""Create/update Module Profile that blocks all modules except manager-allowed set."""
	all_modules = set(frappe.get_all("Module Def", pluck="name"))
	to_block = sorted(all_modules - MANAGER_ALLOWED_MODULES)

	if frappe.db.exists("Module Profile", MODULE_PROFILE_NAME):
		doc = frappe.get_doc("Module Profile", MODULE_PROFILE_NAME)
	else:
		doc = frappe.new_doc("Module Profile")
		doc.module_profile_name = MODULE_PROFILE_NAME

	doc.set("block_modules", [])
	for module in to_block:
		doc.append("block_modules", {"module": module})

	doc.flags.ignore_permissions = True
	_clear_module_profile_lock(doc)

	# Run ModuleProfile.update_all_users inline (avoid background queue during migrate).
	was_install = getattr(frappe.flags, "in_install", False)
	frappe.flags.in_install = True
	try:
		doc.save()
	finally:
		frappe.flags.in_install = was_install

	if not quiet:
		print(
			f"[pos_next] Module Profile '{MODULE_PROFILE_NAME}': "
			f"blocked {len(to_block)} modules, allowed {sorted(MANAGER_ALLOWED_MODULES & all_modules)}"
		)


def setup_manager_custom_docperms(quiet=False):
	"""Grant Nexus POS Manager the same Custom DocPerm rows as Sales Manager for POS-related parents."""
	role = "Nexus POS Manager"
	reference = "Sales Manager"
	created = 0

	for parent in MANAGER_CUSTOM_DOCPERM_PARENTS:
		if not frappe.db.exists("DocType", parent):
			continue

		ref_rows = frappe.get_all(
			"Custom DocPerm",
			filters={"parent": parent, "role": reference},
			pluck="name",
		)
		for ref_name in ref_rows:
			ref = frappe.get_doc("Custom DocPerm", ref_name)
			if frappe.db.exists(
				"Custom DocPerm",
				{"parent": parent, "role": role, "permlevel": ref.permlevel},
			):
				continue

			row = frappe.copy_doc(ref)
			row.name = None
			row.role = role
			row.flags.ignore_permissions = True
			row.insert()
			created += 1

	if created and not quiet:
		print(f"[pos_next] Created {created} Custom DocPerm row(s) for {role}")


def _ensure_role_on_doc(doc, child_field, role, reference):
	"""Append a child-table role row copied from reference role, if missing."""
	rows = doc.get(child_field) or []
	if any(r.role == role for r in rows):
		return False
	if not any(r.role == reference for r in rows):
		return False
	doc.append(child_field, {"role": role})
	return True


_PERM_FIELDS = (
	"select",
	"read",
	"write",
	"create",
	"delete",
	"submit",
	"cancel",
	"amend",
	"report",
	"export",
	"import",
	"share",
	"print",
	"email",
	"if_owner",
	"permlevel",
)


def _clone_docperm_for_doctype(doctype, role, reference_role):
	"""Create Custom DocPerm rows for role by copying reference role's standard/custom perms."""
	created = False

	for source_dt in ("DocPerm", "Custom DocPerm"):
		for ref_name in frappe.get_all(
			source_dt,
			filters={"parent": doctype, "role": reference_role},
			pluck="name",
		):
			ref = frappe.get_doc(source_dt, ref_name)
			if not (ref.read or ref.write or ref.create):
				continue
			if frappe.db.exists(
				"Custom DocPerm",
				{"parent": doctype, "role": role, "permlevel": ref.permlevel},
			):
				continue

			row = frappe.new_doc("Custom DocPerm")
			row.parent = doctype
			row.role = role
			for field in _PERM_FIELDS:
				row.set(field, ref.get(field))
			row.flags.ignore_permissions = True
			row.insert()
			created = True

	return created


def setup_manager_module_access_permissions(quiet=False):
	"""Grant read access on CRM/HR doctypes so those modules appear in Desk."""
	role = "Nexus POS Manager"
	created = 0
	installed_modules = set(frappe.get_all("Module Def", pluck="name"))

	for module, reference_role in MANAGER_MODULE_ACCESS:
		if module not in installed_modules:
			continue
		if not frappe.db.exists("Role", reference_role):
			continue

		doctypes = frappe.get_all(
			"DocType",
			filters={"module": module, "istable": 0},
			pluck="name",
		)
		for doctype in doctypes:
			if _clone_docperm_for_doctype(doctype, role, reference_role):
				created += 1

	for doctype, reference_role in MANAGER_EXTRA_DOCTYPE_ACCESS:
		if frappe.db.exists("DocType", doctype) and frappe.db.exists("Role", reference_role):
			if _clone_docperm_for_doctype(doctype, role, reference_role):
				created += 1

	if created and not quiet:
		print(f"[pos_next] Created {created} module/app Custom DocPerm row(s) for {role}")


def ensure_manager_crm_roles(user=None, quiet=False):
	"""Assign Frappe CRM roles to users who have Nexus POS Manager.

	Frappe CRM requires System Manager, Sales Manager, or Sales User
	(see crm.api.session.CRM_ALLOWED_ROLES). We assign Sales Manager + Sales User.
	"""
	user = user or frappe.session.user
	if not user or user in frappe.STANDARD_USERS:
		return False

	if MANAGER_ROLE not in frappe.get_roles(user):
		return False

	user_doc = frappe.get_doc("User", user)
	existing = {r.role for r in user_doc.roles}
	added = []

	for role in MANAGER_CRM_ACCESS_ROLES:
		if role in existing:
			continue
		if not frappe.db.exists("Role", role):
			continue
		user_doc.append("roles", {"role": role})
		added.append(role)

	if not added:
		return False

	user_doc.flags.ignore_permissions = True
	user_doc.save()
	frappe.clear_cache(user=user)

	if not quiet:
		print(f"[pos_next] Granted CRM roles {added} to {user}")

	return True


def ensure_manager_crm_roles_on_login(login_manager=None):
	"""on_session_creation: grant CRM roles when a manager logs in."""
	user = getattr(login_manager, "user", None) if login_manager else None
	user = user or frappe.session.user
	if user and user != "Guest":
		ensure_manager_crm_roles(user, quiet=True)


def strip_manager_crm_roles(user, quiet=False):
	"""Remove CRM roles provisioned for demo managers (on session expiry)."""
	user_doc = frappe.get_doc("User", user)
	strip = set(MANAGER_CRM_ACCESS_ROLES)
	original = [r.role for r in user_doc.roles]
	user_doc.roles = [r for r in user_doc.roles if r.role not in strip]
	if [r.role for r in user_doc.roles] == original:
		return False
	user_doc.flags.ignore_permissions = True
	user_doc.save()
	frappe.clear_cache(user=user)
	if not quiet:
		print(f"[pos_next] Stripped CRM roles from {user}")
	return True


def setup_manager_app_access(quiet=False):
	"""CRM/HR app access uses MANAGER_CRM_ACCESS_ROLES assigned on login (see ensure_manager_crm_roles)."""
	if not quiet:
		print("[pos_next] Manager CRM access via Sales Manager + Sales User roles")


def apply_runtime_patches():
	"""Apply patches on each request (workers do not run after_migrate)."""
	from pos_next.pos_next.compat.frappe_delete_doc import ensure_delete_doc_linked_helpers

	ensure_delete_doc_linked_helpers()


def setup_manager_doctype_permissions(quiet=False):
	"""Append Nexus POS Manager to doctype/report permission tables (mirror Sales Manager)."""
	role = "Nexus POS Manager"
	reference = "Sales Manager"
	updated = 0

	for name in MANAGER_PERMISSION_DOCTYPES:
		if frappe.db.exists("Report", name):
			doc = frappe.get_doc("Report", name)
			if _ensure_role_on_doc(doc, "roles", role, reference):
				doc.flags.ignore_permissions = True
				doc.save()
				updated += 1
			continue

		if not frappe.db.exists("DocType", name):
			continue

		meta = frappe.get_meta(name)
		if any(p.role == role for p in (meta.permissions or [])):
			continue

		ref_perm = next((p for p in (meta.permissions or []) if p.role == reference), None)
		if not ref_perm:
			continue

		doc = frappe.get_doc("DocType", name)
		perm = ref_perm.as_dict()
		perm.pop("name", None)
		perm["role"] = role
		doc.append("permissions", perm)
		doc.flags.ignore_permissions = True
		doc.save()
		updated += 1

	if updated and not quiet:
		print(f"[pos_next] Updated permissions on {updated} doctype(s)/report(s) for {role}")


def setup_manager_desk(quiet=False):
	from pos_next.pos_next.compat.frappe_delete_doc import ensure_delete_doc_linked_helpers

	ensure_delete_doc_linked_helpers()

	setup_manager_module_profile(quiet=quiet)
	setup_manager_custom_docperms(quiet=quiet)
	setup_manager_module_access_permissions(quiet=quiet)
	setup_manager_app_access(quiet=quiet)
	setup_manager_doctype_permissions(quiet=quiet)
	frappe.clear_cache()


def apply_module_profile_to_user(user, quiet=False):
	"""Set module_profile on a User (used when provisioning demo managers)."""
	if not frappe.db.exists("Module Profile", MODULE_PROFILE_NAME):
		setup_manager_module_profile(quiet=True)

	user_doc = frappe.get_doc("User", user)
	if user_doc.module_profile == MODULE_PROFILE_NAME:
		return

	user_doc.module_profile = MODULE_PROFILE_NAME
	user_doc.flags.ignore_permissions = True
	user_doc.save()

	if not quiet:
		print(f"[pos_next] Applied module profile '{MODULE_PROFILE_NAME}' to {user}")
