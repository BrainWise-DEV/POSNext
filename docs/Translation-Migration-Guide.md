# Translation System Migration Guide

This guide documents the migration from CSV-based translations to the PO/MO (gettext) format.

## Overview

POS Next has migrated from Frappe's legacy CSV translation format to the standard gettext PO/MO format.

### Benefits of PO/MO Format

| Feature | CSV (Legacy) | PO/MO (New) |
|---------|--------------|-------------|
| **Tools** | Manual editing | Poedit, Weblate, Crowdin, Transifex |
| **Context** | Limited | Full support (comments, references) |
| **Plurals** | No | Yes |
| **Performance** | Parsed at runtime | Compiled binary (MO) |
| **Industry Standard** | Frappe-specific | GNU gettext (universal) |
| **Fuzzy Matching** | No | Yes |
| **Translator Notes** | No | Yes |

## File Structure

```
pos_next/
├── locale/                    # New PO/MO translations
│   ├── main.pot              # Template (source strings only)
│   ├── ar.po                 # Arabic translations
│   ├── pt_br.po              # Brazilian Portuguese translations
│   └── *.mo                  # Compiled binaries (generated)
│
└── translations/              # Legacy CSV (can be deleted)
    ├── ar.csv
    └── pt-br.csv
```

## Workflow

### For Developers

#### 1. Adding New Translatable Strings

**Python (Backend):**
```python
from frappe import _

# Simple string
message = _("Hello World")

# With variables
message = _("Hello {0}").format(user_name)

# With context
message = _("Change", context="Coins")  # Distinguishes from "Change" (verb)
```

**JavaScript/Vue (Frontend):**
```javascript
// Simple string
const message = __("Hello World")

// With variables (positional)
const message = __("Hello {0}", [userName])

// With context
const message = __("Change", null, "Coins")
```

#### 2. Updating Translation Template

After adding new strings, regenerate the POT file:

```bash
# Option 1: Using bench (recommended)
cd ~/frappe-bench
bench generate-pot-file --app pos_next

# Option 2: Using the migration script
cd ~/frappe-bench/apps/pos_next
python scripts/migrate_translations.py
```

The GitHub Action will also automatically update the POT file when you push changes.

#### 3. Compiling Translations for Production

```bash
cd ~/frappe-bench
bench compile-po-to-mo --app pos_next
```

This creates `.mo` files in `sites/assets/locale/`.

### For Translators

#### Using Poedit (Recommended)

1. Download [Poedit](https://poedit.net/) (free)
2. Open the `.po` file (e.g., `pos_next/locale/ar.po`)
3. Translate strings
4. Save (Poedit auto-compiles to `.mo`)

#### Using Weblate/Crowdin (For Teams)

1. Connect repository to translation platform
2. Platform syncs with `locale/*.po` files
3. Translators work in web interface
4. Changes are committed back to repository

#### Manual Editing

PO files are plain text:

```po
#. Context comment for translators
#: pos_next/api/invoices.py:123
msgid "Invoice created successfully"
msgstr "تم إنشاء الفاتورة بنجاح"

#, fuzzy
msgid "This translation needs review"
msgstr "هذه الترجمة تحتاج مراجعة"
```

## Adding a New Language

### Step 1: Create PO File

```bash
cd ~/frappe-bench/apps/pos_next

# Copy template to new locale
cp pos_next/locale/main.pot pos_next/locale/fr.po
```

### Step 2: Edit Header

Open `fr.po` and update the header:

```po
"Language: fr\n"
"Language-Team: French Translation Team\n"
```

### Step 3: Add Translations

Translate the `msgstr` values:

```po
msgid "Hello"
msgstr "Bonjour"
```

### Step 4: Register in Frontend

Update `POS/src/composables/useLocale.js`:

```javascript
export const SUPPORTED_LOCALES = {
  en: { name: "English", nativeName: "English", countryCode: "us", dir: "ltr" },
  ar: { name: "Arabic", nativeName: "العربية", countryCode: "eg", dir: "rtl" },
  "pt-br": { name: "Portuguese (Brazil)", nativeName: "Português", countryCode: "br", dir: "ltr" },
  // Add new locale:
  fr: { name: "French", nativeName: "Français", countryCode: "fr", dir: "ltr" },
}
```

### Step 5: Compile and Test

```bash
bench compile-po-to-mo --app pos_next --locale fr
bench --site [site] clear-cache
```

## Bench Commands Reference

| Command | Description |
|---------|-------------|
| `bench generate-pot-file --app pos_next` | Extract strings from code to POT template |
| `bench migrate-csv-to-po --app pos_next` | Convert legacy CSV to PO format |
| `bench update-po-files --app pos_next` | Sync PO files with latest POT |
| `bench compile-po-to-mo --app pos_next` | Compile PO to binary MO files |

### Options

- `--locale [code]` - Process specific locale only (e.g., `--locale ar`)
- `--force` - Force recompilation even if unchanged

## GitHub Actions

The repository includes automatic translation template updates:

- **Trigger:** Push to `develop` or `main` with code changes
- **Action:** Extracts new strings and updates `main.pot`
- **PO Updates:** Existing PO files are merged with new strings

### Manual Trigger

Go to Actions → "Update Translation Template" → Run workflow

## Migration Script

For one-time migration or environments where bench isn't available:

```bash
cd ~/frappe-bench/apps/pos_next
python scripts/migrate_translations.py
```

This script:
1. Reads CSV files from `translations/`
2. Converts to PO format in `locale/`
3. Creates POT template

## Troubleshooting

### "ModuleNotFoundError" when running bench commands

Your bench has broken app references. Check `apps.txt` matches actual apps in `apps/` folder.

### Translations not appearing

1. Ensure MO files are compiled: `bench compile-po-to-mo --app pos_next`
2. Clear cache: `bench --site [site] clear-cache`
3. Check browser cache (hard refresh)

### Fuzzy translations

Strings marked `#, fuzzy` need review. Remove the fuzzy flag after verification:

```po
#, fuzzy  # Remove this line after review
msgid "Original"
msgstr "Translation"
```

## Resources

- [GNU gettext Manual](https://www.gnu.org/software/gettext/manual/)
- [Frappe Translation Docs](https://docs.frappe.io/framework/user/en/translations)
- [Poedit](https://poedit.net/) - Free PO editor
- [Weblate](https://weblate.org/) - Web-based translation platform
