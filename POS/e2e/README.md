# POS Next UI smoke harness (Playwright)

Automates 12 paths of the UI test plan `docs/superpowers/plans/2026-11-18-ui-test-plan-ff-coupons-offers.md` (section 6).
Not run against any site yet: the selectors come from reading `POS/src`.

## Run

```
bench --site nexus.local execute pos_next.ui_test_seed.seed     # prints the uit-* passwords once
bench --site nexus.local clear-cache
cd POS
yarn playwright install chromium                                # once
UIT_BASE_URL=https://<site> UIT_USER=uit-cashier@uit-pos.example UIT_PASSWORD=<printed> yarn e2e
```

- `yarn playwright test -c e2e --list` only compiles the specs; it needs no site.
- The POS must be served over https (the login page refuses plain http). `global-setup.js` logs in through
  `/api/method/login` and stores the session in `e2e/.auth/` (git-ignored).
- The cashier needs no open shift: the helper resumes one or opens one on `UIT-FF Profile`.
  Close any shift the cashier has on another profile first.
- Run `bench --site nexus.local execute pos_next.ui_test_seed.teardown` and then `check` afterwards, as in plan section 1.
- Artifacts (receipt HTML, RTL screenshots) go to `e2e/artifacts/`; the HTML report goes to `e2e/report/`.

## Environment

| Variable | Needed by | Meaning |
|---|---|---|
| `UIT_BASE_URL`, `UIT_USER`, `UIT_PASSWORD` | all | Site and the `uit-cashier` login |
| `UIT_MAILPIT_URL` | U-01 | Mailpit base URL, default `http://localhost:8025` |
| `UIT_ADMIN_API_KEY`, `UIT_ADMIN_API_SECRET` | U-25 | API key of a user who may edit Pricing Rules; the test disables and re-enables `UIT-PR-FREE`. Skipped without them |
| `UIT_USER2`, `UIT_PASSWORD2`, `UIT_RACE=1` | U-38a | `uit-cashier2` login and an opt-in flag. Skipped without them |

## Which spec covers which plan check

| Test | Plan check | What it asserts in the browser |
|---|---|---|
| U-01 OTP | U-01 | Code step and countdown, 6-digit code read from Mailpit, `verified-badge` |
| U-06 F&F badge and line survive a reload | U-06, INV-2 | `fnf-customer-badge` "F&F 30%", applied message, 100 to 70, same after reload |
| U-09 F&F sale submits at the cart total | U-09, INV-1 | Line at 70, payment dialog total equals `submit_invoice` grand total |
| U-15a line coupon on a held draft | U-15 (a), INV-1 | "UIT-L10 applied successfully", UIT-A 90, UIT-B untouched, Hold then resume keeps the coupon, paid total parity |
| U-18b 50% line coupon wins over F&F | U-18 (b), INV-2 | Muted badge title, "never combined" message, line at 50, same after reload |
| U-21b BXGY 1 to 2 to 1 | U-21b (P0) | Note and "Free gift" row at x2, both gone and F&F 42 at x1, last pricing request has no `UIT-PR-BXGY`, no "Invoice Total Changed", paid request has no `UIT-PR-BXGY` |
| U-23a BXGY x2 free row | U-23 (a), INV-2 | Paid line at 60 plus one free row, same after reload |
| U-25 stale offer | U-25 | Refusal text "not backed by an offer" and "offers changed", then a sale after a reload |
| U-29a offline | U-29 (a) | No badge offline, sale saved offline, syncs online with no error dialog |
| U-33a receipt | U-33 (a) | Built-in receipt HTML saved to `artifacts/U-33a-<SI>.html`; has "Friends & Family discount" and "(FREE)" |
| U-35 RTL | U-35 | `dir=rtl`, screenshots of badge, line note, Coupon dialog, payment dialog; badge and note not clipped |
| U-38a two-context race | U-38 (a) | Both cashiers submit the same capped cart |

## Manual steps the specs do not do

- U-38a: before it, set the cap with `execute pos_next.ui_test_seed.set_ff --kwargs "{'max_discount_per_customer_month': <used + 40>}"`, and run `reset_ff` after.
- Every "Expected server" column (invoice rows, `USG`, `UT`, `LOG`, `ERR`) is still read by hand or by the section 4 probes.
- U-01 spends `UIT-OTP1`; re-seed before running it again.
- U-33a forces the built-in receipt by refusing the `/printview` popup. The Jinja receipt (U-33 b) and the coupon line "Discount" label are not covered.
