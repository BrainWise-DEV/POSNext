# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Registry of authorizable actions.

An :class:`Action` is the only thing the gate knows about. Adding a new gated action —
voiding an invoice, overriding a discount, editing a price — is one :func:`register`
call plus, for document-triggered actions, one ``doc_events`` line in ``hooks.py``.

Nothing else changes: not the gate, the grants, the PIN, the dialog or the log.
"""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Action:
	"""One authorizable action.

	:param name: Both the stable key stored on ``POS Authorization Rule`` and the text
		shown for it in the desk and the POS — one string, not a key plus a separate
		label kept in sync by hand. Write it exactly as it should appear, e.g.
		``"Sales Invoice Return"``, not ``"sales_invoice_return"``. Translated with
		``frappe._()`` at every *display* site (never at registration time — module
		import happens outside a request, where there is no language to translate
		into — and never for storage/comparison: the raw string is what's saved,
		matched and logged). **Never rename it once shipped** — existing rules
		reference it, and renaming orphans them exactly like deleting it would. See
		:func:`all_actions` for how this stays in step with the ``action`` Select on
		``POS Authorization Rule``.
	:param binding: ``(context: dict) -> dict``. What the grant is pinned to. The gate
		treats the result as opaque: every key must match at enforcement time, except
		``amount``, which may come in lower than approved but never higher.
	:param doctype: Set for document-triggered actions, so ``enforce_document`` can find
		them. Leave ``None`` for actions raised from the cart, before a document exists.
	:param applies: ``(doc) -> bool``. For document-triggered actions, whether this action
		fires for this particular document. ``None`` means "always, for this doctype".
	"""

	name: str
	binding: Callable[[dict], dict]
	doctype: str | None = None
	applies: Callable[..., bool] | None = None


_ACTIONS: dict[str, Action] = {}
_LOADED = False


def _ensure_loaded() -> None:
	"""Import the shipped actions on first use.

	Lazy rather than imported from ``hooks.py`` so the registry has no opinion about app
	load order — a lesson from the import-time patching in ``pos_next/__init__.py``.
	"""
	global _LOADED
	if _LOADED:
		return

	_LOADED = True
	import pos_next.authorization.actions


def register(action: Action) -> None:
	"""Add ``action`` to the registry, replacing any action with the same name."""
	if not isinstance(action, Action):
		raise TypeError("register() expects an Action")
	_ACTIONS[action.name] = action


def get(name: str) -> Action | None:
	"""The registered action called ``name``, or ``None``."""
	_ensure_loaded()
	return _ACTIONS.get(name)


def for_doctype(doctype: str) -> list[Action]:
	"""Every registered action triggered by documents of ``doctype``."""
	_ensure_loaded()
	return [action for action in _ACTIONS.values() if action.doctype == doctype]


def all_actions() -> list[Action]:
	"""Every registered action, ordered by name (which is also its display text).

	``POS Authorization Rule.action`` is a hardcoded Select, not driven by this list at
	runtime — its options in pos_authorization_rule.json must list the same names as
	are registered here. Keeping the two in step is a one-line discipline, not
	something worth a parity test: when you add an action, add its name to that
	Select's options in the same change. Forgetting only affects the action you just
	added — ``POSAuthorizationRule.validate_action()`` still refuses to save a rule
	against anything not registered here, so a Select that's fallen behind can never
	make an *existing* rule silently stop gating.
	"""
	_ensure_loaded()
	return sorted(_ACTIONS.values(), key=lambda action: action.name)


def clear(mark_loaded: bool = True) -> None:
	"""Empty the registry. Tests only.

	``mark_loaded`` keeps the shipped actions from being re-imported, so a test can work
	with only the actions it registers itself.
	"""
	global _LOADED
	_ACTIONS.clear()
	_LOADED = mark_loaded
