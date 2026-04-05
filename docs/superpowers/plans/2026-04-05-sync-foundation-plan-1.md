# Branch↔Central Sync — Foundation (Plan 1 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundational scaffolding for branch↔central sync — DocTypes, sync module skeleton, custom fields, role/permissions, install seeding — such that the system can be configured, a connection to central can be verified, and all storage/registry primitives exist. **No data flows yet.**

**Architecture:** Pluggable adapter pattern. A `Sync Site Config` DocType defines role (Branch/Central) with role-dependent cardinality. A registry child table lists which DocTypes sync with what strategy and conflict rule. Outbox + Watermark + Tombstone DocTypes hold change-capture state. A `pos_next/sync/` Python module provides the engine skeleton (auth helper, transport, registry, BaseSyncAdapter, conflict helpers). No adapters, no scheduled jobs yet — those come in Plan 2 & 3.

**Tech Stack:** Frappe Framework (Python 3.10+), Frappe ORM, pytest-style tests via `bench execute`, Frappe DocTypes (JSON), Frappe custom fields, Frappe Password fieldtype for encryption at rest.

**Spec:** `docs/superpowers/specs/2026-04-05-branch-central-architecture-design.md`

**Prerequisites:**
- POS Next app installed on a Frappe site.
- Testing uses `bench execute` — never `bench run-tests` (wipes data per CLAUDE.md memory).
- Use `yarn` for any JS work (not `npm`).
- Frappe/ERPNext site name on this machine: check with `bench --site <site> list-apps`.

---

## File Structure

### New DocTypes (all under `pos_next/pos_next/doctype/`)

| DocType | Purpose | Cardinality |
|---------|---------|-------------|
| `sync_site_config/` | Role, connection config, sync intervals, synced doctypes registry | Singleton on Branch, Multi on Central |
| `sync_doctype_rule/` | Child table: per-entity sync config (direction, cdc, conflict) | Child of Sync Site Config |
| `sync_sibling_branch/` | Child table: read-only list of other branches | Child of Sync Site Config |
| `sync_outbox/` | Pending change events for branch→central push | Many |
| `sync_watermark/` | Per-DocType `last_modified` marker for pull cycles | One per DocType |
| `sync_tombstone/` | Records of deletes to replay | Many |
| `sync_record_state/` | Per-record `last_synced_hash` for conflict detection | One per synced record |
| `sync_field_timestamp/` | Per-field timestamps for Field-Level-LWW | Many (child-like, standalone) |
| `sync_conflict/` | Manual-resolution queue | Many |
| `sync_log/` | Append-only operation log | Many |
| `sync_dead_letter/` | Outbox rows exceeded max retries | Many |
| `sync_history/` | Archived acknowledged outbox rows | Many |

### New Python module (`pos_next/sync/`)

| File | Responsibility |
|------|----------------|
| `__init__.py` | module marker |
| `auth.py` | `SyncSession` class: login/session/retry against central |
| `transport.py` | HTTP client wrapping `requests`: timeout, retry, auth injection |
| `registry.py` | Reads `Sync DocType Rule`, returns adapter class for a doctype |
| `adapters/__init__.py` | Registers adapters in a dict |
| `adapters/base.py` | `BaseSyncAdapter` abstract class |
| `conflict.py` | `resolve(local, incoming, rule)` → winner dict; hash helpers |
| `exceptions.py` | `SyncAuthError`, `SyncTransportError`, `SyncConflictError`, etc. |
| `payload.py` | Serialize/deserialize doc snapshots with children; hash computation |
| `seeds.py` | Seeded default `synced_doctypes` rules installed at setup |
| `defaults.py` | Centralized constants (intervals, retry policy, batch sizes) |

### Modified files

| File | What changes |
|------|--------------|
| `pos_next/hooks.py` | Add `after_install` hook for seeds; fixtures list updates |
| `pos_next/patches.txt` | Add sync foundation patches (post_model_sync) |
| `pos_next/install.py` | Call sync setup in install flow |

### New custom fields (installed via a patch)

On **Sales Invoice**, **Payment Entry**, **Stock Ledger Entry**, **POS Opening Shift**, **POS Closing Shift**, **Customer**:

| Field | Type | Notes |
|-------|------|-------|
| `sync_uuid` | Data, unique indexed | UUID v4, set at creation |
| `origin_branch` | Data | `branch_code` of originating site |
| `synced_from_failover` | Check | 1 when central wrote as proxy |

### New patches (`pos_next/patches/v2_0_0/`)

| File | Purpose |
|------|---------|
| `install_sync_foundation.py` | Create Sync Site Config DocTypes (via migrate), seed default rules |
| `add_sync_custom_fields.py` | Install sync_uuid, origin_branch, synced_from_failover custom fields |
| `backfill_sync_uuid.py` | Fill sync_uuid on existing transaction rows (idempotent, batched) |
| `create_sync_agent_role.py` | Create `POS Next Sync Agent` role with seeded permissions |

### New tests

| Test file | Covers |
|-----------|--------|
| `pos_next/sync/tests/test_sync_site_config.py` | Cardinality, role validation, seeding |
| `pos_next/sync/tests/test_outbox.py` | Compaction on write, terminal-state inserts |
| `pos_next/sync/tests/test_watermark.py` | Watermark CRUD, tombstone application |
| `pos_next/sync/tests/test_conflict.py` | Each conflict strategy (LWW, Central-Wins, Branch-Wins, Field-LWW, Manual) |
| `pos_next/sync/tests/test_payload.py` | Serialize/hash stability, children handling |
| `pos_next/sync/tests/test_auth.py` | Login, retry-on-401, in-memory session caching |
| `pos_next/sync/tests/test_registry.py` | Adapter lookup, missing-adapter handling |
| `pos_next/sync/tests/test_base_adapter.py` | Default serialize/apply/conflict_key behavior |
| `pos_next/sync/tests/test_custom_fields.py` | sync_uuid auto-generation, uniqueness |
| `pos_next/sync/tests/test_backfill.py` | Backfill idempotency |
| `pos_next/sync/tests/test_seeds.py` | Default rules seeded correctly |

---

## Running Tests

All tests are run via `bench execute` (per CLAUDE.md memory — never use `bench run-tests`):

```bash
cd /home/ubuntu/frappe-bench
bench --site <site-name> execute pos_next.sync.tests.test_sync_site_config.run_all
```

Each test module exposes a `run_all()` function that calls every test function and prints PASS/FAIL. This keeps data isolated (tests create + delete their own fixtures).

---

## Tasks

### Task 1: Create `Sync DocType Rule` child DocType

**Files:**
- Create: `pos_next/pos_next/doctype/sync_doctype_rule/__init__.py`
- Create: `pos_next/pos_next/doctype/sync_doctype_rule/sync_doctype_rule.json`
- Create: `pos_next/pos_next/doctype/sync_doctype_rule/sync_doctype_rule.py`

- [ ] **Step 1: Create empty `__init__.py`**

```bash
mkdir -p /home/ubuntu/frappe-bench/apps/pos_next/pos_next/pos_next/doctype/sync_doctype_rule
touch /home/ubuntu/frappe-bench/apps/pos_next/pos_next/pos_next/doctype/sync_doctype_rule/__init__.py
```

- [ ] **Step 2: Create DocType JSON**

File: `pos_next/pos_next/doctype/sync_doctype_rule/sync_doctype_rule.json`

```json
{
 "actions": [],
 "creation": "2026-04-05 00:00:00",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": [
  "doctype_name",
  "direction",
  "cdc_strategy",
  "conflict_rule",
  "priority",
  "batch_size",
  "enabled"
 ],
 "fields": [
  {
   "fieldname": "doctype_name",
   "fieldtype": "Link",
   "in_list_view": 1,
   "label": "DocType",
   "options": "DocType",
   "reqd": 1
  },
  {
   "fieldname": "direction",
   "fieldtype": "Select",
   "in_list_view": 1,
   "label": "Direction",
   "options": "Central→Branch\nBranch→Central\nBidirectional",
   "reqd": 1
  },
  {
   "fieldname": "cdc_strategy",
   "fieldtype": "Select",
   "in_list_view": 1,
   "label": "CDC Strategy",
   "options": "Outbox\nWatermark",
   "reqd": 1
  },
  {
   "fieldname": "conflict_rule",
   "fieldtype": "Select",
   "label": "Conflict Rule",
   "options": "Last-Write-Wins\nCentral-Wins\nBranch-Wins\nField-Level-LWW\nManual",
   "reqd": 1
  },
  {
   "default": "100",
   "fieldname": "priority",
   "fieldtype": "Int",
   "in_list_view": 1,
   "label": "Priority"
  },
  {
   "default": "100",
   "fieldname": "batch_size",
   "fieldtype": "Int",
   "label": "Batch Size"
  },
  {
   "default": "1",
   "fieldname": "enabled",
   "fieldtype": "Check",
   "in_list_view": 1,
   "label": "Enabled"
  }
 ],
 "index_web_pages_for_search": 0,
 "istable": 1,
 "links": [],
 "modified": "2026-04-05 00:00:00",
 "modified_by": "Administrator",
 "module": "POS Next",
 "name": "Sync DocType Rule",
 "owner": "Administrator",
 "permissions": [],
 "sort_field": "priority",
 "sort_order": "ASC",
 "states": [],
 "track_changes": 0
}
```

- [ ] **Step 3: Create DocType Python controller**

File: `pos_next/pos_next/doctype/sync_doctype_rule/sync_doctype_rule.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class SyncDocTypeRule(Document):
    """Child table row describing how one DocType participates in sync."""
    pass
```

- [ ] **Step 4: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/pos_next/doctype/sync_doctype_rule/
git commit -m "feat(sync): add Sync DocType Rule child doctype"
```

---

### Task 2: Create `Sync Sibling Branch` child DocType

**Files:**
- Create: `pos_next/pos_next/doctype/sync_sibling_branch/__init__.py`
- Create: `pos_next/pos_next/doctype/sync_sibling_branch/sync_sibling_branch.json`
- Create: `pos_next/pos_next/doctype/sync_sibling_branch/sync_sibling_branch.py`

- [ ] **Step 1: Create directory and empty init**

```bash
mkdir -p /home/ubuntu/frappe-bench/apps/pos_next/pos_next/pos_next/doctype/sync_sibling_branch
touch /home/ubuntu/frappe-bench/apps/pos_next/pos_next/pos_next/doctype/sync_sibling_branch/__init__.py
```

- [ ] **Step 2: Create DocType JSON**

File: `pos_next/pos_next/doctype/sync_sibling_branch/sync_sibling_branch.json`

```json
{
 "actions": [],
 "creation": "2026-04-05 00:00:00",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": [
  "branch_code",
  "branch",
  "branch_url"
 ],
 "fields": [
  {
   "fieldname": "branch_code",
   "fieldtype": "Data",
   "in_list_view": 1,
   "label": "Branch Code",
   "read_only": 1,
   "reqd": 1
  },
  {
   "fieldname": "branch",
   "fieldtype": "Link",
   "in_list_view": 1,
   "label": "Branch",
   "options": "Branch",
   "read_only": 1
  },
  {
   "fieldname": "branch_url",
   "fieldtype": "Data",
   "label": "Branch URL",
   "read_only": 1
  }
 ],
 "index_web_pages_for_search": 0,
 "istable": 1,
 "links": [],
 "modified": "2026-04-05 00:00:00",
 "modified_by": "Administrator",
 "module": "POS Next",
 "name": "Sync Sibling Branch",
 "owner": "Administrator",
 "permissions": [],
 "sort_field": "branch_code",
 "sort_order": "ASC",
 "states": [],
 "track_changes": 0
}
```

- [ ] **Step 3: Create Python controller**

File: `pos_next/pos_next/doctype/sync_sibling_branch/sync_sibling_branch.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class SyncSiblingBranch(Document):
    """Read-only list entry for another branch, synced down from central."""
    pass
```

- [ ] **Step 4: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/pos_next/doctype/sync_sibling_branch/
git commit -m "feat(sync): add Sync Sibling Branch child doctype"
```

---

### Task 3: Create `Sync Site Config` DocType with cardinality validation

**Files:**
- Create: `pos_next/pos_next/doctype/sync_site_config/__init__.py`
- Create: `pos_next/pos_next/doctype/sync_site_config/sync_site_config.json`
- Create: `pos_next/pos_next/doctype/sync_site_config/sync_site_config.py`
- Create: `pos_next/pos_next/doctype/sync_site_config/sync_site_config.js`
- Create: `pos_next/sync/tests/__init__.py`
- Create: `pos_next/sync/tests/test_sync_site_config.py`

- [ ] **Step 1: Create sync module + tests directory structure**

```bash
mkdir -p /home/ubuntu/frappe-bench/apps/pos_next/pos_next/sync/tests
touch /home/ubuntu/frappe-bench/apps/pos_next/pos_next/sync/__init__.py
touch /home/ubuntu/frappe-bench/apps/pos_next/pos_next/sync/tests/__init__.py
mkdir -p /home/ubuntu/frappe-bench/apps/pos_next/pos_next/pos_next/doctype/sync_site_config
touch /home/ubuntu/frappe-bench/apps/pos_next/pos_next/pos_next/doctype/sync_site_config/__init__.py
```

- [ ] **Step 2: Write failing test — cardinality**

File: `pos_next/sync/tests/test_sync_site_config.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe.exceptions import ValidationError


def _cleanup():
    """Remove all Sync Site Config rows (for test isolation)."""
    frappe.db.delete("Sync Site Config")
    frappe.db.commit()


def test_branch_is_singleton():
    """A Branch-role Sync Site Config can only exist once per site."""
    _cleanup()
    try:
        doc1 = frappe.get_doc({
            "doctype": "Sync Site Config",
            "site_role": "Branch",
            "branch_code": "CAI",
            "enabled": 1,
            "central_url": "https://central.test",
            "sync_username": "sync@test.com",
            "sync_password": "secret123",
        })
        doc1.insert(ignore_permissions=True)

        doc2 = frappe.get_doc({
            "doctype": "Sync Site Config",
            "site_role": "Branch",
            "branch_code": "ALX",
            "enabled": 1,
            "central_url": "https://central.test",
            "sync_username": "sync2@test.com",
            "sync_password": "secret456",
        })

        raised = False
        try:
            doc2.insert(ignore_permissions=True)
        except ValidationError as e:
            raised = True
            assert "Branch" in str(e), f"Expected branch-singleton error, got: {e}"

        assert raised, "Second Branch-role config should have been rejected"
        print("PASS: test_branch_is_singleton")
    finally:
        _cleanup()


def test_central_allows_multiple():
    """Central-role allows multiple Sync Site Config rows (one per branch)."""
    _cleanup()
    try:
        for code in ("CAI", "ALX", "HQ"):
            doc = frappe.get_doc({
                "doctype": "Sync Site Config",
                "site_role": "Central",
                "branch_code": code,
                "enabled": 1,
            })
            doc.insert(ignore_permissions=True)
        count = frappe.db.count("Sync Site Config")
        assert count == 3, f"Expected 3 Central rows, got {count}"
        print("PASS: test_central_allows_multiple")
    finally:
        _cleanup()


def test_branch_code_unique():
    """branch_code must be unique across Sync Site Config rows."""
    _cleanup()
    try:
        doc1 = frappe.get_doc({
            "doctype": "Sync Site Config",
            "site_role": "Central",
            "branch_code": "CAI",
            "enabled": 1,
        })
        doc1.insert(ignore_permissions=True)

        doc2 = frappe.get_doc({
            "doctype": "Sync Site Config",
            "site_role": "Central",
            "branch_code": "CAI",
            "enabled": 1,
        })
        raised = False
        try:
            doc2.insert(ignore_permissions=True)
        except Exception:
            raised = True
        assert raised, "Duplicate branch_code should be rejected"
        print("PASS: test_branch_code_unique")
    finally:
        _cleanup()


def test_https_enforced():
    """central_url must use https:// scheme."""
    _cleanup()
    try:
        doc = frappe.get_doc({
            "doctype": "Sync Site Config",
            "site_role": "Branch",
            "branch_code": "CAI",
            "enabled": 1,
            "central_url": "http://insecure.test",
            "sync_username": "sync@test.com",
            "sync_password": "secret",
        })
        raised = False
        try:
            doc.insert(ignore_permissions=True)
        except ValidationError as e:
            raised = True
            assert "https" in str(e).lower()
        assert raised, "http:// URL should have been rejected"
        print("PASS: test_https_enforced")
    finally:
        _cleanup()


def run_all():
    test_branch_is_singleton()
    test_central_allows_multiple()
    test_branch_code_unique()
    test_https_enforced()
    print("\nAll Sync Site Config tests PASSED")
```

- [ ] **Step 3: Run test to verify it fails (DocType doesn't exist yet)**

```bash
cd /home/ubuntu/frappe-bench
bench --site <site-name> execute pos_next.sync.tests.test_sync_site_config.run_all
```

Expected: FAIL — "DocType Sync Site Config not found" or similar.

- [ ] **Step 4: Create Sync Site Config DocType JSON**

File: `pos_next/pos_next/doctype/sync_site_config/sync_site_config.json`

```json
{
 "actions": [],
 "autoname": "field:branch_code",
 "creation": "2026-04-05 00:00:00",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": [
  "site_role",
  "branch_code",
  "branch",
  "enabled",
  "section_break_central",
  "central_url",
  "sync_username",
  "sync_password",
  "column_break_central",
  "push_interval_seconds",
  "pull_masters_interval_seconds",
  "pull_failover_interval_seconds",
  "section_break_status",
  "last_push_at",
  "last_pull_masters_at",
  "last_pull_failover_at",
  "column_break_status",
  "outbox_depth",
  "last_sync_error",
  "section_break_siblings",
  "sibling_branches",
  "section_break_central_only",
  "registered_branch_url",
  "notes",
  "section_break_registry",
  "synced_doctypes"
 ],
 "fields": [
  {
   "fieldname": "site_role",
   "fieldtype": "Select",
   "in_list_view": 1,
   "label": "Site Role",
   "options": "Branch\nCentral",
   "reqd": 1
  },
  {
   "fieldname": "branch_code",
   "fieldtype": "Data",
   "in_list_view": 1,
   "label": "Branch Code",
   "reqd": 1,
   "unique": 1
  },
  {
   "fieldname": "branch",
   "fieldtype": "Link",
   "label": "Branch",
   "options": "Branch"
  },
  {
   "default": "1",
   "fieldname": "enabled",
   "fieldtype": "Check",
   "label": "Enabled"
  },
  {
   "depends_on": "eval:doc.site_role==\"Branch\"",
   "fieldname": "section_break_central",
   "fieldtype": "Section Break",
   "label": "Central Connection"
  },
  {
   "depends_on": "eval:doc.site_role==\"Branch\"",
   "fieldname": "central_url",
   "fieldtype": "Data",
   "label": "Central URL",
   "mandatory_depends_on": "eval:doc.site_role==\"Branch\""
  },
  {
   "depends_on": "eval:doc.site_role==\"Branch\"",
   "fieldname": "sync_username",
   "fieldtype": "Data",
   "label": "Sync Username",
   "mandatory_depends_on": "eval:doc.site_role==\"Branch\""
  },
  {
   "depends_on": "eval:doc.site_role==\"Branch\"",
   "fieldname": "sync_password",
   "fieldtype": "Password",
   "label": "Sync Password",
   "mandatory_depends_on": "eval:doc.site_role==\"Branch\""
  },
  {
   "fieldname": "column_break_central",
   "fieldtype": "Column Break"
  },
  {
   "default": "60",
   "fieldname": "push_interval_seconds",
   "fieldtype": "Int",
   "label": "Push Interval (seconds)"
  },
  {
   "default": "300",
   "fieldname": "pull_masters_interval_seconds",
   "fieldtype": "Int",
   "label": "Pull Masters Interval (seconds)"
  },
  {
   "default": "120",
   "fieldname": "pull_failover_interval_seconds",
   "fieldtype": "Int",
   "label": "Pull Failover Interval (seconds)"
  },
  {
   "collapsible": 1,
   "fieldname": "section_break_status",
   "fieldtype": "Section Break",
   "label": "Status"
  },
  {
   "fieldname": "last_push_at",
   "fieldtype": "Datetime",
   "label": "Last Push At",
   "read_only": 1
  },
  {
   "fieldname": "last_pull_masters_at",
   "fieldtype": "Datetime",
   "label": "Last Pull Masters At",
   "read_only": 1
  },
  {
   "fieldname": "last_pull_failover_at",
   "fieldtype": "Datetime",
   "label": "Last Pull Failover At",
   "read_only": 1
  },
  {
   "fieldname": "column_break_status",
   "fieldtype": "Column Break"
  },
  {
   "fieldname": "outbox_depth",
   "fieldtype": "Int",
   "label": "Outbox Depth",
   "read_only": 1
  },
  {
   "fieldname": "last_sync_error",
   "fieldtype": "Small Text",
   "label": "Last Sync Error",
   "read_only": 1
  },
  {
   "collapsible": 1,
   "depends_on": "eval:doc.site_role==\"Branch\"",
   "fieldname": "section_break_siblings",
   "fieldtype": "Section Break",
   "label": "Sibling Branches (Read-Only)"
  },
  {
   "fieldname": "sibling_branches",
   "fieldtype": "Table",
   "label": "Sibling Branches",
   "options": "Sync Sibling Branch",
   "read_only": 1
  },
  {
   "collapsible": 1,
   "depends_on": "eval:doc.site_role==\"Central\"",
   "fieldname": "section_break_central_only",
   "fieldtype": "Section Break",
   "label": "Central-Only"
  },
  {
   "fieldname": "registered_branch_url",
   "fieldtype": "Data",
   "label": "Registered Branch URL"
  },
  {
   "fieldname": "notes",
   "fieldtype": "Small Text",
   "label": "Notes"
  },
  {
   "collapsible": 1,
   "fieldname": "section_break_registry",
   "fieldtype": "Section Break",
   "label": "Synced DocTypes Registry"
  },
  {
   "fieldname": "synced_doctypes",
   "fieldtype": "Table",
   "label": "Synced DocTypes",
   "options": "Sync DocType Rule"
  }
 ],
 "index_web_pages_for_search": 0,
 "links": [],
 "modified": "2026-04-05 00:00:00",
 "modified_by": "Administrator",
 "module": "POS Next",
 "name": "Sync Site Config",
 "naming_rule": "By fieldname",
 "owner": "Administrator",
 "permissions": [
  {
   "create": 1,
   "delete": 1,
   "email": 1,
   "export": 1,
   "print": 1,
   "read": 1,
   "report": 1,
   "role": "System Manager",
   "share": 1,
   "write": 1
  }
 ],
 "row_format": "Dynamic",
 "sort_field": "modified",
 "sort_order": "DESC",
 "states": [],
 "track_changes": 1
}
```

- [ ] **Step 5: Create Python controller with cardinality validation**

File: `pos_next/pos_next/doctype/sync_site_config/sync_site_config.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class SyncSiteConfig(Document):
    """
    Sync configuration record.

    Cardinality depends on site_role:
    - Branch: singleton (only one record allowed per site)
    - Central: multi-record (one per registered branch)
    """

    def validate(self):
        self._validate_cardinality()
        self._validate_https_url()
        self._validate_branch_code()

    def _validate_cardinality(self):
        """A Branch-role record must be singleton; Central allows many."""
        if self.site_role != "Branch":
            return
        # Count other Branch-role records (excluding self on update)
        existing = frappe.db.sql(
            """
            SELECT name FROM `tabSync Site Config`
            WHERE site_role = 'Branch' AND name != %s
            """,
            (self.name or "",),
        )
        if existing:
            frappe.throw(
                _(
                    "Only one Sync Site Config with site_role=Branch is allowed "
                    "per site. Existing record: {0}"
                ).format(existing[0][0]),
                title=_("Branch Config Already Exists"),
            )

    def _validate_https_url(self):
        """central_url must use https:// scheme."""
        if self.site_role != "Branch":
            return
        if not self.central_url:
            return
        if not self.central_url.startswith("https://"):
            frappe.throw(
                _("central_url must use https:// scheme, got: {0}").format(self.central_url),
                title=_("Insecure URL"),
            )

    def _validate_branch_code(self):
        """branch_code must match [A-Z0-9]{2,16}."""
        import re
        if not self.branch_code:
            return
        if not re.match(r"^[A-Z0-9]{2,16}$", self.branch_code):
            frappe.throw(
                _("branch_code must be 2-16 uppercase letters/digits, got: {0}").format(
                    self.branch_code
                ),
                title=_("Invalid Branch Code"),
            )
```

- [ ] **Step 6: Create minimal JS file (required by Frappe)**

File: `pos_next/pos_next/doctype/sync_site_config/sync_site_config.js`

```javascript
// Copyright (c) 2026, BrainWise and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sync Site Config", {
    refresh(frm) {
        // Test Sync Connection button will be added in Task 11
    }
});
```

- [ ] **Step 7: Run `bench migrate` to install the DocTypes**

```bash
cd /home/ubuntu/frappe-bench
bench --site <site-name> migrate
```

Expected: DocTypes "Sync DocType Rule", "Sync Sibling Branch", "Sync Site Config" created.

- [ ] **Step 8: Run tests to verify they pass**

```bash
cd /home/ubuntu/frappe-bench
bench --site <site-name> execute pos_next.sync.tests.test_sync_site_config.run_all
```

Expected output:
```
PASS: test_branch_is_singleton
PASS: test_central_allows_multiple
PASS: test_branch_code_unique
PASS: test_https_enforced

All Sync Site Config tests PASSED
```

- [ ] **Step 9: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/pos_next/doctype/sync_site_config/ pos_next/sync/
git commit -m "feat(sync): add Sync Site Config doctype with cardinality validation"
```

---

### Task 4: Create `Sync Outbox` DocType with compaction on insert

**Files:**
- Create: `pos_next/pos_next/doctype/sync_outbox/__init__.py`
- Create: `pos_next/pos_next/doctype/sync_outbox/sync_outbox.json`
- Create: `pos_next/pos_next/doctype/sync_outbox/sync_outbox.py`
- Create: `pos_next/sync/tests/test_outbox.py`

- [ ] **Step 1: Write failing tests for outbox**

File: `pos_next/sync/tests/test_outbox.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe


def _cleanup():
    frappe.db.delete("Sync Outbox")
    frappe.db.commit()


def test_insert_creates_row():
    """Creating an outbox row is straightforward."""
    _cleanup()
    try:
        from pos_next.pos_next.doctype.sync_outbox.sync_outbox import SyncOutbox
        row = SyncOutbox.enqueue(
            reference_doctype="Sales Invoice",
            reference_name="SINV-CAI-2026-00001",
            operation="insert",
            payload='{"name":"SINV-CAI-2026-00001","total":100}',
            priority=50,
        )
        assert row.sync_status == "pending"
        assert row.attempts == 0
        print("PASS: test_insert_creates_row")
    finally:
        _cleanup()


def test_compaction_on_update():
    """Multiple updates to same (doctype, name, 'update') collapse to one pending row."""
    _cleanup()
    try:
        from pos_next.pos_next.doctype.sync_outbox.sync_outbox import SyncOutbox
        SyncOutbox.enqueue(
            reference_doctype="Customer",
            reference_name="Walk-In Cairo",
            operation="update",
            payload='{"name":"Walk-In Cairo","v":1}',
            priority=50,
        )
        SyncOutbox.enqueue(
            reference_doctype="Customer",
            reference_name="Walk-In Cairo",
            operation="update",
            payload='{"name":"Walk-In Cairo","v":2}',
            priority=50,
        )
        SyncOutbox.enqueue(
            reference_doctype="Customer",
            reference_name="Walk-In Cairo",
            operation="update",
            payload='{"name":"Walk-In Cairo","v":3}',
            priority=50,
        )
        count = frappe.db.count(
            "Sync Outbox",
            {"reference_doctype": "Customer", "reference_name": "Walk-In Cairo", "sync_status": "pending"},
        )
        assert count == 1, f"Expected 1 compacted row, got {count}"

        payload = frappe.db.get_value(
            "Sync Outbox",
            {"reference_doctype": "Customer", "reference_name": "Walk-In Cairo"},
            "payload",
        )
        assert '"v":3' in payload, f"Latest payload should win, got: {payload}"
        print("PASS: test_compaction_on_update")
    finally:
        _cleanup()


def test_terminal_ops_always_insert():
    """submit/cancel/delete never compact — they always insert new rows."""
    _cleanup()
    try:
        from pos_next.pos_next.doctype.sync_outbox.sync_outbox import SyncOutbox
        for op in ("submit", "cancel", "delete"):
            SyncOutbox.enqueue(
                reference_doctype="Sales Invoice",
                reference_name="SINV-CAI-2026-00001",
                operation=op,
                payload='{"name":"SINV-CAI-2026-00001"}',
                priority=50,
            )
        count = frappe.db.count(
            "Sync Outbox",
            {"reference_doctype": "Sales Invoice", "reference_name": "SINV-CAI-2026-00001"},
        )
        assert count == 3, f"Expected 3 terminal rows, got {count}"
        print("PASS: test_terminal_ops_always_insert")
    finally:
        _cleanup()


def test_acked_row_not_compacted():
    """An acked row is ignored by compaction; new update creates a fresh pending row."""
    _cleanup()
    try:
        from pos_next.pos_next.doctype.sync_outbox.sync_outbox import SyncOutbox
        row = SyncOutbox.enqueue(
            reference_doctype="Customer",
            reference_name="C1",
            operation="update",
            payload='{"v":1}',
            priority=50,
        )
        # Simulate successful sync
        frappe.db.set_value("Sync Outbox", row.name, "sync_status", "acked")
        frappe.db.commit()

        SyncOutbox.enqueue(
            reference_doctype="Customer",
            reference_name="C1",
            operation="update",
            payload='{"v":2}',
            priority=50,
        )
        pending = frappe.db.count(
            "Sync Outbox",
            {"reference_doctype": "Customer", "reference_name": "C1", "sync_status": "pending"},
        )
        acked = frappe.db.count(
            "Sync Outbox",
            {"reference_doctype": "Customer", "reference_name": "C1", "sync_status": "acked"},
        )
        assert pending == 1 and acked == 1, f"Expected pending=1, acked=1, got pending={pending}, acked={acked}"
        print("PASS: test_acked_row_not_compacted")
    finally:
        _cleanup()


def run_all():
    test_insert_creates_row()
    test_compaction_on_update()
    test_terminal_ops_always_insert()
    test_acked_row_not_compacted()
    print("\nAll Sync Outbox tests PASSED")
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/ubuntu/frappe-bench
bench --site <site-name> execute pos_next.sync.tests.test_outbox.run_all
```

Expected: FAIL — "DocType Sync Outbox not found" or ImportError.

- [ ] **Step 3: Create Sync Outbox DocType directory**

```bash
mkdir -p /home/ubuntu/frappe-bench/apps/pos_next/pos_next/pos_next/doctype/sync_outbox
touch /home/ubuntu/frappe-bench/apps/pos_next/pos_next/pos_next/doctype/sync_outbox/__init__.py
```

- [ ] **Step 4: Create Sync Outbox DocType JSON**

File: `pos_next/pos_next/doctype/sync_outbox/sync_outbox.json`

```json
{
 "actions": [],
 "autoname": "hash",
 "creation": "2026-04-05 00:00:00",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": [
  "reference_doctype",
  "reference_name",
  "operation",
  "sync_status",
  "priority",
  "attempts",
  "next_attempt_at",
  "acked_at",
  "last_error",
  "payload"
 ],
 "fields": [
  {
   "fieldname": "reference_doctype",
   "fieldtype": "Link",
   "in_list_view": 1,
   "in_standard_filter": 1,
   "label": "Reference DocType",
   "options": "DocType",
   "reqd": 1
  },
  {
   "fieldname": "reference_name",
   "fieldtype": "Data",
   "in_list_view": 1,
   "in_standard_filter": 1,
   "label": "Reference Name",
   "reqd": 1
  },
  {
   "fieldname": "operation",
   "fieldtype": "Select",
   "in_list_view": 1,
   "in_standard_filter": 1,
   "label": "Operation",
   "options": "insert\nupdate\nsubmit\ncancel\ndelete",
   "reqd": 1
  },
  {
   "default": "pending",
   "fieldname": "sync_status",
   "fieldtype": "Select",
   "in_list_view": 1,
   "in_standard_filter": 1,
   "label": "Sync Status",
   "options": "pending\nsyncing\nacked\nfailed\ndead"
  },
  {
   "default": "100",
   "fieldname": "priority",
   "fieldtype": "Int",
   "in_list_view": 1,
   "label": "Priority"
  },
  {
   "default": "0",
   "fieldname": "attempts",
   "fieldtype": "Int",
   "label": "Attempts"
  },
  {
   "fieldname": "next_attempt_at",
   "fieldtype": "Datetime",
   "label": "Next Attempt At"
  },
  {
   "fieldname": "acked_at",
   "fieldtype": "Datetime",
   "label": "Acked At",
   "read_only": 1
  },
  {
   "fieldname": "last_error",
   "fieldtype": "Small Text",
   "label": "Last Error"
  },
  {
   "fieldname": "payload",
   "fieldtype": "Long Text",
   "label": "Payload (JSON)"
  }
 ],
 "index_web_pages_for_search": 0,
 "links": [],
 "modified": "2026-04-05 00:00:00",
 "modified_by": "Administrator",
 "module": "POS Next",
 "name": "Sync Outbox",
 "owner": "Administrator",
 "permissions": [
  {
   "create": 1,
   "delete": 1,
   "email": 1,
   "export": 1,
   "print": 1,
   "read": 1,
   "report": 1,
   "role": "System Manager",
   "share": 1,
   "write": 1
  }
 ],
 "row_format": "Dynamic",
 "sort_field": "creation",
 "sort_order": "DESC",
 "states": [],
 "track_changes": 0
}
```

- [ ] **Step 5: Create Sync Outbox Python controller with `enqueue` classmethod**

File: `pos_next/pos_next/doctype/sync_outbox/sync_outbox.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


TERMINAL_OPERATIONS = {"submit", "cancel", "delete"}


class SyncOutbox(Document):
    """Pending change event awaiting push to central."""

    @classmethod
    def enqueue(cls, reference_doctype, reference_name, operation, payload, priority=100):
        """
        Add a change event to the outbox, compacting pending updates to the same record.

        For terminal operations (submit/cancel/delete), always insert.
        For insert/update, if a pending row already exists for this
        (reference_doctype, reference_name, operation), update its payload in place.

        Returns the created or updated Sync Outbox document.
        """
        if operation not in TERMINAL_OPERATIONS:
            existing = frappe.db.get_value(
                "Sync Outbox",
                {
                    "reference_doctype": reference_doctype,
                    "reference_name": reference_name,
                    "operation": operation,
                    "sync_status": "pending",
                },
                "name",
            )
            if existing:
                doc = frappe.get_doc("Sync Outbox", existing)
                doc.payload = payload
                doc.priority = priority
                doc.save(ignore_permissions=True)
                return doc

        doc = frappe.get_doc({
            "doctype": "Sync Outbox",
            "reference_doctype": reference_doctype,
            "reference_name": reference_name,
            "operation": operation,
            "payload": payload,
            "priority": priority,
            "sync_status": "pending",
            "attempts": 0,
        })
        doc.insert(ignore_permissions=True)
        return doc
```

- [ ] **Step 6: Run `bench migrate` to install**

```bash
cd /home/ubuntu/frappe-bench
bench --site <site-name> migrate
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
cd /home/ubuntu/frappe-bench
bench --site <site-name> execute pos_next.sync.tests.test_outbox.run_all
```

Expected: all 4 tests PASS.

- [ ] **Step 8: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/pos_next/doctype/sync_outbox/ pos_next/sync/tests/test_outbox.py
git commit -m "feat(sync): add Sync Outbox with compaction on pending updates"
```

---

### Task 5: Create `Sync Watermark` + `Sync Tombstone` DocTypes

**Files:**
- Create: `pos_next/pos_next/doctype/sync_watermark/` (init, json, py)
- Create: `pos_next/pos_next/doctype/sync_tombstone/` (init, json, py)
- Create: `pos_next/sync/tests/test_watermark.py`

- [ ] **Step 1: Write failing tests**

File: `pos_next/sync/tests/test_watermark.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import now_datetime


def _cleanup():
    frappe.db.delete("Sync Watermark")
    frappe.db.delete("Sync Tombstone")
    frappe.db.commit()


def test_watermark_upsert():
    """Watermark CRUD via upsert helper."""
    _cleanup()
    try:
        from pos_next.pos_next.doctype.sync_watermark.sync_watermark import SyncWatermark
        ts = now_datetime()
        row = SyncWatermark.upsert("Item", ts, records_pulled=10)
        assert row.doctype_name == "Item"
        assert row.records_pulled == 10

        ts2 = now_datetime()
        row2 = SyncWatermark.upsert("Item", ts2, records_pulled=5)
        assert row2.name == row.name, "upsert should update existing row, not create new"
        assert row2.records_pulled == 5
        print("PASS: test_watermark_upsert")
    finally:
        _cleanup()


def test_watermark_unique_per_doctype():
    """Only one Sync Watermark row per DocType."""
    _cleanup()
    try:
        from pos_next.pos_next.doctype.sync_watermark.sync_watermark import SyncWatermark
        ts = now_datetime()
        SyncWatermark.upsert("Item", ts)
        SyncWatermark.upsert("Customer", ts)
        SyncWatermark.upsert("Item", ts)  # should update, not insert
        count = frappe.db.count("Sync Watermark")
        assert count == 2, f"Expected 2 rows (Item, Customer), got {count}"
        print("PASS: test_watermark_unique_per_doctype")
    finally:
        _cleanup()


def test_tombstone_record():
    """Creating tombstones is simple."""
    _cleanup()
    try:
        from pos_next.pos_next.doctype.sync_tombstone.sync_tombstone import SyncTombstone
        t = SyncTombstone.record("Item", "ITEM-001")
        assert t.reference_doctype == "Item"
        assert t.reference_name == "ITEM-001"
        assert t.deleted_at is not None
        print("PASS: test_tombstone_record")
    finally:
        _cleanup()


def run_all():
    test_watermark_upsert()
    test_watermark_unique_per_doctype()
    test_tombstone_record()
    print("\nAll Watermark/Tombstone tests PASSED")
```

- [ ] **Step 2: Run test to confirm failure**

```bash
cd /home/ubuntu/frappe-bench
bench --site <site-name> execute pos_next.sync.tests.test_watermark.run_all
```

Expected: FAIL — doctypes missing.

- [ ] **Step 3: Create Sync Watermark DocType**

```bash
mkdir -p /home/ubuntu/frappe-bench/apps/pos_next/pos_next/pos_next/doctype/sync_watermark
touch /home/ubuntu/frappe-bench/apps/pos_next/pos_next/pos_next/doctype/sync_watermark/__init__.py
```

File: `pos_next/pos_next/doctype/sync_watermark/sync_watermark.json`

```json
{
 "actions": [],
 "autoname": "field:doctype_name",
 "creation": "2026-04-05 00:00:00",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": [
  "doctype_name",
  "last_modified",
  "last_pulled_at",
  "records_pulled"
 ],
 "fields": [
  {
   "fieldname": "doctype_name",
   "fieldtype": "Link",
   "in_list_view": 1,
   "label": "DocType",
   "options": "DocType",
   "reqd": 1,
   "unique": 1
  },
  {
   "fieldname": "last_modified",
   "fieldtype": "Datetime",
   "in_list_view": 1,
   "label": "Last Modified"
  },
  {
   "fieldname": "last_pulled_at",
   "fieldtype": "Datetime",
   "in_list_view": 1,
   "label": "Last Pulled At"
  },
  {
   "default": "0",
   "fieldname": "records_pulled",
   "fieldtype": "Int",
   "in_list_view": 1,
   "label": "Records Pulled"
  }
 ],
 "index_web_pages_for_search": 0,
 "links": [],
 "modified": "2026-04-05 00:00:00",
 "modified_by": "Administrator",
 "module": "POS Next",
 "name": "Sync Watermark",
 "naming_rule": "By fieldname",
 "owner": "Administrator",
 "permissions": [
  {
   "create": 1,
   "delete": 1,
   "read": 1,
   "report": 1,
   "role": "System Manager",
   "write": 1
  }
 ],
 "row_format": "Dynamic",
 "sort_field": "modified",
 "sort_order": "DESC",
 "states": [],
 "track_changes": 0
}
```

File: `pos_next/pos_next/doctype/sync_watermark/sync_watermark.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class SyncWatermark(Document):
    """Per-DocType watermark for master pull cycles."""

    @classmethod
    def upsert(cls, doctype_name, last_modified, records_pulled=0):
        """Insert or update the watermark row for a DocType."""
        existing = frappe.db.get_value("Sync Watermark", {"doctype_name": doctype_name}, "name")
        if existing:
            doc = frappe.get_doc("Sync Watermark", existing)
            doc.last_modified = last_modified
            doc.last_pulled_at = now_datetime()
            doc.records_pulled = records_pulled
            doc.save(ignore_permissions=True)
            return doc
        doc = frappe.get_doc({
            "doctype": "Sync Watermark",
            "doctype_name": doctype_name,
            "last_modified": last_modified,
            "last_pulled_at": now_datetime(),
            "records_pulled": records_pulled,
        })
        doc.insert(ignore_permissions=True)
        return doc

    @classmethod
    def get_for(cls, doctype_name):
        """Fetch the watermark row for a DocType, or None."""
        name = frappe.db.get_value("Sync Watermark", {"doctype_name": doctype_name}, "name")
        return frappe.get_doc("Sync Watermark", name) if name else None
```

- [ ] **Step 4: Create Sync Tombstone DocType**

```bash
mkdir -p /home/ubuntu/frappe-bench/apps/pos_next/pos_next/pos_next/doctype/sync_tombstone
touch /home/ubuntu/frappe-bench/apps/pos_next/pos_next/pos_next/doctype/sync_tombstone/__init__.py
```

File: `pos_next/pos_next/doctype/sync_tombstone/sync_tombstone.json`

```json
{
 "actions": [],
 "autoname": "hash",
 "creation": "2026-04-05 00:00:00",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": [
  "reference_doctype",
  "reference_name",
  "deleted_at"
 ],
 "fields": [
  {
   "fieldname": "reference_doctype",
   "fieldtype": "Link",
   "in_list_view": 1,
   "in_standard_filter": 1,
   "label": "Reference DocType",
   "options": "DocType",
   "reqd": 1
  },
  {
   "fieldname": "reference_name",
   "fieldtype": "Data",
   "in_list_view": 1,
   "in_standard_filter": 1,
   "label": "Reference Name",
   "reqd": 1
  },
  {
   "fieldname": "deleted_at",
   "fieldtype": "Datetime",
   "in_list_view": 1,
   "label": "Deleted At",
   "reqd": 1
  }
 ],
 "index_web_pages_for_search": 0,
 "links": [],
 "modified": "2026-04-05 00:00:00",
 "modified_by": "Administrator",
 "module": "POS Next",
 "name": "Sync Tombstone",
 "owner": "Administrator",
 "permissions": [
  {
   "create": 1,
   "delete": 1,
   "read": 1,
   "report": 1,
   "role": "System Manager",
   "write": 1
  }
 ],
 "row_format": "Dynamic",
 "sort_field": "deleted_at",
 "sort_order": "DESC",
 "states": [],
 "track_changes": 0
}
```

File: `pos_next/pos_next/doctype/sync_tombstone/sync_tombstone.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class SyncTombstone(Document):
    """Record that a master was deleted on central, so branches can replay the delete."""

    @classmethod
    def record(cls, reference_doctype, reference_name):
        """Create a tombstone for a deleted record."""
        doc = frappe.get_doc({
            "doctype": "Sync Tombstone",
            "reference_doctype": reference_doctype,
            "reference_name": reference_name,
            "deleted_at": now_datetime(),
        })
        doc.insert(ignore_permissions=True)
        return doc
```

- [ ] **Step 5: Run migrate and tests**

```bash
cd /home/ubuntu/frappe-bench
bench --site <site-name> migrate
bench --site <site-name> execute pos_next.sync.tests.test_watermark.run_all
```

Expected: all 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/pos_next/doctype/sync_watermark/ pos_next/pos_next/doctype/sync_tombstone/ pos_next/sync/tests/test_watermark.py
git commit -m "feat(sync): add Sync Watermark and Sync Tombstone doctypes"
```

---

### Task 6: Create remaining tracking DocTypes (`Sync Record State`, `Sync Field Timestamp`, `Sync Conflict`, `Sync Log`, `Sync Dead Letter`, `Sync History`)

**Files:**
- Create: `pos_next/pos_next/doctype/sync_record_state/` (init, json, py)
- Create: `pos_next/pos_next/doctype/sync_field_timestamp/` (init, json, py)
- Create: `pos_next/pos_next/doctype/sync_conflict/` (init, json, py)
- Create: `pos_next/pos_next/doctype/sync_log/` (init, json, py)
- Create: `pos_next/pos_next/doctype/sync_dead_letter/` (init, json, py)
- Create: `pos_next/pos_next/doctype/sync_history/` (init, json, py)

- [ ] **Step 1: Create `Sync Record State` DocType**

```bash
mkdir -p /home/ubuntu/frappe-bench/apps/pos_next/pos_next/pos_next/doctype/sync_record_state
touch /home/ubuntu/frappe-bench/apps/pos_next/pos_next/pos_next/doctype/sync_record_state/__init__.py
```

File: `pos_next/pos_next/doctype/sync_record_state/sync_record_state.json`

```json
{
 "actions": [],
 "autoname": "hash",
 "creation": "2026-04-05 00:00:00",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": [
  "reference_doctype",
  "reference_name",
  "last_synced_hash",
  "last_synced_at",
  "last_synced_from"
 ],
 "fields": [
  {
   "fieldname": "reference_doctype",
   "fieldtype": "Link",
   "in_list_view": 1,
   "label": "Reference DocType",
   "options": "DocType",
   "reqd": 1
  },
  {
   "fieldname": "reference_name",
   "fieldtype": "Data",
   "in_list_view": 1,
   "label": "Reference Name",
   "reqd": 1
  },
  {
   "fieldname": "last_synced_hash",
   "fieldtype": "Data",
   "label": "Last Synced Hash"
  },
  {
   "fieldname": "last_synced_at",
   "fieldtype": "Datetime",
   "label": "Last Synced At"
  },
  {
   "fieldname": "last_synced_from",
   "fieldtype": "Data",
   "label": "Last Synced From"
  }
 ],
 "index_web_pages_for_search": 0,
 "links": [],
 "modified": "2026-04-05 00:00:00",
 "modified_by": "Administrator",
 "module": "POS Next",
 "name": "Sync Record State",
 "owner": "Administrator",
 "permissions": [
  {"create": 1, "delete": 1, "read": 1, "report": 1, "role": "System Manager", "write": 1}
 ],
 "row_format": "Dynamic",
 "sort_field": "modified",
 "sort_order": "DESC",
 "states": [],
 "track_changes": 0
}
```

File: `pos_next/pos_next/doctype/sync_record_state/sync_record_state.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class SyncRecordState(Document):
    """Per-record sync tracking: hash + source + timestamp of last successful sync."""

    @classmethod
    def upsert(cls, reference_doctype, reference_name, payload_hash, source):
        """Record that a record was just synced; store hash + source."""
        existing = frappe.db.get_value(
            "Sync Record State",
            {"reference_doctype": reference_doctype, "reference_name": reference_name},
            "name",
        )
        if existing:
            doc = frappe.get_doc("Sync Record State", existing)
            doc.last_synced_hash = payload_hash
            doc.last_synced_at = now_datetime()
            doc.last_synced_from = source
            doc.save(ignore_permissions=True)
            return doc
        doc = frappe.get_doc({
            "doctype": "Sync Record State",
            "reference_doctype": reference_doctype,
            "reference_name": reference_name,
            "last_synced_hash": payload_hash,
            "last_synced_at": now_datetime(),
            "last_synced_from": source,
        })
        doc.insert(ignore_permissions=True)
        return doc

    @classmethod
    def get_hash(cls, reference_doctype, reference_name):
        """Return the last-synced hash, or None."""
        return frappe.db.get_value(
            "Sync Record State",
            {"reference_doctype": reference_doctype, "reference_name": reference_name},
            "last_synced_hash",
        )
```

- [ ] **Step 2: Create `Sync Field Timestamp` DocType**

```bash
mkdir -p /home/ubuntu/frappe-bench/apps/pos_next/pos_next/pos_next/doctype/sync_field_timestamp
touch /home/ubuntu/frappe-bench/apps/pos_next/pos_next/pos_next/doctype/sync_field_timestamp/__init__.py
```

File: `pos_next/pos_next/doctype/sync_field_timestamp/sync_field_timestamp.json`

```json
{
 "actions": [],
 "autoname": "hash",
 "creation": "2026-04-05 00:00:00",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": [
  "reference_doctype",
  "reference_name",
  "fieldname",
  "modified_at"
 ],
 "fields": [
  {
   "fieldname": "reference_doctype",
   "fieldtype": "Link",
   "label": "Reference DocType",
   "options": "DocType",
   "reqd": 1
  },
  {
   "fieldname": "reference_name",
   "fieldtype": "Data",
   "label": "Reference Name",
   "reqd": 1
  },
  {
   "fieldname": "fieldname",
   "fieldtype": "Data",
   "label": "Fieldname",
   "reqd": 1
  },
  {
   "fieldname": "modified_at",
   "fieldtype": "Datetime",
   "label": "Modified At",
   "reqd": 1
  }
 ],
 "index_web_pages_for_search": 0,
 "links": [],
 "modified": "2026-04-05 00:00:00",
 "modified_by": "Administrator",
 "module": "POS Next",
 "name": "Sync Field Timestamp",
 "owner": "Administrator",
 "permissions": [
  {"create": 1, "delete": 1, "read": 1, "role": "System Manager", "write": 1}
 ],
 "row_format": "Dynamic",
 "sort_field": "modified",
 "sort_order": "DESC",
 "states": [],
 "track_changes": 0
}
```

File: `pos_next/pos_next/doctype/sync_field_timestamp/sync_field_timestamp.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class SyncFieldTimestamp(Document):
    """Per-field modification timestamp for Field-Level-LWW conflict resolution."""
    pass
```

- [ ] **Step 3: Create `Sync Conflict` DocType**

```bash
mkdir -p /home/ubuntu/frappe-bench/apps/pos_next/pos_next/pos_next/doctype/sync_conflict
touch /home/ubuntu/frappe-bench/apps/pos_next/pos_next/pos_next/doctype/sync_conflict/__init__.py
```

File: `pos_next/pos_next/doctype/sync_conflict/sync_conflict.json`

```json
{
 "actions": [],
 "autoname": "hash",
 "creation": "2026-04-05 00:00:00",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": [
  "reference_doctype",
  "reference_name",
  "status",
  "incoming_from",
  "detected_at",
  "local_payload",
  "incoming_payload",
  "resolved_by",
  "resolution_notes"
 ],
 "fields": [
  {"fieldname": "reference_doctype", "fieldtype": "Link", "in_list_view": 1, "label": "Reference DocType", "options": "DocType", "reqd": 1},
  {"fieldname": "reference_name", "fieldtype": "Data", "in_list_view": 1, "label": "Reference Name", "reqd": 1},
  {"fieldname": "status", "fieldtype": "Select", "in_list_view": 1, "label": "Status", "options": "pending\nresolved_local\nresolved_incoming\nresolved_merged", "default": "pending"},
  {"fieldname": "incoming_from", "fieldtype": "Data", "in_list_view": 1, "label": "Incoming From"},
  {"fieldname": "detected_at", "fieldtype": "Datetime", "label": "Detected At"},
  {"fieldname": "local_payload", "fieldtype": "Long Text", "label": "Local Payload"},
  {"fieldname": "incoming_payload", "fieldtype": "Long Text", "label": "Incoming Payload"},
  {"fieldname": "resolved_by", "fieldtype": "Link", "label": "Resolved By", "options": "User"},
  {"fieldname": "resolution_notes", "fieldtype": "Text", "label": "Resolution Notes"}
 ],
 "index_web_pages_for_search": 0,
 "links": [],
 "modified": "2026-04-05 00:00:00",
 "modified_by": "Administrator",
 "module": "POS Next",
 "name": "Sync Conflict",
 "owner": "Administrator",
 "permissions": [
  {"create": 1, "delete": 1, "read": 1, "report": 1, "role": "System Manager", "write": 1}
 ],
 "row_format": "Dynamic",
 "sort_field": "detected_at",
 "sort_order": "DESC",
 "states": [],
 "track_changes": 1
}
```

File: `pos_next/pos_next/doctype/sync_conflict/sync_conflict.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class SyncConflict(Document):
    """Manual-resolution queue entry for sync conflicts."""
    pass
```

- [ ] **Step 4: Create `Sync Log` DocType**

```bash
mkdir -p /home/ubuntu/frappe-bench/apps/pos_next/pos_next/pos_next/doctype/sync_log
touch /home/ubuntu/frappe-bench/apps/pos_next/pos_next/pos_next/doctype/sync_log/__init__.py
```

File: `pos_next/pos_next/doctype/sync_log/sync_log.json`

```json
{
 "actions": [],
 "autoname": "hash",
 "creation": "2026-04-05 00:00:00",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": [
  "operation",
  "status",
  "duration_ms",
  "records_touched",
  "error",
  "context"
 ],
 "fields": [
  {"fieldname": "operation", "fieldtype": "Data", "in_list_view": 1, "in_standard_filter": 1, "label": "Operation"},
  {"fieldname": "status", "fieldtype": "Select", "in_list_view": 1, "in_standard_filter": 1, "label": "Status", "options": "success\nfailure\npartial"},
  {"fieldname": "duration_ms", "fieldtype": "Int", "in_list_view": 1, "label": "Duration (ms)"},
  {"fieldname": "records_touched", "fieldtype": "Int", "in_list_view": 1, "label": "Records Touched"},
  {"fieldname": "error", "fieldtype": "Small Text", "label": "Error"},
  {"fieldname": "context", "fieldtype": "Long Text", "label": "Context (JSON)"}
 ],
 "index_web_pages_for_search": 0,
 "links": [],
 "modified": "2026-04-05 00:00:00",
 "modified_by": "Administrator",
 "module": "POS Next",
 "name": "Sync Log",
 "owner": "Administrator",
 "permissions": [
  {"read": 1, "report": 1, "role": "System Manager"}
 ],
 "row_format": "Dynamic",
 "sort_field": "creation",
 "sort_order": "DESC",
 "states": [],
 "track_changes": 0
}
```

File: `pos_next/pos_next/doctype/sync_log/sync_log.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SyncLog(Document):
    """Append-only log of sync operations."""

    @classmethod
    def record(cls, operation, status, duration_ms=0, records_touched=0, error=None, context=None):
        """Write a log entry. Safe to call from anywhere."""
        import json
        doc = frappe.get_doc({
            "doctype": "Sync Log",
            "operation": operation,
            "status": status,
            "duration_ms": duration_ms,
            "records_touched": records_touched,
            "error": (error or "")[:500],
            "context": json.dumps(context) if context else None,
        })
        doc.insert(ignore_permissions=True)
        return doc
```

- [ ] **Step 5: Create `Sync Dead Letter` DocType**

```bash
mkdir -p /home/ubuntu/frappe-bench/apps/pos_next/pos_next/pos_next/doctype/sync_dead_letter
touch /home/ubuntu/frappe-bench/apps/pos_next/pos_next/pos_next/doctype/sync_dead_letter/__init__.py
```

File: `pos_next/pos_next/doctype/sync_dead_letter/sync_dead_letter.json`

```json
{
 "actions": [],
 "autoname": "hash",
 "creation": "2026-04-05 00:00:00",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": [
  "reference_doctype",
  "reference_name",
  "operation",
  "last_error",
  "attempts",
  "payload",
  "moved_at"
 ],
 "fields": [
  {"fieldname": "reference_doctype", "fieldtype": "Link", "in_list_view": 1, "label": "Reference DocType", "options": "DocType"},
  {"fieldname": "reference_name", "fieldtype": "Data", "in_list_view": 1, "label": "Reference Name"},
  {"fieldname": "operation", "fieldtype": "Data", "in_list_view": 1, "label": "Operation"},
  {"fieldname": "last_error", "fieldtype": "Small Text", "label": "Last Error"},
  {"fieldname": "attempts", "fieldtype": "Int", "label": "Attempts"},
  {"fieldname": "payload", "fieldtype": "Long Text", "label": "Payload"},
  {"fieldname": "moved_at", "fieldtype": "Datetime", "label": "Moved At"}
 ],
 "index_web_pages_for_search": 0,
 "links": [],
 "modified": "2026-04-05 00:00:00",
 "modified_by": "Administrator",
 "module": "POS Next",
 "name": "Sync Dead Letter",
 "owner": "Administrator",
 "permissions": [
  {"create": 1, "delete": 1, "read": 1, "report": 1, "role": "System Manager", "write": 1}
 ],
 "row_format": "Dynamic",
 "sort_field": "moved_at",
 "sort_order": "DESC",
 "states": [],
 "track_changes": 0
}
```

File: `pos_next/pos_next/doctype/sync_dead_letter/sync_dead_letter.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class SyncDeadLetter(Document):
    """Outbox rows that exceeded max retries; awaiting human handling."""
    pass
```

- [ ] **Step 6: Create `Sync History` DocType**

```bash
mkdir -p /home/ubuntu/frappe-bench/apps/pos_next/pos_next/pos_next/doctype/sync_history
touch /home/ubuntu/frappe-bench/apps/pos_next/pos_next/pos_next/doctype/sync_history/__init__.py
```

File: `pos_next/pos_next/doctype/sync_history/sync_history.json`

```json
{
 "actions": [],
 "autoname": "hash",
 "creation": "2026-04-05 00:00:00",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": [
  "reference_doctype",
  "reference_name",
  "operation",
  "acked_at",
  "attempts",
  "payload_hash"
 ],
 "fields": [
  {"fieldname": "reference_doctype", "fieldtype": "Link", "in_list_view": 1, "label": "Reference DocType", "options": "DocType"},
  {"fieldname": "reference_name", "fieldtype": "Data", "in_list_view": 1, "label": "Reference Name"},
  {"fieldname": "operation", "fieldtype": "Data", "in_list_view": 1, "label": "Operation"},
  {"fieldname": "acked_at", "fieldtype": "Datetime", "in_list_view": 1, "label": "Acked At"},
  {"fieldname": "attempts", "fieldtype": "Int", "label": "Attempts"},
  {"fieldname": "payload_hash", "fieldtype": "Data", "label": "Payload Hash"}
 ],
 "index_web_pages_for_search": 0,
 "links": [],
 "modified": "2026-04-05 00:00:00",
 "modified_by": "Administrator",
 "module": "POS Next",
 "name": "Sync History",
 "owner": "Administrator",
 "permissions": [
  {"read": 1, "report": 1, "role": "System Manager"}
 ],
 "row_format": "Dynamic",
 "sort_field": "acked_at",
 "sort_order": "DESC",
 "states": [],
 "track_changes": 0
}
```

File: `pos_next/pos_next/doctype/sync_history/sync_history.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class SyncHistory(Document):
    """Archived acknowledged Sync Outbox rows."""
    pass
```

- [ ] **Step 7: Run migrate**

```bash
cd /home/ubuntu/frappe-bench
bench --site <site-name> migrate
```

Expected: all 6 new DocTypes created.

- [ ] **Step 8: Quick smoke test**

```bash
bench --site <site-name> execute 'frappe.db.sql("SELECT COUNT(*) FROM `tabSync Log`")'
```

Expected: `((0,),)` — table exists.

- [ ] **Step 9: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/pos_next/doctype/sync_record_state/ pos_next/pos_next/doctype/sync_field_timestamp/ pos_next/pos_next/doctype/sync_conflict/ pos_next/pos_next/doctype/sync_log/ pos_next/pos_next/doctype/sync_dead_letter/ pos_next/pos_next/doctype/sync_history/
git commit -m "feat(sync): add tracking doctypes (record state, field timestamp, conflict, log, dead letter, history)"
```

---

### Task 7: Create `pos_next/sync/` module skeleton — defaults, exceptions, payload helpers

**Files:**
- Create: `pos_next/sync/defaults.py`
- Create: `pos_next/sync/exceptions.py`
- Create: `pos_next/sync/payload.py`
- Create: `pos_next/sync/tests/test_payload.py`

- [ ] **Step 1: Create `defaults.py`**

File: `pos_next/sync/defaults.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Centralized defaults for the sync engine."""

DEFAULT_PUSH_INTERVAL_SECONDS = 60
DEFAULT_PULL_MASTERS_INTERVAL_SECONDS = 300
DEFAULT_PULL_FAILOVER_INTERVAL_SECONDS = 120

DEFAULT_BATCH_SIZE = 100
MAX_ATTEMPTS_BEFORE_DEAD = 10
REPLAY_REJECT_HOURS = 24

HTTP_TIMEOUT_SECONDS = 30
LOGIN_TIMEOUT_SECONDS = 10

# Outbox back-pressure thresholds
OUTBOX_WARN_DEPTH = 1000
OUTBOX_CRITICAL_DEPTH = 10000

# Retention
HISTORY_ARCHIVE_AFTER_DAYS = 7
HISTORY_PURGE_AFTER_DAYS = 90
TOMBSTONE_RETAIN_DAYS = 90

# Conflict rules
CONFLICT_RULES = {
    "Last-Write-Wins",
    "Central-Wins",
    "Branch-Wins",
    "Field-Level-LWW",
    "Manual",
}
CDC_STRATEGIES = {"Outbox", "Watermark"}
DIRECTIONS = {"Central→Branch", "Branch→Central", "Bidirectional"}
```

- [ ] **Step 2: Create `exceptions.py`**

File: `pos_next/sync/exceptions.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Sync engine exception hierarchy."""


class SyncError(Exception):
    """Base class for all sync engine errors."""
    pass


class SyncAuthError(SyncError):
    """Authentication against central failed (bad credentials, expired session)."""
    pass


class SyncTransportError(SyncError):
    """HTTP/network-level failure talking to central."""
    pass


class SyncConflictError(SyncError):
    """A conflict was detected and resolution is deferred to human review."""
    pass


class SyncValidationError(SyncError):
    """Incoming payload failed adapter.validate_incoming()."""
    pass


class SyncReplayRejected(SyncError):
    """Payload rejected because created_at is older than the replay window."""
    pass
```

- [ ] **Step 3: Write failing tests for `payload.py`**

File: `pos_next/sync/tests/test_payload.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe


def test_compute_hash_stable():
    """Same payload (order-independent) produces same hash."""
    from pos_next.sync.payload import compute_hash
    a = {"name": "ITEM-001", "item_name": "Apple", "price": 100}
    b = {"price": 100, "name": "ITEM-001", "item_name": "Apple"}
    assert compute_hash(a) == compute_hash(b)
    print("PASS: test_compute_hash_stable")


def test_compute_hash_different_on_change():
    from pos_next.sync.payload import compute_hash
    a = {"name": "ITEM-001", "price": 100}
    b = {"name": "ITEM-001", "price": 101}
    assert compute_hash(a) != compute_hash(b)
    print("PASS: test_compute_hash_different_on_change")


def test_compute_hash_ignores_meta_fields():
    """modified, modified_by, owner, creation are excluded from hash."""
    from pos_next.sync.payload import compute_hash
    a = {"name": "ITEM-001", "price": 100, "modified": "2026-04-05 10:00:00", "modified_by": "a@x.com"}
    b = {"name": "ITEM-001", "price": 100, "modified": "2026-04-05 11:00:00", "modified_by": "b@x.com"}
    assert compute_hash(a) == compute_hash(b)
    print("PASS: test_compute_hash_ignores_meta_fields")


def test_strip_meta():
    """strip_meta removes server-side meta fields."""
    from pos_next.sync.payload import strip_meta
    payload = {
        "name": "ITEM-001",
        "price": 100,
        "modified": "2026-04-05",
        "modified_by": "a@x.com",
        "owner": "admin",
        "creation": "2026-01-01",
        "docstatus": 0,
    }
    stripped = strip_meta(payload)
    assert "modified" not in stripped
    assert "modified_by" not in stripped
    assert "owner" not in stripped
    assert "creation" not in stripped
    assert stripped["name"] == "ITEM-001"
    assert stripped["price"] == 100
    assert "docstatus" in stripped  # docstatus is kept — it's semantic
    print("PASS: test_strip_meta")


def run_all():
    test_compute_hash_stable()
    test_compute_hash_different_on_change()
    test_compute_hash_ignores_meta_fields()
    test_strip_meta()
    print("\nAll Payload tests PASSED")
```

- [ ] **Step 4: Run test to confirm failure**

```bash
cd /home/ubuntu/frappe-bench
bench --site <site-name> execute pos_next.sync.tests.test_payload.run_all
```

Expected: FAIL — ImportError (no `payload` module).

- [ ] **Step 5: Create `payload.py`**

File: `pos_next/sync/payload.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Payload serialization, hashing, and meta-stripping helpers."""

import hashlib
import json


# Fields we strip before hashing (they change on every save, aren't semantic)
META_FIELDS = {
    "modified",
    "modified_by",
    "owner",
    "creation",
    "idx",
    "_user_tags",
    "_comments",
    "_assign",
    "_liked_by",
}


def strip_meta(payload):
    """Return a copy of payload with server-side meta fields removed."""
    return {k: v for k, v in payload.items() if k not in META_FIELDS}


def compute_hash(payload):
    """
    Return SHA256 hex of a canonical JSON serialization of the payload,
    excluding meta fields. Key order does not affect the hash.
    """
    clean = strip_meta(payload)
    canonical = json.dumps(clean, sort_keys=True, default=str, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def to_payload(doc):
    """
    Convert a Frappe Document to a sync payload dict.
    Includes children via Frappe's as_dict(); caller strips meta as needed.
    """
    if hasattr(doc, "as_dict"):
        return doc.as_dict(convert_dates_to_str=True)
    return dict(doc)
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd /home/ubuntu/frappe-bench
bench --site <site-name> execute pos_next.sync.tests.test_payload.run_all
```

Expected: all 4 tests PASS.

- [ ] **Step 7: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/sync/defaults.py pos_next/sync/exceptions.py pos_next/sync/payload.py pos_next/sync/tests/test_payload.py
git commit -m "feat(sync): add defaults, exceptions, and payload helpers"
```

---

### Task 8: Create `BaseSyncAdapter` abstract class and adapter registry

**Files:**
- Create: `pos_next/sync/adapters/__init__.py`
- Create: `pos_next/sync/adapters/base.py`
- Create: `pos_next/sync/registry.py`
- Create: `pos_next/sync/tests/test_base_adapter.py`
- Create: `pos_next/sync/tests/test_registry.py`

- [ ] **Step 1: Create adapters directory**

```bash
mkdir -p /home/ubuntu/frappe-bench/apps/pos_next/pos_next/sync/adapters
touch /home/ubuntu/frappe-bench/apps/pos_next/pos_next/sync/adapters/__init__.py
```

- [ ] **Step 2: Write failing tests for BaseSyncAdapter and registry**

File: `pos_next/sync/tests/test_base_adapter.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt


def test_base_adapter_interface():
    """BaseSyncAdapter has the expected methods."""
    from pos_next.sync.adapters.base import BaseSyncAdapter
    required = {"serialize", "apply_incoming", "conflict_key", "validate_incoming", "pre_apply_transform"}
    for method in required:
        assert hasattr(BaseSyncAdapter, method), f"Missing: {method}"
    print("PASS: test_base_adapter_interface")


def test_base_adapter_default_conflict_key():
    """Default conflict_key returns ('name',)."""
    from pos_next.sync.adapters.base import BaseSyncAdapter

    class DummyAdapter(BaseSyncAdapter):
        doctype = "Item"

    adapter = DummyAdapter()
    assert adapter.conflict_key({"name": "ITEM-001"}) == ("name",)
    print("PASS: test_base_adapter_default_conflict_key")


def test_base_adapter_default_validate_passes():
    """Default validate_incoming does nothing (no raise)."""
    from pos_next.sync.adapters.base import BaseSyncAdapter

    class DummyAdapter(BaseSyncAdapter):
        doctype = "Item"

    adapter = DummyAdapter()
    adapter.validate_incoming({"name": "ITEM-001"})  # should not raise
    print("PASS: test_base_adapter_default_validate_passes")


def test_base_adapter_default_pre_apply_transform_identity():
    """Default pre_apply_transform returns payload unchanged."""
    from pos_next.sync.adapters.base import BaseSyncAdapter

    class DummyAdapter(BaseSyncAdapter):
        doctype = "Item"

    adapter = DummyAdapter()
    p = {"name": "ITEM-001", "price": 100}
    result = adapter.pre_apply_transform(p)
    assert result == p
    print("PASS: test_base_adapter_default_pre_apply_transform_identity")


def run_all():
    test_base_adapter_interface()
    test_base_adapter_default_conflict_key()
    test_base_adapter_default_validate_passes()
    test_base_adapter_default_pre_apply_transform_identity()
    print("\nAll BaseSyncAdapter tests PASSED")
```

File: `pos_next/sync/tests/test_registry.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt


def test_registry_register_and_lookup():
    from pos_next.sync.adapters.base import BaseSyncAdapter
    from pos_next.sync import registry

    class FakeItemAdapter(BaseSyncAdapter):
        doctype = "Fake Item"

    registry.register(FakeItemAdapter)
    got = registry.get_adapter("Fake Item")
    assert isinstance(got, FakeItemAdapter)
    print("PASS: test_registry_register_and_lookup")


def test_registry_unknown_returns_none():
    from pos_next.sync import registry
    got = registry.get_adapter("Does Not Exist")
    assert got is None
    print("PASS: test_registry_unknown_returns_none")


def test_registry_list_registered():
    from pos_next.sync.adapters.base import BaseSyncAdapter
    from pos_next.sync import registry

    class A(BaseSyncAdapter):
        doctype = "Alpha"

    class B(BaseSyncAdapter):
        doctype = "Beta"

    registry.register(A)
    registry.register(B)
    registered = registry.list_registered()
    assert "Alpha" in registered
    assert "Beta" in registered
    print("PASS: test_registry_list_registered")


def run_all():
    test_registry_register_and_lookup()
    test_registry_unknown_returns_none()
    test_registry_list_registered()
    print("\nAll Registry tests PASSED")
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
cd /home/ubuntu/frappe-bench
bench --site <site-name> execute pos_next.sync.tests.test_base_adapter.run_all
bench --site <site-name> execute pos_next.sync.tests.test_registry.run_all
```

Expected: FAIL — modules missing.

- [ ] **Step 4: Create `BaseSyncAdapter`**

File: `pos_next/sync/adapters/base.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Base class for per-DocType sync adapters."""

import frappe
from pos_next.sync.payload import to_payload


class BaseSyncAdapter:
    """
    Subclass per synced DocType. Override methods as needed.

    Each subclass MUST set the class attribute `doctype`.
    """
    doctype: str = ""

    def serialize(self, doc):
        """Build a sync payload dict from a Frappe Document."""
        return to_payload(doc)

    def apply_incoming(self, payload, operation):
        """
        Apply an incoming payload locally. Default implementation:
        - delete operation → delete local record if exists
        - insert/update/submit/cancel → upsert

        Returns the local document name.
        """
        name = payload.get("name")
        if not name:
            raise ValueError(f"{self.doctype}: payload missing 'name' field")

        if operation == "delete":
            if frappe.db.exists(self.doctype, name):
                frappe.delete_doc(self.doctype, name, ignore_permissions=True, force=True)
            return name

        payload = self.pre_apply_transform(payload)

        if frappe.db.exists(self.doctype, name):
            doc = frappe.get_doc(self.doctype, name)
            doc.update(payload)
            doc.save(ignore_permissions=True)
        else:
            payload_with_doctype = {"doctype": self.doctype, **payload}
            doc = frappe.get_doc(payload_with_doctype)
            doc.insert(ignore_permissions=True)
        return doc.name

    def conflict_key(self, payload):
        """Tuple of fieldnames that identify this record across sites."""
        return ("name",)

    def validate_incoming(self, payload):
        """Raise on invalid payload. Default: accept everything."""
        return None

    def pre_apply_transform(self, payload):
        """Transform payload before apply. Default: identity."""
        return payload
```

- [ ] **Step 5: Create registry**

File: `pos_next/sync/registry.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Sync adapter registry. Adapters register themselves at import time."""

_REGISTRY = {}


def register(adapter_class):
    """Register an adapter class. adapter_class.doctype must be set."""
    if not getattr(adapter_class, "doctype", None):
        raise ValueError(f"Adapter {adapter_class.__name__} has no doctype attribute")
    _REGISTRY[adapter_class.doctype] = adapter_class


def get_adapter(doctype):
    """Return an instance of the adapter for a DocType, or None."""
    cls = _REGISTRY.get(doctype)
    return cls() if cls else None


def list_registered():
    """Return a list of DocType names that have registered adapters."""
    return list(_REGISTRY.keys())


def clear():
    """Clear the registry. For tests only."""
    _REGISTRY.clear()
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd /home/ubuntu/frappe-bench
bench --site <site-name> execute pos_next.sync.tests.test_base_adapter.run_all
bench --site <site-name> execute pos_next.sync.tests.test_registry.run_all
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/sync/adapters/ pos_next/sync/registry.py pos_next/sync/tests/test_base_adapter.py pos_next/sync/tests/test_registry.py
git commit -m "feat(sync): add BaseSyncAdapter and adapter registry"
```

---

### Task 9: Create conflict resolution engine

**Files:**
- Create: `pos_next/sync/conflict.py`
- Create: `pos_next/sync/tests/test_conflict.py`

- [ ] **Step 1: Write failing tests**

File: `pos_next/sync/tests/test_conflict.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

from datetime import datetime


def test_last_write_wins_incoming_newer():
    from pos_next.sync.conflict import resolve
    local = {"name": "X", "v": 1, "modified": "2026-04-05 10:00:00"}
    incoming = {"name": "X", "v": 2, "modified": "2026-04-05 11:00:00"}
    winner, verdict = resolve(local, incoming, "Last-Write-Wins")
    assert winner is incoming
    assert verdict == "incoming"
    print("PASS: test_last_write_wins_incoming_newer")


def test_last_write_wins_local_newer():
    from pos_next.sync.conflict import resolve
    local = {"name": "X", "v": 1, "modified": "2026-04-05 12:00:00"}
    incoming = {"name": "X", "v": 2, "modified": "2026-04-05 11:00:00"}
    winner, verdict = resolve(local, incoming, "Last-Write-Wins")
    assert winner is local
    assert verdict == "local"
    print("PASS: test_last_write_wins_local_newer")


def test_last_write_wins_tie_goes_to_incoming():
    from pos_next.sync.conflict import resolve
    ts = "2026-04-05 10:00:00"
    local = {"name": "X", "v": 1, "modified": ts}
    incoming = {"name": "X", "v": 2, "modified": ts}
    winner, verdict = resolve(local, incoming, "Last-Write-Wins")
    assert winner is incoming
    print("PASS: test_last_write_wins_tie_goes_to_incoming")


def test_central_wins():
    from pos_next.sync.conflict import resolve
    local = {"name": "X", "v": 1}
    incoming = {"name": "X", "v": 2}
    winner, verdict = resolve(local, incoming, "Central-Wins")
    assert winner is incoming
    assert verdict == "incoming"
    print("PASS: test_central_wins")


def test_branch_wins():
    from pos_next.sync.conflict import resolve
    local = {"name": "X", "v": 1}
    incoming = {"name": "X", "v": 2}
    winner, verdict = resolve(local, incoming, "Branch-Wins")
    assert winner is incoming
    assert verdict == "incoming"
    print("PASS: test_branch_wins")


def test_manual_rule_raises():
    from pos_next.sync.conflict import resolve
    from pos_next.sync.exceptions import SyncConflictError
    local = {"name": "X", "v": 1}
    incoming = {"name": "X", "v": 2}
    raised = False
    try:
        resolve(local, incoming, "Manual")
    except SyncConflictError:
        raised = True
    assert raised, "Manual rule should raise SyncConflictError"
    print("PASS: test_manual_rule_raises")


def test_field_level_lww_merges_per_field():
    from pos_next.sync.conflict import resolve
    local = {
        "name": "X",
        "field_a": "local-a",
        "field_b": "local-b",
        "__field_ts": {"field_a": "2026-04-05 10:00:00", "field_b": "2026-04-05 12:00:00"},
    }
    incoming = {
        "name": "X",
        "field_a": "incoming-a",
        "field_b": "incoming-b",
        "__field_ts": {"field_a": "2026-04-05 11:00:00", "field_b": "2026-04-05 11:00:00"},
    }
    winner, verdict = resolve(local, incoming, "Field-Level-LWW")
    assert verdict == "merged"
    assert winner["field_a"] == "incoming-a"  # incoming had newer ts
    assert winner["field_b"] == "local-b"     # local had newer ts
    print("PASS: test_field_level_lww_merges_per_field")


def test_unknown_rule_raises():
    from pos_next.sync.conflict import resolve
    raised = False
    try:
        resolve({}, {}, "NotARealRule")
    except ValueError:
        raised = True
    assert raised
    print("PASS: test_unknown_rule_raises")


def run_all():
    test_last_write_wins_incoming_newer()
    test_last_write_wins_local_newer()
    test_last_write_wins_tie_goes_to_incoming()
    test_central_wins()
    test_branch_wins()
    test_manual_rule_raises()
    test_field_level_lww_merges_per_field()
    test_unknown_rule_raises()
    print("\nAll Conflict tests PASSED")
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
cd /home/ubuntu/frappe-bench
bench --site <site-name> execute pos_next.sync.tests.test_conflict.run_all
```

Expected: FAIL — module missing.

- [ ] **Step 3: Create `conflict.py`**

File: `pos_next/sync/conflict.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Conflict resolution strategies."""

from pos_next.sync.defaults import CONFLICT_RULES
from pos_next.sync.exceptions import SyncConflictError


def resolve(local, incoming, rule):
    """
    Apply a conflict resolution rule to two payloads.

    Returns (winner_payload, verdict) where verdict is one of:
      "local", "incoming", "merged".

    Raises:
      SyncConflictError if rule is "Manual".
      ValueError if rule is not recognized.
    """
    if rule not in CONFLICT_RULES:
        raise ValueError(f"Unknown conflict rule: {rule}")

    if rule == "Manual":
        raise SyncConflictError(
            f"Manual resolution required for {incoming.get('name', '<unnamed>')}"
        )

    if rule == "Central-Wins":
        return incoming, "incoming"

    if rule == "Branch-Wins":
        return incoming, "incoming"

    if rule == "Last-Write-Wins":
        local_ts = str(local.get("modified") or "")
        incoming_ts = str(incoming.get("modified") or "")
        if incoming_ts >= local_ts:
            return incoming, "incoming"
        return local, "local"

    if rule == "Field-Level-LWW":
        return _merge_field_level(local, incoming), "merged"

    raise ValueError(f"Unimplemented conflict rule: {rule}")


def _merge_field_level(local, incoming):
    """
    Merge two payloads field-by-field based on per-field timestamps.

    Both payloads must carry a `__field_ts` dict mapping fieldname → timestamp.
    For each field, the value from whichever payload has the newer timestamp wins.
    Fields with no timestamp entry default to local's value.
    """
    local_ts = local.get("__field_ts", {}) or {}
    incoming_ts = incoming.get("__field_ts", {}) or {}

    merged = dict(local)
    all_fields = set(local.keys()) | set(incoming.keys())
    all_fields.discard("__field_ts")

    for field in all_fields:
        l_ts = str(local_ts.get(field, ""))
        i_ts = str(incoming_ts.get(field, ""))
        if i_ts and i_ts > l_ts:
            merged[field] = incoming.get(field)

    # Merge the timestamp maps too — keep max per field
    merged_ts = dict(local_ts)
    for f, ts in incoming_ts.items():
        if str(ts) > str(merged_ts.get(f, "")):
            merged_ts[f] = ts
    merged["__field_ts"] = merged_ts
    return merged
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/ubuntu/frappe-bench
bench --site <site-name> execute pos_next.sync.tests.test_conflict.run_all
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/sync/conflict.py pos_next/sync/tests/test_conflict.py
git commit -m "feat(sync): add conflict resolution engine with 5 strategies"
```

---

### Task 10: Create HTTP transport + auth helper (`auth.py`, `transport.py`)

**Files:**
- Create: `pos_next/sync/auth.py`
- Create: `pos_next/sync/transport.py`
- Create: `pos_next/sync/tests/test_auth.py`

- [ ] **Step 1: Write failing tests**

File: `pos_next/sync/tests/test_auth.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

from unittest.mock import patch, MagicMock


def test_session_login_caches_sid():
    """After login, the session cookie (sid) is held in memory."""
    from pos_next.sync.auth import SyncSession

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.cookies = {"sid": "test-sid-xyz"}
    fake_response.raise_for_status = MagicMock()

    with patch("pos_next.sync.auth.requests.post", return_value=fake_response) as mock_post:
        session = SyncSession(
            central_url="https://central.test",
            username="sync@test.com",
            password="pw",
        )
        session.login()
        assert session._sid == "test-sid-xyz"
        # Second call does NOT re-login
        session.login()
        assert mock_post.call_count == 1
    print("PASS: test_session_login_caches_sid")


def test_session_login_failure_raises():
    """Failed login raises SyncAuthError."""
    from pos_next.sync.auth import SyncSession
    from pos_next.sync.exceptions import SyncAuthError
    import requests

    fake_response = MagicMock()
    fake_response.status_code = 401
    fake_response.raise_for_status = MagicMock(
        side_effect=requests.HTTPError("401 Unauthorized")
    )

    with patch("pos_next.sync.auth.requests.post", return_value=fake_response):
        session = SyncSession(
            central_url="https://central.test",
            username="sync@test.com",
            password="bad",
        )
        raised = False
        try:
            session.login()
        except SyncAuthError:
            raised = True
        assert raised
    print("PASS: test_session_login_failure_raises")


def test_session_auto_relogin_on_401():
    """A 401 response from an authenticated request triggers one re-login + retry."""
    from pos_next.sync.auth import SyncSession

    # First login succeeds
    login_resp = MagicMock()
    login_resp.status_code = 200
    login_resp.cookies = {"sid": "sid-1"}
    login_resp.raise_for_status = MagicMock()

    # First authenticated call returns 401
    call_resp_401 = MagicMock()
    call_resp_401.status_code = 401

    # Re-login produces new sid
    login_resp_2 = MagicMock()
    login_resp_2.status_code = 200
    login_resp_2.cookies = {"sid": "sid-2"}
    login_resp_2.raise_for_status = MagicMock()

    # Retry succeeds
    call_resp_ok = MagicMock()
    call_resp_ok.status_code = 200
    call_resp_ok.json = MagicMock(return_value={"message": "ok"})
    call_resp_ok.raise_for_status = MagicMock()

    with patch("pos_next.sync.auth.requests.post") as mock_post:
        mock_post.side_effect = [login_resp, call_resp_401, login_resp_2, call_resp_ok]
        session = SyncSession(
            central_url="https://central.test",
            username="sync@test.com",
            password="pw",
        )
        session.login()
        result = session.post("/api/method/something", data={"x": 1})
        assert result.status_code == 200
        assert session._sid == "sid-2"
    print("PASS: test_session_auto_relogin_on_401")


def run_all():
    test_session_login_caches_sid()
    test_session_login_failure_raises()
    test_session_auto_relogin_on_401()
    print("\nAll Auth tests PASSED")
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
cd /home/ubuntu/frappe-bench
bench --site <site-name> execute pos_next.sync.tests.test_auth.run_all
```

Expected: FAIL — module missing.

- [ ] **Step 3: Create `auth.py`**

File: `pos_next/sync/auth.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Username/password session login against central."""

import requests

from pos_next.sync.defaults import HTTP_TIMEOUT_SECONDS, LOGIN_TIMEOUT_SECONDS
from pos_next.sync.exceptions import SyncAuthError, SyncTransportError


class SyncSession:
    """
    Holds a logged-in session against central.

    Login happens lazily on first use. On a 401 response, we automatically
    re-log in once and retry the original request.
    """

    def __init__(self, central_url, username, password):
        self.central_url = central_url.rstrip("/")
        self.username = username
        self.password = password
        self._sid = None

    def login(self):
        """POST /api/method/login. Cache sid in memory."""
        if self._sid:
            return
        url = f"{self.central_url}/api/method/login"
        try:
            resp = requests.post(
                url,
                data={"usr": self.username, "pwd": self.password},
                timeout=LOGIN_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
        except requests.HTTPError as e:
            raise SyncAuthError(f"Login failed for {self.username}: {e}")
        except requests.RequestException as e:
            raise SyncTransportError(f"Login request failed: {e}")
        sid = resp.cookies.get("sid")
        if not sid:
            raise SyncAuthError("Login response did not include sid cookie")
        self._sid = sid

    def _cookies(self):
        return {"sid": self._sid} if self._sid else {}

    def post(self, path, data=None, json=None):
        """Authenticated POST. On 401, re-login and retry once."""
        self.login()
        url = f"{self.central_url}{path}"
        resp = requests.post(
            url,
            data=data,
            json=json,
            cookies=self._cookies(),
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        if resp.status_code == 401:
            self._sid = None
            self.login()
            resp = requests.post(
                url,
                data=data,
                json=json,
                cookies=self._cookies(),
                timeout=HTTP_TIMEOUT_SECONDS,
            )
        return resp

    def get(self, path, params=None):
        """Authenticated GET. On 401, re-login and retry once."""
        self.login()
        url = f"{self.central_url}{path}"
        resp = requests.get(
            url,
            params=params,
            cookies=self._cookies(),
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        if resp.status_code == 401:
            self._sid = None
            self.login()
            resp = requests.get(
                url,
                params=params,
                cookies=self._cookies(),
                timeout=HTTP_TIMEOUT_SECONDS,
            )
        return resp

    def logout(self):
        """POST /api/method/logout. Best-effort; ignore errors."""
        if not self._sid:
            return
        try:
            requests.post(
                f"{self.central_url}/api/method/logout",
                cookies=self._cookies(),
                timeout=LOGIN_TIMEOUT_SECONDS,
            )
        except requests.RequestException:
            pass
        self._sid = None
```

- [ ] **Step 4: Create `transport.py`**

File: `pos_next/sync/transport.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""HTTP transport helpers wrapping SyncSession.

Provides a factory that builds a SyncSession from the Sync Site Config record.
"""

import frappe

from pos_next.sync.auth import SyncSession
from pos_next.sync.exceptions import SyncAuthError


def build_session_from_config():
    """
    Read the (singleton) Branch Sync Site Config and return a SyncSession.

    Raises SyncAuthError if no Branch config exists or credentials are missing.
    """
    name = frappe.db.get_value("Sync Site Config", {"site_role": "Branch"}, "name")
    if not name:
        raise SyncAuthError("No Branch Sync Site Config found on this site")
    cfg = frappe.get_doc("Sync Site Config", name)
    if not (cfg.central_url and cfg.sync_username and cfg.sync_password):
        raise SyncAuthError("Branch Sync Site Config missing credentials")
    password = cfg.get_password("sync_password")
    return SyncSession(
        central_url=cfg.central_url,
        username=cfg.sync_username,
        password=password,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /home/ubuntu/frappe-bench
bench --site <site-name> execute pos_next.sync.tests.test_auth.run_all
```

Expected: all 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/sync/auth.py pos_next/sync/transport.py pos_next/sync/tests/test_auth.py
git commit -m "feat(sync): add SyncSession auth + transport factory"
```

---

### Task 11: Add "Test Sync Connection" button on Sync Site Config form

**Files:**
- Modify: `pos_next/pos_next/doctype/sync_site_config/sync_site_config.js`
- Modify: `pos_next/pos_next/doctype/sync_site_config/sync_site_config.py` (add whitelisted method)

- [ ] **Step 1: Add whitelisted `test_connection` method to the DocType controller**

File: `pos_next/pos_next/doctype/sync_site_config/sync_site_config.py`

Append to the class:

```python
    @frappe.whitelist()
    def test_connection(self):
        """
        Attempt login against central and return a short status message.
        Only meaningful on Branch-role configs.
        """
        if self.site_role != "Branch":
            return {"ok": False, "message": "Test Connection only applies to Branch role"}
        if not (self.central_url and self.sync_username and self.sync_password):
            return {"ok": False, "message": "Fill central_url, sync_username, sync_password first"}

        from pos_next.sync.auth import SyncSession
        from pos_next.sync.exceptions import SyncAuthError, SyncTransportError

        password = self.get_password("sync_password")
        session = SyncSession(
            central_url=self.central_url,
            username=self.sync_username,
            password=password,
        )
        try:
            session.login()
        except SyncAuthError as e:
            return {"ok": False, "message": f"Auth failed: {e}"}
        except SyncTransportError as e:
            return {"ok": False, "message": f"Network error: {e}"}
        except Exception as e:
            return {"ok": False, "message": f"Unexpected error: {e}"}
        finally:
            session.logout()
        return {"ok": True, "message": f"Connected to {self.central_url} as {self.sync_username}"}
```

Also add the `frappe` import at the top if not already there.

- [ ] **Step 2: Add button in the JS form**

File: `pos_next/pos_next/doctype/sync_site_config/sync_site_config.js`

```javascript
// Copyright (c) 2026, BrainWise and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sync Site Config", {
    refresh(frm) {
        if (frm.doc.site_role === "Branch" && !frm.is_new()) {
            frm.add_custom_button(__("Test Sync Connection"), () => {
                frappe.call({
                    doc: frm.doc,
                    method: "test_connection",
                    freeze: true,
                    freeze_message: __("Testing connection..."),
                    callback(r) {
                        if (!r.message) return;
                        const msg = r.message.message;
                        const ok = r.message.ok;
                        frappe.msgprint({
                            title: ok ? __("Connection OK") : __("Connection Failed"),
                            message: msg,
                            indicator: ok ? "green" : "red",
                        });
                    },
                });
            });
        }
    },
});
```

- [ ] **Step 3: Manual smoke test — create a branch config and click the button**

Via UI or bench command:

```bash
bench --site <site-name> execute 'frappe.get_doc({"doctype":"Sync Site Config","site_role":"Branch","branch_code":"TEST","enabled":0,"central_url":"https://nonexistent.test","sync_username":"x@x.com","sync_password":"x"}).insert(ignore_permissions=True)'
```

Open the form in the desk, click "Test Sync Connection". Expect a red "Network error" dialog (host doesn't exist). Delete the test record afterward:

```bash
bench --site <site-name> execute 'frappe.delete_doc("Sync Site Config", "TEST", force=1)'
```

- [ ] **Step 4: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/pos_next/doctype/sync_site_config/sync_site_config.py pos_next/pos_next/doctype/sync_site_config/sync_site_config.js
git commit -m "feat(sync): add Test Sync Connection button on Sync Site Config form"
```

---

### Task 12: Install custom fields (`sync_uuid`, `origin_branch`, `synced_from_failover`) via patch

**Files:**
- Create: `pos_next/patches/v2_0_0/__init__.py` (if missing)
- Create: `pos_next/patches/v2_0_0/add_sync_custom_fields.py`
- Modify: `pos_next/patches.txt`
- Create: `pos_next/sync/tests/test_custom_fields.py`

- [ ] **Step 1: Ensure patches dir exists**

```bash
ls /home/ubuntu/frappe-bench/apps/pos_next/pos_next/patches/v2_0_0/ || mkdir -p /home/ubuntu/frappe-bench/apps/pos_next/pos_next/patches/v2_0_0
touch /home/ubuntu/frappe-bench/apps/pos_next/pos_next/patches/v2_0_0/__init__.py
```

- [ ] **Step 2: Write failing test for custom fields**

File: `pos_next/sync/tests/test_custom_fields.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe


TARGET_DOCTYPES = [
    "Sales Invoice",
    "Payment Entry",
    "Stock Ledger Entry",
    "POS Opening Shift",
    "POS Closing Shift",
    "Customer",
]

EXPECTED_FIELDS = {"sync_uuid", "origin_branch", "synced_from_failover"}


def test_custom_fields_installed():
    """All three sync custom fields are installed on every target DocType."""
    for dt in TARGET_DOCTYPES:
        for fieldname in EXPECTED_FIELDS:
            exists = frappe.db.exists(
                "Custom Field", {"dt": dt, "fieldname": fieldname}
            )
            assert exists, f"Missing custom field {fieldname} on {dt}"
    print("PASS: test_custom_fields_installed")


def test_sync_uuid_is_unique():
    """sync_uuid has unique=1 on target DocTypes."""
    for dt in TARGET_DOCTYPES:
        cf = frappe.db.get_value(
            "Custom Field",
            {"dt": dt, "fieldname": "sync_uuid"},
            ["fieldtype", "unique"],
            as_dict=True,
        )
        assert cf is not None, f"sync_uuid missing on {dt}"
        assert cf.fieldtype == "Data", f"sync_uuid should be Data on {dt}"
        assert cf.unique == 1, f"sync_uuid should be unique on {dt}"
    print("PASS: test_sync_uuid_is_unique")


def run_all():
    test_custom_fields_installed()
    test_sync_uuid_is_unique()
    print("\nAll Custom Fields tests PASSED")
```

- [ ] **Step 3: Run test to confirm failure**

```bash
cd /home/ubuntu/frappe-bench
bench --site <site-name> execute pos_next.sync.tests.test_custom_fields.run_all
```

Expected: FAIL — custom fields don't exist yet.

- [ ] **Step 4: Write the patch**

File: `pos_next/patches/v2_0_0/add_sync_custom_fields.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Install sync_uuid, origin_branch, synced_from_failover custom fields."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


TARGET_DOCTYPES = [
    "Sales Invoice",
    "Payment Entry",
    "Stock Ledger Entry",
    "POS Opening Shift",
    "POS Closing Shift",
    "Customer",
]


def execute():
    fields_per_doctype = {}
    for dt in TARGET_DOCTYPES:
        fields_per_doctype[dt] = [
            {
                "fieldname": "sync_uuid",
                "label": "Sync UUID",
                "fieldtype": "Data",
                "unique": 1,
                "read_only": 1,
                "no_copy": 1,
                "description": "Cross-site dedup key; set at creation",
                "insert_after": "name" if dt == "Customer" else None,
            },
            {
                "fieldname": "origin_branch",
                "label": "Origin Branch",
                "fieldtype": "Data",
                "read_only": 1,
                "no_copy": 1,
                "description": "branch_code of the site that originated this record",
            },
            {
                "fieldname": "synced_from_failover",
                "label": "Synced From Failover",
                "fieldtype": "Check",
                "read_only": 1,
                "no_copy": 1,
                "default": "0",
                "description": "1 when central wrote this record as a failover proxy for a branch",
            },
        ]
    create_custom_fields(fields_per_doctype, update=True)
    frappe.db.commit()
    print(f"Installed sync custom fields on {len(TARGET_DOCTYPES)} doctypes")
```

- [ ] **Step 5: Register the patch**

Append to `pos_next/patches.txt` under `[post_model_sync]`:

```
pos_next.patches.v2_0_0.add_sync_custom_fields
```

- [ ] **Step 6: Run the patch**

```bash
cd /home/ubuntu/frappe-bench
bench --site <site-name> migrate
```

Expected: patch output "Installed sync custom fields on 6 doctypes".

- [ ] **Step 7: Run test to verify it passes**

```bash
bench --site <site-name> execute pos_next.sync.tests.test_custom_fields.run_all
```

Expected: both tests PASS.

- [ ] **Step 8: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/patches/v2_0_0/ pos_next/patches.txt pos_next/sync/tests/test_custom_fields.py
git commit -m "feat(sync): install sync_uuid, origin_branch, synced_from_failover custom fields"
```

---

### Task 13: Backfill `sync_uuid` on existing transaction rows (idempotent patch)

**Files:**
- Create: `pos_next/patches/v2_0_0/backfill_sync_uuid.py`
- Modify: `pos_next/patches.txt`
- Create: `pos_next/sync/tests/test_backfill.py`

- [ ] **Step 1: Write failing test**

File: `pos_next/sync/tests/test_backfill.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe


TARGET_DOCTYPES = [
    "Sales Invoice",
    "Payment Entry",
    "Stock Ledger Entry",
    "POS Opening Shift",
    "POS Closing Shift",
    "Customer",
]


def test_no_null_sync_uuids_after_backfill():
    """After the backfill runs, no rows in target DocTypes have NULL sync_uuid."""
    from pos_next.patches.v2_0_0.backfill_sync_uuid import execute

    execute()  # idempotent

    for dt in TARGET_DOCTYPES:
        # Some tables may be empty on a fresh install — skip those
        total = frappe.db.count(dt)
        if total == 0:
            continue
        null_count = frappe.db.sql(
            f"SELECT COUNT(*) FROM `tab{dt}` WHERE sync_uuid IS NULL OR sync_uuid = ''"
        )[0][0]
        assert null_count == 0, f"{dt}: {null_count} rows have NULL sync_uuid"
    print("PASS: test_no_null_sync_uuids_after_backfill")


def test_backfill_is_idempotent():
    """Running the backfill twice does not change existing UUIDs."""
    from pos_next.patches.v2_0_0.backfill_sync_uuid import execute

    execute()
    # Snapshot a few
    rows_before = frappe.db.sql(
        "SELECT name, sync_uuid FROM `tabCustomer` WHERE sync_uuid IS NOT NULL LIMIT 5",
        as_dict=True,
    )
    execute()
    rows_after = frappe.db.sql(
        "SELECT name, sync_uuid FROM `tabCustomer` WHERE sync_uuid IS NOT NULL LIMIT 5",
        as_dict=True,
    )
    # Map both for direct comparison
    before = {r.name: r.sync_uuid for r in rows_before}
    after = {r.name: r.sync_uuid for r in rows_after}
    for name, uuid in before.items():
        assert after.get(name) == uuid, f"Customer {name}: uuid changed"
    print("PASS: test_backfill_is_idempotent")


def run_all():
    test_no_null_sync_uuids_after_backfill()
    test_backfill_is_idempotent()
    print("\nAll Backfill tests PASSED")
```

- [ ] **Step 2: Write the patch**

File: `pos_next/patches/v2_0_0/backfill_sync_uuid.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Backfill sync_uuid on existing rows in sync-tracked doctypes. Idempotent."""

import uuid

import frappe


TARGET_DOCTYPES = [
    "Sales Invoice",
    "Payment Entry",
    "Stock Ledger Entry",
    "POS Opening Shift",
    "POS Closing Shift",
    "Customer",
]

BATCH_SIZE = 500


def execute():
    total_updated = 0
    for dt in TARGET_DOCTYPES:
        updated = _backfill_doctype(dt)
        total_updated += updated
        print(f"Backfilled sync_uuid: {dt} — {updated} rows")
    print(f"Total rows backfilled: {total_updated}")
    frappe.db.commit()


def _backfill_doctype(doctype_name):
    """Fill sync_uuid where NULL or empty, in batches."""
    updated = 0
    while True:
        rows = frappe.db.sql(
            f"""
            SELECT name FROM `tab{doctype_name}`
            WHERE sync_uuid IS NULL OR sync_uuid = ''
            LIMIT {BATCH_SIZE}
            """,
            as_dict=True,
        )
        if not rows:
            break
        for row in rows:
            new_uuid = str(uuid.uuid4())
            frappe.db.sql(
                f"UPDATE `tab{doctype_name}` SET sync_uuid = %s WHERE name = %s",
                (new_uuid, row.name),
            )
        frappe.db.commit()
        updated += len(rows)
        if len(rows) < BATCH_SIZE:
            break
    return updated
```

- [ ] **Step 3: Register the patch**

Append to `pos_next/patches.txt`:

```
pos_next.patches.v2_0_0.backfill_sync_uuid
```

- [ ] **Step 4: Run migrate**

```bash
cd /home/ubuntu/frappe-bench
bench --site <site-name> migrate
```

- [ ] **Step 5: Run tests**

```bash
bench --site <site-name> execute pos_next.sync.tests.test_backfill.run_all
```

Expected: both tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/patches/v2_0_0/backfill_sync_uuid.py pos_next/patches.txt pos_next/sync/tests/test_backfill.py
git commit -m "feat(sync): backfill sync_uuid on existing transaction rows"
```

---

### Task 14: Create `POS Next Sync Agent` role and permission query condition

**Files:**
- Create: `pos_next/patches/v2_0_0/create_sync_agent_role.py`
- Modify: `pos_next/patches.txt`

- [ ] **Step 1: Write the patch**

File: `pos_next/patches/v2_0_0/create_sync_agent_role.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Create the POS Next Sync Agent role."""

import frappe


ROLE_NAME = "POS Next Sync Agent"


def execute():
    if not frappe.db.exists("Role", ROLE_NAME):
        role = frappe.get_doc({
            "doctype": "Role",
            "role_name": ROLE_NAME,
            "desk_access": 0,
            "is_custom": 1,
        })
        role.insert(ignore_permissions=True)
        print(f"Created role: {ROLE_NAME}")
    else:
        print(f"Role already exists: {ROLE_NAME}")
    frappe.db.commit()
```

- [ ] **Step 2: Register the patch**

Append to `pos_next/patches.txt`:

```
pos_next.patches.v2_0_0.create_sync_agent_role
```

- [ ] **Step 3: Run migrate and verify**

```bash
cd /home/ubuntu/frappe-bench
bench --site <site-name> migrate
bench --site <site-name> execute 'print(frappe.db.exists("Role", "POS Next Sync Agent"))'
```

Expected: prints `POS Next Sync Agent` (the role name itself — Frappe `exists` returns the name).

- [ ] **Step 4: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/patches/v2_0_0/create_sync_agent_role.py pos_next/patches.txt
git commit -m "feat(sync): create POS Next Sync Agent role"
```

---

### Task 15: Create seeds module with default `synced_doctypes` rules

**Files:**
- Create: `pos_next/sync/seeds.py`
- Create: `pos_next/sync/tests/test_seeds.py`

- [ ] **Step 1: Write failing test**

File: `pos_next/sync/tests/test_seeds.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

import frappe


def _cleanup():
    frappe.db.delete("Sync Site Config")
    frappe.db.commit()


def test_seeds_populate_registry():
    """seed_default_rules returns a list of Sync DocType Rule dicts."""
    from pos_next.sync.seeds import DEFAULT_SYNC_RULES

    assert isinstance(DEFAULT_SYNC_RULES, list)
    assert len(DEFAULT_SYNC_RULES) >= 20, f"Expected at least 20 seeded rules, got {len(DEFAULT_SYNC_RULES)}"
    required_keys = {"doctype_name", "direction", "cdc_strategy", "conflict_rule", "priority"}
    for rule in DEFAULT_SYNC_RULES:
        missing = required_keys - set(rule.keys())
        assert not missing, f"Rule {rule.get('doctype_name')} missing keys: {missing}"
    print("PASS: test_seeds_populate_registry")


def test_seeds_include_required_doctypes():
    """Seeds include the core DocTypes from the spec."""
    from pos_next.sync.seeds import DEFAULT_SYNC_RULES
    names = {r["doctype_name"] for r in DEFAULT_SYNC_RULES}
    required = {
        "Item",
        "Item Price",
        "POS Profile",
        "Warehouse",
        "Customer",
        "Sales Invoice",
        "Payment Entry",
        "POS Opening Shift",
        "POS Closing Shift",
        "Stock Ledger Entry",
        "User",
        "Mode of Payment",
    }
    missing = required - names
    assert not missing, f"Missing from seeds: {missing}"
    print("PASS: test_seeds_include_required_doctypes")


def test_apply_seeds_to_config():
    """apply_seeds_to_config populates synced_doctypes on a config row."""
    _cleanup()
    try:
        from pos_next.sync.seeds import apply_seeds_to_config

        doc = frappe.get_doc({
            "doctype": "Sync Site Config",
            "site_role": "Central",
            "branch_code": "HQ",
            "enabled": 1,
        })
        doc.insert(ignore_permissions=True)

        apply_seeds_to_config(doc)
        doc.reload()
        assert len(doc.synced_doctypes) >= 20, f"Expected >=20 rules, got {len(doc.synced_doctypes)}"
        print("PASS: test_apply_seeds_to_config")
    finally:
        _cleanup()


def test_priorities_are_sorted_correctly():
    """POS Opening Shift has lowest priority (synced first)."""
    from pos_next.sync.seeds import DEFAULT_SYNC_RULES
    by_name = {r["doctype_name"]: r for r in DEFAULT_SYNC_RULES}
    opening_prio = by_name["POS Opening Shift"]["priority"]
    invoice_prio = by_name["Sales Invoice"]["priority"]
    assert opening_prio < invoice_prio, (
        f"POS Opening Shift priority ({opening_prio}) should be < "
        f"Sales Invoice priority ({invoice_prio})"
    )
    print("PASS: test_priorities_are_sorted_correctly")


def run_all():
    test_seeds_populate_registry()
    test_seeds_include_required_doctypes()
    test_apply_seeds_to_config()
    test_priorities_are_sorted_correctly()
    print("\nAll Seeds tests PASSED")
```

- [ ] **Step 2: Run test to confirm failure**

```bash
cd /home/ubuntu/frappe-bench
bench --site <site-name> execute pos_next.sync.tests.test_seeds.run_all
```

Expected: FAIL — module missing.

- [ ] **Step 3: Create `seeds.py`**

File: `pos_next/sync/seeds.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Default Sync DocType Rule seeds applied to new Sync Site Config records."""


DEFAULT_SYNC_RULES = [
    # --- Masters pulled central → branch, Central-Wins ---
    {"doctype_name": "Item",                "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 100, "batch_size": 100},
    {"doctype_name": "Item Price",          "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 110, "batch_size": 100},
    {"doctype_name": "Item Group",          "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 100, "batch_size": 100},
    {"doctype_name": "Item Barcode",        "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 100, "batch_size": 100},
    {"doctype_name": "UOM",                 "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 100, "batch_size": 100},
    {"doctype_name": "Price List",          "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 100, "batch_size": 100},
    {"doctype_name": "POS Profile",         "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority":  90, "batch_size": 100},
    {"doctype_name": "POS Settings",        "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority":  90, "batch_size": 100},
    {"doctype_name": "POS Offer",           "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 120, "batch_size": 100},
    {"doctype_name": "POS Coupon",          "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 120, "batch_size": 100},
    {"doctype_name": "Loyalty Program",     "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 120, "batch_size": 100},
    {"doctype_name": "Warehouse",           "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority":  90, "batch_size": 100},
    {"doctype_name": "Branch",              "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority":  90, "batch_size": 100},
    {"doctype_name": "Company",             "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority":  80, "batch_size": 100},
    {"doctype_name": "Currency",            "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority":  80, "batch_size": 100},
    {"doctype_name": "Mode of Payment",     "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 110, "batch_size": 100},
    {"doctype_name": "Sales Taxes and Charges Template", "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 110, "batch_size": 100},
    {"doctype_name": "Item Tax Template",   "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 110, "batch_size": 100},
    {"doctype_name": "User",                "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority":  80, "batch_size": 100},
    {"doctype_name": "Role Profile",        "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority":  80, "batch_size": 100},
    {"doctype_name": "Employee",            "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 110, "batch_size": 100},
    {"doctype_name": "Sales Person",        "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 110, "batch_size": 100},
    {"doctype_name": "Customer Group",      "direction": "Central→Branch", "cdc_strategy": "Watermark", "conflict_rule": "Central-Wins", "priority": 110, "batch_size": 100},

    # --- Customer: bidirectional, mobile-no Field-Level-LWW ---
    {"doctype_name": "Customer",            "direction": "Bidirectional", "cdc_strategy": "Outbox", "conflict_rule": "Field-Level-LWW", "priority":  50, "batch_size": 100},

    # --- Transactions branch → central, Branch-Wins ---
    {"doctype_name": "POS Opening Shift",   "direction": "Branch→Central", "cdc_strategy": "Outbox", "conflict_rule": "Branch-Wins", "priority":  10, "batch_size":  50},
    {"doctype_name": "POS Closing Shift",   "direction": "Branch→Central", "cdc_strategy": "Outbox", "conflict_rule": "Branch-Wins", "priority":  20, "batch_size":  50},
    {"doctype_name": "Sales Invoice",       "direction": "Branch→Central", "cdc_strategy": "Outbox", "conflict_rule": "Branch-Wins", "priority":  50, "batch_size": 100},
    {"doctype_name": "Payment Entry",       "direction": "Branch→Central", "cdc_strategy": "Outbox", "conflict_rule": "Branch-Wins", "priority":  50, "batch_size": 100},
    {"doctype_name": "Stock Ledger Entry",  "direction": "Branch→Central", "cdc_strategy": "Outbox", "conflict_rule": "Branch-Wins", "priority":  60, "batch_size": 200},
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/ubuntu/frappe-bench
bench --site <site-name> execute pos_next.sync.tests.test_seeds.run_all
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/sync/seeds.py pos_next/sync/tests/test_seeds.py
git commit -m "feat(sync): add default Sync DocType Rule seeds"
```

---

### Task 16: Auto-apply seeds on Sync Site Config creation

**Files:**
- Modify: `pos_next/pos_next/doctype/sync_site_config/sync_site_config.py`

- [ ] **Step 1: Extend SyncSiteConfig with after_insert hook**

In `pos_next/pos_next/doctype/sync_site_config/sync_site_config.py`, add method:

```python
    def after_insert(self):
        """Seed the synced_doctypes registry with default rules."""
        from pos_next.sync.seeds import apply_seeds_to_config
        apply_seeds_to_config(self)
```

- [ ] **Step 2: Verify via smoke test**

```bash
cd /home/ubuntu/frappe-bench
bench --site <site-name> execute '
import frappe
frappe.db.delete("Sync Site Config")
doc = frappe.get_doc({"doctype":"Sync Site Config","site_role":"Central","branch_code":"SEEDTEST","enabled":1}).insert(ignore_permissions=True)
doc.reload()
print(f"Rules seeded: {len(doc.synced_doctypes)}")
frappe.db.delete("Sync Site Config", {"name": "SEEDTEST"})
frappe.db.commit()
'
```

Expected: `Rules seeded: 32` (or similar count matching DEFAULT_SYNC_RULES).

- [ ] **Step 3: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/pos_next/doctype/sync_site_config/sync_site_config.py
git commit -m "feat(sync): auto-apply default rules when creating Sync Site Config"
```

---

### Task 17: Install custom fields hooks for fixtures (so they migrate on deploy)

**Files:**
- Modify: `pos_next/hooks.py`

- [ ] **Step 1: Add fixtures entry for custom fields**

In `pos_next/hooks.py`, find or add the `fixtures` list. If none exists yet, add:

```python
fixtures = [
    {
        "doctype": "Custom Field",
        "filters": [
            [
                "fieldname", "in", ["sync_uuid", "origin_branch", "synced_from_failover"]
            ]
        ]
    },
    {
        "doctype": "Role",
        "filters": [
            ["role_name", "=", "POS Next Sync Agent"]
        ]
    },
]
```

If `fixtures` exists, merge these entries into it.

- [ ] **Step 2: Export fixtures to verify**

```bash
cd /home/ubuntu/frappe-bench
bench --site <site-name> export-fixtures --app pos_next
ls /home/ubuntu/frappe-bench/apps/pos_next/pos_next/fixtures/
```

Expected: files `custom_field.json` and `role.json` contain the sync-related entries.

- [ ] **Step 3: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/hooks.py pos_next/fixtures/
git commit -m "feat(sync): add sync custom fields and role to fixtures"
```

---

### Task 18: Create `sync_uuid` auto-fill hook on target DocTypes

**Files:**
- Create: `pos_next/sync/hooks_uuid.py`
- Modify: `pos_next/hooks.py`

- [ ] **Step 1: Create `hooks_uuid.py`**

File: `pos_next/sync/hooks_uuid.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Auto-fill sync_uuid on creation of sync-tracked documents."""

import uuid

import frappe


def set_sync_uuid_if_missing(doc, method=None):
    """Before-insert hook: set sync_uuid to a fresh UUID4 if not already set."""
    if getattr(doc, "sync_uuid", None):
        return
    doc.sync_uuid = str(uuid.uuid4())


def set_origin_branch_if_missing(doc, method=None):
    """Before-insert hook: set origin_branch to this site's branch_code if empty."""
    if getattr(doc, "origin_branch", None):
        return
    branch_code = frappe.db.get_value(
        "Sync Site Config", {"site_role": "Branch"}, "branch_code"
    )
    if branch_code:
        doc.origin_branch = branch_code
```

- [ ] **Step 2: Wire hooks in `hooks.py`**

In `pos_next/hooks.py`, add (or extend):

```python
doc_events = {
    "Sales Invoice": {
        "before_insert": [
            "pos_next.sync.hooks_uuid.set_sync_uuid_if_missing",
            "pos_next.sync.hooks_uuid.set_origin_branch_if_missing",
        ],
    },
    "Payment Entry": {
        "before_insert": [
            "pos_next.sync.hooks_uuid.set_sync_uuid_if_missing",
            "pos_next.sync.hooks_uuid.set_origin_branch_if_missing",
        ],
    },
    "Stock Ledger Entry": {
        "before_insert": [
            "pos_next.sync.hooks_uuid.set_sync_uuid_if_missing",
            "pos_next.sync.hooks_uuid.set_origin_branch_if_missing",
        ],
    },
    "POS Opening Shift": {
        "before_insert": [
            "pos_next.sync.hooks_uuid.set_sync_uuid_if_missing",
            "pos_next.sync.hooks_uuid.set_origin_branch_if_missing",
        ],
    },
    "POS Closing Shift": {
        "before_insert": [
            "pos_next.sync.hooks_uuid.set_sync_uuid_if_missing",
            "pos_next.sync.hooks_uuid.set_origin_branch_if_missing",
        ],
    },
    "Customer": {
        "before_insert": [
            "pos_next.sync.hooks_uuid.set_sync_uuid_if_missing",
            "pos_next.sync.hooks_uuid.set_origin_branch_if_missing",
        ],
    },
}
```

If `doc_events` already exists in hooks.py, merge these entries carefully.

- [ ] **Step 3: Restart bench to pick up hook changes**

```bash
cd /home/ubuntu/frappe-bench
bench restart
```

- [ ] **Step 4: Smoke test — create a Customer and verify sync_uuid is populated**

```bash
bench --site <site-name> execute '
import frappe
c = frappe.get_doc({"doctype":"Customer","customer_name":"TEST SYNC UUID","customer_type":"Individual","customer_group":"Individual","territory":"All Territories"}).insert(ignore_permissions=True)
print(f"sync_uuid: {c.sync_uuid}")
print(f"origin_branch: {c.origin_branch}")
frappe.delete_doc("Customer", c.name, force=1)
frappe.db.commit()
'
```

Expected: `sync_uuid: <a uuid>` (not empty), `origin_branch` either empty (no Branch config) or a branch_code.

- [ ] **Step 5: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/sync/hooks_uuid.py pos_next/hooks.py
git commit -m "feat(sync): auto-fill sync_uuid + origin_branch on before_insert"
```

---

### Task 19: Full test-suite runner

**Files:**
- Create: `pos_next/sync/tests/run_all_tests.py`

- [ ] **Step 1: Write the runner**

File: `pos_next/sync/tests/run_all_tests.py`

```python
# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Run every Plan 1 test module and report PASS/FAIL counts."""

import traceback


TEST_MODULES = [
    "pos_next.sync.tests.test_sync_site_config",
    "pos_next.sync.tests.test_outbox",
    "pos_next.sync.tests.test_watermark",
    "pos_next.sync.tests.test_payload",
    "pos_next.sync.tests.test_base_adapter",
    "pos_next.sync.tests.test_registry",
    "pos_next.sync.tests.test_conflict",
    "pos_next.sync.tests.test_auth",
    "pos_next.sync.tests.test_custom_fields",
    "pos_next.sync.tests.test_backfill",
    "pos_next.sync.tests.test_seeds",
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
    print(f"\n\n=== SUMMARY: {passed} passed, {failed} failed ===")
    if failed:
        raise SystemExit(1)
```

- [ ] **Step 2: Run it**

```bash
cd /home/ubuntu/frappe-bench
bench --site <site-name> execute pos_next.sync.tests.run_all_tests.run
```

Expected: `=== SUMMARY: 11 passed, 0 failed ===`.

- [ ] **Step 3: Commit**

```bash
cd /home/ubuntu/frappe-bench/apps/pos_next
git add pos_next/sync/tests/run_all_tests.py
git commit -m "test(sync): add full Plan 1 test-suite runner"
```

---

## Done — What Plan 1 Delivers

After completing all 19 tasks:

- **All foundation DocTypes exist:** Sync Site Config, Sync DocType Rule, Sync Sibling Branch, Sync Outbox, Sync Watermark, Sync Tombstone, Sync Record State, Sync Field Timestamp, Sync Conflict, Sync Log, Sync Dead Letter, Sync History.
- **Custom fields installed** on Sales Invoice, Payment Entry, SLE, POS Opening/Closing Shift, Customer.
- **Existing rows backfilled** with sync_uuid.
- **POS Next Sync Agent role** created.
- **Seeded default rules** populated on new Sync Site Config.
- **`pos_next/sync/` module skeleton** with auth, transport, registry, BaseSyncAdapter, conflict resolver, payload helpers, defaults, exceptions.
- **"Test Sync Connection" button** works and verifies login against central.
- **Automatic sync_uuid + origin_branch generation** on document creation.
- **11 test modules, all passing.**
- **No data flows yet** — that's Plan 2 (Masters pull) and Plan 3 (Transactions + failover).

## Self-Review Checklist (do not skip)

Before considering Plan 1 complete, verify:

- [ ] All 19 tasks committed.
- [ ] `bench --site <site> migrate` runs clean.
- [ ] `bench --site <site> execute pos_next.sync.tests.run_all_tests.run` reports 0 failures.
- [ ] A test Branch Sync Site Config can be created (fill central_url=`https://bogus.test`) and "Test Sync Connection" shows red "Network error" (proves wiring).
- [ ] A new Customer gets a sync_uuid and origin_branch set automatically.
- [ ] `bench --site <site> migrate` a second time is a no-op (idempotent).
