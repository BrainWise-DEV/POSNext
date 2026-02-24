"""
# POS Next API Reference

POS Next is a modern Point of Sale application built on ERPNext/Frappe.
This is the auto-generated API reference for all backend endpoints.

## Modules

| Module | Description |
|--------|-------------|
| **`auth`** | Authentication, login, and session management |
| **`bootstrap`** | Initial data loading for POS startup |
| **`branding`** | Custom branding and white-label configuration |
| **`constants`** | Shared constants and field name definitions |
| **`credit_sales`** | Credit sales and outstanding balance management |
| **`customers`** | Customer CRUD and search |
| **`invoices`** | Invoice creation, submission, returns, and draft management |
| **`items`** | Item search, stock availability, variants, and bulk fetching |
| **`localization`** | Language settings and translations |
| **`offers`** | Offer evaluation and application |
| **`partial_payments`** | Split/partial payment handling |
| **`pos_profile`** | POS Profile configuration and data |
| **`promotions`** | Pricing Rules and Promotional Schemes |
| **`qz`** | QZ Tray print integration |
| **`sales_invoice_hooks`** | Server-side hooks on Sales Invoice events |
| **`shifts`** | POS Opening/Closing shift management |
| **`utilities`** | Miscellaneous utility endpoints |
| **`wallet`** | Digital wallet and loyalty points |

## Endpoint Convention

All public endpoints use `@frappe.whitelist()` and are callable via:

```
POST /api/method/pos_next.api.<module>.<function>
```
"""

import frappe

# Import API modules to make them accessible
from . import auth, customers, invoices, items, offers, pos_profile, promotions, shifts, utilities


@frappe.whitelist(allow_guest=True)  # nosemgrep: frappe-semgrep-rules.rules.security.guest-whitelisted-method
def ping():
	"""Simple ping endpoint for connectivity checks"""
	return "pong"
