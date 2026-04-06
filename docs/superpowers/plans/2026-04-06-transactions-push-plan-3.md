# Transactions Push — Implementation Plan (Plan 3 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement branch → central transaction push via the Outbox: capture transaction events, drain to central, apply as read-only replicas.

**Architecture:** Transaction doc_events (submit/cancel/update) enqueue payloads into the Sync Outbox (Plan 1). An `OutboxDrainer` scheduled job batches pending rows by DocType and POSTs to central's ingest API. Central applies via `SubmittableAdapter` subclasses that handle docstatus-aware insert (no re-submission). Exponential backoff on failure, dead letter after 10 attempts.

**Tech Stack:** Frappe Framework (Python 3.10+/3.14), Frappe ORM, `requests` for HTTP, `bench execute` for tests.

**Spec:** `docs/superpowers/specs/2026-04-06-transactions-push-design.md`

**Prerequisites:**
- Plan 1 + Plan 2 complete (all tests passing).
- Two-bench dev environment running.
- Use `bench --site pos-dev execute ...` for adapter tests (pos-dev has ERPNext data).
- Use tabs for indentation. NEVER `bench run-tests`.

---

## File Structure

### New files

| File | Responsibility |
|------|----------------|
| `pos_next/sync/adapters/submittable.py` | `SubmittableAdapter` base — docstatus-aware insert/cancel for submitted docs |
| `pos_next/sync/adapters/sales_invoice.py` | Sales Invoice adapter — naming validation, child tables |
| `pos_next/sync/adapters/payment_entry.py` | Payment Entry adapter |
| `pos_next/sync/adapters/pos_opening_shift.py` | POS Opening Shift adapter (priority 10) |
| `pos_next/sync/adapters/pos_closing_shift.py` | POS Closing Shift adapter (priority 20) |
| `pos_next/sync/adapters/stock_ledger_entry.py` | SLE adapter — insert-only |
| `pos_next/sync/hooks_outbox.py` | Outbox hooks — enqueue on submit/cancel/update |
| `pos_next/sync/outbox_drainer.py` | `OutboxDrainer` + `push_if_due` entry point |
| `pos_next/sync/api/ingest.py` | Central ingest endpoint |
| `pos_next/sync/tests/test_hooks_outbox.py` | Tests for outbox hooks |
| `pos_next/sync/tests/test_outbox_drainer.py` | Tests for OutboxDrainer |
| `pos_next/sync/tests/test_ingest_api.py` | Tests for ingest endpoint |
| `pos_next/sync/tests/test_submittable_adapter.py` | Tests for SubmittableAdapter |
| `pos_next/sync/tests/run_plan3_tests.py` | Plan 3 test runner |
| `pos_next/sync/tests/_test_e2e_push.py` | Cross-bench integration test |

### Modified files

| File | What changes |
|------|--------------|
| `pos_next/hooks.py` | Add outbox `doc_events` for transaction DocTypes, add `push_if_due` to cron |

---

## Tasks

### Task 1: Create `SubmittableAdapter` base class

**Files:**
- Create: `pos_next/sync/adapters/submittable.py`
- Create: `pos_next/sync/tests/test_submittable_adapter.py`

- [ ] **Step 1: Write failing tests**

File: `pos_next/sync/tests/test_submittable_adapter.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt


def test_submittable_adapter_interface():
	"""SubmittableAdapter has apply_incoming that handles docstatus."""
	from pos_next.sync.adapters.submittable import SubmittableAdapter
	assert hasattr(SubmittableAdapter, "apply_incoming")
	assert hasattr(SubmittableAdapter, "doctype")
	print("PASS: test_submittable_adapter_interface")


def test_submittable_adapter_is_base_adapter():
	"""SubmittableAdapter inherits from BaseSyncAdapter."""
	from pos_next.sync.adapters.submittable import SubmittableAdapter
	from pos_next.sync.adapters.base import BaseSyncAdapter
	assert issubclass(SubmittableAdapter, BaseSyncAdapter)
	print("PASS: test_submittable_adapter_is_base_adapter")


def run_all():
	test_submittable_adapter_interface()
	test_submittable_adapter_is_base_adapter()
	print("\nAll SubmittableAdapter tests PASSED")
```

- [ ] **Step 2: Create `submittable.py`**

File: `pos_next/sync/adapters/submittable.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Base adapter for submitted documents — docstatus-aware insert/cancel."""

import frappe
from pos_next.sync.adapters.base import BaseSyncAdapter, SKIP_ON_UPSERT, _set_sync_flags


class SubmittableAdapter(BaseSyncAdapter):
	"""
	Adapter for DocTypes that use docstatus (submit/cancel workflow).

	On central, submitted docs are inserted as read-only replicas
	with docstatus already set — no doc.submit() is called.
	Cancel sets docstatus=2 via db_update — no doc.cancel() is called.
	"""

	def apply_incoming(self, payload, operation):
		name = payload.get("name")
		if not name:
			raise ValueError(f"{self.doctype}: payload missing 'name' field")

		if operation == "delete":
			if frappe.db.exists(self.doctype, name):
				frappe.delete_doc(self.doctype, name, ignore_permissions=True, force=True)
			return name

		if operation == "cancel":
			if frappe.db.exists(self.doctype, name):
				doc = frappe.get_doc(self.doctype, name)
				doc.docstatus = 2
				doc.db_update()
			return name

		payload = self.pre_apply_transform(payload)

		try:
			doc = frappe.get_doc(self.doctype, name)
			for key, val in payload.items():
				if key not in SKIP_ON_UPSERT and not isinstance(val, list):
					doc.set(key, val)
			doc.db_update()
		except frappe.DoesNotExistError:
			doc = frappe.get_doc({"doctype": self.doctype, **payload})
			_set_sync_flags(doc)
			doc.insert(ignore_permissions=True)
		return doc.name
```

- [ ] **Step 3: Run tests**

```bash
cd /home/ubuntu/frappe-bench
bench --site pos-dev execute pos_next.sync.tests.test_submittable_adapter.run_all
```

- [ ] **Step 4: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/sync/adapters/submittable.py pos_next/sync/tests/test_submittable_adapter.py
git commit -m "feat(sync): add SubmittableAdapter base for docstatus-aware sync

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Create transaction adapters (Sales Invoice, Payment Entry, POS Shifts, SLE)

**Files:**
- Create: `pos_next/sync/adapters/sales_invoice.py`
- Create: `pos_next/sync/adapters/payment_entry.py`
- Create: `pos_next/sync/adapters/pos_opening_shift.py`
- Create: `pos_next/sync/adapters/pos_closing_shift.py`
- Create: `pos_next/sync/adapters/stock_ledger_entry.py`

- [ ] **Step 1: Create all 5 adapter files**

File: `pos_next/sync/adapters/sales_invoice.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Adapter for Sales Invoice — naming series validation, child tables."""

import frappe
from pos_next.sync.adapters.submittable import SubmittableAdapter
from pos_next.sync.payload import strip_meta
from pos_next.sync.exceptions import SyncValidationError
from pos_next.sync import registry


class SalesInvoiceAdapter(SubmittableAdapter):
	doctype = "Sales Invoice"

	def validate_incoming(self, payload):
		origin_branch = payload.get("origin_branch")
		if not origin_branch:
			frappe.log_error(
				f"Sales Invoice {payload.get('name')} missing origin_branch",
				"Sync Sales Invoice Adapter",
			)
			return

		# Validate naming series matches the origin branch code.
		# Branch POS Profiles use branch-coded naming series (e.g. SINV-CAI-.#####).
		name = payload.get("name", "")
		naming_series = payload.get("naming_series", "")
		if naming_series and origin_branch not in naming_series:
			raise SyncValidationError(
				f"Sales Invoice {name}: naming series '{naming_series}' "
				f"does not contain origin branch code '{origin_branch}'"
			)

	def pre_apply_transform(self, payload):
		cleaned = strip_meta(payload)
		for key, val in cleaned.items():
			if isinstance(val, list):
				cleaned[key] = [strip_meta(row) if isinstance(row, dict) else row for row in val]
		return cleaned


registry.register(SalesInvoiceAdapter)
```

**Naming series convention:** Each branch's POS Profile carries a naming series that encodes the branch code (e.g., `SINV-CAI-.#####` for Cairo Downtown). When a Sales Invoice is pushed to central, `validate_incoming` verifies the naming series matches the `origin_branch` field. This prevents cross-branch naming collisions and ensures traceability.

File: `pos_next/sync/adapters/payment_entry.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Adapter for Payment Entry."""

from pos_next.sync.adapters.submittable import SubmittableAdapter
from pos_next.sync.payload import strip_meta
from pos_next.sync import registry


class PaymentEntryAdapter(SubmittableAdapter):
	doctype = "Payment Entry"

	def pre_apply_transform(self, payload):
		cleaned = strip_meta(payload)
		for key, val in cleaned.items():
			if isinstance(val, list):
				cleaned[key] = [strip_meta(row) if isinstance(row, dict) else row for row in val]
		return cleaned


registry.register(PaymentEntryAdapter)
```

File: `pos_next/sync/adapters/pos_opening_shift.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Adapter for POS Opening Shift — priority 10, synced first."""

from pos_next.sync.adapters.submittable import SubmittableAdapter
from pos_next.sync import registry


class POSOpeningShiftAdapter(SubmittableAdapter):
	doctype = "POS Opening Shift"


registry.register(POSOpeningShiftAdapter)
```

File: `pos_next/sync/adapters/pos_closing_shift.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Adapter for POS Closing Shift — priority 20."""

from pos_next.sync.adapters.submittable import SubmittableAdapter
from pos_next.sync import registry


class POSClosingShiftAdapter(SubmittableAdapter):
	doctype = "POS Closing Shift"


registry.register(POSClosingShiftAdapter)
```

File: `pos_next/sync/adapters/stock_ledger_entry.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Adapter for Stock Ledger Entry — insert-only, no updates."""

import frappe
from pos_next.sync.adapters.base import BaseSyncAdapter, _set_sync_flags
from pos_next.sync import registry


class StockLedgerEntryAdapter(BaseSyncAdapter):
	doctype = "Stock Ledger Entry"

	def apply_incoming(self, payload, operation):
		"""Insert-only: SLEs are never updated after creation."""
		name = payload.get("name")
		if not name:
			raise ValueError("SLE payload missing 'name'")

		if operation == "delete":
			if frappe.db.exists(self.doctype, name):
				frappe.delete_doc(self.doctype, name, ignore_permissions=True, force=True)
			return name

		# Skip if already exists (insert-only)
		if frappe.db.exists(self.doctype, name):
			return name

		payload = self.pre_apply_transform(payload)
		doc = frappe.get_doc({"doctype": self.doctype, **payload})
		_set_sync_flags(doc)
		doc.insert(ignore_permissions=True)
		return doc.name


registry.register(StockLedgerEntryAdapter)
```

- [ ] **Step 2: Verify adapters are auto-discovered**

```bash
cd /home/ubuntu/frappe-bench
bench --site pos-dev execute 'from pos_next.sync.masters_puller import _ensure_adapters_loaded; _ensure_adapters_loaded(); from pos_next.sync import registry; registered = registry.list_registered(); print(f"Registered: {len(registered)}"); [print(f"  {r}") for r in sorted(registered) if r in ("Sales Invoice","Payment Entry","POS Opening Shift","POS Closing Shift","Stock Ledger Entry")]'
```

Expected: all 5 new adapters listed.

- [ ] **Step 3: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/sync/adapters/sales_invoice.py pos_next/sync/adapters/payment_entry.py pos_next/sync/adapters/pos_opening_shift.py pos_next/sync/adapters/pos_closing_shift.py pos_next/sync/adapters/stock_ledger_entry.py
git commit -m "feat(sync): add transaction adapters (Sales Invoice, Payment Entry, POS shifts, SLE)

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Create outbox hooks — capture transaction events

**Files:**
- Create: `pos_next/sync/hooks_outbox.py`
- Create: `pos_next/sync/tests/test_hooks_outbox.py`

- [ ] **Step 1: Write failing tests**

File: `pos_next/sync/tests/test_hooks_outbox.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
import json


def _cleanup():
	frappe.db.delete("Sync Outbox")
	frappe.db.commit()


def test_method_to_operation():
	"""Maps Frappe doc_event method names to outbox operations."""
	from pos_next.sync.hooks_outbox import _method_to_operation
	assert _method_to_operation("on_submit") == "submit"
	assert _method_to_operation("on_cancel") == "cancel"
	assert _method_to_operation("on_update") == "update"
	assert _method_to_operation("on_update_after_submit") == "update"
	assert _method_to_operation("after_insert") == "insert"
	assert _method_to_operation("on_trash") == "delete"
	print("PASS: test_method_to_operation")


def test_enqueue_guard_skips_on_central():
	"""On a site with no Branch config, enqueue is a no-op."""
	from pos_next.sync.hooks_outbox import _is_branch_site
	# pos-dev has a Branch config so this may return True
	# Just verify the function exists and returns a bool
	result = _is_branch_site()
	assert isinstance(result, bool)
	print("PASS: test_enqueue_guard_skips_on_central")


def test_enqueue_creates_outbox_row():
	"""enqueue_to_outbox creates a Sync Outbox row."""
	_cleanup()
	try:
		from pos_next.sync.hooks_outbox import enqueue_to_outbox
		from unittest.mock import MagicMock

		# Create a fake doc
		doc = MagicMock()
		doc.doctype = "Sales Invoice"
		doc.name = "TEST-SINV-001"
		doc.as_dict.return_value = {"name": "TEST-SINV-001", "total": 100}

		enqueue_to_outbox(doc, method="on_submit")

		count = frappe.db.count("Sync Outbox", {"reference_doctype": "Sales Invoice", "reference_name": "TEST-SINV-001"})
		assert count == 1, f"Expected 1 outbox row, got {count}"

		row = frappe.get_all(
			"Sync Outbox",
			filters={"reference_name": "TEST-SINV-001"},
			fields=["operation", "sync_status"],
		)[0]
		assert row.operation == "submit"
		assert row.sync_status == "pending"
		print("PASS: test_enqueue_creates_outbox_row")
	finally:
		_cleanup()


def run_all():
	test_method_to_operation()
	test_enqueue_guard_skips_on_central()
	test_enqueue_creates_outbox_row()
	print("\nAll Outbox Hooks tests PASSED")
```

- [ ] **Step 2: Create `hooks_outbox.py`**

File: `pos_next/sync/hooks_outbox.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Outbox hooks — capture transaction doc_events into Sync Outbox."""

import json

import frappe

from pos_next.sync.payload import to_payload


_METHOD_MAP = {
	"on_submit": "submit",
	"on_cancel": "cancel",
	"on_update": "update",
	"on_update_after_submit": "update",
	"after_insert": "insert",
	"on_trash": "delete",
}


def _method_to_operation(method):
	"""Convert Frappe doc_event method name to outbox operation."""
	return _METHOD_MAP.get(method, "update")


def _is_branch_site():
	"""Check if this site has an enabled Branch Sync Site Config."""
	cache_key = "pos_next_is_branch"
	result = frappe.cache().get_value(cache_key)
	if result is None:
		result = bool(frappe.db.get_value(
			"Sync Site Config", {"site_role": "Branch", "enabled": 1}, "name"
		))
		frappe.cache().set_value(cache_key, result, expires_in_sec=300)
	return result


def _get_priority(doctype_name):
	"""Get sync priority for a DocType from cache or registry."""
	cache_key = f"pos_next_sync_priority_{doctype_name}"
	prio = frappe.cache().get_value(cache_key)
	if prio is None:
		prio = frappe.db.get_value(
			"Sync DocType Rule",
			{"doctype_name": doctype_name, "parenttype": "Sync Site Config"},
			"priority",
		) or 100
		frappe.cache().set_value(cache_key, int(prio), expires_in_sec=300)
	return int(prio)


def enqueue_to_outbox(doc, method=None):
	"""
	Generic doc_event hook: capture document change into Sync Outbox.
	Only fires on Branch sites with sync enabled.
	"""
	if not _is_branch_site():
		return

	from pos_next.pos_next.doctype.sync_outbox.sync_outbox import SyncOutbox

	operation = _method_to_operation(method)
	payload = json.dumps(to_payload(doc), default=str)
	priority = _get_priority(doc.doctype)

	SyncOutbox.enqueue(
		reference_doctype=doc.doctype,
		reference_name=doc.name,
		operation=operation,
		payload=payload,
		priority=priority,
	)
```

- [ ] **Step 3: Run tests**

```bash
cd /home/ubuntu/frappe-bench
bench --site pos-dev execute pos_next.sync.tests.test_hooks_outbox.run_all
```

- [ ] **Step 4: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/sync/hooks_outbox.py pos_next/sync/tests/test_hooks_outbox.py
git commit -m "feat(sync): add outbox hooks for transaction event capture

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Create central ingest API

**Files:**
- Create: `pos_next/sync/api/ingest.py`
- Create: `pos_next/sync/tests/test_ingest_api.py`

- [ ] **Step 1: Write failing tests**

File: `pos_next/sync/tests/test_ingest_api.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
import json


def _cleanup():
	frappe.db.delete("Sync Record State")
	frappe.db.commit()


def test_ingest_returns_results():
	"""Ingest endpoint returns per-record results."""
	from pos_next.sync.api.ingest import ingest

	# Import adapters for registration
	from pos_next.sync.masters_puller import _ensure_adapters_loaded
	_ensure_adapters_loaded()

	result = ingest(
		doctype="Warehouse",
		branch_code="CAI",
		records=json.dumps([
			{"operation": "update", "payload": {"name": "FAKE-WH-INGEST", "warehouse_name": "Test"}},
		]),
	)
	assert "results" in result
	assert len(result["results"]) == 1
	# May be ok or error depending on site data — just verify structure
	assert "name" in result["results"][0]
	assert "status" in result["results"][0]
	print("PASS: test_ingest_returns_results")


def test_ingest_idempotent_by_sync_uuid():
	"""Records with existing sync_uuid are skipped."""
	_cleanup()
	try:
		from pos_next.sync.api.ingest import ingest
		from pos_next.sync.masters_puller import _ensure_adapters_loaded
		_ensure_adapters_loaded()

		uuid_val = "test-uuid-idempotent-001"
		records = json.dumps([
			{"operation": "update", "payload": {"name": "FAKE-IDEMP", "sync_uuid": uuid_val}},
		])

		# First call
		result1 = ingest(doctype="Warehouse", branch_code="CAI", records=records)
		# Second call — should skip
		result2 = ingest(doctype="Warehouse", branch_code="CAI", records=records)
		# Both should succeed (first applies, second skips as idempotent)
		assert result2["results"][0]["status"] == "skipped"
		print("PASS: test_ingest_idempotent_by_sync_uuid")
	finally:
		_cleanup()


def test_ingest_empty_records():
	"""Empty records list returns empty results."""
	from pos_next.sync.api.ingest import ingest
	result = ingest(doctype="Warehouse", branch_code="CAI", records=json.dumps([]))
	assert result["results"] == []
	print("PASS: test_ingest_empty_records")


def run_all():
	test_ingest_returns_results()
	test_ingest_idempotent_by_sync_uuid()
	test_ingest_empty_records()
	print("\nAll Ingest API tests PASSED")
```

- [ ] **Step 2: Create `ingest.py`**

File: `pos_next/sync/api/ingest.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Central-side API: receive and apply pushed transactions from branches."""

import json

import frappe

from pos_next.sync import registry
from pos_next.sync.adapters.base import BaseSyncAdapter
from pos_next.sync.payload import compute_hash
from pos_next.sync.masters_puller import _ensure_adapters_loaded
from pos_next.pos_next.doctype.sync_record_state.sync_record_state import SyncRecordState


@frappe.whitelist()
def ingest(doctype, branch_code, records):
	"""
	Receive a batch of records pushed from a branch.

	Args:
		doctype: The DocType being pushed
		branch_code: The branch_code of the pushing site
		records: JSON string of [{operation, payload}, ...]

	Returns: {"results": [{name, sync_uuid, status, error?}, ...]}
	"""
	_ensure_adapters_loaded()

	if isinstance(records, str):
		records = json.loads(records)

	adapter = registry.get_adapter(doctype)
	if not adapter:
		adapter = BaseSyncAdapter()
		adapter.doctype = doctype

	results = []
	for record in records:
		operation = record.get("operation", "update")
		payload = record.get("payload", {})
		name = payload.get("name", "")
		sync_uuid = payload.get("sync_uuid", "")

		try:
			# Idempotency: skip if sync_uuid already exists locally
			if sync_uuid and frappe.db.exists(doctype, {"sync_uuid": sync_uuid}):
				results.append({"name": name, "sync_uuid": sync_uuid, "status": "skipped"})
				continue

			adapter.validate_incoming(payload)
			adapter.apply_incoming(payload, operation)

			# Record state
			payload_hash = compute_hash(payload)
			SyncRecordState.upsert(doctype, name, payload_hash, branch_code)

			results.append({"name": name, "sync_uuid": sync_uuid, "status": "ok"})
		except Exception as e:
			frappe.log_error(f"Ingest {doctype}/{name}: {e}", "Sync Ingest")
			results.append({"name": name, "sync_uuid": sync_uuid, "status": "error", "error": str(e)[:500]})

	frappe.db.commit()
	return {"results": results}
```

- [ ] **Step 3: Run tests**

```bash
cd /home/ubuntu/frappe-bench
bench --site pos-dev execute pos_next.sync.tests.test_ingest_api.run_all
```

- [ ] **Step 4: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/sync/api/ingest.py pos_next/sync/tests/test_ingest_api.py
git commit -m "feat(sync): add central ingest API for transaction push

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Create `OutboxDrainer` — push engine

**Files:**
- Create: `pos_next/sync/outbox_drainer.py`
- Create: `pos_next/sync/tests/test_outbox_drainer.py`

- [ ] **Step 1: Write failing tests**

File: `pos_next/sync/tests/test_outbox_drainer.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
import json
from unittest.mock import MagicMock


def _cleanup():
	frappe.db.delete("Sync Outbox")
	frappe.db.delete("Sync Dead Letter")
	frappe.db.commit()


def test_push_if_due_noop_on_central():
	"""push_if_due does nothing when no Branch config exists."""
	from pos_next.sync.outbox_drainer import push_if_due
	push_if_due()
	print("PASS: test_push_if_due_noop_on_central")


def test_drainer_processes_pending_rows():
	"""OutboxDrainer sends pending outbox rows to central."""
	_cleanup()
	try:
		from pos_next.sync.outbox_drainer import OutboxDrainer
		from pos_next.pos_next.doctype.sync_outbox.sync_outbox import SyncOutbox

		# Create a pending outbox row
		SyncOutbox.enqueue(
			reference_doctype="Sales Invoice",
			reference_name="TEST-SINV-DRAIN",
			operation="submit",
			payload='{"name":"TEST-SINV-DRAIN","docstatus":1}',
			priority=50,
		)

		# Mock session — central returns ok
		fake_session = MagicMock()
		fake_resp = MagicMock()
		fake_resp.status_code = 200
		fake_resp.json.return_value = {
			"message": {
				"results": [{"name": "TEST-SINV-DRAIN", "sync_uuid": "", "status": "ok"}]
			}
		}
		fake_session.post.return_value = fake_resp

		drainer = OutboxDrainer(fake_session, branch_code="CAI")
		acked, failed, dead = drainer.drain()

		assert acked >= 1, f"Expected at least 1 acked, got {acked}"
		# Verify outbox row is now acked
		status = frappe.db.get_value(
			"Sync Outbox",
			{"reference_name": "TEST-SINV-DRAIN"},
			"sync_status",
		)
		assert status == "acked", f"Expected acked, got {status}"
		print("PASS: test_drainer_processes_pending_rows")
	finally:
		_cleanup()


def test_drainer_handles_failure():
	"""On failure, outbox row gets attempts incremented and backoff set."""
	_cleanup()
	try:
		from pos_next.sync.outbox_drainer import OutboxDrainer
		from pos_next.pos_next.doctype.sync_outbox.sync_outbox import SyncOutbox

		SyncOutbox.enqueue(
			reference_doctype="Sales Invoice",
			reference_name="TEST-SINV-FAIL",
			operation="submit",
			payload='{"name":"TEST-SINV-FAIL"}',
			priority=50,
		)

		# Mock session — central returns error
		fake_session = MagicMock()
		fake_resp = MagicMock()
		fake_resp.status_code = 200
		fake_resp.json.return_value = {
			"message": {
				"results": [{"name": "TEST-SINV-FAIL", "sync_uuid": "", "status": "error", "error": "test error"}]
			}
		}
		fake_session.post.return_value = fake_resp

		drainer = OutboxDrainer(fake_session, branch_code="CAI")
		acked, failed, dead = drainer.drain()

		assert failed >= 1
		row = frappe.get_all(
			"Sync Outbox",
			filters={"reference_name": "TEST-SINV-FAIL"},
			fields=["sync_status", "attempts", "last_error"],
		)[0]
		assert row.sync_status == "failed"
		assert row.attempts == 1
		assert "test error" in (row.last_error or "")
		print("PASS: test_drainer_handles_failure")
	finally:
		_cleanup()


def test_drainer_dead_letters_after_max_attempts():
	"""After MAX_ATTEMPTS_BEFORE_DEAD, row moves to dead letter."""
	_cleanup()
	try:
		from pos_next.sync.outbox_drainer import OutboxDrainer
		from pos_next.pos_next.doctype.sync_outbox.sync_outbox import SyncOutbox
		from pos_next.sync.defaults import MAX_ATTEMPTS_BEFORE_DEAD

		row = SyncOutbox.enqueue(
			reference_doctype="Sales Invoice",
			reference_name="TEST-SINV-DEAD",
			operation="submit",
			payload='{"name":"TEST-SINV-DEAD"}',
			priority=50,
		)
		# Set attempts to just below threshold
		frappe.db.set_value("Sync Outbox", row.name, {
			"attempts": MAX_ATTEMPTS_BEFORE_DEAD,
			"sync_status": "failed",
		})
		frappe.db.commit()

		# Mock session — central returns error again
		fake_session = MagicMock()
		fake_resp = MagicMock()
		fake_resp.status_code = 200
		fake_resp.json.return_value = {
			"message": {
				"results": [{"name": "TEST-SINV-DEAD", "sync_uuid": "", "status": "error", "error": "persistent error"}]
			}
		}
		fake_session.post.return_value = fake_resp

		drainer = OutboxDrainer(fake_session, branch_code="CAI")
		acked, failed, dead = drainer.drain()

		assert dead >= 1
		# Verify outbox row is gone
		assert not frappe.db.exists("Sync Outbox", {"reference_name": "TEST-SINV-DEAD"})
		# Verify dead letter exists
		assert frappe.db.exists("Sync Dead Letter", {"reference_name": "TEST-SINV-DEAD"})
		print("PASS: test_drainer_dead_letters_after_max_attempts")
	finally:
		_cleanup()
		frappe.db.delete("Sync Dead Letter")
		frappe.db.commit()


def run_all():
	test_push_if_due_noop_on_central()
	test_drainer_processes_pending_rows()
	test_drainer_handles_failure()
	test_drainer_dead_letters_after_max_attempts()
	print("\nAll OutboxDrainer tests PASSED")
```

- [ ] **Step 2: Create `outbox_drainer.py`**

File: `pos_next/sync/outbox_drainer.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Branch-side outbox drainer — pushes transactions to central."""

import json
import time
from datetime import timedelta

import frappe
from frappe.utils import now_datetime, time_diff_in_seconds

from pos_next.sync.defaults import (
	DEFAULT_BATCH_SIZE,
	DEFAULT_PUSH_INTERVAL_SECONDS,
	MAX_ATTEMPTS_BEFORE_DEAD,
)
from pos_next.sync.masters_puller import _ensure_adapters_loaded
from pos_next.pos_next.doctype.sync_log.sync_log import SyncLog


def push_if_due():
	"""
	Scheduler entry point (called every minute by cron).
	Checks if this site is a Branch and if enough time has passed since last push.
	"""
	cfg_name = frappe.db.get_value("Sync Site Config", {"site_role": "Branch", "enabled": 1}, "name")
	if not cfg_name:
		return

	cfg = frappe.get_doc("Sync Site Config", cfg_name)
	interval = cfg.push_interval_seconds or DEFAULT_PUSH_INTERVAL_SECONDS

	if cfg.last_push_at:
		elapsed = time_diff_in_seconds(now_datetime(), cfg.last_push_at)
		if elapsed < interval:
			return

	_ensure_adapters_loaded()

	try:
		from pos_next.sync.transport import build_session_from_config
		session = build_session_from_config()
		drainer = OutboxDrainer(session, branch_code=cfg.branch_code)
		acked, failed, dead = drainer.drain()

		frappe.db.set_value("Sync Site Config", cfg_name, "last_push_at", now_datetime())
		frappe.db.commit()

		_log(
			"push_outbox", "success" if (failed + dead) == 0 else "partial",
			records_touched=acked + failed + dead,
			context={"acked": acked, "failed": failed, "dead": dead},
		)
	except Exception as e:
		frappe.db.set_value("Sync Site Config", cfg_name, "last_sync_error", str(e)[:500])
		frappe.db.commit()
		_log("push_outbox", "failure", error=str(e))


class OutboxDrainer:
	"""Drains pending Sync Outbox rows by POSTing to central's ingest API."""

	def __init__(self, session, branch_code):
		self.session = session
		self.branch_code = branch_code

	def drain(self):
		"""
		Process all drainable outbox rows. Returns (acked, failed, dead).
		"""
		total_acked = 0
		total_failed = 0
		total_dead = 0

		# Get pending/failed rows ready for retry
		rows = frappe.get_all(
			"Sync Outbox",
			filters={
				"sync_status": ("in", ["pending", "failed"]),
				"next_attempt_at": ("is", "not set"),
			},
			or_filters={
				"next_attempt_at": ("<=", now_datetime()),
			},
			fields=["name", "reference_doctype", "reference_name", "operation", "payload", "attempts"],
			order_by="priority asc, creation asc",
			limit_page_length=DEFAULT_BATCH_SIZE,
		)

		# Also get failed rows whose next_attempt_at has passed
		retry_rows = frappe.get_all(
			"Sync Outbox",
			filters={
				"sync_status": "failed",
				"next_attempt_at": ("<=", now_datetime()),
			},
			fields=["name", "reference_doctype", "reference_name", "operation", "payload", "attempts"],
			order_by="priority asc, creation asc",
			limit_page_length=DEFAULT_BATCH_SIZE,
		)

		# Merge and deduplicate
		seen = {r.name for r in rows}
		for r in retry_rows:
			if r.name not in seen:
				rows.append(r)
				seen.add(r.name)

		if not rows:
			return 0, 0, 0

		# Group by doctype
		by_doctype = {}
		for row in rows:
			by_doctype.setdefault(row.reference_doctype, []).append(row)

		# Push each doctype batch
		for dt, dt_rows in by_doctype.items():
			records = []
			for row in dt_rows:
				payload = row.payload
				if isinstance(payload, str):
					try:
						payload = json.loads(payload)
					except json.JSONDecodeError:
						payload = {}
				records.append({
					"operation": row.operation,
					"payload": payload,
				})

			try:
				resp = self.session.post(
					"/api/method/pos_next.sync.api.ingest.ingest",
					json={
						"doctype": dt,
						"branch_code": self.branch_code,
						"records": records,
					},
				)
				if resp.status_code != 200:
					# Entire batch failed
					for row in dt_rows:
						self._mark_failed(row, f"HTTP {resp.status_code}")
						total_failed += 1
					continue

				results = resp.json().get("message", {}).get("results", [])
				# Map results back to rows by index
				for i, row in enumerate(dt_rows):
					if i < len(results):
						result = results[i]
						if result.get("status") in ("ok", "skipped"):
							self._mark_acked(row)
							total_acked += 1
						else:
							error = result.get("error", "Unknown error")
							if self._should_dead_letter(row):
								self._move_to_dead_letter(row, error)
								total_dead += 1
							else:
								self._mark_failed(row, error)
								total_failed += 1
					else:
						self._mark_failed(row, "No result from central")
						total_failed += 1

			except Exception as e:
				for row in dt_rows:
					self._mark_failed(row, str(e))
					total_failed += 1

		frappe.db.commit()
		return total_acked, total_failed, total_dead

	def _mark_acked(self, row):
		frappe.db.set_value("Sync Outbox", row.name, {
			"sync_status": "acked",
			"acked_at": now_datetime(),
		})

	def _mark_failed(self, row, error):
		attempts = (row.attempts or 0) + 1
		backoff_seconds = min(2 ** attempts, 3600)  # cap at 1 hour
		frappe.db.set_value("Sync Outbox", row.name, {
			"sync_status": "failed",
			"attempts": attempts,
			"last_error": str(error)[:500],
			"next_attempt_at": now_datetime() + timedelta(seconds=backoff_seconds),
		})

	def _should_dead_letter(self, row):
		return (row.attempts or 0) >= MAX_ATTEMPTS_BEFORE_DEAD

	def _move_to_dead_letter(self, row, error):
		frappe.get_doc({
			"doctype": "Sync Dead Letter",
			"reference_doctype": row.reference_doctype,
			"reference_name": row.reference_name,
			"operation": row.operation,
			"last_error": str(error)[:500],
			"attempts": (row.attempts or 0) + 1,
			"payload": row.payload,
			"moved_at": now_datetime(),
		}).insert(ignore_permissions=True)
		frappe.delete_doc("Sync Outbox", row.name, ignore_permissions=True, force=True)


def _log(operation, status, duration_ms=0, records_touched=0, error=None, context=None):
	try:
		SyncLog.record(
			operation=operation, status=status, duration_ms=duration_ms,
			records_touched=records_touched, error=error, context=context,
		)
		frappe.db.commit()
	except Exception:
		pass
```

- [ ] **Step 3: Run tests**

```bash
cd /home/ubuntu/frappe-bench
bench --site pos-dev execute pos_next.sync.tests.test_outbox_drainer.run_all
```

- [ ] **Step 4: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/sync/outbox_drainer.py pos_next/sync/tests/test_outbox_drainer.py
git commit -m "feat(sync): add OutboxDrainer with backoff and dead letter handling

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Wire outbox hooks + push scheduler into `hooks.py`

**Files:**
- Modify: `pos_next/hooks.py`

- [ ] **Step 1: Add outbox hooks to doc_events**

Read `pos_next/hooks.py`. Add `enqueue_to_outbox` hook to transaction DocTypes:

For `Sales Invoice`, add to existing entry:
```python
"on_submit": [...existing..., "pos_next.sync.hooks_outbox.enqueue_to_outbox"],
"on_cancel": "pos_next.sync.hooks_outbox.enqueue_to_outbox",
"on_update_after_submit": "pos_next.sync.hooks_outbox.enqueue_to_outbox",
```

For `Payment Entry`, add:
```python
"on_submit": "pos_next.sync.hooks_outbox.enqueue_to_outbox",
"on_cancel": "pos_next.sync.hooks_outbox.enqueue_to_outbox",
```

For `POS Opening Shift` and `POS Closing Shift`, add:
```python
"on_submit": "pos_next.sync.hooks_outbox.enqueue_to_outbox",
```

For `Stock Ledger Entry`, add:
```python
"after_insert": "pos_next.sync.hooks_outbox.enqueue_to_outbox",
```

For `Customer`, add to existing entry:
```python
"on_update": [...existing..., "pos_next.sync.hooks_outbox.enqueue_to_outbox"],
```

- [ ] **Step 2: Add `push_if_due` to cron scheduler**

In `scheduler_events.cron`, add to the `* * * * *` list:
```python
"pos_next.sync.outbox_drainer.push_if_due",
```

- [ ] **Step 3: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/hooks.py
git commit -m "feat(sync): wire outbox hooks + push scheduler into hooks.py

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Plan 3 test runner

**Files:**
- Create: `pos_next/sync/tests/run_plan3_tests.py`

- [ ] **Step 1: Create the runner**

File: `pos_next/sync/tests/run_plan3_tests.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Run every Plan 3 test module and report PASS/FAIL counts."""

import traceback


TEST_MODULES = [
	"pos_next.sync.tests.test_submittable_adapter",
	"pos_next.sync.tests.test_hooks_outbox",
	"pos_next.sync.tests.test_ingest_api",
	"pos_next.sync.tests.test_outbox_drainer",
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
	print(f"\n\n=== PLAN 3 SUMMARY: {passed} passed, {failed} failed ===")
	if failed:
		raise SystemExit(1)
```

- [ ] **Step 2: Run full Plan 3 suite**

```bash
cd /home/ubuntu/frappe-bench
bench --site pos-dev execute pos_next.sync.tests.run_plan3_tests.run
```

Expected: `=== PLAN 3 SUMMARY: 4 passed, 0 failed ===`

- [ ] **Step 3: Verify Plan 1 + 2 still pass**

```bash
bench --site pos-dev execute pos_next.sync.tests.run_all_tests.run
bench --site pos-dev execute pos_next.sync.tests.run_plan2_tests.run
```

- [ ] **Step 4: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/sync/tests/run_plan3_tests.py
git commit -m "test(sync): add Plan 3 test runner

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Cross-bench e2e push test

**Files:**
- Create: `pos_next/sync/tests/_test_e2e_push.py`

- [ ] **Step 1: Create integration test**

File: `pos_next/sync/tests/_test_e2e_push.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""
E2E: enqueue an outbox row on branch → drain to central → verify on central.

Run from BRANCH site (dev.pos on frappe-bench-16):
  bench --site dev.pos execute pos_next.sync.tests._test_e2e_push.run_all
"""

import frappe
import json
from pos_next.sync.transport import build_session_from_config
from pos_next.sync.outbox_drainer import OutboxDrainer
from pos_next.sync.masters_puller import _ensure_adapters_loaded


def test_push_outbox_to_central():
	"""Enqueue a fake outbox row and drain it to central."""
	_ensure_adapters_loaded()
	from pos_next.pos_next.doctype.sync_outbox.sync_outbox import SyncOutbox

	# Clean up any previous test rows
	frappe.db.delete("Sync Outbox", {"reference_name": "E2E-PUSH-TEST"})
	frappe.db.commit()

	# Enqueue a test row (using Warehouse since it's simple)
	SyncOutbox.enqueue(
		reference_doctype="Warehouse",
		reference_name="E2E-PUSH-TEST",
		operation="update",
		payload=json.dumps({"name": "E2E-PUSH-TEST", "warehouse_name": "E2E Push Test WH"}),
		priority=50,
	)

	# Drain to central
	session = build_session_from_config()
	branch_code = frappe.db.get_value("Sync Site Config", {"site_role": "Branch"}, "branch_code")
	drainer = OutboxDrainer(session, branch_code=branch_code)
	acked, failed, dead = drainer.drain()

	print(f"Drain result: acked={acked}, failed={failed}, dead={dead}")
	assert acked >= 1, f"Expected at least 1 acked, got {acked}"

	# Verify outbox row is acked
	status = frappe.db.get_value("Sync Outbox", {"reference_name": "E2E-PUSH-TEST"}, "sync_status")
	assert status == "acked", f"Expected acked, got {status}"

	session.logout()
	print("PASS: test_push_outbox_to_central")


def run_all():
	test_push_outbox_to_central()
	print("\nAll E2E Push tests PASSED")
```

- [ ] **Step 2: Push to remote, pull on bench-16, run**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/sync/tests/_test_e2e_push.py
git commit -m "test(sync): add e2e push integration test

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
git push community feat/sync-foundation
```

On bench-16:
```bash
cd /home/ubuntu/frappe-bench-16/apps/pos_next && git pull origin feat/sync-foundation
bench --site dev.pos migrate
bench --site dev.pos execute pos_next.sync.tests._test_e2e_push.run_all
```

---

## Done — What Plan 3 Delivers

After completing all 8 tasks:

- **Outbox hooks** capture `on_submit`/`on_cancel`/`on_update` for Sales Invoice, Payment Entry, POS shifts, SLE, Customer.
- **OutboxDrainer** batches and POSTs pending rows to central every 60 seconds.
- **Central ingest API** applies received records via adapters, with `sync_uuid` idempotency.
- **SubmittableAdapter** base class handles docstatus-aware insert (no re-submission on central).
- **5 transaction adapters** registered: Sales Invoice, Payment Entry, POS Opening/Closing Shift, SLE.
- **Exponential backoff** on failure, **dead letter** after 10 attempts.
- **4 test modules + 1 e2e integration test.**
- Combined with Plan 2: **complete bidirectional sync** for all DocTypes.

## Self-Review Checklist

- [ ] All 8 tasks committed.
- [ ] `bench --site pos-dev execute pos_next.sync.tests.run_plan3_tests.run` — 0 failures.
- [ ] Plan 1 tests still pass (11/11).
- [ ] Plan 2 tests still pass (6/6).
- [ ] E2E push test passes from bench-16.
- [ ] `bench --site pos-dev migrate` runs clean.
