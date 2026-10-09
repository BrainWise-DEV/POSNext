# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Return ownership of the POS authorization gate to pos_next.

The gate was shipped by both apps: identical DocTypes under the same module name
(``POS Next Auth Gate``), identical Python, and a ``before_submit`` hook each. Frappe
warned about the collision on every boot — ``module 'pos_next_auth_gate' found in apps
'pos_next' and 'posnext_promotions'`` — and the Module Def recorded posnext_promotions
as the owner, so a ``bench migrate`` could resolve the DocTypes into an app that is
meant to be optional.

Authorization is host governance, not promotions: the registry gates returns and cart
overrides, none of which involve an offer. pos_next now owns it and posnext_promotions
ships no copy.

This patch only re-labels ownership metadata. The DocTypes keep their names, their
module (``POS Next Auth Gate``) and every row: rules, approvers, PINs and the audit log
are untouched.
"""

import frappe

MODULE_NAME = "POS Next Auth Gate"
OWNING_APP = "pos_next"
OWNING_MODULE = "POS Next"

#: Fields the gate writes on Sales Invoice. posnext_promotions used to ship them, so on
#: existing sites they still carry its module label.
AUTH_CUSTOM_FIELDS = ("custom_authorized_by", "custom_authorized_at")


def execute():
	_rehome_module_def()
	_rehome_custom_fields()
	frappe.clear_cache()


def _rehome_module_def():
	if not frappe.db.exists("Module Def", MODULE_NAME):
		# Fresh site: the module is created from pos_next's modules.txt already.
		return

	current = frappe.db.get_value("Module Def", MODULE_NAME, "app_name")
	if current == OWNING_APP:
		return

	frappe.db.set_value("Module Def", MODULE_NAME, "app_name", OWNING_APP, update_modified=False)
	print(f"Re-homed Module Def {MODULE_NAME}: {current} -> {OWNING_APP}")


def _rehome_custom_fields():
	"""Point the gate's Sales Invoice fields at pos_next's module.

	``sync_customizations`` upserts by fieldname and would fix this on the next
	migrate anyway, but only after this patch has run — doing it here keeps the
	labelling correct even if the sync is skipped.
	"""
	for fieldname in AUTH_CUSTOM_FIELDS:
		name = frappe.db.get_value("Custom Field", {"dt": "Sales Invoice", "fieldname": fieldname})
		if not name:
			continue
		if frappe.db.get_value("Custom Field", name, "module") == OWNING_MODULE:
			continue
		frappe.db.set_value("Custom Field", name, "module", OWNING_MODULE, update_modified=False)
		print(f"Re-homed Custom Field {name} -> {OWNING_MODULE}")
