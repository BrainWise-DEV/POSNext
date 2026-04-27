"""
POS Next Customer API
Handles customer search, creation, and management for POS operations
"""

import frappe
from frappe import _


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
            fields=["name", "customer_name", "mobile_no", "email_id", "disabled"],
            limit=customer_limit,
            order_by="customer_name asc",
        )
        frappe.logger().debug(f"get_customers returned {len(result)} customers")
        return result
    except Exception as e:
        frappe.logger().error(f"Error in get_customers: {str(e)}")
        frappe.logger().error(frappe.get_traceback())
        frappe.throw(_("Error fetching customers: {0}").format(str(e)))


@frappe.whitelist()
def create_customer(
    customer_name,
    mobile_no=None,
    email_id=None,
    customer_group="Individual",
    territory="All Territories",
    company=None,
    pos_profile=None,
):
    """
    Create a new customer from POS.

    Args:
        customer_name (str): Customer name (required)
        mobile_no (str): Mobile number (optional)
        email_id (str): Email address (optional)
        customer_group (str): Customer group (default: Individual)
        territory (str): Territory (default: All Territories)
        company (str): Company (optional, used to auto-assign loyalty program)
        pos_profile (str): POS Profile (optional, preferred for context-aware loyalty assignment)

    Returns:
        dict: Created customer document
    """
    # Check if user has permission to create customers
    if not frappe.has_permission("Customer", "create"):
        frappe.throw(_("You don't have permission to create customers"), frappe.PermissionError)

    if not customer_name:
        frappe.throw(_("Customer name is required"))

    loyalty_program = get_default_loyalty_program_from_settings(
        company=company,
        pos_profile=pos_profile,
    )

    customer = frappe.get_doc(
        {
            "doctype": "Customer",
            "customer_name": customer_name,
            "customer_type": "Individual",
            "customer_group": customer_group or "Individual",
            "territory": territory or "All Territories",
            "mobile_no": mobile_no or "",
            "email_id": email_id or "",
            "loyalty_program": loyalty_program,
        }
    )

    frappe.flags.pos_next_customer_company = company
    frappe.flags.pos_next_customer_pos_profile = pos_profile
    try:
        customer.insert()
    finally:
        frappe.flags.pos_next_customer_company = None
        frappe.flags.pos_next_customer_pos_profile = None

    return customer.as_dict()


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
    loyalty_program = frappe.db.get_value(
        "Loyalty Program",
        {"company": company, "auto_opt_in": 1},
        "name"
    )

    if loyalty_program:
        return loyalty_program

    # Fallback: any loyalty program for the company
    loyalty_program = frappe.db.get_value(
        "Loyalty Program",
        {"company": company},
        "name"
    )

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
        frappe.logger().info(
            f"Auto-assigned loyalty program '{loyalty_program}' to customer '{doc.name}'"
        )


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

    return frappe.get_cached_doc("Customer", customer).as_dict()


def _get_addresses_for_customers(customer_names):
    """Return ``{customer: [address, ...]}`` for the given customer names.

    Resolves the Address ↔ Customer relationship via the Dynamic Link
    child table so we can bulk-fetch addresses in one query.
    """
    if not customer_names:
        return {}

    links = frappe.get_all(
        "Dynamic Link",
        filters={
            "link_doctype": "Customer",
            "link_name": ["in", customer_names],
            "parenttype": "Address",
        },
        fields=["link_name", "parent"],
    )

    if not links:
        return {}

    address_names = list({row.parent for row in links})
    address_rows = frappe.get_all(
        "Address",
        filters={"name": ["in", address_names], "disabled": 0},
        fields=[
            "name",
            "address_title",
            "address_type",
            "address_line1",
            "address_line2",
            "city",
            "state",
            "country",
            "pincode",
            "phone",
            "is_primary_address",
            "is_shipping_address",
        ],
    )
    address_by_name = {row.name: row for row in address_rows}

    addresses_by_customer = {}
    for link in links:
        addr = address_by_name.get(link.parent)
        if not addr:
            continue
        addresses_by_customer.setdefault(link.link_name, []).append(addr)

    # Stable order: primary first, then shipping, then by title.
    for addrs in addresses_by_customer.values():
        addrs.sort(
            key=lambda a: (
                0 if a.get("is_primary_address") else 1,
                0 if a.get("is_shipping_address") else 1,
                a.get("address_title") or "",
            )
        )

    return addresses_by_customer


def _get_loyalty_points_for_customers(customer_names, company=None):
    """Return ``{customer: points}`` aggregating active Loyalty Point Entries.

    Mirrors ERPNext's ``get_loyalty_program_details_with_points`` aggregation
    but in bulk — one query for many customers.
    """
    if not customer_names:
        return {}

    filters = {
        "customer": ["in", customer_names],
        "expiry_date": [">=", frappe.utils.today()],
    }
    if company:
        filters["company"] = company

    rows = frappe.get_all(
        "Loyalty Point Entry",
        filters=filters,
        fields=["customer", "loyalty_points", "redeem_against"],
    )
    points_by_customer = {}
    for row in rows:
        # Standard pattern: positive entries collect, redeem entries are
        # negative or referenced via redeem_against — sum them all.
        points_by_customer[row.customer] = points_by_customer.get(row.customer, 0) + (
            row.loyalty_points or 0
        )
    return points_by_customer


def _get_wallet_balances_for_customers(customer_names, company=None):
    """Return ``{customer: balance}`` for active wallets.

    Reuses ``pos_next.api.wallet.get_customer_wallet_balance`` per customer.
    Bulk-aggregating GL is non-trivial with pending POS deductions, so we
    fall back to the per-customer helper but cap exposure for very large
    sets to keep the bootstrap call snappy.
    """
    if not customer_names:
        return {}

    # Cap individual lookups to avoid stalling the bootstrap call.
    # Anything beyond this can be lazy-loaded by the frontend.
    LOOKUP_CAP = 500
    targets = customer_names[:LOOKUP_CAP]

    from pos_next.api.wallet import get_customer_wallet_balance

    balances = {}
    for name in targets:
        try:
            balances[name] = float(get_customer_wallet_balance(name, company=company) or 0)
        except Exception:
            # Wallet lookup is best-effort during bulk caching.
            balances[name] = 0.0
    return balances


@frappe.whitelist()
def get_customers_for_offline(pos_profile=None, modified_since=None, limit=2000):
    """Bulk-fetch customers with addresses, loyalty points, and wallet balance
    for IndexedDB seeding.

    The shape mirrors ``get_customers`` but enriches each row with:
      - ``addresses``: list of address dicts (primary first)
      - ``loyalty_program``, ``loyalty_points``: cached for offline display
      - ``wallet_balance``: best-effort balance, ``0`` on failure

    Args:
        pos_profile: Filter to the customer group on this profile (optional).
        modified_since: ISO timestamp for delta sync (optional).
        limit: ``0`` returns all rows (default ``2000``).
    """
    company = None
    customer_group = None
    if pos_profile:
        profile = frappe.get_cached_doc("POS Profile", pos_profile)
        company = getattr(profile, "company", None)
        customer_group = getattr(profile, "customer_group", None)

    filters = {}
    if customer_group:
        filters["customer_group"] = customer_group
    if modified_since:
        filters["modified"] = [">=", modified_since]
    else:
        filters["disabled"] = 0

    fetch_limit = limit if limit not in (None, 0) else frappe.db.count("Customer", filters)
    customers = frappe.get_all(
        "Customer",
        filters=filters,
        fields=[
            "name",
            "customer_name",
            "customer_type",
            "customer_group",
            "territory",
            "mobile_no",
            "email_id",
            "tax_id",
            "loyalty_program",
            "loyalty_program_tier",
            "default_currency",
            "default_price_list",
            "disabled",
            "modified",
        ],
        limit=fetch_limit,
        order_by="customer_name asc",
    )

    customer_names = [c.name for c in customers]
    addresses_by_customer = _get_addresses_for_customers(customer_names)
    points_by_customer = _get_loyalty_points_for_customers(customer_names, company=company)
    balances_by_customer = _get_wallet_balances_for_customers(customer_names, company=company)

    enriched = []
    for c in customers:
        enriched.append(
            {
                **c,
                "addresses": addresses_by_customer.get(c.name, []),
                "loyalty_points": points_by_customer.get(c.name, 0),
                "wallet_balance": balances_by_customer.get(c.name, 0.0),
            }
        )
    return enriched


@frappe.whitelist()
def get_customer_offline_extras(customer, company=None):
    """Per-customer extras (addresses, loyalty points, wallet) for cache top-ups.

    Used when a customer is selected/changed and we want to refresh just that
    record without redoing the full bulk cache.
    """
    if not customer:
        frappe.throw(_("Customer is required"))

    addresses = _get_addresses_for_customers([customer]).get(customer, [])
    points = _get_loyalty_points_for_customers([customer], company=company).get(customer, 0)
    balances = _get_wallet_balances_for_customers([customer], company=company).get(customer, 0.0)

    return {
        "customer": customer,
        "addresses": addresses,
        "loyalty_points": points,
        "wallet_balance": balances,
    }


@frappe.whitelist()
def replay_offline_customer(
    offline_id,
    customer_name,
    mobile_no=None,
    email_id=None,
    customer_group="Individual",
    territory="All Territories",
    company=None,
    pos_profile=None,
):
    """Replay a customer that was created while the POS was offline.

    Idempotent: if a customer with the same ``offline_id`` was already
    created (tracked via the ``pos_next_offline_id`` Customer field, or by
    fingerprint match on name+mobile), the existing record is returned.

    Args:
        offline_id: Client-generated UUID for deduplication.
        ... rest same as ``create_customer``.
    """
    if not offline_id:
        frappe.throw(_("offline_id is required"))
    if not customer_name:
        frappe.throw(_("Customer name is required"))

    # Idempotency: check if we've already replayed this offline_id.
    # We store the offline_id in the customer doc's `pos_next_offline_id`
    # field if it exists (added via fixture), otherwise fall back to the
    # name+mobile fingerprint check.
    existing = None
    meta = frappe.get_meta("Customer")
    if meta.has_field("pos_next_offline_id"):
        existing = frappe.db.get_value(
            "Customer",
            {"pos_next_offline_id": offline_id},
            "name",
        )

    if not existing and mobile_no:
        existing = frappe.db.get_value(
            "Customer",
            {"customer_name": customer_name, "mobile_no": mobile_no},
            "name",
        )

    if existing:
        return {
            "name": existing,
            "deduplicated": True,
            "doc": frappe.get_cached_doc("Customer", existing).as_dict(),
        }

    created = create_customer(
        customer_name=customer_name,
        mobile_no=mobile_no,
        email_id=email_id,
        customer_group=customer_group,
        territory=territory,
        company=company,
        pos_profile=pos_profile,
    )

    # Persist the offline_id when the field exists so future replays are idempotent.
    if meta.has_field("pos_next_offline_id"):
        frappe.db.set_value("Customer", created["name"], "pos_next_offline_id", offline_id)
        created["pos_next_offline_id"] = offline_id

    return {
        "name": created["name"],
        "deduplicated": False,
        "doc": created,
    }
