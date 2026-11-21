"""Version gate for the Friends & Family contract between apps.

Runs as a ``before_migrate`` hook, so it is enforced on every migrate (a patch
would run once per site only).
"""

import importlib

import frappe

# app -> (minimum FF_CONTRACT, release that provides it)
REQUIREMENTS = {
	"posnext_promotions": (3, "0.3.0"),
	"magento_integration": (1, "0.2.0"),
}


def check(app_requirements, installed_apps, importer=importlib.import_module):
	"""Return one message per installed companion whose FF_CONTRACT is missing or too low."""
	messages = []
	for app, (required, release) in app_requirements.items():
		if app not in installed_apps:
			continue
		have = getattr(importer(app), "FF_CONTRACT", None)
		if not isinstance(have, int) or isinstance(have, bool) or have < required:
			messages.append(f"Update {app} to >= {release} before migrating (an older version is installed).")
	return messages


def before_migrate(importer=importlib.import_module):
	messages = check(REQUIREMENTS, frappe.get_installed_apps(), importer)
	if messages:
		frappe.throw("\n".join(messages), title="Update required")
