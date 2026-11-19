# Copyright (c) 2026, BrainWise and contributors
"""Every __() key used in POS/src has an Arabic row in pos_next/translations/ar.csv."""

import csv
import html
import re
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
POS_SRC = APP_ROOT / "POS" / "src"
AR_CSV = APP_ROOT / "pos_next" / "translations" / "ar.csv"

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

	def test_context_calls_have_context_rows(self):
		have = csv_keys()
		missing = sorted(f"{s}:{c}" for (s, c) in used_keys() if c and f"{s}:{c}" not in have)
		self.assertFalse(missing, "Context keys missing from ar.csv: " + ", ".join(missing))
