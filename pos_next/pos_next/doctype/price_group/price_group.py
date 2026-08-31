"""Price Group — outlet-scoped selling prices, ported from the `selling_additional` app.

A Price Group owns one generated Price List (`PG-<name>`), the unscoped Item Price rows
on that list, and every POS Profile matching its outlets. All writes are targeted
(`frappe.db.set_value`) rather than document saves: saving a Price List runs
`PriceList.on_update`, which rewrites every Item Price on the list and can claim the
global `Selling Settings.selling_price_list` default.
"""

from types import MappingProxyType

import frappe
from frappe import _
from frappe.model.document import Document

from pos_next.price_group_ownership import (
	ITEM_PRICE_OWNER_FIELD,
	PRICE_LIST_OWNER_FIELD,
	PROFILE_OWNER_FIELD,
	PROFILE_PREVIOUS_PRICE_LIST_FIELD,
	SCOPE_FIELDS,
	ManagedState,
	managed_item_price_filters,
	managed_price_list_name,
)


class PriceGroup(Document):
	def validate(self) -> None:
		self._validate_items()
		self._validate_outlets()
		self._set_uom()

	def on_update(self) -> None:
		state = self._lock_managed_state()
		self._validate_managed_state(state)
		self._validate_item_uom_conversions()
		self._sync_price_list(state)
		self._sync_item_prices(state)
		self._sync_profiles(state)

	def on_trash(self) -> None:
		state = self._lock_managed_state()
		self._validate_managed_state(state, validate_desired=False)
		self._cleanup(state)

	def _validate_items(self) -> None:
		if not self.items:
			frappe.throw(_("At least one item is required"))

		seen = set()
		for row in self.items:
			if not row.rate or row.rate <= 0:
				frappe.throw(_("Row {0}: Rate must be greater than zero").format(row.idx))
			if row.item_code in seen:
				frappe.throw(_("Row {0}: Duplicate item {1}").format(row.idx, row.item_code))
			seen.add(row.item_code)

	def _validate_outlets(self) -> None:
		seen = set()
		for row in self.outlets:
			key = (row.company, row.warehouse)
			if key in seen:
				frappe.throw(
					_("Row {0}: Duplicate outlet {1} / {2}").format(row.idx, row.company, row.warehouse)
				)
			seen.add(key)

			# Verify warehouse belongs to company
			wh_company = frappe.db.get_value("Warehouse", row.warehouse, "company")
			if wh_company != row.company:
				frappe.throw(
					_("Row {0}: Warehouse {1} belongs to company {2}, not {3}").format(
						row.idx, row.warehouse, wh_company, row.company
					)
				)

	def _set_uom(self) -> None:
		for row in self.items:
			if not frappe.db.exists("Item", row.item_code):
				frappe.throw(_("Item {0} does not exist").format(row.item_code))
			# Managed identity is (item_code, uom) with uom DERIVED from the Item's current
			# stock UOM on every save. Derive unconditionally, never fill-if-blank: the child
			# field is read_only, and preserving a stale value is what prevents identity from
			# moving after a stock-UOM change.
			row.uom = frappe.db.get_value("Item", row.item_code, "stock_uom")
			if not row.uom:
				frappe.throw(_("Item {0} has no stock UOM").format(row.item_code))
			if not frappe.db.exists("UOM", row.uom):
				frappe.throw(_("UOM {0} does not exist").format(row.uom))

	def _currently_owned_profiles(self) -> list[str]:
		if not self.name:
			return []
		return sorted(
			frappe.get_all(
				"POS Profile",
				filters={PROFILE_OWNER_FIELD: self.name},
				pluck="name",
			)
		)

	def _lock_managed_state(self) -> ManagedState:
		# Lock order for BOTH on_update() and on_trash():
		# 1. Price Group row
		if self.name and frappe.db.exists("Price Group", self.name):
			frappe.db.get_value("Price Group", self.name, "modified", for_update=True)

		# 2. Resolve desired profile names and per-outlet mapping deterministically
		desired_set: set[str] = set()
		outlet_profiles_dict: dict[tuple[str, str], str | None] = {}
		for row in self.outlets:
			key = (row.company, row.warehouse)
			if key not in outlet_profiles_dict:
				matching = frappe.get_all(
					"POS Profile",
					filters={"company": row.company, "warehouse": row.warehouse},
					pluck="name",
					order_by="name asc",
				)
				chosen = matching[0] if matching else None
				outlet_profiles_dict[key] = chosen
				if chosen:
					desired_set.add(chosen)

		desired = sorted(desired_set)
		currently_owned = self._currently_owned_profiles()
		all_profiles = sorted(set(desired) | set(currently_owned))

		# 3. Lock the sorted union of those profile rows
		for p_name in all_profiles:
			frappe.db.get_value("POS Profile", p_name, "modified", for_update=True)

		# 4. Lock the managed Price List row when it exists
		pl_name = managed_price_list_name(self.price_group_name)
		if frappe.db.exists("Price List", pl_name):
			frappe.db.get_value("Price List", pl_name, "modified", for_update=True)

		# 5. Query existing marked Item Price names using unscoped filters, sort them, lock each row
		existing_marked_ips = []
		if self.name:
			existing_marked_ips = sorted(
				frappe.get_all(
					"Item Price",
					filters=managed_item_price_filters(self.name, pl_name),
					pluck="name",
				)
			)
		for ip_name in existing_marked_ips:
			frappe.db.get_value("Item Price", ip_name, "modified", for_update=True)

		return ManagedState(
			price_list_name=pl_name,
			desired_profiles=tuple(desired),
			currently_owned_profiles=tuple(currently_owned),
			all_profiles=tuple(all_profiles),
			managed_item_prices=tuple(existing_marked_ips),
			outlet_profiles=MappingProxyType(outlet_profiles_dict),
		)

	def _validate_managed_state(self, state: ManagedState, *, validate_desired: bool = True) -> None:
		# Read ownership values again from locked rows, validate collisions & invariants
		pl_name = state.price_list_name
		if frappe.db.exists("Price List", pl_name):
			pl_owner = frappe.db.get_value("Price List", pl_name, PRICE_LIST_OWNER_FIELD)
			if pl_owner and pl_owner != self.name:
				frappe.throw(_("Price List {0} already exists and is owned by {1}").format(pl_name, pl_owner))
			if not pl_owner:
				frappe.throw(
					_("Price List {0} already exists and is not linked to this Price Group").format(pl_name)
				)

		# Desired-profile collisions block a save, but NOT a delete: delete is scoped to
		# owned profiles, and a foreign-owned profile this group merely desires is untouched.
		if validate_desired:
			for p_name in state.desired_profiles:
				p_owner = frappe.db.get_value("POS Profile", p_name, PROFILE_OWNER_FIELD)
				if p_owner and p_owner != self.name:
					frappe.throw(
						_("POS Profile {0} is already claimed by Price Group {1}").format(p_name, p_owner)
					)

		for p_name in state.currently_owned_profiles:
			p_owner = frappe.db.get_value("POS Profile", p_name, PROFILE_OWNER_FIELD)
			if p_owner and p_owner != self.name:
				frappe.throw(
					_("POS Profile {0} is owned by {1}, expected {2}").format(p_name, p_owner, self.name)
				)

	def _validate_item_uom_conversions(self) -> None:
		"""Fail before any Item Price mutation when a resolved UOM has no conversion row.

		`ItemPrice.validate_item` requires a UOM Conversion Detail row for the Item and UOM
		and throws MID-mutation, after the Price List already exists. Frappe normally
		guarantees one for the stock UOM (`Item.add_default_uom_in_conversion_factor_table`),
		so this only catches a hand-damaged Item — and names the Item and UOM when it does.
		"""
		for row in self.items:
			if not row.uom:
				continue
			if not frappe.db.exists(
				"UOM Conversion Detail",
				{"parenttype": "Item", "parent": row.item_code, "uom": row.uom},
			):
				frappe.throw(
					_("Conversion Factor for UOM {0} does not exist for Item {1}").format(
						row.uom, row.item_code
					),
					exc=frappe.ValidationError,
				)

	def _sync_price_list(self, state: ManagedState) -> None:
		# Targeted writes avoid PriceList.on_update, which rewrites all Item Prices and may
		# claim the global Selling default.
		pl_name = state.price_list_name
		if frappe.db.exists("Price List", pl_name):
			frappe.db.set_value(
				"Price List",
				pl_name,
				{
					"enabled": 1 if self.enabled else 0,
					"currency": self.currency,
					PRICE_LIST_OWNER_FIELD: self.name,
				},
				update_modified=False,
			)
			frappe.cache.hdel("price_list_details", pl_name)
		else:
			# The row is usually ABSENT here (every restore below deletes it), so this
			# FOR UPDATE takes a gap lock on (doctype, field) rather than a row lock.
			# tabSingles has only a non-unique index and no primary key, and gap locks
			# exist only under REPEATABLE READ. Under READ COMMITTED this degrades to an
			# optimistic read-then-restore.
			res = frappe.db.sql(
				"""select value from tabSingles
				   where doctype = 'Selling Settings' and field = 'selling_price_list'
				   for update"""
			)
			prev_single = res[0][0] if res else None

			prev_default_rows = frappe.db.sql(
				"""select defvalue from tabDefaultValue
				   where parent = '__default' and defkey = 'selling_price_list'"""
			)
			prev_default = prev_default_rows[0][0] if prev_default_rows else None

			pl = frappe.get_doc(
				{
					"doctype": "Price List",
					"price_list_name": pl_name,
					"selling": 1,
					"buying": 0,
					"currency": self.currency,
					"enabled": 1 if self.enabled else 0,
					PRICE_LIST_OWNER_FIELD: self.name,
				}
			)
			pl.insert(ignore_permissions=True)

			curr_single = frappe.db.get_single_value("Selling Settings", "selling_price_list")
			if curr_single != prev_single and curr_single == pl_name:
				if prev_single:
					frappe.db.sql(
						"""update tabSingles set value = %s
						   where doctype = 'Selling Settings' and field = 'selling_price_list'""",
						(prev_single,),
					)
				else:
					frappe.db.sql(
						"""delete from tabSingles
						   where doctype = 'Selling Settings' and field = 'selling_price_list'"""
					)
				frappe.clear_document_cache("Selling Settings", "Selling Settings")

			curr_default_rows = frappe.db.sql(
				"""select defvalue from tabDefaultValue
				   where parent = '__default' and defkey = 'selling_price_list'"""
			)
			curr_default = curr_default_rows[0][0] if curr_default_rows else None
			if curr_default != prev_default and curr_default == pl_name:
				if prev_default:
					frappe.db.set_default("selling_price_list", prev_default)
				else:
					frappe.defaults.clear_default("selling_price_list", parent="__default")

		if self.price_list != pl_name:
			self.db_set("price_list", pl_name, update_modified=False)
			self.price_list = pl_name

	def _sync_item_prices(self, state: ManagedState) -> None:
		if not self.enabled:
			# Disabled: do not insert, update, or delete Item Prices. Keep all marked rows
			# so a later re-enable restores the exact same prices.
			return

		pl_name = state.price_list_name
		desired_identities = {}
		for row in self.items:
			desired_identities[(row.item_code, row.uom)] = row.rate

		# Stale detection using ONLY already locked marked rows
		existing_marked_by_ident = {}
		for ip_name in state.managed_item_prices:
			ident = frappe.db.get_value("Item Price", ip_name, ["item_code", "uom"], as_dict=True)
			if ident:
				if (ident.item_code, ident.uom) in existing_marked_by_ident:
					frappe.throw(
						_("Two managed Item Prices share identity ({0}, {1}) on {2}").format(
							ident.item_code, ident.uom, pl_name
						)
					)
				existing_marked_by_ident[(ident.item_code, ident.uom)] = ip_name

		# Precheck for colliding unmanaged unscoped Item Prices before mutating.
		# Deliberately broader than ItemPrice.check_duplicates on valid_from: SCOPE_FIELDS omits
		# it (see its docstring), so this matches an unmanaged row on ANY start date rather than
		# only today's. That is the conservative direction — an open-ended unmanaged row makes
		# price resolution on a managed list ambiguous whatever its start date.
		# The uom predicate is normalization-aware: a legacy NULL/empty-uom row on this list
		# normalizes to the Item's stock UOM — exactly the identity being inserted — and
		# ItemPrice.check_duplicates treats NULL and '' as equivalent, so catching it here
		# produces the named validation error instead of ERPNext's late duplicate exception.
		for item_code, uom in desired_identities:
			if (item_code, uom) in existing_marked_by_ident:
				continue
			colliding_filters = {
				"price_list": pl_name,
				"item_code": item_code,
				"uom": ["in", [uom, None, ""]],
				ITEM_PRICE_OWNER_FIELD: ["is", "not set"],
			}
			for field in SCOPE_FIELDS:
				colliding_filters[field] = ["in", [None, 0]] if field == "packing_unit" else ["is", "not set"]
			colliding = frappe.get_all("Item Price", filters=colliding_filters, pluck="name", limit=1)
			if colliding:
				frappe.throw(
					_(
						"An existing unmanaged Item Price {0} already covers Item {1} with UOM {2} "
						"on Price List {3}. Resolve it before this Price Group can manage that item."
					).format(colliding[0], item_code, uom, pl_name)
				)

		# Update or insert desired marked rows
		for (item_code, uom), rate in desired_identities.items():
			if (item_code, uom) in existing_marked_by_ident:
				ip_name = existing_marked_by_ident[(item_code, uom)]
				curr_rate = frappe.db.get_value("Item Price", ip_name, "price_list_rate")
				if curr_rate != rate:
					frappe.db.set_value(
						"Item Price",
						ip_name,
						{"price_list_rate": rate, ITEM_PRICE_OWNER_FIELD: self.name},
					)
			else:
				ip = frappe.get_doc(
					{
						"doctype": "Item Price",
						"item_code": item_code,
						"uom": uom,
						"price_list": pl_name,
						"price_list_rate": rate,
						"currency": self.currency,
						ITEM_PRICE_OWNER_FIELD: self.name,
					}
				)
				ip.insert(ignore_permissions=True)

		# Delete only marked rows not in desired identities
		for (item_code, uom), ip_name in existing_marked_by_ident.items():
			if (item_code, uom) not in desired_identities:
				frappe.delete_doc("Item Price", ip_name, ignore_permissions=True)

	def _restore_profile(self, p_name: str) -> None:
		prev_pl = frappe.db.get_value("POS Profile", p_name, PROFILE_PREVIOUS_PRICE_LIST_FIELD)
		frappe.db.set_value(
			"POS Profile",
			p_name,
			{
				"selling_price_list": prev_pl,
				PROFILE_OWNER_FIELD: None,
				PROFILE_PREVIOUS_PRICE_LIST_FIELD: None,
			},
			update_modified=False,
		)

	def _sync_profiles(self, state: ManagedState) -> None:
		# Targeted restore bypasses unrelated POS Profile validation while preserving the
		# recorded prior list.
		pl_name = state.price_list_name
		desired_set = set(state.desired_profiles) if self.enabled else set()

		# Update outlet child table statuses & pos_profile links from the state snapshot
		for row in self.outlets:
			profile_name = state.outlet_profiles.get((row.company, row.warehouse))
			if not profile_name:
				row.status = "No POS Profile"
				row.pos_profile = None
			else:
				row.status = "Linked"
				row.pos_profile = profile_name

			if row.name:
				frappe.db.set_value(
					"Price Group Outlet",
					row.name,
					{"status": row.status, "pos_profile": row.pos_profile},
					update_modified=False,
				)

		# Claim desired profiles
		for p_name in desired_set:
			p_owner = frappe.db.get_value("POS Profile", p_name, PROFILE_OWNER_FIELD)
			current_pl = frappe.db.get_value("POS Profile", p_name, "selling_price_list")
			if not p_owner:
				# Empty owner: store current list once, set owner, assign managed list
				frappe.db.set_value(
					"POS Profile",
					p_name,
					{
						PROFILE_PREVIOUS_PRICE_LIST_FIELD: current_pl,
						PROFILE_OWNER_FIELD: self.name,
						"selling_price_list": pl_name,
					},
					update_modified=False,
				)
			elif p_owner == self.name:
				# Same owner: update only assigned list
				if current_pl != pl_name:
					frappe.db.set_value(
						"POS Profile",
						p_name,
						{"selling_price_list": pl_name},
						update_modified=False,
					)

		# Restore currently owned profiles not desired (or all when disabled)
		for p_name in state.currently_owned_profiles:
			if p_name not in desired_set:
				self._restore_profile(p_name)

	def _cleanup(self, state: ManagedState) -> None:
		# Delete restores every owned profile, deletes only marked Item Prices, clears the
		# Price List marker, then disables and RETAINS the Price List.
		# Never force-delete and never delete the Price List.

		# 1. Restore every owned profile
		for p_name in state.currently_owned_profiles:
			self._restore_profile(p_name)

		# 2. Delete only marked Item Prices
		for ip_name in state.managed_item_prices:
			if frappe.db.exists("Item Price", ip_name):
				frappe.delete_doc("Item Price", ip_name, ignore_permissions=True)

		# 3. Clear Price List marker, disable and retain Price List
		pl_name = state.price_list_name
		if frappe.db.exists("Price List", pl_name):
			frappe.db.set_value(
				"Price List",
				pl_name,
				{
					"enabled": 0,
					PRICE_LIST_OWNER_FIELD: None,
				},
				update_modified=False,
			)
			frappe.cache.hdel("price_list_details", pl_name)
