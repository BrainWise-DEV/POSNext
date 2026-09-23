# POSNext Local Agent (Phase 3B)

The Local Agent provides a hardened loopback-only bridge for Windows receipt printers and cash drawers when QZ Tray is not used for drawer control.

## Security model

- Listens only on `127.0.0.1` / localhost.
- Requires a randomly generated 256-bit terminal token.
- Checks the browser `Origin` against an allowlist.
- Restricts printing and drawer pulses to explicitly allowlisted printer names.
- Requires a unique nonce on every authenticated request and rejects replayed nonces.
- Applies a general request rate limit and a stricter drawer pulse rate limit.
- Exposes semantic endpoints only; it does not expose arbitrary raw printer bytes to the browser.

## Install on a Windows POS terminal

Open PowerShell **as Administrator** in this folder:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1 -PrinterName "EPSON TM-T20II Receipt" -Origin "https://erp.bm-kw.com"
```

The installer displays a **Local Agent Token**. In POSNext:

1. User Menu -> Cash Drawer Setup.
2. Authorize with the manager POS PIN.
3. Choose `POSNext Local Agent`.
4. Enter the Terminal ID.
5. Paste the Local Agent Token.
6. Click **Refresh** and select the receipt printer.
7. Use **Test Print** and **Test Cash Drawer**.
8. Save Terminal Setup.

## Endpoints

- `GET /health`
- `GET /printers`
- `POST /test-print`
- `POST /drawer/open`

Phase 3B keeps normal ERPNext HTML invoice silent printing on QZ Tray. The Local Agent in this phase handles printer discovery, raw test printing and the cash-drawer pulse.
