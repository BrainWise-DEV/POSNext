"""
POS Next Customer API
Handles customer search, creation, and management for POS operations
"""

import frappe
from frappe import _

from pos_next.api.constants import EMAIL_VERIFICATION_FIELDS
from pos_next.integrations.registry import (
	ExistingCustomerFound,
	after_customer_insert,
	after_customer_update,
	get_customer_sync_error,
	prepare_customer_doc,
	resolve_existing_customer,
	validate_customer_create,
)
from pos_next.utils import validate_pos_profile_access


@frappe.whitelist()
def get_customers(search_term="", pos_profile=None, limit=20, modified_since=None):
	"""
	Search customers for inline customer selection in POS.

	Args:
	    search_term (str): Search query (name, mobile, or customer ID)
	    pos_profile (str): POS Profile to filter by customer group
	    limit (int): Maximum number of results to return
	    modified_since (str): Fetch customers modified after this timestamp (ISO format)

	Returns:
	    list: List of customer dictionaries with name, customer_name, mobile_no, email_id, disabled
	"""
	try:
		frappe.logger().debug(
			f"get_customers called with search_term={search_term}, pos_profile={pos_profile}, limit={limit}, modified_since={modified_since}"
		)

		filters = {}
		or_filters = []

		# Filter by POS Profile customer group if specified
		if pos_profile:
			frappe.logger().debug(f"Loading POS Profile: {pos_profile}")
			profile_doc = frappe.get_cached_doc("POS Profile", pos_profile)
			# Check if customer_group field exists (it may not exist in all versions)
			if hasattr(profile_doc, "customer_group") and profile_doc.customer_group:
				filters["customer_group"] = profile_doc.customer_group
				frappe.logger().debug(f"Filtering by customer_group: {profile_doc.customer_group}")

		if modified_since:
			# Delta sync: include disabled customers so frontend can purge them
			filters["modified"] = [">=", modified_since]
		else:
			# Full fetch: only active customers
			filters["disabled"] = 0

		search_term = (search_term or "").strip()
		if search_term:
			like_term = f"%{search_term}%"
			or_filters = [
				["Customer", "name", "like", like_term],
				["Customer", "customer_name", "like", like_term],
				["Customer", "mobile_no", "like", like_term],
				["Customer", "email_id", "like", like_term],
			]

		customer_limit = limit if limit not in (None, 0) else frappe.db.count("Customer", filters)
		result = frappe.get_all(
			"Customer",
			filters=filters,
			or_filters=or_filters or None,
			fields=["name", "customer_name", "mobile_no", "email_id", "disabled", *EMAIL_VERIFICATION_FIELDS],
			limit=customer_limit,
			order_by="customer_name asc",
		)
		frappe.logger().debug(f"get_customers returned {len(result)} customers")
		return result
	except Exception as e:
		frappe.logger().error(f"Error in get_customers: {e!s}")
		frappe.logger().error(frappe.get_traceback())
		frappe.throw(_("Error fetching customers: {0}").format(str(e)))


def _drop_rename_note():
	"""Drop ERPNext's "Changed customer name to ... already exists" note.

	Duplicate display names are allowed; the record keeps ERPNext's unique ID, and the
	note reads as an error to cashiers. Matches the translated text, so it works in any
	language, and leaves every other message in place.
	"""
	prefix = _("Changed customer name to '{}' as '{}' already exists.").split("{}")[0]

	def text(entry):
		message = entry.get("message") if isinstance(entry, dict) else entry
		return message if isinstance(message, str) else ""

	log = frappe.local.message_log
	log[:] = [entry for entry in log if not text(entry).startswith(prefix)]


@frappe.whitelist()
def create_customer(
	customer_name,
	mobile_no=None,
	email_id=None,
	customer_group=None,
	territory=None,
	company=None,
	pos_profile=None,
	custom_governorate=None,
	custom_district=None,
	custom_first_name=None,
	custom_last_name=None,
	custom_is_publish=1,
):
	"""
	Create a new customer from POS.

	Args:
	    customer_name (str): Customer name (required)
	    mobile_no (str): Mobile number (optional)
	    email_id (str): Email address (optional)
	    customer_group (str): Customer group (default: from Selling Settings)
	    territory (str): Territory (default: from Selling Settings)
	    company (str): Company (optional, used to auto-assign loyalty program)
	    pos_profile (str): POS Profile (optional, preferred for context-aware loyalty assignment)
	    custom_governorate (str): Governorate (optional)
	    custom_district (str): District (optional, must belong to the governorate)
	    custom_first_name (str): First name for Magento sync (required when masar_miraaya installed)
	    custom_last_name (str): Last name for Magento sync (required when masar_miraaya installed)
	    custom_is_publish (int): Publish customer to Magento (default 1)

	Returns:
	    dict: Created customer document
	"""
	# Check if user has permission to create customers
	if not frappe.has_permission("Customer", "create"):
		frappe.throw(_("You don't have permission to create customers"), frappe.PermissionError)

	if not customer_name:
		frappe.throw(_("Customer name is required"))

	validate_customer_create(
		customer_name=customer_name,
		email_id=email_id,
		mobile_no=mobile_no,
		custom_first_name=custom_first_name,
		custom_last_name=custom_last_name,
		custom_is_publish=custom_is_publish,
	)

	existing = resolve_existing_customer(
		customer_name=customer_name,
		email_id=email_id,
		mobile_no=mobile_no,
		custom_first_name=custom_first_name,
		custom_last_name=custom_last_name,
		custom_is_publish=custom_is_publish,
		customer_group=customer_group,
		territory=territory,
		company=company,
		pos_profile=pos_profile,
	)
	if existing and existing.get("existing_customer"):
		return {
			"already_exists": True,
			"message": existing.get("message") or _("A customer with this email already exists."),
			"existing_customer": existing["existing_customer"],
		}

	loyalty_program = get_default_loyalty_program_from_settings(
		company=company,
		pos_profile=pos_profile,
	)

	resolved_customer_group = _resolve_leaf_customer_group(customer_group)
	resolved_territory = _resolve_leaf_territory(territory)

	customer = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": customer_name,
			"customer_type": "Individual",
			"customer_group": resolved_customer_group,
			"territory": resolved_territory,
			"mobile_no": mobile_no or "",
			"email_id": email_id or "",
			"loyalty_program": loyalty_program,
			"custom_governorate": custom_governorate or None,
			"custom_district": custom_district or None,
		}
	)

	sync_external_customer = prepare_customer_doc(
		customer,
		custom_first_name=custom_first_name,
		custom_last_name=custom_last_name,
		custom_is_publish=custom_is_publish,
	)

	frappe.flags.pos_next_customer_company = company
	frappe.flags.pos_next_customer_pos_profile = pos_profile
	try:
		try:
			customer.insert()
			_drop_rename_note()
			if sync_external_customer:
				after_customer_insert(
					customer,
					email_id=email_id,
					mobile_no=mobile_no,
					custom_first_name=custom_first_name,
					custom_last_name=custom_last_name,
					custom_is_publish=custom_is_publish,
				)
		except ExistingCustomerFound as exc:
			message = str(getattr(exc, "message", None) or exc or "").strip() or _(
				"A customer with this email already exists."
			)
			existing_doc = getattr(exc, "existing_customer", None)
			frappe.db.rollback()
			if not existing_doc:
				resolved = resolve_existing_customer(
					customer_name=customer_name,
					email_id=email_id,
					mobile_no=mobile_no,
					custom_first_name=custom_first_name,
					custom_last_name=custom_last_name,
					custom_is_publish=custom_is_publish,
					customer_group=customer_group,
					territory=territory,
					company=company,
					pos_profile=pos_profile,
				)
				if resolved:
					existing_doc = resolved.get("existing_customer")
					message = resolved.get("message") or message
			if existing_doc:
				return {
					"already_exists": True,
					"message": message,
					"existing_customer": existing_doc,
				}
			frappe.throw(message)
	finally:
		frappe.flags.pos_next_customer_company = None
		frappe.flags.pos_next_customer_pos_profile = None

	out = customer.as_dict()
	if sync_external_customer:
		from pos_next.integrations.registry import get_customer_sync_error

		sync_error = get_customer_sync_error(customer.name)
		if sync_error:
			# Saved locally, but the external system (Magento) rejected it — e.g.
			# the email is already registered with a different mobile number.
			out["external_sync_error"] = sync_error
	return out


def _is_leaf_customer_group(name):
	"""True when name exists and is not a group node."""
	if not name:
		return False
	return frappe.db.get_value("Customer Group", name, "is_group") == 0


def _is_leaf_territory(name):
	"""True when name exists and is not a group node."""
	if not name:
		return False
	return frappe.db.get_value("Territory", name, "is_group") == 0


def _resolve_leaf_customer_group(customer_group=None):
	"""
	Resolve a non-group Customer Group for POS creates.

	Selling Settings often defaults to 'All Customer Groups' (is_group=1), which
	ERPNext rejects on Customer.validate. Prefer an explicit leaf, then Selling
	Settings only if it is a leaf, then any leaf group.
	"""
	candidates = [
		customer_group,
		frappe.db.get_single_value("Selling Settings", "customer_group"),
	]
	for name in candidates:
		if _is_leaf_customer_group(name):
			return name

	leaf = frappe.db.get_value("Customer Group", {"is_group": 0}, "name", order_by="lft")
	if leaf:
		return leaf

	frappe.throw(_("No non-group Customer Group found. Please create one in Customer Group."))


def _resolve_leaf_territory(territory=None):
	"""Resolve a Territory ERPNext will accept on Customer (prefer non-group)."""
	candidates = [
		territory,
		frappe.db.get_single_value("Selling Settings", "territory"),
	]
	for name in candidates:
		# Territory allows selecting group nodes in some setups; prefer leaves.
		# Non-leaf / missing names fall through to the next candidate or fallback.
		if _is_leaf_territory(name):
			return name

	leaf = frappe.db.get_value("Territory", {"is_group": 0}, "name", order_by="lft")
	if leaf:
		return leaf

	# Last resort — ERPNext ships with this; better than failing create.
	return "All Territories"


def get_default_loyalty_program(company):
	"""
	Get the default loyalty program for a company.
	Prefers programs with auto_opt_in enabled.

	Args:
	    company (str): Company name

	Returns:
	    str: Loyalty program name or None
	"""
	# First try to find a loyalty program with auto_opt_in for the company
	loyalty_program = frappe.db.get_value("Loyalty Program", {"company": company, "auto_opt_in": 1}, "name")

	if loyalty_program:
		return loyalty_program

	# Fallback: any loyalty program for the company
	loyalty_program = frappe.db.get_value("Loyalty Program", {"company": company}, "name")

	return loyalty_program


def auto_assign_loyalty_program(doc, method=None):
	"""
	Auto-assign loyalty program to newly created customers.
	Called as after_insert hook on Customer doctype.

	Uses the default_loyalty_program from POS Settings.
	If no loyalty program is configured in POS Settings, no auto-assignment occurs.

	Args:
	    doc: Customer document
	    method: Hook method name (not used)
	"""
	# Skip if customer already has a loyalty program
	if doc.loyalty_program:
		return

	company, pos_profile = _get_customer_assignment_context()
	loyalty_program = get_default_loyalty_program_from_settings(
		company=company,
		pos_profile=pos_profile,
	)

	if loyalty_program:
		# Use db_set to avoid triggering validate hooks again
		doc.db_set("loyalty_program", loyalty_program, update_modified=False)
		frappe.logger().info(f"Auto-assigned loyalty program '{loyalty_program}' to customer '{doc.name}'")


def _get_customer_assignment_context():
	"""Get company/profile context for customer auto-assignment from the current request."""
	company = getattr(frappe.flags, "pos_next_customer_company", None)
	pos_profile = getattr(frappe.flags, "pos_next_customer_pos_profile", None)

	form_dict = getattr(frappe.local, "form_dict", None)
	if form_dict:
		company = company or form_dict.get("company")
		pos_profile = pos_profile or form_dict.get("pos_profile")

	return company, pos_profile


def get_default_loyalty_program_from_settings(company=None, pos_profile=None):
	"""
	Get the default loyalty program from POS Settings using explicit context.
	Returns a program only when the company/profile context is clear enough to avoid
	assigning the wrong loyalty program.

	Returns:
	    str: Loyalty program name or None if not configured
	"""
	if pos_profile:
		pos_settings = frappe.db.get_value(
			"POS Settings",
			{"enabled": 1, "pos_profile": pos_profile},
			"default_loyalty_program",
		)
		return pos_settings or None

	if not company:
		return None

	pos_settings = frappe.get_all(
		"POS Settings",
		filters={"enabled": 1, "default_loyalty_program": ["is", "set"]},
		fields=["pos_profile", "default_loyalty_program"],
		order_by="modified desc",
	)

	company_programs = []
	for row in pos_settings:
		profile_company = frappe.get_cached_value("POS Profile", row.pos_profile, "company")
		if profile_company == company:
			company_programs.append(row.default_loyalty_program)

	unique_programs = list(dict.fromkeys(program for program in company_programs if program))
	if len(unique_programs) == 1:
		return unique_programs[0]

	return None


@frappe.whitelist()
def get_customer_details(customer):
	"""
	Get detailed customer information.

	Args:
	    customer (str): Customer ID

	Returns:
	    dict: Customer details
	"""
	if not customer:
		frappe.throw(_("Customer is required"))

	# Avoid a stale cache after the primary Contact (and fetch_from fields) change.
	return frappe.get_doc("Customer", customer).as_dict()


@frappe.whitelist()
def update_customer(
	name: str,
	customer_name: str | None = None,
	mobile_no: str | None = None,
	email_id: str | None = None,
	customer_group: str | None = None,
	territory: str | None = None,
	custom_governorate: str | None = None,
	custom_district: str | None = None,
	custom_first_name: str | None = None,
	custom_last_name: str | None = None,
	pos_profile: str | None = None,
	company: str | None = None,
):
	"""Update an existing POS customer, including email and mobile.

	Customer.email_id and Customer.mobile_no are read-only fields fetched from
	the primary Contact. Writing them with frappe.client.set_value looks like a
	successful save, then fetch_from overwrites them with the unchanged Contact.
	This updates the Contact first, then the Customer.
	"""
	if not name:
		frappe.throw(_("Customer is required"))

	customer = frappe.get_doc("Customer", name)
	if not customer.has_permission("write"):
		frappe.throw(_("You don't have permission to update this customer"), frappe.PermissionError)
	if pos_profile:
		validate_pos_profile_access(pos_profile, frappe.PermissionError)
	meta = frappe.get_meta("Customer")

	first = (custom_first_name or "").strip()
	last = (custom_last_name or "").strip()
	if first or last:
		computed_name = " ".join(part for part in (first, last) if part).strip()
		if computed_name:
			customer_name = computed_name

	if customer_name is not None:
		customer_name = (customer_name or "").strip()
		if not customer_name:
			frappe.throw(_("Customer name is required"))

	# A changed email or phone must not take over another customer's (same rule as create).
	email_changed = (
		email_id is not None and (email_id or "").strip().lower() != (customer.email_id or "").strip().lower()
	)
	mobile_changed = mobile_no is not None and (mobile_no or "").strip() != (customer.mobile_no or "").strip()
	if email_changed or mobile_changed:
		existing = resolve_existing_customer(
			customer_name=customer_name or customer.customer_name,
			email_id=(email_id or "").strip() if email_changed else None,
			mobile_no=(mobile_no or "").strip() if mobile_changed else None,
			custom_first_name=first or customer.get("custom_first_name"),
			custom_last_name=last or customer.get("custom_last_name"),
			custom_is_publish=customer.get("custom_is_publish") or 0,
			customer_group=customer.customer_group,
			territory=customer.territory,
			company=company,
			pos_profile=pos_profile,
			exclude_customer=name,
		)
		found = (existing or {}).get("existing_customer")
		if found and found.get("name") != name:
			return {
				"already_exists": True,
				"message": existing.get("message") or _("A customer with this email already exists."),
				"existing_customer": found,
			}

	validate_customer_create(
		customer_name=customer_name or customer.customer_name,
		email_id=customer.email_id if email_id is None else email_id,
		mobile_no=customer.mobile_no if mobile_no is None else mobile_no,
		custom_first_name=first or customer.get("custom_first_name"),
		custom_last_name=last or customer.get("custom_last_name"),
		custom_is_publish=customer.get("custom_is_publish") or 0,
	)

	if customer_name is not None:
		customer.customer_name = customer_name
	if customer_group:
		customer.customer_group = _resolve_leaf_customer_group(customer_group)
	if territory:
		customer.territory = _resolve_leaf_territory(territory)
	if custom_governorate is not None and meta.has_field("custom_governorate"):
		customer.custom_governorate = custom_governorate or None
	if custom_district is not None and meta.has_field("custom_district"):
		customer.custom_district = custom_district or None
	if first and meta.has_field("custom_first_name"):
		customer.custom_first_name = first
	if last and meta.has_field("custom_last_name"):
		customer.custom_last_name = last

	resolved_email = customer.email_id if email_id is None else (email_id or "").strip()
	resolved_mobile = customer.mobile_no if mobile_no is None else (mobile_no or "").strip()
	if email_id is not None:
		customer.email_id = resolved_email
		if meta.has_field("custom_email"):
			customer.custom_email = resolved_email
	if mobile_no is not None:
		customer.mobile_no = resolved_mobile

	update_hooks = frappe.get_hooks("pos_next_customer_after_update") or []
	if update_hooks:
		frappe.flags.skip_magento_customer_sync = True
	try:
		sync_primary_contact(
			customer,
			email_id=None if email_id is None else resolved_email,
			mobile_no=None if mobile_no is None else resolved_mobile,
			first_name=first or None,
			last_name=last or None,
		)
		customer.save()
		if update_hooks:
			after_customer_update(
				customer,
				email_id=resolved_email,
				mobile_no=resolved_mobile,
				custom_first_name=first or customer.get("custom_first_name"),
				custom_last_name=last or customer.get("custom_last_name"),
			)
	finally:
		frappe.flags.skip_magento_customer_sync = False

	customer.reload()
	out = customer.as_dict()
	sync_error = get_customer_sync_error(customer.name)
	if sync_error:
		out["external_sync_error"] = sync_error
	return out


def sync_primary_contact(
	customer,
	email_id=None,
	mobile_no=None,
	first_name=None,
	last_name=None,
):
	"""Update the primary Contact so Customer email_id / mobile_no stay in sync.

	These Customer fields are fetched from customer_primary_contact. Changing
	them on Customer alone is reverted on save. Returns True when the Contact
	was saved.
	"""
	contact_name = customer.get("customer_primary_contact") or frappe.db.get_value(
		"Customer", customer.name, "customer_primary_contact"
	)
	if not contact_name:
		# Customer.on_update.create_primary_contact creates one when email/mobile are set.
		return False

	contact = frappe.get_doc("Contact", contact_name)
	changed = False

	if email_id is not None:
		email_id = (email_id or "").strip()
		changed = set_contact_primary_email(contact, email_id) or changed
		if (contact.email_id or "") != email_id:
			contact.email_id = email_id
			changed = True

	if mobile_no is not None:
		mobile_no = (mobile_no or "").strip()
		changed = set_contact_primary_mobile(contact, mobile_no) or changed
		if (contact.mobile_no or "") != mobile_no:
			contact.mobile_no = mobile_no
			changed = True

	if first_name:
		first_name = first_name.strip()
		if contact.first_name != first_name:
			contact.first_name = first_name
			changed = True
	if last_name is not None:
		last_name = (last_name or "").strip()
		if contact.last_name != last_name:
			contact.last_name = last_name
			changed = True

	if changed:
		contact.save(ignore_permissions=True)
	return changed


def set_contact_primary_email(contact, email_id):
	"""Set or replace the Contact's primary email. Returns whether a child row changed."""
	changed = False
	primary = None
	for row in contact.email_ids:
		if not row.is_primary:
			continue
		if primary is None:
			primary = row
			continue
		row.is_primary = 0
		changed = True

	if email_id:
		if primary:
			if (primary.email_id or "").strip() != email_id:
				primary.email_id = email_id
				changed = True
			if not primary.is_primary:
				primary.is_primary = 1
				changed = True
		else:
			contact.append("email_ids", {"email_id": email_id, "is_primary": 1})
			changed = True
	elif primary:
		contact.remove(primary)
		changed = True
	return changed


def set_contact_primary_mobile(contact, mobile_no):
	"""Set or replace the Contact's primary mobile number. Returns whether a child row changed."""
	changed = False
	primary = None
	for row in contact.phone_nos:
		if not row.is_primary_mobile_no:
			continue
		if primary is None:
			primary = row
			continue
		row.is_primary_mobile_no = 0
		changed = True

	if mobile_no:
		if primary:
			if (primary.phone or "").strip() != mobile_no:
				primary.phone = mobile_no
				changed = True
			if not primary.is_primary_mobile_no:
				primary.is_primary_mobile_no = 1
				changed = True
		else:
			contact.append(
				"phone_nos",
				{"phone": mobile_no, "is_primary_mobile_no": 1},
			)
			changed = True
	elif primary:
		contact.remove(primary)
		changed = True
	return changed
