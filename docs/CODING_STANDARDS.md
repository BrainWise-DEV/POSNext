# POS Next Coding Standards

This document defines the coding standards enforced by CI on every pull request. All code **must** pass these checks before merging.

## CI Pipeline Overview

| Check | Tool | Config |
|-------|------|--------|
| Trailing whitespace | pre-commit | `.pre-commit-config.yaml` |
| Python linting | ruff v0.8.1 | `pyproject.toml [tool.ruff]` |
| Python formatting | ruff-format | `pyproject.toml [tool.ruff.format]` |
| Python imports | ruff isort | `pyproject.toml [tool.ruff.lint]` |
| JS/Vue/SCSS formatting | prettier v2.7.1 | `.pre-commit-config.yaml` |
| JS linting | eslint v8.44 | `.eslintrc` |
| Security & correctness | Semgrep | `frappe-semgrep-rules` + `python.lang.correctness` |
| Dependency audit | pip-audit | `pyproject.toml` |

---

## Python Standards

### Formatting

- **Indentation**: Tabs (not spaces)
- **Quotes**: Double quotes (`"`)
- **Line length**: 110 characters max (soft — E501 is ignored, but keep it reasonable)
- **Formatter**: `ruff format` — run before committing

```bash
# Format all Python files
ruff format pos_next/

# Check without modifying
ruff format --check pos_next/
```

### Linting

Ruff enforces these rule sets (see `pyproject.toml`):

| Rule Set | What It Checks |
|----------|----------------|
| `F` | Pyflakes — undefined names, unused variables |
| `E` / `W` | pycodestyle — whitespace, syntax |
| `I` | isort — import ordering |
| `UP` | pyupgrade — modern Python syntax (`str \| None` instead of `Optional[str]`) |
| `B` | flake8-bugbear — common bugs |
| `RUF` | Ruff-specific rules |

```bash
# Lint all Python files
ruff check pos_next/

# Auto-fix what's possible
ruff check --fix pos_next/
```

### Import Ordering

Imports must follow isort conventions (enforced by `ruff --select=I`):

```python
# 1. Standard library
import json
import os

# 2. Third-party
import frappe
from frappe import _
from frappe.utils import cint, flt

# 3. Local
from pos_next.api.items import get_items
```

---

## JavaScript / Vue / SCSS Standards

### Formatting

- **Formatter**: prettier v2.7.1 (NOT v3+, CI uses v2.7.1)
- **Indentation**: Tabs
- **Quotes**: As per prettier defaults

```bash
# Format from POS directory
cd POS
npx prettier@2.7.1 --write "src/**/*.{js,vue,scss}"

# Also format config files in POS root
npx prettier@2.7.1 --write "*.{js,json}"
```

### ESLint Rules

ESLint v8.44 extends `eslint:recommended`. Key rules to follow:

| Rule | What To Do |
|------|------------|
| `no-case-declarations` | Wrap `case` blocks containing `const`/`let` in braces `{}` |
| `no-async-promise-executor` | Never pass `async` function to `new Promise()` — do async work before the constructor |
| `no-console` | Use `console.warn`/`console.error` sparingly; avoid `console.log` in production |

**Example — no-case-declarations:**
```javascript
// BAD
switch (type) {
    case "name":
        const value = getName();
        break;
}

// GOOD
switch (type) {
    case "name": {
        const value = getName();
        break;
    }
}
```

**Example — no-async-promise-executor:**
```javascript
// BAD
return new Promise(async (resolve, reject) => {
    const data = await fetchData();
    resolve(data);
});

// GOOD
const data = await fetchData();
return new Promise((resolve, reject) => {
    resolve(data);
});
```

---

## Semgrep Rules (Security & Correctness)

Semgrep runs `frappe-semgrep-rules` and `python.lang.correctness` on every PR. These are **blocking** — any finding fails CI.

### Type Hints on Whitelisted Functions

**Rule**: `missing-argument-type-hint`

Every parameter in `@frappe.whitelist()` functions **must** have a type hint. This prevents type confusion attacks from untyped HTTP inputs.

```python
# BAD
@frappe.whitelist()
def get_items(pos_profile, limit=20):
    pass

# GOOD
@frappe.whitelist()
def get_items(pos_profile: str, limit: int = 20):
    pass
```

**Type hint guidelines for whitelisted functions:**

| Parameter Type | Type Hint |
|----------------|-----------|
| String (names, IDs, doctypes) | `str` |
| Optional string with default None | `str \| None = None` |
| Numeric with default | `int = 0`, `int = 20` |
| Boolean flags (HTTP sends 0/1) | `int = 0` |
| JSON data from frontend | `str` (parsed inside the function with `json.loads()`) |

### SQL Injection Prevention

**Rule**: `frappe-sql-format-injection`

Never use f-strings or `.format()` to insert **user values** into SQL queries.

```python
# BAD — SQL injection risk
frappe.db.sql(f"SELECT * FROM `tabItem` WHERE name = '{item_name}'")

# GOOD — parameterized query
frappe.db.sql("SELECT * FROM `tabItem` WHERE name = %s", (item_name,))

# GOOD — using frappe query builder
frappe.db.get_value("Item", item_name, "item_name")
```

When f-strings are used **only for safe table/column names** (not user input), suppress with a nosemgrep comment:

```python
# Safe — ITEM_FIELDS is a code constant, not user input
frappe.db.sql(  # nosemgrep: frappe-sql-format-injection
    f"SELECT {ITEM_FIELDS} FROM `tabItem` WHERE name = %s",
    (item_name,),
)
```

### Translation

**Rules**: `frappe-missing-translate-function-python`, `frappe-missing-translate-function-in-report-python`

All user-facing text must be wrapped in `_()`:

```python
from frappe import _

# BAD
frappe.throw("Item not found")
frappe.msgprint("Operation completed", title="Success")

# GOOD
frappe.throw(_("Item not found"))
frappe.msgprint(_("Operation completed"), title=_("Success"))
```

### Single DocType Value Access

**Rule**: `frappe-single-value-type-safety`

Use `get_single_value()` for Single DocTypes, not `get_value()`:

```python
# BAD
frappe.db.get_value("System Settings", "System Settings", "language")

# GOOD
frappe.db.get_single_value("System Settings", "language")
```

### Guest-Accessible Endpoints

**Rule**: `guest-whitelisted-method`

Methods with `allow_guest=True` are flagged for security review. If intentional (e.g., health check), suppress:

```python
@frappe.whitelist(allow_guest=True)  # nosemgrep: guest-whitelisted-method
def ping():
    return "pong"
```

### File System Access

**Rule**: `frappe-security-file-traversal`

Any `open()` call is flagged. If paths are hardcoded/validated, suppress:

```python
path = frappe.get_site_path("private", "qz", "cert.pem")
with open(path) as f:  # nosemgrep: frappe-security-file-traversal
    return f.read()
```

### Template Rendering

**Rule**: `frappe-ssti`

`render_template()` is flagged for server-side template injection. If the template is a trusted app file, suppress:

```python
frappe.render_template(  # nosemgrep: frappe-ssti
    "pos_next/templates/report.html",
    context
)
```

### Other Semgrep Rules to Be Aware Of

| Rule | What It Checks |
|------|----------------|
| `frappe-codeinjection-eval` | No `eval()`, `exec()`, `safe_exec()` |
| `frappe-breaks-multitenancy` | No module-level DB/cache calls in global variables |
| `frappe-modifying-but-not-comitting` | Call `db_set()` or `save()` after modifying DocType fields |
| `frappe-print-function-in-doctypes` | Use `frappe.log()` or `msgprint()` instead of `print()` |
| `frappe-manual-commit` | Avoid `frappe.db.commit()` — understand Frappe's transaction model |
| `overusing-args` | Don't use a single `args` parameter — use explicit named params |
| `frappe-cur-frm-usage` | `cur_frm` is deprecated in JS |

---

## Pre-Commit Setup (Local)

Install pre-commit hooks locally to catch issues before pushing:

```bash
cd /path/to/frappe-bench/apps/pos_next
pip install pre-commit
pre-commit install

# Run on all files (first time)
pre-commit run --all-files
```

This runs the same checks as CI: ruff, prettier, eslint, and basic file checks.

---

## Quick Reference Checklist

Before creating a PR, verify:

- [ ] `ruff check pos_next/` passes with no errors
- [ ] `ruff format --check pos_next/` reports no changes needed
- [ ] All `@frappe.whitelist()` function params have type hints
- [ ] No f-strings in `frappe.db.sql()` with user values
- [ ] All `frappe.throw()` / `frappe.msgprint()` messages wrapped in `_()`
- [ ] Single DocTypes use `get_single_value()` / `set_single_value()`
- [ ] JS/Vue files formatted with prettier v2.7.1
- [ ] No `const`/`let` in bare `case` blocks (wrap in `{}`)
- [ ] No `async` executor in `new Promise()`
