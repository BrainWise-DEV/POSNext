# Printing

POS Next supports two print paths:

- Browser print opens Frappe `/printview` and uses an HTML print format.
- Silent print sends output through QZ Tray and can use either HTML or raw ESC/POS print formats.

## ESC/POS Raw Printing

Raw ESC/POS print formats, such as `POS Next ESC/POS Receipt`, require silent print and QZ Tray. If silent print is disabled and the POS Profile uses a raw ESC/POS format, POS Next falls back to `POS Next Receipt` for browser printing because browsers cannot print raw printer commands through the normal print dialog.

## Offline Receipts

Offline/local-only invoices (`OFFLINE-*` and `pos_offline_*`) do not exist on the server yet, so Frappe cannot render server-side raw ESC/POS commands for them.

When silent print is enabled and the resolved POS Profile format is raw ESC/POS, POS Next builds the ESC/POS command string in the browser from the local invoice data and sends it to QZ Tray. This gives offline receipts the same raw thermal-printing path without waiting for sync.

Offline invoices save the active POS Profile's `print_format` into the local invoice payload. The currently opened POS Profile is also cached in `localStorage` as part of `pos_shift_data`, and the print resolver uses that cached profile if an older offline invoice does not already have `print_format` saved on it.

When silent print is disabled, offline receipts still use the local HTML browser-print template because browsers cannot send raw ESC/POS bytes through the normal print dialog.

After the invoice syncs and has a server-side Sales Invoice name, reprinting uses Frappe's server-rendered print format again.
