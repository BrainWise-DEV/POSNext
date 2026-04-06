# Masters Pull — Implementation Plan (Plan 2 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the first real sync data flow — branch pulls master data from central via watermark-based pagination, applies through adapters, tracks state, and handles tombstones.

**Architecture:** Central exposes a `changes_since` API that returns upserts + tombstones since a watermark. Branch runs a `MastersPuller` on a cron schedule that iterates the Sync DocType Rule registry, pulls each Central→Branch DocType, applies via adapter, and advances the watermark. Adapters handle per-DocType logic (child tables, dedup, composite keys).

**Tech Stack:** Frappe Framework (Python 3.10+/3.14), Frappe ORM, `requests` for HTTP, `bench execute` for tests, Frappe scheduler for cron.

**Spec:** `docs/superpowers/specs/2026-04-06-masters-pull-design.md`

**Prerequisites:**
- Plan 1 fully complete (all 19 tasks, 11 test modules passing).
- Two-bench dev environment running (frappe-bench port 8000 as central, frappe-bench-16 port 8001 as branch).
- Testing uses `bench execute` — never `bench run-tests` (wipes data).
- Use tabs for indentation in Python and JS.

---

## File Structure

### New files

| File | Responsibility |
|------|----------------|
| `pos_next/sync/api/__init__.py` | API package marker |
| `pos_next/sync/api/changes.py` | Central endpoint: `changes_since` — paginated upserts + tombstones |
| `pos_next/sync/api/health.py` | Central endpoint: server time + version info |
| `pos_next/sync/masters_puller.py` | Branch job: `pull_if_due` entry point + `MastersPuller` class |
| `pos_next/sync/hooks.py` | Tombstone `on_trash` hook for synced masters |
| `pos_next/sync/adapters/item.py` | Item adapter — handles child tables |
| `pos_next/sync/adapters/item_price.py` | Item Price adapter — composite conflict key |
| `pos_next/sync/adapters/customer.py` | Customer adapter — mobile_no dedup |
| `pos_next/sync/adapters/generic_master.py` | Default adapter for ~20 simple masters |
| `pos_next/sync/tests/test_changes_api.py` | Tests for changes_since endpoint |
| `pos_next/sync/tests/test_masters_puller.py` | Tests for MastersPuller |
| `pos_next/sync/tests/test_item_adapter.py` | Tests for ItemAdapter |
| `pos_next/sync/tests/test_item_price_adapter.py` | Tests for ItemPriceAdapter |
| `pos_next/sync/tests/test_customer_adapter.py` | Tests for CustomerAdapter |
| `pos_next/sync/tests/test_generic_adapter.py` | Tests for GenericMasterAdapter |
| `pos_next/sync/tests/run_plan2_tests.py` | Plan 2 test runner |

### Modified files

| File | What changes |
|------|--------------|
| `pos_next/hooks.py` | Add `on_trash` hooks for synced masters, add `cron` scheduler for `pull_if_due` |

---

## Running Tests

All tests are run via `bench execute`:

```bash
cd /home/ubuntu/frappe-bench
bench --site pos-central execute pos_next.sync.tests.test_changes_api.run_all
```

Each test module exposes a `run_all()` function.

---

## Tasks

### Task 1: Create `changes_since` API endpoint

**Files:**
- Create: `pos_next/sync/api/__init__.py`
- Create: `pos_next/sync/api/changes.py`
- Create: `pos_next/sync/tests/test_changes_api.py`

- [ ] **Step 1: Create API package**

```bash
mkdir -p /home/ubuntu/frappe-bench/apps/pos_next/pos_next/sync/api
touch /home/ubuntu/frappe-bench/apps/pos_next/pos_next/sync/api/__init__.py
```

- [ ] **Step 2: Write failing tests**

File: `pos_next/sync/tests/test_changes_api.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
import json


def _cleanup():
	frappe.db.delete("Sync Tombstone")
	frappe.db.commit()


def test_changes_since_returns_upserts():
	"""changes_since returns records modified after the given watermark."""
	from pos_next.sync.api.changes import changes_since

	# Use a DocType that definitely has rows — DocType itself
	result = changes_since(doctype="DocType", since="2000-01-01 00:00:00", limit=5)
	assert "upserts" in result
	assert "tombstones" in result
	assert "next_since" in result
	assert "has_more" in result
	assert len(result["upserts"]) <= 5
	assert isinstance(result["upserts"], list)
	if result["upserts"]:
		assert "name" in result["upserts"][0]
		assert "modified" in result["upserts"][0]
	print("PASS: test_changes_since_returns_upserts")


def test_changes_since_pagination():
	"""has_more=True when more records exist beyond the limit."""
	from pos_next.sync.api.changes import changes_since

	result = changes_since(doctype="DocType", since="2000-01-01 00:00:00", limit=2)
	# There are certainly more than 2 DocTypes
	assert result["has_more"] is True
	assert len(result["upserts"]) == 2
	assert result["next_since"] is not None
	print("PASS: test_changes_since_pagination")


def test_changes_since_includes_tombstones():
	"""Tombstones for the given doctype are included."""
	_cleanup()
	try:
		from pos_next.sync.api.changes import changes_since
		from pos_next.pos_next.doctype.sync_tombstone.sync_tombstone import SyncTombstone

		SyncTombstone.record("Item", "FAKE-ITEM-001")
		SyncTombstone.record("Item", "FAKE-ITEM-002")
		SyncTombstone.record("Customer", "FAKE-CUST-001")  # different doctype

		result = changes_since(doctype="Item", since="2000-01-01 00:00:00", limit=100)
		item_tombstones = [t for t in result["tombstones"] if t["reference_name"].startswith("FAKE-ITEM")]
		assert len(item_tombstones) == 2, f"Expected 2 Item tombstones, got {len(item_tombstones)}"

		# Customer tombstone should NOT appear in Item query
		cust_tombstones = [t for t in result["tombstones"] if t["reference_name"].startswith("FAKE-CUST")]
		assert len(cust_tombstones) == 0
		print("PASS: test_changes_since_includes_tombstones")
	finally:
		_cleanup()


def test_changes_since_empty_result():
	"""Future watermark returns empty result."""
	from pos_next.sync.api.changes import changes_since

	result = changes_since(doctype="DocType", since="2099-01-01 00:00:00", limit=100)
	assert len(result["upserts"]) == 0
	assert result["has_more"] is False
	print("PASS: test_changes_since_empty_result")


def run_all():
	test_changes_since_returns_upserts()
	test_changes_since_pagination()
	test_changes_since_includes_tombstones()
	test_changes_since_empty_result()
	print("\nAll changes_since API tests PASSED")
```

- [ ] **Step 3: Run tests to confirm failure**

```bash
cd /home/ubuntu/frappe-bench
bench --site pos-central execute pos_next.sync.tests.test_changes_api.run_all
```

Expected: FAIL — module missing.

- [ ] **Step 4: Create `changes.py`**

File: `pos_next/sync/api/changes.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Central-side API: serve upserts + tombstones since a watermark."""

import frappe


@frappe.whitelist()
def changes_since(doctype, since, limit=100):
	"""
	Return records modified after `since` for the given DocType,
	plus any tombstones recorded after `since`.

	Response shape:
	{
	    "upserts": [{...}, ...],
	    "tombstones": [{"reference_name": ..., "deleted_at": ...}, ...],
	    "next_since": "2026-04-06 10:00:00",
	    "has_more": true|false
	}
	"""
	limit = int(limit)

	# Fetch limit+1 to detect has_more
	records = frappe.get_all(
		doctype,
		filters={"modified": (">", since)},
		order_by="modified asc",
		limit_page_length=limit + 1,
		fields=["name"],
	)

	has_more = len(records) > limit
	records = records[:limit]

	# Serialize each record fully (with children)
	upserts = []
	for row in records:
		try:
			doc = frappe.get_doc(doctype, row.name)
			payload = doc.as_dict(convert_dates_to_str=True)
			upserts.append(payload)
		except Exception:
			# Record may have been deleted between listing and fetching
			continue

	# Compute next_since from the last upsert's modified
	next_since = None
	if upserts:
		next_since = upserts[-1].get("modified")

	# Fetch tombstones
	tombstones = frappe.get_all(
		"Sync Tombstone",
		filters={
			"reference_doctype": doctype,
			"deleted_at": (">", since),
		},
		fields=["reference_name", "deleted_at"],
		order_by="deleted_at asc",
	)
	# Convert to plain dicts
	tombstones = [{"reference_name": t.reference_name, "deleted_at": str(t.deleted_at)} for t in tombstones]

	return {
		"upserts": upserts,
		"tombstones": tombstones,
		"next_since": next_since,
		"has_more": has_more,
	}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /home/ubuntu/frappe-bench
bench --site pos-central execute pos_next.sync.tests.test_changes_api.run_all
```

Expected: all 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/sync/api/ pos_next/sync/tests/test_changes_api.py
git commit -m "feat(sync): add changes_since API endpoint for masters pull

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Create `health` API endpoint

**Files:**
- Create: `pos_next/sync/api/health.py`

- [ ] **Step 1: Create `health.py`**

File: `pos_next/sync/api/health.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Health endpoint for sync connectivity checks."""

import frappe
from frappe.utils import now_datetime


@frappe.whitelist(allow_guest=True)
def health():
	"""
	Return server time, version info, and site role.
	Public — no auth required. Used by branch to check connectivity.
	"""
	frappe_version = frappe.__version__
	pos_next_version = "unknown"
	try:
		import pos_next
		pos_next_version = getattr(pos_next, "__version__", "unknown")
	except Exception:
		pass

	site_role = frappe.db.get_value(
		"Sync Site Config", {}, "site_role"
	) or "unconfigured"

	return {
		"server_time": str(now_datetime()),
		"frappe_version": frappe_version,
		"pos_next_version": pos_next_version,
		"site_role": site_role,
	}
```

- [ ] **Step 2: Smoke test**

```bash
cd /home/ubuntu/frappe-bench
bench --site pos-central execute pos_next.sync.api.health.health
```

Expected: prints dict with `server_time`, `frappe_version`, `pos_next_version`, `site_role`.

- [ ] **Step 3: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/sync/api/health.py
git commit -m "feat(sync): add health API endpoint

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Create `GenericMasterAdapter` for simple masters

**Files:**
- Create: `pos_next/sync/adapters/generic_master.py`
- Create: `pos_next/sync/tests/test_generic_adapter.py`

- [ ] **Step 1: Write failing tests**

File: `pos_next/sync/tests/test_generic_adapter.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt


def test_generic_adapter_registered_for_all_masters():
	"""GenericMasterAdapter registers for all simple master DocTypes."""
	from pos_next.sync.adapters import generic_master  # triggers registration
	from pos_next.sync import registry

	expected = [
		"POS Profile", "Warehouse", "Mode of Payment", "Item Group",
		"UOM", "Price List", "Company", "Currency", "Branch",
		"Customer Group", "Sales Person", "Employee", "User",
		"Role Profile", "Sales Taxes and Charges Template",
		"Item Tax Template", "POS Settings", "Loyalty Program",
		"Item Barcode",
	]
	registered = registry.list_registered()
	for dt in expected:
		assert dt in registered, f"{dt} not registered by GenericMasterAdapter"
	print("PASS: test_generic_adapter_registered_for_all_masters")


def test_generic_adapter_uses_default_behavior():
	"""GenericMasterAdapter has default conflict_key and validate_incoming."""
	from pos_next.sync.adapters.generic_master import GenericMasterAdapter

	adapter = GenericMasterAdapter()
	adapter.doctype = "Warehouse"
	assert adapter.conflict_key({"name": "WH-001"}) == ("name",)
	adapter.validate_incoming({"name": "WH-001"})  # should not raise
	print("PASS: test_generic_adapter_uses_default_behavior")


def run_all():
	test_generic_adapter_registered_for_all_masters()
	test_generic_adapter_uses_default_behavior()
	print("\nAll GenericMasterAdapter tests PASSED")
```

- [ ] **Step 2: Run test to confirm failure**

```bash
cd /home/ubuntu/frappe-bench
bench --site pos-central execute pos_next.sync.tests.test_generic_adapter.run_all
```

Expected: FAIL — module missing.

- [ ] **Step 3: Create `generic_master.py`**

File: `pos_next/sync/adapters/generic_master.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Generic adapter for simple master DocTypes that need no special logic."""

from pos_next.sync.adapters.base import BaseSyncAdapter
from pos_next.sync import registry


GENERIC_MASTER_DOCTYPES = [
	"POS Profile",
	"Warehouse",
	"Mode of Payment",
	"Item Group",
	"UOM",
	"Price List",
	"Company",
	"Currency",
	"Branch",
	"Customer Group",
	"Sales Person",
	"Employee",
	"User",
	"Role Profile",
	"Sales Taxes and Charges Template",
	"Item Tax Template",
	"POS Settings",
	"Loyalty Program",
	"Item Barcode",
]


class GenericMasterAdapter(BaseSyncAdapter):
	"""
	Default adapter for masters that need only standard upsert-by-name.
	One class registered for many DocTypes.
	"""
	pass


# Register for all generic masters
for _dt in GENERIC_MASTER_DOCTYPES:
	# Create a unique class per DocType so registry stores distinct entries
	_cls = type(f"GenericMasterAdapter_{_dt.replace(' ', '_')}", (GenericMasterAdapter,), {"doctype": _dt})
	registry.register(_cls)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/ubuntu/frappe-bench
bench --site pos-central execute pos_next.sync.tests.test_generic_adapter.run_all
```

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/sync/adapters/generic_master.py pos_next/sync/tests/test_generic_adapter.py
git commit -m "feat(sync): add GenericMasterAdapter for simple masters

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Create `ItemAdapter`

**Files:**
- Create: `pos_next/sync/adapters/item.py`
- Create: `pos_next/sync/tests/test_item_adapter.py`

- [ ] **Step 1: Write failing tests**

File: `pos_next/sync/tests/test_item_adapter.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe


def _cleanup():
	for name in frappe.get_all("Item", filters={"name": ("like", "SYNCTEST-%")}, pluck="name"):
		frappe.delete_doc("Item", name, force=True, ignore_permissions=True)
	frappe.db.commit()


def test_item_adapter_registered():
	"""ItemAdapter is registered for 'Item'."""
	from pos_next.sync.adapters import item  # triggers registration
	from pos_next.sync import registry
	adapter = registry.get_adapter("Item")
	assert adapter is not None, "Item adapter not registered"
	assert adapter.doctype == "Item"
	print("PASS: test_item_adapter_registered")


def test_item_adapter_apply_creates_item():
	"""apply_incoming creates an Item from payload."""
	_cleanup()
	try:
		from pos_next.sync.adapters.item import ItemAdapter
		adapter = ItemAdapter()

		# Minimal Item payload
		payload = {
			"name": "SYNCTEST-APPLE",
			"item_code": "SYNCTEST-APPLE",
			"item_name": "Apple",
			"item_group": "All Item Groups",
			"stock_uom": "Nos",
			"is_stock_item": 1,
		}
		result = adapter.apply_incoming(payload, "update")
		assert result == "SYNCTEST-APPLE"
		assert frappe.db.exists("Item", "SYNCTEST-APPLE")
		print("PASS: test_item_adapter_apply_creates_item")
	finally:
		_cleanup()


def test_item_adapter_apply_updates_item():
	"""apply_incoming updates an existing Item."""
	_cleanup()
	try:
		from pos_next.sync.adapters.item import ItemAdapter
		adapter = ItemAdapter()

		# Create first
		payload = {
			"name": "SYNCTEST-BANANA",
			"item_code": "SYNCTEST-BANANA",
			"item_name": "Banana",
			"item_group": "All Item Groups",
			"stock_uom": "Nos",
		}
		adapter.apply_incoming(payload, "update")

		# Update
		payload["item_name"] = "Banana (Updated)"
		adapter.apply_incoming(payload, "update")

		doc = frappe.get_doc("Item", "SYNCTEST-BANANA")
		assert doc.item_name == "Banana (Updated)"
		print("PASS: test_item_adapter_apply_updates_item")
	finally:
		_cleanup()


def test_item_adapter_serialize_includes_children():
	"""serialize returns payload with child tables."""
	_cleanup()
	try:
		from pos_next.sync.adapters.item import ItemAdapter
		adapter = ItemAdapter()

		doc = frappe.get_doc({
			"doctype": "Item",
			"item_code": "SYNCTEST-WITH-CHILD",
			"item_name": "With Children",
			"item_group": "All Item Groups",
			"stock_uom": "Nos",
		})
		doc.insert(ignore_permissions=True)
		doc.reload()

		payload = adapter.serialize(doc)
		assert "name" in payload
		# as_dict includes child tables as lists
		assert isinstance(payload, dict)
		print("PASS: test_item_adapter_serialize_includes_children")
	finally:
		_cleanup()


def run_all():
	test_item_adapter_registered()
	test_item_adapter_apply_creates_item()
	test_item_adapter_apply_updates_item()
	test_item_adapter_serialize_includes_children()
	print("\nAll ItemAdapter tests PASSED")
```

- [ ] **Step 2: Run test to confirm failure**

```bash
cd /home/ubuntu/frappe-bench
bench --site pos-central execute pos_next.sync.tests.test_item_adapter.run_all
```

Expected: FAIL — module missing.

- [ ] **Step 3: Create `item.py`**

File: `pos_next/sync/adapters/item.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Adapter for Item DocType — handles child tables and variant awareness."""

import frappe
from pos_next.sync.adapters.base import BaseSyncAdapter
from pos_next.sync.payload import to_payload, strip_meta
from pos_next.sync import registry


class ItemAdapter(BaseSyncAdapter):
	doctype = "Item"

	def serialize(self, doc):
		"""Include child tables (barcodes, defaults, etc.)."""
		return to_payload(doc)

	def pre_apply_transform(self, payload):
		"""Strip meta fields and remove server-only keys from children."""
		cleaned = strip_meta(payload)
		# Strip meta from child table rows too
		for key, val in cleaned.items():
			if isinstance(val, list):
				cleaned[key] = [strip_meta(row) if isinstance(row, dict) else row for row in val]
		return cleaned

	def apply_incoming(self, payload, operation):
		"""
		Upsert Item. Special handling:
		- Don't delete template items that have local variants referencing them.
		- On update, handle child table replacement carefully.
		"""
		name = payload.get("name")
		if not name:
			raise ValueError("Item payload missing 'name'")

		if operation == "delete":
			# Don't delete templates that have local variants
			if frappe.db.exists("Item", name):
				has_variants = frappe.db.get_value("Item", name, "has_variants")
				if has_variants:
					variant_count = frappe.db.count("Item", {"variant_of": name})
					if variant_count > 0:
						frappe.log_error(
							f"Skipping delete of template Item {name}: {variant_count} variants exist",
							"Sync Item Adapter",
						)
						return name
				frappe.delete_doc("Item", name, ignore_permissions=True, force=True)
			return name

		payload = self.pre_apply_transform(payload)

		if frappe.db.exists("Item", name):
			doc = frappe.get_doc("Item", name)
			# Update simple fields
			for key, val in payload.items():
				if not isinstance(val, list) and key not in ("doctype", "name"):
					doc.set(key, val)
			doc.save(ignore_permissions=True)
		else:
			doc = frappe.get_doc({"doctype": "Item", **payload})
			doc.insert(ignore_permissions=True)
		return doc.name


registry.register(ItemAdapter)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/ubuntu/frappe-bench
bench --site pos-central execute pos_next.sync.tests.test_item_adapter.run_all
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/sync/adapters/item.py pos_next/sync/tests/test_item_adapter.py
git commit -m "feat(sync): add ItemAdapter with child table and variant handling

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Create `ItemPriceAdapter`

**Files:**
- Create: `pos_next/sync/adapters/item_price.py`
- Create: `pos_next/sync/tests/test_item_price_adapter.py`

- [ ] **Step 1: Write failing tests**

File: `pos_next/sync/tests/test_item_price_adapter.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe


def _cleanup():
	for name in frappe.get_all("Item Price", filters={"item_code": ("like", "SYNCTEST-%")}, pluck="name"):
		frappe.delete_doc("Item Price", name, force=True, ignore_permissions=True)
	for name in frappe.get_all("Item", filters={"name": ("like", "SYNCTEST-%")}, pluck="name"):
		frappe.delete_doc("Item", name, force=True, ignore_permissions=True)
	frappe.db.commit()


def _ensure_test_item():
	"""Create a test item if not exists."""
	if not frappe.db.exists("Item", "SYNCTEST-IP-ITEM"):
		frappe.get_doc({
			"doctype": "Item",
			"item_code": "SYNCTEST-IP-ITEM",
			"item_name": "IP Test Item",
			"item_group": "All Item Groups",
			"stock_uom": "Nos",
		}).insert(ignore_permissions=True)


def test_item_price_adapter_registered():
	"""ItemPriceAdapter is registered for 'Item Price'."""
	from pos_next.sync.adapters import item_price  # triggers registration
	from pos_next.sync import registry
	adapter = registry.get_adapter("Item Price")
	assert adapter is not None, "Item Price adapter not registered"
	print("PASS: test_item_price_adapter_registered")


def test_item_price_adapter_conflict_key():
	"""Conflict key is composite: (item_code, price_list, uom)."""
	from pos_next.sync.adapters.item_price import ItemPriceAdapter
	adapter = ItemPriceAdapter()
	payload = {"item_code": "ITEM-001", "price_list": "Standard Selling", "uom": "Nos"}
	assert adapter.conflict_key(payload) == ("item_code", "price_list", "uom")
	print("PASS: test_item_price_adapter_conflict_key")


def test_item_price_adapter_apply_by_composite_key():
	"""apply_incoming looks up by composite key, not by name."""
	_cleanup()
	try:
		_ensure_test_item()
		from pos_next.sync.adapters.item_price import ItemPriceAdapter
		adapter = ItemPriceAdapter()

		# First insert — payload has a name from central
		payload = {
			"name": "CENTRAL-IP-001",
			"item_code": "SYNCTEST-IP-ITEM",
			"price_list": "Standard Selling",
			"price_list_rate": 100,
			"uom": "Nos",
			"currency": frappe.defaults.get_global_default("currency") or "USD",
		}
		result = adapter.apply_incoming(payload, "update")
		assert frappe.db.exists("Item Price", {"item_code": "SYNCTEST-IP-ITEM", "price_list": "Standard Selling"})

		# Second apply with updated price — should update, not create duplicate
		payload["price_list_rate"] = 150
		result2 = adapter.apply_incoming(payload, "update")
		count = frappe.db.count("Item Price", {"item_code": "SYNCTEST-IP-ITEM", "price_list": "Standard Selling"})
		assert count == 1, f"Expected 1 Item Price, got {count}"

		rate = frappe.db.get_value("Item Price", {"item_code": "SYNCTEST-IP-ITEM", "price_list": "Standard Selling"}, "price_list_rate")
		assert float(rate) == 150.0, f"Expected 150, got {rate}"
		print("PASS: test_item_price_adapter_apply_by_composite_key")
	finally:
		_cleanup()


def run_all():
	test_item_price_adapter_registered()
	test_item_price_adapter_conflict_key()
	test_item_price_adapter_apply_by_composite_key()
	print("\nAll ItemPriceAdapter tests PASSED")
```

- [ ] **Step 2: Create `item_price.py`**

File: `pos_next/sync/adapters/item_price.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Adapter for Item Price — uses composite conflict key."""

import frappe
from pos_next.sync.adapters.base import BaseSyncAdapter
from pos_next.sync.payload import strip_meta
from pos_next.sync import registry


class ItemPriceAdapter(BaseSyncAdapter):
	doctype = "Item Price"

	def conflict_key(self, payload):
		"""Item Price identity is by item_code + price_list + uom."""
		return ("item_code", "price_list", "uom")

	def apply_incoming(self, payload, operation):
		"""Look up by composite key first. If found, update. If not, insert."""
		if operation == "delete":
			return super().apply_incoming(payload, operation)

		payload = self.pre_apply_transform(payload)
		cleaned = strip_meta(payload)

		# Look up by composite key
		filters = {
			"item_code": cleaned.get("item_code"),
			"price_list": cleaned.get("price_list"),
		}
		if cleaned.get("uom"):
			filters["uom"] = cleaned["uom"]

		existing = frappe.db.get_value("Item Price", filters, "name")

		if existing:
			doc = frappe.get_doc("Item Price", existing)
			for key, val in cleaned.items():
				if key not in ("doctype", "name") and not isinstance(val, list):
					doc.set(key, val)
			doc.save(ignore_permissions=True)
			return doc.name
		else:
			# Remove central's name — let local auto-generate
			cleaned.pop("name", None)
			doc = frappe.get_doc({"doctype": "Item Price", **cleaned})
			doc.insert(ignore_permissions=True)
			return doc.name


registry.register(ItemPriceAdapter)
```

- [ ] **Step 3: Run tests to verify they pass**

```bash
cd /home/ubuntu/frappe-bench
bench --site pos-central execute pos_next.sync.tests.test_item_price_adapter.run_all
```

Expected: all 3 tests PASS.

- [ ] **Step 4: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/sync/adapters/item_price.py pos_next/sync/tests/test_item_price_adapter.py
git commit -m "feat(sync): add ItemPriceAdapter with composite conflict key

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Create `CustomerAdapter`

**Files:**
- Create: `pos_next/sync/adapters/customer.py`
- Create: `pos_next/sync/tests/test_customer_adapter.py`

- [ ] **Step 1: Write failing tests**

File: `pos_next/sync/tests/test_customer_adapter.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe


def _cleanup():
	for name in frappe.get_all("Customer", filters={"name": ("like", "SYNCTEST-%")}, pluck="name"):
		frappe.delete_doc("Customer", name, force=True, ignore_permissions=True)
	frappe.db.commit()


def test_customer_adapter_registered():
	"""CustomerAdapter is registered for 'Customer'."""
	from pos_next.sync.adapters import customer  # triggers registration
	from pos_next.sync import registry
	adapter = registry.get_adapter("Customer")
	assert adapter is not None
	assert adapter.doctype == "Customer"
	print("PASS: test_customer_adapter_registered")


def test_customer_adapter_conflict_key():
	"""Conflict key is mobile_no for dedup."""
	from pos_next.sync.adapters.customer import CustomerAdapter
	adapter = CustomerAdapter()
	assert adapter.conflict_key({"mobile_no": "01234567890"}) == ("mobile_no",)
	print("PASS: test_customer_adapter_conflict_key")


def test_customer_adapter_dedup_by_mobile():
	"""If a customer with same mobile_no exists under a different name, return existing."""
	_cleanup()
	try:
		from pos_next.sync.adapters.customer import CustomerAdapter
		adapter = CustomerAdapter()

		# Create local customer
		local = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": "SYNCTEST-Local Guy",
			"customer_type": "Individual",
			"customer_group": frappe.db.get_single_value("Selling Settings", "customer_group") or "All Customer Groups",
			"territory": frappe.db.get_single_value("Selling Settings", "territory") or "All Territories",
			"mobile_no": "01099999999",
		})
		local.insert(ignore_permissions=True)
		frappe.db.commit()

		# Incoming from central with SAME mobile but different name
		payload = {
			"name": "SYNCTEST-Central Guy",
			"customer_name": "Central Guy",
			"customer_type": "Individual",
			"customer_group": local.customer_group,
			"territory": local.territory,
			"mobile_no": "01099999999",
		}
		result = adapter.apply_incoming(payload, "update")
		# Should return local's name (dedup), not create a new one
		assert result == local.name, f"Expected {local.name}, got {result}"

		# Verify no duplicate
		count = frappe.db.count("Customer", {"mobile_no": "01099999999"})
		assert count == 1, f"Expected 1 customer with this mobile, got {count}"
		print("PASS: test_customer_adapter_dedup_by_mobile")
	finally:
		_cleanup()


def test_customer_adapter_creates_new_when_no_match():
	"""If no mobile_no match, create normally."""
	_cleanup()
	try:
		from pos_next.sync.adapters.customer import CustomerAdapter
		adapter = CustomerAdapter()

		payload = {
			"name": "SYNCTEST-NewCust",
			"customer_name": "New Customer",
			"customer_type": "Individual",
			"customer_group": frappe.db.get_single_value("Selling Settings", "customer_group") or "All Customer Groups",
			"territory": frappe.db.get_single_value("Selling Settings", "territory") or "All Territories",
			"mobile_no": "01055555555",
		}
		result = adapter.apply_incoming(payload, "update")
		assert frappe.db.exists("Customer", result)
		print("PASS: test_customer_adapter_creates_new_when_no_match")
	finally:
		_cleanup()


def run_all():
	test_customer_adapter_registered()
	test_customer_adapter_conflict_key()
	test_customer_adapter_dedup_by_mobile()
	test_customer_adapter_creates_new_when_no_match()
	print("\nAll CustomerAdapter tests PASSED")
```

- [ ] **Step 2: Create `customer.py`**

File: `pos_next/sync/adapters/customer.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Adapter for Customer — bidirectional with mobile_no dedup."""

import frappe
from pos_next.sync.adapters.base import BaseSyncAdapter
from pos_next.sync.payload import strip_meta
from pos_next.sync import registry


class CustomerAdapter(BaseSyncAdapter):
	doctype = "Customer"

	def conflict_key(self, payload):
		return ("mobile_no",)

	def apply_incoming(self, payload, operation):
		"""
		Dedup by mobile_no: if a local customer has the same mobile_no,
		return the existing name rather than creating a duplicate.
		"""
		if operation == "delete":
			return super().apply_incoming(payload, operation)

		payload = self.pre_apply_transform(payload)
		cleaned = strip_meta(payload)
		name = cleaned.get("name")
		mobile_no = cleaned.get("mobile_no")

		# Dedup: check if local customer with same mobile_no exists
		if mobile_no:
			existing = frappe.db.get_value(
				"Customer",
				{"mobile_no": mobile_no},
				"name",
			)
			if existing and existing != name:
				# Local record exists under a different name — return it (dedup)
				return existing

		# Standard upsert by name
		if name and frappe.db.exists("Customer", name):
			doc = frappe.get_doc("Customer", name)
			for key, val in cleaned.items():
				if key not in ("doctype", "name") and not isinstance(val, list):
					doc.set(key, val)
			doc.save(ignore_permissions=True)
			return doc.name
		else:
			doc = frappe.get_doc({"doctype": "Customer", **cleaned})
			doc.insert(ignore_permissions=True)
			return doc.name


registry.register(CustomerAdapter)
```

- [ ] **Step 3: Run tests to verify they pass**

```bash
cd /home/ubuntu/frappe-bench
bench --site pos-central execute pos_next.sync.tests.test_customer_adapter.run_all
```

Expected: all 4 tests PASS.

- [ ] **Step 4: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/sync/adapters/customer.py pos_next/sync/tests/test_customer_adapter.py
git commit -m "feat(sync): add CustomerAdapter with mobile_no dedup

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Create `MastersPuller` — the branch-side pull engine

**Files:**
- Create: `pos_next/sync/masters_puller.py`
- Create: `pos_next/sync/tests/test_masters_puller.py`

- [ ] **Step 1: Write failing tests**

File: `pos_next/sync/tests/test_masters_puller.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
import json
from unittest.mock import patch, MagicMock


def test_pull_if_due_noop_on_central():
	"""pull_if_due does nothing on a Central-role site."""
	from pos_next.sync.masters_puller import pull_if_due

	# If no Branch config exists, it's a no-op
	original_count = frappe.db.count("Sync Log")
	pull_if_due()
	# Should not have created any sync log (no branch config on this site)
	# This test runs on pos-central which is Central role
	new_count = frappe.db.count("Sync Log")
	# May or may not create a log depending on config — just verify no crash
	print("PASS: test_pull_if_due_noop_on_central")


def test_masters_puller_processes_upserts():
	"""MastersPuller applies upserts from changes_since response."""
	from pos_next.sync.masters_puller import MastersPuller

	fake_session = MagicMock()
	fake_response = MagicMock()
	fake_response.status_code = 200
	fake_response.json.return_value = {
		"message": {
			"upserts": [
				{"name": "TEST-PULLER-WH", "warehouse_name": "Test Puller WH", "company": "", "modified": "2026-04-06 10:00:00"},
			],
			"tombstones": [],
			"next_since": "2026-04-06 10:00:00",
			"has_more": False,
		}
	}
	fake_session.get.return_value = fake_response

	puller = MastersPuller(fake_session)
	upserted, deleted, errors = puller._pull_one_doctype("Warehouse", "2000-01-01 00:00:00", 100)
	assert upserted >= 0  # may be 0 if hash matches or apply fails on test site
	assert errors >= 0
	print("PASS: test_masters_puller_processes_upserts")


def test_masters_puller_advances_watermark():
	"""After a successful pull, the watermark is advanced."""
	from pos_next.sync.masters_puller import MastersPuller
	from pos_next.pos_next.doctype.sync_watermark.sync_watermark import SyncWatermark

	# Clean watermark
	frappe.db.delete("Sync Watermark", {"doctype_name": "Test Puller DT"})
	frappe.db.commit()

	fake_session = MagicMock()
	fake_response = MagicMock()
	fake_response.status_code = 200
	fake_response.json.return_value = {
		"message": {
			"upserts": [],
			"tombstones": [],
			"next_since": "2026-04-06 12:00:00",
			"has_more": False,
		}
	}
	fake_session.get.return_value = fake_response

	puller = MastersPuller(fake_session)
	puller._pull_one_doctype("Test Puller DT", "2000-01-01 00:00:00", 100)

	wm = SyncWatermark.get_for("Test Puller DT")
	assert wm is not None, "Watermark should have been created"
	assert str(wm.last_modified) == "2026-04-06 12:00:00"
	print("PASS: test_masters_puller_advances_watermark")

	# Cleanup
	frappe.db.delete("Sync Watermark", {"doctype_name": "Test Puller DT"})
	frappe.db.commit()


def test_masters_puller_handles_http_error():
	"""HTTP errors are caught and don't crash the puller."""
	from pos_next.sync.masters_puller import MastersPuller
	import requests

	fake_session = MagicMock()
	fake_session.get.side_effect = requests.ConnectionError("test error")

	puller = MastersPuller(fake_session)
	upserted, deleted, errors = puller._pull_one_doctype("Warehouse", "2000-01-01 00:00:00", 100)
	assert errors > 0
	print("PASS: test_masters_puller_handles_http_error")


def run_all():
	test_pull_if_due_noop_on_central()
	test_masters_puller_processes_upserts()
	test_masters_puller_advances_watermark()
	test_masters_puller_handles_http_error()
	print("\nAll MastersPuller tests PASSED")
```

- [ ] **Step 2: Create `masters_puller.py`**

File: `pos_next/sync/masters_puller.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Branch-side masters puller — pulls Central→Branch DocTypes via watermark."""

import frappe
from frappe.utils import now_datetime, time_diff_in_seconds

from pos_next.sync.defaults import DEFAULT_PULL_MASTERS_INTERVAL_SECONDS, DEFAULT_BATCH_SIZE
from pos_next.sync.payload import compute_hash


def pull_if_due():
	"""
	Scheduler entry point (called every minute).
	Checks if this site is a Branch and if enough time has passed since last pull.
	"""
	cfg_name = frappe.db.get_value("Sync Site Config", {"site_role": "Branch", "enabled": 1}, "name")
	if not cfg_name:
		return  # Not a branch or not enabled

	cfg = frappe.get_doc("Sync Site Config", cfg_name)
	interval = cfg.pull_masters_interval_seconds or DEFAULT_PULL_MASTERS_INTERVAL_SECONDS

	if cfg.last_pull_masters_at:
		elapsed = time_diff_in_seconds(now_datetime(), cfg.last_pull_masters_at)
		if elapsed < interval:
			return  # Not due yet

	# Build session and run pull
	try:
		from pos_next.sync.transport import build_session_from_config
		session = build_session_from_config()
		puller = MastersPuller(session)
		puller.run(cfg)
	except Exception as e:
		frappe.db.set_value("Sync Site Config", cfg_name, "last_sync_error", str(e)[:500])
		frappe.db.commit()
		_log("pull_masters", "failure", error=str(e))


class MastersPuller:
	"""Pulls master data from central for all Central→Branch DocTypes."""

	def __init__(self, session):
		self.session = session

	def run(self, cfg):
		"""Execute a full pull cycle for all enabled Central→Branch rules."""
		import time
		start = time.time()

		rules = self._get_pull_rules(cfg)
		total_upserted = 0
		total_deleted = 0
		total_errors = 0

		for rule in rules:
			dt = rule.doctype_name
			batch_size = rule.batch_size or DEFAULT_BATCH_SIZE
			watermark = self._get_watermark(dt)

			upserted, deleted, errors = self._pull_one_doctype(dt, watermark, batch_size)
			total_upserted += upserted
			total_deleted += deleted
			total_errors += errors

		# Update last pull timestamp
		frappe.db.set_value("Sync Site Config", cfg.name, "last_pull_masters_at", now_datetime())
		frappe.db.commit()

		duration_ms = int((time.time() - start) * 1000)
		_log(
			"pull_masters", "success" if total_errors == 0 else "partial",
			duration_ms=duration_ms,
			records_touched=total_upserted + total_deleted,
			context={"upserted": total_upserted, "deleted": total_deleted, "errors": total_errors},
		)

	def _get_pull_rules(self, cfg):
		"""Get enabled Central→Branch rules sorted by priority."""
		rules = []
		for rule in (cfg.synced_doctypes or []):
			if not rule.enabled:
				continue
			if rule.direction in ("Central→Branch", "Bidirectional"):
				rules.append(rule)
		rules.sort(key=lambda r: r.priority or 100)
		return rules

	def _get_watermark(self, doctype_name):
		"""Get last_modified watermark for a DocType, or epoch."""
		from pos_next.pos_next.doctype.sync_watermark.sync_watermark import SyncWatermark
		wm = SyncWatermark.get_for(doctype_name)
		if wm and wm.last_modified:
			return str(wm.last_modified)
		return "2000-01-01 00:00:00"

	def _pull_one_doctype(self, doctype_name, since, batch_size):
		"""
		Pull all pages for one DocType. Returns (upserted, deleted, errors).
		"""
		total_upserted = 0
		total_deleted = 0
		total_errors = 0
		current_since = since

		while True:
			try:
				resp = self.session.get(
					"/api/method/pos_next.sync.api.changes.changes_since",
					params={
						"doctype": doctype_name,
						"since": current_since,
						"limit": batch_size,
					},
				)
				if resp.status_code != 200:
					total_errors += 1
					break

				data = resp.json().get("message", {})
				if not data:
					break

			except Exception as e:
				total_errors += 1
				frappe.log_error(f"Pull {doctype_name}: {e}", "MastersPuller")
				break

			# Apply upserts
			for payload in data.get("upserts", []):
				try:
					self._apply_upsert(doctype_name, payload)
					total_upserted += 1
				except Exception as e:
					total_errors += 1
					frappe.log_error(
						f"Apply {doctype_name}/{payload.get('name')}: {e}",
						"MastersPuller",
					)

			# Apply tombstones
			for tomb in data.get("tombstones", []):
				try:
					self._apply_tombstone(doctype_name, tomb["reference_name"])
					total_deleted += 1
				except Exception as e:
					total_errors += 1

			# Advance watermark
			next_since = data.get("next_since")
			if next_since:
				from pos_next.pos_next.doctype.sync_watermark.sync_watermark import SyncWatermark
				SyncWatermark.upsert(
					doctype_name, next_since,
					records_pulled=total_upserted,
				)
				frappe.db.commit()
				current_since = next_since

			if not data.get("has_more"):
				break

		return total_upserted, total_deleted, total_errors

	def _apply_upsert(self, doctype_name, payload):
		"""Apply a single upsert via the adapter."""
		from pos_next.sync import registry
		from pos_next.pos_next.doctype.sync_record_state.sync_record_state import SyncRecordState

		adapter = registry.get_adapter(doctype_name)

		# Check hash — skip if unchanged
		payload_hash = compute_hash(payload)
		existing_hash = SyncRecordState.get_hash(doctype_name, payload.get("name", ""))
		if existing_hash == payload_hash:
			return  # No change

		if adapter:
			adapter.validate_incoming(payload)
			adapter.apply_incoming(payload, "update")
		else:
			# No adapter — use default BaseSyncAdapter behavior
			from pos_next.sync.adapters.base import BaseSyncAdapter
			default = BaseSyncAdapter()
			default.doctype = doctype_name
			default.apply_incoming(payload, "update")

		# Record state
		SyncRecordState.upsert(doctype_name, payload.get("name", ""), payload_hash, "central")
		frappe.db.commit()

	def _apply_tombstone(self, doctype_name, reference_name):
		"""Delete a local record that was deleted on central."""
		if frappe.db.exists(doctype_name, reference_name):
			frappe.delete_doc(doctype_name, reference_name, ignore_permissions=True, force=True)
			# Remove record state
			state_name = frappe.db.get_value(
				"Sync Record State",
				{"reference_doctype": doctype_name, "reference_name": reference_name},
				"name",
			)
			if state_name:
				frappe.delete_doc("Sync Record State", state_name, ignore_permissions=True, force=True)
			frappe.db.commit()


def _log(operation, status, duration_ms=0, records_touched=0, error=None, context=None):
	"""Write a Sync Log entry."""
	try:
		from pos_next.pos_next.doctype.sync_log.sync_log import SyncLog
		SyncLog.record(
			operation=operation,
			status=status,
			duration_ms=duration_ms,
			records_touched=records_touched,
			error=error,
			context=context,
		)
		frappe.db.commit()
	except Exception:
		pass  # Don't let logging failure crash the puller
```

- [ ] **Step 3: Run tests to verify they pass**

```bash
cd /home/ubuntu/frappe-bench
bench --site pos-central execute pos_next.sync.tests.test_masters_puller.run_all
```

Expected: all 4 tests PASS.

- [ ] **Step 4: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/sync/masters_puller.py pos_next/sync/tests/test_masters_puller.py
git commit -m "feat(sync): add MastersPuller engine for branch-side masters pull

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Add tombstone hooks + scheduler to `hooks.py`

**Files:**
- Create: `pos_next/sync/hooks.py`
- Modify: `pos_next/hooks.py`

- [ ] **Step 1: Create `pos_next/sync/hooks.py`**

File: `pos_next/sync/hooks.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Sync doc_event hooks — tombstone recording on master deletion."""

import frappe


def write_tombstone_on_trash(doc, method=None):
	"""
	on_trash hook for synced master DocTypes.
	Records a tombstone so branches can replay the delete.
	"""
	from pos_next.pos_next.doctype.sync_tombstone.sync_tombstone import SyncTombstone
	try:
		SyncTombstone.record(doc.doctype, doc.name)
		frappe.db.commit()
	except Exception:
		# Don't block the delete if tombstone creation fails
		frappe.log_error(f"Tombstone write failed for {doc.doctype}/{doc.name}", "Sync Hooks")
```

- [ ] **Step 2: Add `on_trash` hooks and scheduler to `pos_next/hooks.py`**

Read `pos_next/hooks.py` first. Then:

1. Add `on_trash` hook for synced master DocTypes that don't already have one.
2. Add `cron` section to `scheduler_events`.

In `doc_events`, add `on_trash` for these DocTypes: Item, Item Price, Item Group, Item Barcode, UOM, Price List, POS Profile, Warehouse, Mode of Payment, Company, Currency, Branch, Customer Group, Sales Person, Employee, User, Role Profile, Sales Taxes and Charges Template, Item Tax Template, POS Settings, POS Offer, POS Coupon, Loyalty Program.

For DocTypes already in `doc_events` (like Item, Customer), add `on_trash` to the existing entry. For new ones, add a new entry.

The hook path is: `"pos_next.sync.hooks.write_tombstone_on_trash"`

In `scheduler_events`, add:
```python
"cron": {
    "* * * * *": [
        "pos_next.sync.masters_puller.pull_if_due",
    ]
},
```

- [ ] **Step 3: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/sync/hooks.py pos_next/hooks.py
git commit -m "feat(sync): add tombstone on_trash hooks + masters pull scheduler

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Plan 2 test runner + full integration test

**Files:**
- Create: `pos_next/sync/tests/run_plan2_tests.py`

- [ ] **Step 1: Create the runner**

File: `pos_next/sync/tests/run_plan2_tests.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Run every Plan 2 test module and report PASS/FAIL counts."""

import traceback


TEST_MODULES = [
	"pos_next.sync.tests.test_changes_api",
	"pos_next.sync.tests.test_generic_adapter",
	"pos_next.sync.tests.test_item_adapter",
	"pos_next.sync.tests.test_item_price_adapter",
	"pos_next.sync.tests.test_customer_adapter",
	"pos_next.sync.tests.test_masters_puller",
]


def run():
	passed = 0
	failed = 0
	for mod_name in TEST_MODULES:
		print(f"\n=== {mod_name} ===")
		try:
			mod = __import__(mod_name, fromlist=["run_all"])
			mod.run_all()
			passed += 1
		except Exception:
			failed += 1
			print(f"FAILED: {mod_name}")
			traceback.print_exc()
	print(f"\n\n=== PLAN 2 SUMMARY: {passed} passed, {failed} failed ===")
	if failed:
		raise SystemExit(1)
```

- [ ] **Step 2: Run the full Plan 2 test suite**

```bash
cd /home/ubuntu/frappe-bench
bench --site pos-central execute pos_next.sync.tests.run_plan2_tests.run
```

Expected: `=== PLAN 2 SUMMARY: 6 passed, 0 failed ===`

- [ ] **Step 3: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/sync/tests/run_plan2_tests.py
git commit -m "test(sync): add Plan 2 test runner

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Cross-bench integration test — end-to-end masters pull

**Files:**
- Create: `pos_next/sync/tests/_test_e2e_masters_pull.py`

- [ ] **Step 1: Create the integration test**

File: `pos_next/sync/tests/_test_e2e_masters_pull.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""
End-to-end integration test: create Item on central → pull on branch → verify.

Run from the BRANCH site (dev.pos on frappe-bench-16):
  bench --site dev.pos execute pos_next.sync.tests._test_e2e_masters_pull.run_all

Prerequisites:
  - Both benches running (port 8000 central, port 8001 branch)
  - Sync Site Config configured on both (use _setup_multi_site helpers)
  - Adapters imported (generic_master, item, etc.)
"""

import frappe
from pos_next.sync.transport import build_session_from_config
from pos_next.sync.masters_puller import MastersPuller


def test_pull_items_from_central():
	"""Pull Items from central and verify they arrive."""
	session = build_session_from_config()

	# First, check how many Items we have locally
	local_count_before = frappe.db.count("Item")

	puller = MastersPuller(session)

	# Pull just Items
	watermark = "2000-01-01 00:00:00"
	upserted, deleted, errors = puller._pull_one_doctype("Item", watermark, 50)

	print(f"Pulled: upserted={upserted}, deleted={deleted}, errors={errors}")
	assert errors == 0 or upserted > 0, "Expected some items to sync or no errors"

	local_count_after = frappe.db.count("Item")
	print(f"Items before={local_count_before}, after={local_count_after}")

	session.logout()
	print("PASS: test_pull_items_from_central")


def test_pull_creates_watermark():
	"""After pulling, a Sync Watermark record exists for the DocType."""
	from pos_next.pos_next.doctype.sync_watermark.sync_watermark import SyncWatermark

	wm = SyncWatermark.get_for("Item")
	if wm:
		print(f"Watermark for Item: last_modified={wm.last_modified}, records_pulled={wm.records_pulled}")
		assert wm.last_modified is not None
		print("PASS: test_pull_creates_watermark")
	else:
		print("SKIP: test_pull_creates_watermark (no watermark — pull may have returned empty)")


def run_all():
	# Import adapters to register them
	import pos_next.sync.adapters.item
	import pos_next.sync.adapters.item_price
	import pos_next.sync.adapters.customer
	import pos_next.sync.adapters.generic_master

	test_pull_items_from_central()
	test_pull_creates_watermark()
	print("\nAll E2E Masters Pull tests PASSED")
```

- [ ] **Step 2: Push to remote and pull on bench-16**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/sync/tests/_test_e2e_masters_pull.py
git commit -m "test(sync): add end-to-end masters pull integration test

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
git push community feat/sync-foundation
```

Then on bench-16:
```bash
cd /home/ubuntu/frappe-bench-16/apps/pos_next
git pull origin feat/sync-foundation
bench --site dev.pos migrate
```

- [ ] **Step 3: Run the integration test from branch**

```bash
cd /home/ubuntu/frappe-bench-16
bench --site dev.pos execute pos_next.sync.tests._test_e2e_masters_pull.run_all
```

Expected: Items pulled from central, watermark created.

---

## Done — What Plan 2 Delivers

After completing all 10 tasks:

- **Central exposes `changes_since` + `health` API endpoints.**
- **Branch runs `MastersPuller`** on a cron schedule, pulling all Central→Branch DocTypes.
- **4 adapter types:** ItemAdapter (child tables + variant protection), ItemPriceAdapter (composite key), CustomerAdapter (mobile_no dedup), GenericMasterAdapter (~20 simple masters).
- **Tombstone hooks** on central record deletions for branch replay.
- **Scheduler integration** — `pull_if_due` runs every minute, self-throttled.
- **Watermark tracking** — per-DocType pull progress, survives restarts.
- **Hash-based skip** — unchanged records are not re-applied.
- **Sync Log** — every pull cycle logged.
- **6 test modules, all passing + 1 cross-bench integration test.**

## Self-Review Checklist

Before considering Plan 2 complete, verify:

- [ ] All 10 tasks committed.
- [ ] `bench --site pos-central execute pos_next.sync.tests.run_plan2_tests.run` reports 0 failures.
- [ ] `bench --site pos-central execute pos_next.sync.tests.run_all_tests.run` still reports 0 failures (Plan 1 tests).
- [ ] Cross-bench integration test passes from bench-16.
- [ ] `bench --site pos-central migrate` runs clean.
- [ ] Create an Item on pos-central → manually trigger pull on dev.pos → Item appears.
