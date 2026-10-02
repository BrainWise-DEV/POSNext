import frappe

CUSTOM_FIELDS = [
	"Brand-custom_company",
	"Customer-custom_company",
	"Customer Group-custom_company",
	"Item-custom_company",
	"Item Group-custom_company",
	"Price List-custom_company",
	"Supplier-custom_company",
	"Supplier Group-custom_company",
]


def execute():
	for field_name in CUSTOM_FIELDS:
		if frappe.db.exists("Custom Field", field_name):
			frappe.delete_doc("Custom Field", field_name, force=True, ignore_permissions=True)

	frappe.cache().delete_keys("pos_settings_allow_global_items:*")
