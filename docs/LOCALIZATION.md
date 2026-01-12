# Language Settings

This guide explains how to configure languages in POS Next.

## Configuring Allowed Languages

You can control which languages are available in the POS language switcher through POS Settings.

### Steps to Configure

1. Navigate to **POS Settings** in ERPNext
2. Open your POS Settings record (or create one for your POS Profile)
3. Find the **Localization** section at the top
4. Click on **Allowed Languages** field
5. Select the languages you want to enable from the dropdown
6. Click **Save**

### Available Languages

POS Next supports the following languages out of the box:

| Language | Code | Direction |
|----------|------|-----------|
| English | en | Left-to-Right |
| Arabic | ar | Right-to-Left |
| Portuguese (Brazil) | pt_br | Left-to-Right |

### Default Behavior

- If **no languages are selected**, English and Arabic will be available by default
- If **one or more languages are selected**, only those languages will appear in the language switcher

## Using the Language Switcher

### Switching Languages

1. Look for the language button in the POS interface (shows current flag and language name)
2. Click to open the language dropdown
3. Select your preferred language
4. The interface will update immediately without page reload

### What Changes

When you switch languages:
- All interface text updates to the selected language
- For RTL languages (like Arabic), the entire layout mirrors
- Your preference is saved and remembered for next login

## Offline Support

Language settings work offline:
- Your language preference is saved locally
- Translations are cached for offline use
- The language switcher remembers available languages

## Troubleshooting

### Language not appearing in switcher

- Check that the language is added in POS Settings > Allowed Languages
- Refresh the POS page after saving POS Settings
- Clear browser cache if the language still doesn't appear

### Interface not translating

- Some text may not have translations yet
- Contact your administrator to add missing translations

### RTL layout looks incorrect

- Ensure you're using a supported browser (Chrome, Firefox, Safari, Edge)
- Try refreshing the page after switching to/from RTL language
