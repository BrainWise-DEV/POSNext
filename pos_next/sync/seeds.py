# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Default Sync DocType Rule seeds applied to new Sync Site Config records."""


DEFAULT_SYNC_RULES = [
	# --- Masters pulled central → branch, Central-Wins ---
	{"doctype_name": "Item",                "direction": "Bidirectional", "cdc_strategy": "Outbox",    "conflict_rule": "Field-Level-LWW", "priority":   5, "batch_size": 100},
	{"doctype_name": "Item Price",          "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 110, "batch_size": 100},
	{"doctype_name": "Item Group",          "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 100, "batch_size": 100},
	{"doctype_name": "Item Barcode",        "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 100, "batch_size": 100},
	{"doctype_name": "UOM",                 "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 100, "batch_size": 100},
	{"doctype_name": "Price List",          "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 100, "batch_size": 100},
	{"doctype_name": "POS Profile",         "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority":  90, "batch_size": 100, "branch_filter_field": "branch"},
	{"doctype_name": "POS Settings",        "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority":  90, "batch_size": 100},
	{"doctype_name": "POS Offer",           "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 120, "batch_size": 100},
	{"doctype_name": "POS Coupon",          "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 120, "batch_size": 100},
	{"doctype_name": "Loyalty Program",     "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 120, "batch_size": 100},
	{"doctype_name": "Warehouse",           "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority":  90, "batch_size": 100, "branch_filter_field": "branch"},
	{"doctype_name": "Branch",              "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority":  90, "batch_size": 100},
	{"doctype_name": "Company",             "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority":  80, "batch_size": 100},
	{"doctype_name": "Currency",            "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority":  80, "batch_size": 100},
	{"doctype_name": "Mode of Payment",     "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 110, "batch_size": 100},
	{"doctype_name": "Sales Taxes and Charges Template", "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 110, "batch_size": 100},
	{"doctype_name": "Item Tax Template",   "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 110, "batch_size": 100},
	{"doctype_name": "Role Profile",        "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority":  80, "batch_size": 100},
	{"doctype_name": "Employee",            "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 110, "batch_size": 100, "branch_filter_field": "branch"},
	{"doctype_name": "Sales Person",        "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 110, "batch_size": 100},
	{"doctype_name": "Customer Group",      "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 110, "batch_size": 100},
	# --- Customer: bidirectional, Field-Level-LWW ---
	{"doctype_name": "Customer",            "direction": "Bidirectional", "cdc_strategy": "Outbox", "conflict_rule": "Field-Level-LWW", "priority":  50, "batch_size": 100},
	# --- Transactions branch → central, Branch-Wins ---
	{"doctype_name": "POS Opening Shift",   "direction": "Branch→Central", "cdc_strategy": "Outbox", "conflict_rule": "Branch-Wins", "priority":  10, "batch_size":  50},
	{"doctype_name": "POS Closing Shift",   "direction": "Branch→Central", "cdc_strategy": "Outbox", "conflict_rule": "Branch-Wins", "priority":  20, "batch_size":  50},
	# Stock-altering docs (priority 30) drain BEFORE Sales Invoice (50) so central's
	# Bin reflects branch stock movements before any consuming SI lands. If a stock-add
	# doc is missing on central, the dependent SI will (correctly) hard-fail — that
	# loud failure is preferred to silent negative-stock accumulation.
	{"doctype_name": "Purchase Receipt",     "direction": "Branch→Central", "cdc_strategy": "Outbox", "conflict_rule": "Branch-Wins", "priority":  30, "batch_size":  50},
	{"doctype_name": "Stock Entry",          "direction": "Branch→Central", "cdc_strategy": "Outbox", "conflict_rule": "Branch-Wins", "priority":  30, "batch_size":  50},
	{"doctype_name": "Stock Reconciliation", "direction": "Branch→Central", "cdc_strategy": "Outbox", "conflict_rule": "Branch-Wins", "priority":  30, "batch_size":  50},
	# Delivery Note consumes stock like SI but is independent of the SI submit chain.
	{"doctype_name": "Delivery Note",        "direction": "Branch→Central", "cdc_strategy": "Outbox", "conflict_rule": "Branch-Wins", "priority":  40, "batch_size":  50},
	{"doctype_name": "Sales Invoice",       "direction": "Branch→Central", "cdc_strategy": "Outbox", "conflict_rule": "Branch-Wins", "priority":  50, "batch_size": 100},
	{"doctype_name": "Payment Entry",       "direction": "Branch→Central", "cdc_strategy": "Outbox", "conflict_rule": "Branch-Wins", "priority":  50, "batch_size": 100},
	{"doctype_name": "Offline Invoice Sync","direction": "Branch→Central", "cdc_strategy": "Outbox", "conflict_rule": "Branch-Wins", "priority":  70, "batch_size": 100},
	# --- Wallet bidirectional ---
	{"doctype_name": "Wallet",              "direction": "Bidirectional", "cdc_strategy": "Outbox", "conflict_rule": "Field-Level-LWW", "priority":  60, "batch_size": 100},
	{"doctype_name": "Wallet Transaction",  "direction": "Bidirectional", "cdc_strategy": "Outbox", "conflict_rule": "Branch-Wins",      "priority":  60, "batch_size": 100},
]


def apply_seeds_to_config(config_doc):
	"""
	Populate synced_doctypes on a Sync Site Config doc with DEFAULT_SYNC_RULES.
	Only adds rules that don't already exist on the config (by doctype_name).
	"""
	existing = {row.doctype_name for row in (config_doc.synced_doctypes or [])}
	added = 0
	for rule in DEFAULT_SYNC_RULES:
		if rule["doctype_name"] in existing:
			continue
		config_doc.append("synced_doctypes", {
			**rule,
			"enabled": 1,
		})
		added += 1
	if added:
		config_doc.save(ignore_permissions=True)
	return added
