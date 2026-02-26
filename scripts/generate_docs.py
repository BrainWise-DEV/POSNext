#!/usr/bin/env python3
"""Generate API documentation for pos_next using pdoc.

This script creates mock stubs for frappe/erpnext so that pdoc can import
pos_next modules outside of a full bench environment. It then runs pdoc
programmatically and outputs HTML to docs/_build/.

Usage:
    python scripts/generate_docs.py

The generated docs will be in docs/_build/. Open docs/_build/index.html
in a browser to preview locally.
"""

import importlib
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# 1. Build a lightweight frappe mock that satisfies import-time checks
# ---------------------------------------------------------------------------


class _MockModule(types.ModuleType):
	"""A module-like object that returns MagicMock for any attribute access
	and allows arbitrary sub-imports (e.g. frappe.utils.cint).
	"""

	def __init__(self, name: str, doc: str = ""):
		super().__init__(name, doc)
		self.__path__ = []  # make it a package
		self.__all__: list[str] = []

	def __getattr__(self, name: str):
		# Return a stable child mock so repeated accesses get the same object
		if name.startswith("__") and name.endswith("__"):
			raise AttributeError(name)
		child = MagicMock()
		object.__setattr__(self, name, child)
		return child


def _make_mock_package(root_name: str, submodules: list[str]) -> None:
	"""Register *root_name* and all *submodules* as mock packages in sys.modules."""
	root = _MockModule(root_name)
	sys.modules[root_name] = root

	for dotted in submodules:
		full = f"{root_name}.{dotted}"
		parts = dotted.split(".")
		parent = root
		# Ensure every intermediate package exists
		for i, part in enumerate(parts):
			intermediate = f"{root_name}.{'.'.join(parts[: i + 1])}"
			if intermediate not in sys.modules:
				mod = _MockModule(intermediate)
				sys.modules[intermediate] = mod
				setattr(parent, part, mod)
			parent = sys.modules[intermediate]


# Frappe core and submodules used by pos_next
_FRAPPE_SUBMODULES = [
	"utils",
	"utils.password",
	"utils.data",
	"translate",
	"rate_limiter",
	"model",
	"model.document",
	"model.meta",
	"model.naming",
	"tests",
	"tests.utils",
	"query_builder",
	"query_builder.functions",
	"client",
	"handler",
	"permissions",
	"defaults",
	"cache_manager",
	"realtime",
	"website",
	"website.utils",
]

# ERPNext submodules used by pos_next
_ERPNEXT_SUBMODULES = [
	"accounts",
	"accounts.utils",
	"accounts.general_ledger",
	"accounts.doctype",
	"accounts.doctype.sales_invoice",
	"accounts.doctype.sales_invoice.sales_invoice",
	"accounts.doctype.pos_invoice_merge_log",
	"accounts.doctype.pos_invoice_merge_log.pos_invoice_merge_log",
	"controllers",
	"controllers.accounts_controller",
	"stock",
	"stock.doctype",
	"stock.doctype.batch",
	"stock.doctype.batch.batch",
	"stock.get_item_details",
]


def install_mocks() -> None:
	"""Install frappe & erpnext mocks into sys.modules."""
	_make_mock_package("frappe", _FRAPPE_SUBMODULES)

	# Make frappe.whitelist() a decorator that tags functions
	def _whitelist(methods=None, allow_guest=False, xss_safe=False):
		def decorator(fn):
			fn._is_whitelisted = True
			return fn

		# Allow both @frappe.whitelist and @frappe.whitelist()
		if callable(methods):
			methods._is_whitelisted = True
			return methods
		return decorator

	sys.modules["frappe"].whitelist = _whitelist

	# frappe._() is the translation function — identity
	sys.modules["frappe"]._ = lambda s, *a, **kw: s

	# frappe.throw / frappe.msgprint — no-ops
	sys.modules["frappe"].throw = MagicMock()
	sys.modules["frappe"].msgprint = MagicMock()
	sys.modules["frappe"].log_error = MagicMock()

	# Common utility functions
	utils = sys.modules["frappe.utils"]
	utils.cint = lambda x=0, *a: int(x or 0)
	utils.cstr = lambda x="", *a: str(x or "")
	utils.flt = lambda x=0, *a, **kw: float(x or 0)
	utils.getdate = MagicMock()
	utils.nowdate = MagicMock(return_value="2025-01-01")
	utils.today = MagicMock(return_value="2025-01-01")
	utils.now = MagicMock(return_value="2025-01-01 00:00:00")
	utils.get_datetime = MagicMock()
	utils.nowtime = MagicMock(return_value="00:00:00")
	utils.get_time = MagicMock()
	utils.add_days = MagicMock()
	utils.strip = lambda x: (x or "").strip()
	utils.time_diff_in_hours = MagicMock(return_value=0)

	# frappe.model.document.Document — base class for doctypes
	doc_mod = sys.modules["frappe.model.document"]
	doc_mod.Document = type("Document", (), {})

	# frappe.tests.utils.FrappeTestCase
	test_mod = sys.modules["frappe.tests.utils"]
	test_mod.FrappeTestCase = type("FrappeTestCase", (), {})

	# frappe.rate_limiter.rate_limit — no-op decorator
	rl_mod = sys.modules["frappe.rate_limiter"]

	def _rate_limit(*args, **kwargs):
		def decorator(fn):
			return fn
		return decorator

	rl_mod.rate_limit = _rate_limit

	# frappe.query_builder
	qb_mod = sys.modules["frappe.query_builder"]
	qb_mod.DocType = MagicMock()
	qb_fn = sys.modules["frappe.query_builder.functions"]
	qb_fn.Coalesce = MagicMock()
	qb_fn.Count = MagicMock()

	# ERPNext
	_make_mock_package("erpnext", _ERPNEXT_SUBMODULES)

	# Provide stub classes that pos_next subclasses
	si_mod = sys.modules["erpnext.accounts.doctype.sales_invoice.sales_invoice"]
	si_mod.SalesInvoice = type("SalesInvoice", (doc_mod.Document,), {})
	si_mod.get_bank_cash_account = MagicMock()

	ac_mod = sys.modules["erpnext.controllers.accounts_controller"]
	ac_mod.AccountsController = type("AccountsController", (doc_mod.Document,), {})


# ---------------------------------------------------------------------------
# 2. Run pdoc
# ---------------------------------------------------------------------------

# Modules to document — the public API surface
MODULES_TO_DOCUMENT = [
	"pos_next.api",
	"pos_next.validations",
]


def main() -> None:
	# Resolve paths
	project_root = Path(__file__).resolve().parent.parent
	output_dir = project_root / "docs" / "_build"

	# Ensure the pos_next package is importable
	if str(project_root) not in sys.path:
		sys.path.insert(0, str(project_root))

	# Install mocks BEFORE any pos_next imports
	install_mocks()

	# Now import pdoc (must be installed: pip install pdoc)
	try:
		import pdoc
	except ImportError:
		print("ERROR: pdoc is not installed. Run: pip install pdoc")
		sys.exit(1)

	# Verify modules can be imported
	successful = []
	failed = []
	for mod_name in MODULES_TO_DOCUMENT:
		try:
			importlib.import_module(mod_name)
			successful.append(mod_name)
		except Exception as exc:
			print(f"WARNING: Could not import {mod_name}: {exc}")
			failed.append(mod_name)

	# Only show @frappe.whitelist() endpoints in docs.
	# pdoc uses __all__ to control what's documented.
	import inspect

	for name, submod in list(sys.modules.items()):
		is_target = any(name == m or name.startswith(m + ".") for m in successful)
		if not is_target or submod is None:
			continue
		whitelisted = [
			attr_name
			for attr_name in dir(submod)
			if not attr_name.startswith("_")
			and inspect.isfunction(getattr(submod, attr_name, None))
			and getattr(getattr(submod, attr_name), "_is_whitelisted", False)
		]
		# Also keep submodules so pdoc can navigate into them
		for attr_name in dir(submod):
			obj = getattr(submod, attr_name, None)
			if inspect.ismodule(obj) and not attr_name.startswith("_"):
				whitelisted.append(attr_name)
		if whitelisted:
			submod.__all__ = whitelisted

	if not successful:
		print("ERROR: No modules could be imported. Check your setup.")
		sys.exit(1)

	print(f"Generating docs for {len(successful)} modules...")
	if failed:
		print(f"  Skipping {len(failed)} modules that failed to import")

	# Configure pdoc with custom templates
	template_dir = project_root / "scripts" / "pdoc-templates"
	pdoc.render.configure(
		docformat="google",
		show_source=True,
		template_directory=template_dir,
	)

	pdoc.pdoc(
		*successful,
		output_directory=output_dir,
	)

	print(f"Documentation generated in {output_dir}/")
	print(f"Open {output_dir / 'index.html'} in a browser to preview.")


if __name__ == "__main__":
	main()
