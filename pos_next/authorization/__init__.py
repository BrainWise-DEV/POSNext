# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Generic POS authorization gate.

Some action is attempted at the POS; if a ``POS Authorization Rule`` covers it, an
approver identifies themselves and enters a PIN, the server issues a short-lived
grant, and the action cannot complete without it.

Public API::

    from pos_next.authorization import gate, registry

    gate.enforce_document(doc)  # doc_events entry point
    gate.enforce_context(action, context, token)  # cart-level actions, no doc yet
    registry.register(Action(...))  # plug in a new action
"""

from pos_next.authorization.registry import Action, register

__all__ = ["Action", "register"]
