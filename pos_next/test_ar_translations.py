# Copyright (c) 2026, BrainWise and contributors
"""Every __() key used in POS/src, and every _() key in the server files below,
has an Arabic row in pos_next/translations/ar.csv."""

import ast
import csv
import html
import json
import re
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
POS_SRC = APP_ROOT / "POS" / "src"
AR_CSV = APP_ROOT / "pos_next" / "translations" / "ar.csv"
APP = APP_ROOT / "pos_next"
POS_SETTINGS = APP / "pos_next" / "doctype" / "pos_settings"

# Server files scanned whole: customer email verification, the OTP / benefit
# integrations, POS Settings, and the files the Phase 2 invoice tasks changed.
SERVER_PY = [
	APP / "api" / "email_verification.py",
	APP / "api" / "invoices.py",
	APP / "api" / "customers.py",
	APP / "api" / "sales_invoice_hooks.py",
	APP / "utils.py",
	APP / "pos_next" / "doctype" / "pos_coupon" / "pos_coupon.py",
	POS_SETTINGS / "pos_settings.py",
	*sorted(p for p in (APP / "integrations").glob("*.py") if not p.name.startswith("test_")),
]
SERVER_JS = [POS_SETTINGS / "pos_settings.js"]
EMAIL_TEMPLATES = sorted((APP / "templates" / "emails").glob("*.html"))
DOCTYPE_JSON = [POS_SETTINGS / "pos_settings.json"]

# Keys intentionally left untranslated (dynamic or shown as-is)
ALLOWLIST = set()

COMMENTS = re.compile(r"/\*.*?\*/|^\s*//.*?$|<!--.*?-->", re.S | re.M)
STRING = r"""(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')"""
CALL = re.compile(rf"\b__\(\s*{STRING}(?:\s*,\s*(?:null|undefined|\{{\s*\}}|\[\s*\])\s*,\s*{STRING})?")


def used_keys():
	"""Return {(source, context): file} for every literal __() call in POS/src."""
	keys = {}
	for path in POS_SRC.rglob("*"):
		if path.suffix not in {".vue", ".js", ".ts"} or "__tests__" in path.parts:
			continue
		code = COMMENTS.sub("", path.read_text(encoding="utf-8"))
		for m in CALL.finditer(code):
			source = re.sub(
				r"\\(.)",
				lambda e: "\n" if e.group(1) == "n" else e.group(1),
				m.group(1) if m.group(1) is not None else m.group(2),
			)
			# Vue decodes HTML entities in templates
			source = html.unescape(source) if path.suffix == ".vue" else source
			keys.setdefault((source, m.group(3) or m.group(4) or ""), str(path.relative_to(POS_SRC)))
	return keys


def _is_translate_call(node):
	func = node.func
	if isinstance(func, ast.Name):
		return func.id == "_"
	return (
		isinstance(func, ast.Attribute)
		and func.attr == "_"
		and isinstance(func.value, ast.Name)
		and func.value.id == "frappe"
	)


def python_keys(path):
	"""{(source, context): file} for every _("literal") / frappe._("literal") call."""
	keys = {}
	for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
		if not (isinstance(node, ast.Call) and _is_translate_call(node) and node.args):
			continue
		first = node.args[0]
		if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
			continue
		context = next(
			(
				kw.value.value
				for kw in node.keywords
				if kw.arg == "context" and isinstance(kw.value, ast.Constant)
			),
			"",
		)
		keys.setdefault((first.value, context or ""), str(path.relative_to(APP_ROOT)))
	return keys


JINJA_CALL = re.compile(rf"\b_\(\s*{STRING}\s*\)")


def server_keys():
	"""{(source, context): file} for the server files listed at the top."""
	keys = {}
	for path in SERVER_PY:
		for key, file in python_keys(path).items():
			keys.setdefault(key, file)
	for path in SERVER_JS:
		code = COMMENTS.sub("", path.read_text(encoding="utf-8"))
		for m in CALL.finditer(code):
			source = m.group(1) if m.group(1) is not None else m.group(2)
			keys.setdefault((source, m.group(3) or m.group(4) or ""), str(path.relative_to(APP_ROOT)))
	for path in EMAIL_TEMPLATES:
		for m in JINJA_CALL.finditer(path.read_text(encoding="utf-8")):
			source = m.group(1) if m.group(1) is not None else m.group(2)
			keys.setdefault((source, ""), str(path.relative_to(APP_ROOT)))
	for path in DOCTYPE_JSON:
		for field in json.loads(path.read_text(encoding="utf-8")).get("fields", []):
			if field.get("label"):
				keys.setdefault((field["label"], ""), str(path.relative_to(APP_ROOT)))
	return keys


def csv_keys():
	"""Return the {source} and {source:context} keys frappe builds from ar.csv."""
	with AR_CSV.open(encoding="utf-8", newline="") as f:
		rows = [r for r in csv.reader(f) if len(r) >= 2]
	return {r[0].replace("\\n", "\n") + (f":{r[2]}" if len(r) > 2 and r[2] else "") for r in rows}


class TestArabicTranslationCoverage(unittest.TestCase):
	def test_every_pos_key_has_an_arabic_row(self):
		have = csv_keys() | ALLOWLIST
		missing = sorted(
			f"{file}: {source!r}" + (f" (context {ctx!r})" if ctx else "")
			for (source, ctx), file in used_keys().items()
			if source not in have and f"{source}:{ctx}" not in have
		)
		self.assertFalse(missing, f"{len(missing)} __() keys missing from ar.csv:\n" + "\n".join(missing))

	def test_every_server_key_has_an_arabic_row(self):
		have = csv_keys() | ALLOWLIST
		missing = sorted(
			f"{file}: {source!r}" + (f" (context {ctx!r})" if ctx else "")
			for (source, ctx), file in server_keys().items()
			if (f"{source}:{ctx}" if ctx else source) not in have
		)
		self.assertFalse(missing, f"{len(missing)} server _() keys missing from ar.csv:\n" + "\n".join(missing))

	def test_server_scan_finds_keys(self):
		"""Guards the scanner itself: a broken parse would pass with nothing to check."""
		keys = server_keys()
		self.assertIn(("Health check failed", ""), keys)
		self.assertIn(("POS Profile is required.", ""), keys)

	def test_context_calls_have_context_rows(self):
		have = csv_keys()
		missing = sorted(f"{s}:{c}" for (s, c) in used_keys() if c and f"{s}:{c}" not in have)
		self.assertFalse(missing, "Context keys missing from ar.csv: " + ", ".join(missing))
