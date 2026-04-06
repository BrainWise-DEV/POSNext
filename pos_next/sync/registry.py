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
