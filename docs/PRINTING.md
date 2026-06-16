# Printing

POS Next supports two print paths:

- Browser print opens Frappe `/printview` and uses an HTML print format.
- Silent print sends output through QZ Tray and can use either HTML or raw ESC/POS print formats.

## ESC/POS Raw Printing

Raw ESC/POS print formats, such as `POS Next ESC/POS Receipt`, require silent print and QZ Tray. If silent print is disabled and the POS Profile uses a raw ESC/POS format, POS Next falls back to `POS Next Receipt` for browser printing because browsers cannot print raw printer commands through the normal print dialog.

## Offline Receipts

Offline/local-only invoices (`OFFLINE-*` and `pos_offline_*`) do not exist on the server yet, so POS Next keeps the older offline behavior: it prints the local built-in HTML receipt template.

This applies to both browser print and silent print. Silent print sends the local HTML receipt through QZ Tray as HTML; it does not generate raw ESC/POS commands offline.

After the invoice syncs and has a server-side Sales Invoice name, reprinting uses Frappe's server-rendered print format again.
