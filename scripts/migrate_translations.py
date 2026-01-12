#!/usr/bin/env python3
"""
Migration script: Convert CSV translations to PO format

Usage:
    python scripts/migrate_translations.py

This script:
1. Reads existing CSV translation files from pos_next/translations/
2. Converts them to PO format in pos_next/locale/
3. Creates a POT template file

After running this script, you can use standard gettext tools or:
    bench compile-po-to-mo --app pos_next
"""

import csv
import os
import re
from datetime import datetime
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent.parent
TRANSLATIONS_DIR = BASE_DIR / "pos_next" / "translations"
LOCALE_DIR = BASE_DIR / "pos_next" / "locale"

# Locale mappings
LOCALE_MAP = {
	"ar": {"language": "Arabic", "team": "Arabic Translation Team"},
	"pt_br": {"language": "Portuguese (Brazil)", "team": "Brazilian Portuguese Translation Team"},
	"fr": {"language": "French", "team": "French Translation Team"},
}


def escape_po_string(s):
	"""Escape special characters for PO format."""
	if not s:
		return ""
	s = s.replace("\\", "\\\\")
	s = s.replace('"', '\\"')
	s = s.replace("\n", "\\n")
	s = s.replace("\t", "\\t")
	return s


def format_po_string(s, prefix=""):
	"""Format a string for PO file, handling multiline."""
	if not s:
		return f'{prefix}""'

	escaped = escape_po_string(s)

	# For long strings or strings with newlines, use multiline format
	if len(escaped) > 70 or "\\n" in escaped:
		lines = []
		lines.append(f'{prefix}""')
		# Split into chunks
		chunks = escaped.split("\\n")
		for i, chunk in enumerate(chunks):
			if i < len(chunks) - 1:
				chunk += "\\n"
			if chunk:
				lines.append(f'"{chunk}"')
		return "\n".join(lines)

	return f'{prefix}"{escaped}"'


def create_po_header(locale, language, team):
	"""Create PO file header."""
	now = datetime.now().strftime("%Y-%m-%d %H:%M%z")
	return f'''# {language} translations for POS Next.
# Copyright (C) {datetime.now().year} BrainWise
# This file is distributed under the same license as the POS Next package.
#
msgid ""
msgstr ""
"Project-Id-Version: POS Next 1.13.0\\n"
"Report-Msgid-Bugs-To: support@brainwise.me\\n"
"POT-Creation-Date: {now}\\n"
"PO-Revision-Date: {now}\\n"
"Last-Translator: \\n"
"Language-Team: {team}\\n"
"Language: {locale}\\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
"Plural-Forms: nplurals=2; plural=(n != 1);\\n"

'''


def create_pot_header():
	"""Create POT template file header."""
	now = datetime.now().strftime("%Y-%m-%d %H:%M%z")
	return f'''# SOME DESCRIPTIVE TITLE.
# Copyright (C) {datetime.now().year} BrainWise
# This file is distributed under the same license as the POS Next package.
# FIRST AUTHOR <EMAIL@ADDRESS>, YEAR.
#
#, fuzzy
msgid ""
msgstr ""
"Project-Id-Version: POS Next 1.13.0\\n"
"Report-Msgid-Bugs-To: support@brainwise.me\\n"
"POT-Creation-Date: {now}\\n"
"PO-Revision-Date: YEAR-MO-DA HO:MI+ZONE\\n"
"Last-Translator: FULL NAME <EMAIL@ADDRESS>\\n"
"Language-Team: LANGUAGE <LL@li.org>\\n"
"Language: \\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"

'''


def read_csv_translations(csv_path):
	"""Read translations from CSV file."""
	translations = []
	with open(csv_path, "r", encoding="utf-8") as f:
		reader = csv.reader(f)
		for row in reader:
			if len(row) >= 2:
				source = row[0].strip()
				target = row[1].strip()
				context = row[2].strip() if len(row) > 2 else ""
				if source:  # Skip empty source strings
					translations.append({
						"source": source,
						"target": target,
						"context": context
					})
	return translations


def write_po_file(translations, locale, output_path):
	"""Write translations to PO file."""
	info = LOCALE_MAP.get(locale, {"language": locale, "team": f"{locale} Team"})

	with open(output_path, "w", encoding="utf-8") as f:
		f.write(create_po_header(locale, info["language"], info["team"]))

		for t in translations:
			# Add context comment if present
			if t["context"]:
				f.write(f'#. {t["context"]}\n')

			# Write msgid
			f.write(format_po_string(t["source"], "msgid ") + "\n")

			# Write msgstr
			f.write(format_po_string(t["target"], "msgstr ") + "\n")
			f.write("\n")

	print(f"  Created: {output_path}")


def write_pot_file(translations, output_path):
	"""Write POT template file (no translations, just source strings)."""
	with open(output_path, "w", encoding="utf-8") as f:
		f.write(create_pot_header())

		# Deduplicate sources
		seen = set()
		for t in translations:
			if t["source"] not in seen:
				seen.add(t["source"])

				if t["context"]:
					f.write(f'#. {t["context"]}\n')

				f.write(format_po_string(t["source"], "msgid ") + "\n")
				f.write('msgstr ""\n')
				f.write("\n")

	print(f"  Created: {output_path}")


def main():
	print("=" * 60)
	print("POS Next Translation Migration: CSV → PO/POT")
	print("=" * 60)

	# Ensure locale directory exists
	LOCALE_DIR.mkdir(parents=True, exist_ok=True)
	print(f"\nLocale directory: {LOCALE_DIR}")

	# Find all CSV files
	csv_files = list(TRANSLATIONS_DIR.glob("*.csv"))
	if not csv_files:
		print(f"\nNo CSV files found in {TRANSLATIONS_DIR}")
		return

	print(f"\nFound {len(csv_files)} CSV file(s):")
	for f in csv_files:
		print(f"  - {f.name}")

	# Collect all translations for POT file
	all_translations = []

	# Process each CSV file
	print("\nConverting CSV to PO:")
	for csv_file in csv_files:
		locale = csv_file.stem  # e.g., "ar" from "ar.csv"
		print(f"\nProcessing {csv_file.name} ({locale})...")

		translations = read_csv_translations(csv_file)
		print(f"  Read {len(translations)} translations")

		all_translations.extend(translations)

		# Write PO file
		po_path = LOCALE_DIR / f"{locale}.po"
		write_po_file(translations, locale, po_path)

	# Write POT template
	print("\nCreating POT template:")
	pot_path = LOCALE_DIR / "main.pot"
	write_pot_file(all_translations, pot_path)

	print("\n" + "=" * 60)
	print("Migration complete!")
	print("=" * 60)
	print(f"""
Next steps:
1. Review the generated files in {LOCALE_DIR}
2. Run 'bench compile-po-to-mo --app pos_next' to compile MO files
3. Optionally delete the old CSV files:
   rm {TRANSLATIONS_DIR}/*.csv
4. Update translations using standard PO tools (Poedit, Weblate, etc.)
""")


if __name__ == "__main__":
	main()
