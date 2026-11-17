"""Dev-site test runner. Never whitelisted.

Use instead of `bench run-tests` (which wipes data on a dev site):

	bench --site nexus.local execute pos_next.dev_tests.run \
		--kwargs '{"module": "pos_next.api.test_customers"}'
"""

import importlib
import unittest


def run(module: str) -> dict:
	"""Load and run every test in `module`. Failures are returned, not raised."""
	mod = importlib.import_module(module)
	suite = unittest.TestLoader().loadTestsFromModule(mod)
	result = unittest.TextTestRunner(verbosity=2).run(suite)
	return {
		"tests_run": result.testsRun,
		"failures": [str(f[0]) for f in result.failures],
		"errors": [str(e[0]) for e in result.errors],
		"was_successful": result.wasSuccessful(),
	}
