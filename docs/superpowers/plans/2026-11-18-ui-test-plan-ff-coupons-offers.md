# UI test plan — Friends & Family, coupons, offers (POS Next, lean version)

Date: 2026-11-18 (rewritten the same day after the Codex critique). Type: test plan. Nothing here has been run yet.

This plan replaces the 328-case draft with **52 current-phase checks**:
- **40 UI checks**, manual or browser;
- **12 scripted request probes**;
- **11 of the 40 UI checks** are then automated as a small Playwright smoke run (§6).

The binding direction is `.superpowers/sdd/2026-11-16-ff-phase2-unlock/codex-ui-test-plan-critique.md`: the Q5 keep-list, the Q2 merges and the Q6 missing items. The server suites stay the exhaustive matrix. These checks prove only three things:
- the browser contract;
- a few end-to-end seams;
- the cases where the browser and the server could disagree.

**Sources** (the **Src** column):
- Spec: `docs/superpowers/specs/2026-11-16-friends-and-family-generic-design.md` (`§`).
- Plans: P1 (`P1-T…`) and P2 (`P2-T…`).
- Rulings (`R…`): from the two ledgers, `posnext_promotions/.superpowers/sdd/2026-11-16-ff-phase1-foundation/progress.md` and `pos_next/.superpowers/sdd/2026-11-16-ff-phase2-unlock/progress.md`. A ruling binds where it differs from a plan.
- Old IDs (`OTP-01`, `CVF-03`, …) are kept in each row, so a reader can trace a check back to the 328-case draft in git history.

---

## 1. Setup: seed, run, tear down

All test data comes from one script. It creates records named `UIT-…` (users and emails `uit-…@….example`) and touches nothing else, except the two site settings listed below. It records those settings first and restores them on teardown.

```
bench --site nexus.local execute pos_next.ui_test_seed.seed       # idempotent; prints the user passwords once
bench --site nexus.local clear-cache                              # then reload any open POS tab
#   … run §3 – §6 …
bench --site nexus.local execute pos_next.ui_test_seed.teardown
bench --site nexus.local execute pos_next.ui_test_seed.check      # must print "ok": true (check U-40)
```

- **Changing F&F Settings during a run:** `bench --site nexus.local execute pos_next.ui_test_seed.set_ff --kwargs "{'max_discount_per_order': 50}"`. Any scalar field works.
- **Putting F&F Settings back:** `bench --site nexus.local execute pos_next.ui_test_seed.reset_ff` returns them to the seeded values. The F&F Settings are site-wide: a cap or policy left changed breaks later checks for every customer. Every row that changes one ends with `reset_ff`. Teardown then restores the pre-seed snapshot.
- **Changing the UIT records:** edit the UIT POS Settings rows, UIT rules and UIT coupons in Desk. Teardown deletes them.
- **Self-check of the script** (it commits; never use run-tests): `bench --site <site> execute pos_next.test_ui_test_seed.run`. It seeds twice, tears down, then checks.
- **Before the run (ops):** do the manual ops checklist (Appendix B, items O-1 to O-3). The site must be migrated and built, Mailpit must be up, and the fake Magento must be on for `UIT-NOFF Profile`.
- **Open the shift** in the POS as `uit-cashier@uit-pos.example`, profile `UIT-FF Profile`. Teardown cancels and deletes UIT shifts.

### 1.1 What the seed creates (`pos_next/ui_test_seed.py`)

| Kind | Records |
|---|---|
| Price list | `UIT-Selling SAR`, in company currency SAR. This avoids Main POS Profile's EGP list. |
| Group / brand | `UIT-Group` (child of the root), `UIT-Brand` |
| Items (non-stock, so they make no stock ledger) | `UIT-A` 100, `UIT-A2` 100, `UIT-B` 200, `UIT-C` 50, `UIT-EXCL` 80, `UIT-ODD` 33.33, `UIT-P100` 25, `UIT-BXGY` 60, `UIT-TRIG` 100, `UIT-GIFT` 30, `UIT-GWP1` 30, `UIT-GWP2` 45, and `UIT-NOPRICE` with no Item Price |
| Tax | `UIT-VAT 15% - <abbr>`: exclusive 15% on net, on both UIT profiles (only if the company has a Tax account) |
| Customers | **Cart checks (never re-verified or edited):** `UIT-Verified` (`uit-verified@uit-ff.example`, verified) · `UIT-Unverified` (`uit-unverified@uit-ff.example`) · `UIT-Cap` (`uit-cap@uit-ff.example`, verified, kept for the cap races) · `UIT-Walk-in` (no email; the profiles' default customer). **OTP checks (spent by them):** `UIT-OTP1`, `UIT-OTP2`, `UIT-OTP3` (`uit-otpN@uit-ff.example`, not verified) · `UIT-Mag` (`uit-mag@uit-ff.example`, mobile `+442079460958`) · `UIT-Shared` (`uit-verified@UIT-FF.example`: same address as UIT-Verified in another case, not verified). The OTP limit is 5 sends per hour per customer and profile, so the OTP rows spread their sends over these customers. |
| Profiles | `UIT-FF Profile` (`allow_friends_family` 1) and `UIT-NOFF Profile` (0). Both are on `UIT-Selling SAR`, limited to `UIT-Group`, with `update_stock` 0. Warehouse, accounts and payments are copied from an existing profile of the company. |
| POS Settings (one per profile) | **S0**: item discount 1, rate 0, additional 0, max 0. `allow_sales_order` 1, `allow_delete_offline_invoice` 1. Verification on, provider blank (Frappe Email), TTL 900, cooldown 60, 5 sends/h. |
| Users | `uit-cashier@`, `uit-cashier2@` (cashier role), `uit-manager@` (manager role + cashier role), all `@uit-pos.example`. The role names are read from pos_next's Role fixtures and DocPerms, not hard-coded. Random passwords are printed once. |
| Pricing Rules (all `for_price_list` = UIT list) | `UIT-PR-B20` (20% on UIT-B) · `UIT-PR-C40` (40% on UIT-C) · `UIT-PR-P100` (100% on UIT-P100) · `UIT-PR-CART5` (Transaction 5% at ≥ 1000) · `UIT-PR-BXGY` (buy 2 UIT-BXGY, get 1, same item) · `UIT-PR-FREE` (buy 1 UIT-TRIG, get 1 UIT-GIFT) · `UIT-PR-CART-GIFT` (Transaction ≥ 500 → 1 UIT-GIFT) · `UIT-PR-GWP` (promotions only: GWP on UIT-GWP1/2, min 2, free 1, Max Price basis) |
| POS Coupons | **Line-level:** `UIT-L10`, `UIT-L20`, `UIT-L50`, `UIT-L100`. **Order-level:** `UIT-O40` and `UIT-O100` (amounts). `UIT-MAX1` (10%, `maximum_use` 1). **Promotions only:** `UIT-SI20` (20%, scope Item Code UIT-A) and `UIT-BET` (30%, "Better of the two"). |
| F&F Settings (promotions only; site Single, snapshotted) | `enabled` 1, 30%, scope Entire Cart. `allow_free_gift_with_ff` 0. Caps: 500 per order and 2000 per month, which ordinary carts never reach; checks lower them with `set_ff`. Approved domain `uit-ff.example`. `excluded_items` UIT-EXCL. Allow and log, Compete. |
| Live rules (snapshotted) | Disabled for the run: every enabled, non-coupon selling rule of the company that a UIT cart would pick up. That means Transaction rules, plus Item Group, Item and Brand rules that cover UIT items. They are found by query; on nexus.local today that is `PRLE-0023` and `PRLE-0289`. |

Two things get verified at seed time:
- **Rule kinds.** The seed checks that promotions' `classify_promotion` gives each seeded rule its intended kind: `price`, `bxgy`, `free_item`, `cart_total_gift` and `gwp`. If any differs, it throws.
- **Snapshot.** The snapshot is the private File `UIT-seed-snapshot.json`. A second seed reuses it and never re-snapshots.

### 1.2 Discount-permission sets (edit the `UIT-FF Profile` POS Settings row as `uit-manager`; return to S0 afterwards)

| Set | item discount | rate edit | additional (header) | max discount |
|---|---|---|---|---|
| S0 (seeded) | 1 | 0 | 0 | 0 |
| S2 | 1 | 1 | 0 | 10 |
| S4 | 1 | 0 | 1 | 10 |

### 1.3 Server-state notation

You can read it in Desk, or with read-only SQL through `bench --site nexus.local mariadb`.

| Shorthand | What it is |
|---|---|
| `SI` | Sales Invoice header |
| `SII[item]` | Sales Invoice Item row. **F&F markers** = `posnext_discount_source = friends_and_family` and `posnext_fnf_percentage > 0`. |
| `USG` | Friends and Family Usage rows of the invoice |
| `UT` | The Usage Total counter |
| `LOG(type[, reason])` | Friends and Family Log row |
| `ERR(title)` | Error Log row. These are deferred: flush first with `bench --site nexus.local execute frappe.deferred_insert.save_to_db`. |
| `CPN.used` | `POS Coupon.used` |
| `OIS` | Offline Invoice Sync row |

### 1.4 Two invariants applied inside the checks

- **INV-1 Cart/server total parity.**
  - Before you press Complete, read the payment dialog total.
  - After submit, `SI.grand_total` (or `rounded_total` when rounding is on) must equal it to the cent.
  - The UIT profiles carry the 15% exclusive tax, so tax is always in the sum.
  - Applied in U-09 (F&F), U-15 (line and order coupon), U-17 (free row from a coupon), U-19 (mixed per line) and U-22 (free gift).
  - Playwright compares the dialog total with `grand_total` in the `submit_invoice` response.
- **INV-2 Reload persistence.**
  - After the check's main assertion, reload the tab (F5).
  - The cart must come back with the same badge, the same line breakdown, the same coupon and the same free row, and with no extra rows.
  - Applied in U-06, U-18 (the CVF-03 row) and U-23 (the OFR-01 row).

---

## 2. Execution order

1. **Manual checklist.** Run the 40 UI checks in §3 in order. Each block only needs the seeded state, plus the `set_ff`, POS Settings or UIT-rule changes the row names. Run the smoke rows first (U-01, U-06, U-09, U-15, U-23). Stop if any of them fails.
2. **Existing vitest:** `cd apps/pos_next/POS && yarn test:run`. The relevant specs are:
   - `friendsAndFamily*.spec.js`, `couponLines`, `couponPerLineFnf`, `couponMaxDiscountCap`;
   - `emailVerificationPanel`, `customerVerification`, `posSettings.verification`;
   - `posCartDiscountLimits`, `posCartHeaderDiscount`, `posCartCouponPerLine`, `posCart.salesOrder`;
   - `manualDiscount`, `useInvoiceFnfMarkers`.
3. **The 12 probes** in §4, using `page.evaluate` from a logged-in `uit-cashier` tab.
4. **Playwright smoke** (§6): 11 stable paths, added only after steps 1–3 pass.
5. **Teardown and isolation check** (U-40).

---

## 3. UI checks (40)

Unless a row names another, the profile is `UIT-FF Profile` and the user is `uit-cashier`. "F&F customer" means `UIT-Verified`. "Plain customer" means `UIT-Unverified`.

**A row that changes a setting restores it at its end:**
- F&F Settings: `reset_ff`;
- POS Settings: back to S0;
- a UIT rule: re-enable it.

Nothing a row changes may leak into the next row.

### 3.1 OTP and the customer dialog

| # | Check (old IDs) | Steps | Expected UI | Expected server | Src |
|---|---|---|---|---|---|
| U-01 | **Frappe Email verify** (OTP-01) | Edit `UIT-OTP1` → Verify → read the code from Mailpit → enter it. | The code step and the "Code expires in {0}" countdown, then "Email verified" (`verified-badge`). | One Mailpit message with a 6-digit code. `custom_email_verified = 1`, `custom_verified_email` is the lower-cased email, `custom_email_verified_via = frappe_email`. An audit Comment with no code in it. `LOG(Eligibility Applied)` with the domain only. | P2-T3/T4/T8d |
| U-02 | **Panel failures, parameterised** (OTP-02, OTP-05, OTP-07). Customer `UIT-OTP2`. | (a) Send, then enter a wrong code. (b) Send, wait out the cooldown, Resend, enter the first code, then the second. (c) As uit-manager set TTL 60 s, send, wait 70 s, enter the code. Then set TTL back to 900. (b) verifies UIT-OTP2, so before (c) change its email to `uit-otp2b@uit-ff.example` to reset it. | (a) "Wrong code (or email changed)." and the panel stays on the code step. (b) The first code gives "Wrong code…"; the second gives "Email verified". (c) "Code expired. Request a new one." (`expired-msg`). | (a) and (c): not verified. (b): two messages. | P2-T3 |
| U-03 | **Email change** (OTP-09, OTP-08). Customer `UIT-OTP1`, verified by U-01. | (a) Put UIT-OTP1 in a cart with UIT-A, change its email in the POS dialog to `uit-otp1b@uit-ff.example` and save. (b) Send a code to that address, change the email to `uit-otp1c@uit-ff.example`, save, enter the old code. | (a) The badge clears, the cart loses F&F on refresh, and Verify is offered again. (b) "Wrong code (or email changed)." (or "Save the customer's email before verifying it." while unsaved). | (a) The verification fields are cleared, plus a Comment and `LOG(Eligibility Removed)`. (b) Not verified. | P2-T8d, R16 |
| U-04 | **Send control** (OTP-16, OTP-17). Customer `UIT-OTP1`. | (a) Double-click Send. (b) `context.setOffline(true)` (or DevTools offline), then open the panel. | (a) One send, or "Another request is in progress. Please wait." (b) "Verification requires an internet connection." (`offline-msg`), and Send is disabled. | (a) One Mailpit message. | P2-Review 2, P2-T6 |
| U-05 | **Magento provider** (OTP-M1, OTP-M4). Profile `UIT-NOFF Profile` after ops O-3. | (a) Run `mark_synced('UIT-Mag')` (its phone is seeded), then Verify and enter the code from Mailpit. (b) Change UIT-Mag's email to `uit-mag-down@uit-ff.example`, then Send. | (a) "Email verified". (b) "Could not send the code, please try again." (generic, not the provider's text). | (a) `custom_email_verified_via = magento`, phone sent as E.164. (b) `code: unavailable`; the attempt is given back. | P2-T7, P2-T7b |

### 3.2 Cart, eligibility and F&F pricing

| # | Check (old IDs) | Steps | Expected UI | Expected server | Src |
|---|---|---|---|---|---|
| U-06 | **Badge and line** (ELG-01) + INV-2 | F&F customer, add UIT-A, then reload. | The badge "F&F 30%" (`fnf-customer-badge`). "Friends & Family 30% applied to 1 item(s) — saving 30.00" (currency formatted). The line shows 100 → 70. After the reload it is unchanged. | `check_friends_and_family_eligibility` returns `eligible: true, reason: email_verified` | §8.4 |
| U-07 | **Not eligible, then switch back** (ELG-02, ELG-12) | Plain customer + UIT-A. Then switch to the F&F customer, then back again. | Plain customer: no badge, "No Friends & Family: verify the email of customer {0} (OTP) first", list price. The switches add and remove F&F and the badge each time. | `reason: email_not_verified`, `ff_member: true` | eligibility.py, §8.4 |
| U-08 | **Profile without F&F** (ELG-08); the crafted half is P-02 | `UIT-NOFF Profile`, F&F customer, UIT-A. | No badge, no F&F, no F&F message. | `reason: profile_not_allowed` | §6.5 |
| U-09 | **F&F sale submitted** (FFP-01) + INV-1 | F&F customer, UIT-A ×1, pay cash, submit. | The line shows 100 → 70 with the pink F&F badge. The receipt shows "Friends & Family discount". | `SII[UIT-A]`: rate 70, F&F markers, `posnext_fnf_discount_amount` 30. One `USG` row (30, `period_key` YYYY-MM). `UT` +30. `LOG(Discount Applied)`. | P1-T5/T6, P2-T8h |
| U-10 | **Caps and rounding, parameterised** (FFP-12, FFP-20, CUR-01, CUR-02) | (a) `set_ff max_discount_per_order=50`, then UIT-A ×3 and submit. (b) Same cap, UIT-ODD ×7 and submit. (c) `reset_ff` (cap back to 500), then UIT-ODD ×3. | (a) The lines are reduced to a total of 50. "Friends & Family reduced by the discount limit", and the cap message names 50 in currency format, not "30%". (b) The same note. (c) A line discount of 30.00, and the total equals the sum of the lines. | (a) Σ `posnext_fnf_discount_amount` = 50.00, `USG` 50, `LOG(Cap Hit)`. (b) Σ = exactly 50.00 at 2 dp. (c) `USG.amount` = the line amount. | P1-T5, P1-T6b/T6d |
| U-11 | **Kill switch while a cart is open** (FFP-18) | Tab 1 and tab 2 each price the F&F customer + UIT-A. Run `set_ff enabled=0`. (a) Tab 1 holds (saves) the draft. (b) Tab 2 pays and submits. Then `reset_ff`. | (a) The draft saves at list price. (b) Refused with the title "Friends & Family discount not allowed" and "The invoice is already paid, so it was not re-priced. Correct the cart and take payment again." | (a) No markers. (b) Nothing submitted. | P1-T6c, R42 |
| U-12 | **Best discount per line** (BST-01, BST-02) | F&F customer. (a) UIT-B (20% rule). (b) UIT-C (40% rule). | (a) F&F wins, 200 → 140: "Friends & Family discount (30%) is better than … (20%) — Friends & Family applied, … not applied." (b) The promotion wins, 50 → 30, with the decision note on the line. | (a) F&F markers and a signed `posnext_fnf_replaced_discount`. (b) No markers, `LOG(Comparison Lost)`. | R5, P1-T4 |
| U-13 | **Order offer beats F&F** (BST-04) | F&F customer, UIT-EXCL ×13 + UIT-A ×1. The list is 1140, so `UIT-PR-CART5` (5%) applies and beats F&F's 30. | Header discount from the offer, and the line note "Invoice promotion applied instead of Friends & Family". The cart-total gift row UIT-GIFT appears, because the cart is ≥ 500 and holds no F&F. | `SI.discount_amount` = 5% of the total. No F&F markers. `LOG(Order Comparison)`. | best_discount order level |

### 3.3 Coupons

| # | Check (old IDs) | Steps | Expected UI | Expected server | Src |
|---|---|---|---|---|---|
| U-14 | **Coupon dialog basics** (CVF-01, CPN-04, CPN-20) | (a) F&F customer, open the dialog. (b) Apply `NOPE-123`. (c) Apply UIT-L10 to a plain customer's cart, then Remove. | (a) The hint "Friends & Family customer (30%). Only the better discount applies — coupon or Friends & Family, never both." (`coupon-fnf-hint`). (b) "Sorry, this coupon code does not exist". (c) "Discount has been removed", and the lines go back to list price. | — | CouponDialog |
| U-15 | **Line and order coupons, counted on submit** (CPN-01, CPN-02, CPN-21) + INV-1 | Plain customer. (a) UIT-A + UIT-B, apply UIT-L10, hold the draft, then resume, pay and submit. (b) UIT-A ×2, apply UIT-O40, submit. | (a) "UIT-L10 applied successfully". UIT-A shows 90. UIT-B keeps its 20% ("The coupon leaves lines that already have a discount alone."). (b) The header "Coupon discount" shows 40. | (a) The draft does not change `CPN.used`; the submit adds 1. `SI.coupon_code = UIT-L10`, and `posnext_coupon_code` is on UIT-A only. (b) `SI.discount_amount` 40 and no line coupon tag. | P2-T8c, §8.12 |
| U-16 | **Scope and conflict** (CPN-13, plus the seeded Better-of-the-two coupon). Promotions only. | Plain customer. (a) UIT-A + UIT-A2, apply UIT-SI20. (b) UIT-B + UIT-C, apply UIT-BET. | (a) Only UIT-A shows 80. (b) UIT-B takes the coupon's 30% (it beats 20%). UIT-C keeps 40%. The toast names UIT-C as the line where the promotion saves more. | (a) `posnext_coupon_code` on UIT-A only. (b) UIT-B is tagged with the coupon; UIT-C keeps `UIT-PR-C40`. | R78, coupon_engine |
| U-17 | **100% coupon = free row** (CPN-22) + INV-1 | Plain customer, UIT-A, apply UIT-L100, submit. | The line shows Free / 0. | `SII[UIT-A]`: `is_free_item` 1, rate 0, `posnext_coupon_code = UIT-L100`. `CPN.used` +1. | R74 |
| U-18 | **F&F vs line coupon, parameterised** (CVF-02, CVF-03, CVF-12, ELG-14) + INV-2 on CVF-03 | F&F customer. (a) UIT-A + UIT-L10. (b) UIT-A + UIT-L50, then reload. (c) From state (b), switch to the plain customer. | (a) Warning (`coupon-comparison-message`) "Friends & Family discount (30%) is better than coupon UIT-L10 (10%)…". The coupon is not applied. (b) The coupon wins, at 50. The badge is muted, with the title "Coupon UIT-L50 applied instead of Friends & Family". The cart message "… discounts are never combined." The state survives the reload. (c) The coupon's 50 stays, and no stale F&F appears on any line. | (a) After submit: `coupon_code` blank, `CPN.used` unchanged, `USG` written. (b) `posnext_coupon_code = UIT-L50`, no markers, no `USG`. | P1-T6d, P2-T8j, 8j-rev I2 |
| U-19 | **Per line: coupon on one line, F&F on another** (CVF-04, CVF-11) + INV-1 | F&F customer, UIT-EXCL + UIT-A, apply UIT-L20. Submit one cart. On a second identical cart, press Remove coupon. | UIT-EXCL gets the coupon (80 → 64). UIT-A keeps F&F (70). The total discount is 46. After Remove: F&F stays on UIT-A, and UIT-EXCL is back at list. | UIT-EXCL is tagged with the coupon. UIT-A has the markers. `SI.coupon_code = UIT-L20`. `USG` 30 only. The saved invoice equals the cart. | P2-T8j, R54 |
| U-20 | **Order coupon vs F&F** (CVF-06, CVF-07) | F&F customer. (a) UIT-A ×2 (F&F 60), apply UIT-O40. (b) UIT-A ×2 + UIT-EXCL, apply UIT-O100, submit. | (a) Rejected, because F&F 60 is more than 40. (b) The coupon wins the whole order: the header shows 100, and F&F is removed from every line. | (b) No markers anywhere. `SI.discount_amount` 100. No `USG`. `CPN.used` +1. | best_discount_coupon |

### 3.4 Offers, free items and edit dialogs

| # | Check (old IDs) | Steps | Expected UI | Expected server | Src |
|---|---|---|---|---|---|
| U-21 | **BXGY blocks F&F** (CMP-01) + Open Q4 | F&F customer. (a) UIT-BXGY ×2 + UIT-A. (b) UIT-BXGY ×1 alone, which is below "buy 2". | (a) The UIT-BXGY lines stay at full price with the note "Promotion item — not eligible for Friends & Family". A "Free" UIT-BXGY ×1 row appears. UIT-A gets F&F. (b) UIT-BXGY gets F&F (60 → 42). | (a) No markers on the BXGY lines. The free row has `is_free_item` 1 and the BXGY rule. `USG` only for UIT-A. | R7, R19 |
| U-22 | **Free gift with F&F, parameterised** (CMP-05, CMP-06) + Open Q1, Q5 + INV-1 | F&F customer. Run each kind with `set_ff allow_free_gift_with_ff=0`, then `=1`. Kinds: (i) free item, UIT-TRIG. (ii) GWP, UIT-GWP1 + UIT-GWP2 (promotions only). (iii) cart total, UIT-A ×8 (list 800, after F&F 560), then UIT-A ×7 (list 700, after F&F 490). Then `reset_ff`. | **allow 0:** each gift is removed. The trigger lines keep F&F, and the gift rule is detached from them. **allow 1:** (i) and (ii) show F&F **and** the free row. (iii) shows the gift at ×8 but **not** at ×7, because the minimum is measured after F&F (Q5). | allow 0: no free row is saved. allow 1: the free row is saved with its rule (`UIT-PR-FREE` / `UIT-PR-GWP` / `UIT-PR-CART-GIFT`). | R8/R10, P1-T3, §7 |
| U-23 | **Offer shapes, plain customer, parameterised** (OFR-01, OFR-08, OFR-02, OFR-09, OFR-06) + INV-2 on OFR-01 | (a) UIT-BXGY ×2, then reload. (b) UIT-TRIG ×1. (c) UIT-P100. (d) UIT-A ×5 (500), then qty 4. (e) Gift Pool: **not seeded**, so skip unless a UIT Gift Pool scheme is added. | (a) The paid ×2 line at 60, plus a separate "Free" ×1 row; it survives the reload. (b) UIT-TRIG at 100, plus a UIT-GIFT free row. (c) The line shows Free / 0. (d) The gift row appears at 500 and is gone at 400. | (a) and (b): the free row has `is_free_item` 1, rate 0, and the rule on the row. (c) `is_free_item` 1, `pricing_rules = UIT-PR-P100`. | zero-audit, R74, R84/85 |
| U-24 | **Locks** (OFR-11, OFR-12) | (a) Add UIT-NOPRICE. (b) Open EditItemDialog on the free row from U-23 (a). | (a) "Item UIT-NOPRICE has no price and cannot be sold at zero price." It is not added. (b) "Free promotional items cannot be edited". | — | R77, EditItemDialog |
| U-25 | **Stale offer refused** (OFR-15); the crafted half is P-06 | Plain customer, UIT-TRIG + gift. In Desk, disable `UIT-PR-FREE`. The cashier pays without refreshing. Then refresh and pay again. Re-enable the rule afterwards. | First pay: refused with "Row {0}: free item UIT-GIFT is not backed by an offer (free qty 0 expected, 1 sent)." and "The offers changed. Refresh and re-apply offers." After the refresh: the gift is gone and the sale saves. | Nothing saved on the refused try. `ERR("Unbacked free item")` after the flush. | P2-T8i, R58 |
| U-26 | **Edit dialogs: item and header** (MAN-02, MAN-05, MAN-08, HDR-03); the crafted halves are P-03, P-04, P-05 | (a) S0: open EditItemDialog. (b) S2: rate 85 on UIT-A. (c) S2: rate 0. (d) S4: type a 15% invoice discount in the payment dialog. Then back to S0. | (a) Rate disabled, "Rate editing is disabled". (b) "Rate reduction of 15.00% exceeds maximum allowed discount of 10%". (c) "Rate must be greater than zero". (d) The input is capped at 10%. | — | R87, P2-T8m |
| U-27 | **Sales Order strip and back** (SO-01, SO-02) | F&F cart (UIT-A, UIT-B). Switch the document type to Sales Order, then back to Sales Invoice. | SO: the toast "Friends & Family discounts apply to invoices only", lines at list, totals recalculated. Back on SI: F&F is applied again. | — | P2-T8f |

### 3.5 Offline, network and the queue

| # | Check (old IDs) | Steps | Expected UI | Expected server | Src |
|---|---|---|---|---|---|
| U-28 | **Offline sale syncs** (OFL-01) | Plain customer, UIT-A + UIT-BXGY ×2. Go offline, pay, then go online and sync. | "Invoice saved offline. Will sync when online", then the Offline Invoices count goes to 0. | Submitted, with an `OIS` row. The free row is backed. Totals = paid. | P2-T8i |
| U-29 | **Offline disagreement, parameterised** (OFL-02, OFL-03, OFL-04, OFL-06) | (a) Go offline first, then select the F&F customer, add UIT-A, pay, and sync. (b) Price the F&F customer + UIT-A online, go offline, pay, sync. (c) As (b) with `UIT-Cap`, but while offline another tab uses up its monthly cap: set the cap to the used amount + 30 first, spend it, sync, then `reset_ff`. (d) Plain customer, UIT-TRIG + gift offline; disable `UIT-PR-FREE` before the sync, and re-enable it after. | (a) No badge while offline. Every row: the sale syncs with no error shown to the cashier. | (a) Saved at 100, `LOG(Offline Disagreement, missing_fnf)`. (b) Saved at 70, `USG` 30. (c) Saved at 70, `LOG(Offline Disagreement, cap_exceeded)`, `USG` over the cap. (d) Saved, `ERR("Unbacked free item")`. | P1-T6c, §9, P2-T8i |
| U-30 | **Offline coupon overshoot** (OFL-08) | Before each row, set UIT-MAX1 `maximum_use` = used + 1. Tab A applies UIT-MAX1 online, goes offline and pays. Tab B (`uit-cashier2`) submits with UIT-MAX1. Tab A syncs. Set the UIT-FF POS Settings `offline_coupon_overshoot` to (a) Allow and log, then (b) Reject. Then back to Allow and log. | (b) The invoice stays in the queue as failed, visible to the cashier. | (a) Counted (used = max + 1) and an Error Log. (b) Not submitted. | R35 |
| U-31 | **Network failure and retry, distinct from offline** (new) + OFL-09 | (a) Block `apply_offers` once (DevTools request blocking, or Playwright `route.abort()`), change a qty, then unblock and change it again. (b) Let `submit_invoice` reach the server but drop the response (Playwright `route.fetch()` then `route.abort()`), then press Complete again. (c) Force a duplicate sync of one queued `offline_id`. | (a) A non-blocking error. The cart stays usable, and the next change re-prices. (b) A retry message, then success, and only one receipt. (c) One invoice. | (b) and (c): exactly one Sales Invoice for the cart, and `USG` and `CPN.used` counted once. | P2-T8i R68, P1-T5 |
| U-32 | **Queue survives a reload** (new) | Make an offline sale. Reload the tab while still offline. Then close the tab, reopen the POS and go online. | After the reload the Offline Invoices count is still 1. After reopening it syncs once and the count is 0. | One invoice and one `OIS`. | §9 |

### 3.6 Receipts (each one saves an artifact)

| # | Check (old IDs) | Steps | Expected UI | Expected server | Src |
|---|---|---|---|---|---|
| U-33 | **Receipts, parameterised** (RCP-01, RCP-02, RCP-04) | (a) POS print of the U-19 invoice, plus a free row (U-23 b). Capture the print HTML: in Playwright, catch the print window's `page.content()`; by hand, "Save as PDF". (b) Jinja `POS Next Receipt` of the same invoice: `/api/method/frappe.utils.print_format.download_pdf?doctype=Sales%20Invoice&name=<SI>&format=POS%20Next%20Receipt`. (c) POS print of U-17. Store each one as `artifacts/<check>-<SI>.{html,pdf}` next to the run notes. | (a) The F&F line is labelled "Friends & Family discount". The coupon line says "Discount" (an untranslated literal today). The free row shows "(FREE)" and "qty × 0.00 = 0.00". Amounts have 2 dp and no symbol. (b) The free row name with a green "(FREE)", "qty × FREE", 0.00. F&F appears only as "Discount (x%)". (c) "(FREE)". | — | PN-130, §8.7, zero-audit, R74 |

### 3.7 Language, layout and accessibility

| # | Check (old IDs) | Steps | Expected UI | Expected server | Src |
|---|---|---|---|---|---|
| U-34 | **Arabic** (I18N-01, I18N-02, I18N-03) | Set the POS language to Arabic. (a) The verification panel and its results (rerun U-02 a on `UIT-OTP3`). (b) The U-12 (a) comparison. (c) Verify `UIT-OTP3`, entering the code in Arabic-Indic digits (٠-٩). | (a) All Arabic, no English fallback. (b) The Arabic `message_ar` ("خصم الأصدقاء والعائلة (30%) أفضل من …"). (c) Accepted and verified. | (b) The payload carries `message_ar`. | P2-T9, §8.5 |
| U-35 | **RTL layout** (I18N-06) | Arabic. Screenshot four things: the cart badge, an F&F line note, the Coupon dialog and the payment discount field. | No clipped or overlapping text; amounts are readable. | — | — |
| U-36 | **Narrow layout** (new) | Viewports 390×844 and 768×1024: cart, payment dialog, Coupon dialog, OTP panel. | No horizontal page scroll. Every button can be reached without zoom. Touch targets are at least about 40 px. The badge and line notes wrap rather than truncate the amount. | — | — |
| U-37 | **Accessibility basics** (new) | Keyboard only: open the Coupon dialog, type, Enter, then Esc. Enter the OTP and press Verify. Trigger U-14 (b) and U-02 (a). | Focus moves into each modal and is trapped there; Esc closes it and focus returns to the opener. After an error, focus or `aria-live` reaches the error text. Every control with a `data-testid` has an accessible name (`getByRole` finds it). | — | — |

### 3.8 Two tabs

| # | Check (old IDs) | Steps | Expected UI | Expected server | Src |
|---|---|---|---|---|---|
| U-38 | **Two-tab submit race, parameterised** (CON-01, CON-02, CON-04) + Open Q3 | Tab A is `uit-cashier`, tab B is `uit-cashier2`. For (a) and (b), set the `UIT-Cap` monthly cap to its used amount + 40, and in both tabs price UIT-A ×2 (the remaining 40 shows in both). A submits, then B. (a) Allow and log. (b) `set_ff on_cap_breach_at_submit='Block submit'`. (c) Set UIT-MAX1 `maximum_use` = used + 1, apply it in both tabs, A submits, then B. End (a) and (b) with `reset_ff`: the monthly cap is site-wide and would block UIT-Verified. | (a) Both submit. (b) B is refused **after** its payment was entered: the title "Friends & Family cap exceeded". (c) B: the title "Coupon Not Applicable", "Coupon UIT-MAX1 has reached its usage limit". | (a) `UT` = cap + 40; B has `LOG(Cap Hit)` / `LOG(Paid Disagreement, cap_exceeded)`. (b) `UT` = cap. Record whether B's step-1 draft, holding its payments, is left in Sales Invoice (docstatus 0). (c) `CPN.used` = max. | P1-T5, P1-T6c, R33 |
| U-39 | **Same address verified twice at once** (CON-06) | Give `UIT-OTP3` and `UIT-Shared` the same new address `uit-race@uit-ff.example`. Send codes in both tabs, then verify both at once. | Exactly one shows "Email verified". The other shows "This email is already verified for another customer." or "Another request is in progress. Please wait." | One customer has that `custom_verified_email`. | P2-T8d, R39 |

### 3.9 Isolation

| # | Check | Steps | Expected | Src |
|---|---|---|---|---|
| U-40 | **Teardown isolation** (new) | Close the UIT shift. Run `teardown`, then `check`. In each browser that was used: the Offline Invoices list is empty, and DevTools → Application → IndexedDB shows no queued UIT invoice. In Mailpit, delete the messages to `uit-*`. | `check` prints `"ok": true`: no UIT records, no rows linked to UIT customers, profiles, items or coupons, no F&F ledger rows, no GL or Payment Ledger rows for UIT parties, and no pending snapshot. F&F Settings and the disabled live rules are back to their pre-seed values. If `check` lists leftovers, the run is not isolated: fix it before the next run. | Codex Q6 |

---

## 4. Scripted request probes (12)

Run them from a logged-in `uit-cashier` tab, so the session cookie and CSRF token apply. Build every payload from the POS's own captured `update_invoice` request (DevTools "Copy as fetch", or `page.waitForRequest`), and change only the field named. "Refused" means HTTP 417 `ValidationError` (or 403 `PermissionError`) and nothing saved.

```js
await page.evaluate(async ([method, args]) => {
	const r = await fetch(`/api/method/${method}`, {
		method: "POST",
		headers: { "Content-Type": "application/json", "X-Frappe-CSRF-Token": window.csrf_token },
		body: JSON.stringify(args),
	});
	return { status: r.status, body: await r.json() };
}, ["pos_next.api.invoices.submit_invoice", { invoice: payload, data: {} }]);
```

| # | Probe (old ID) | Payload change | Expected | Src |
|---|---|---|---|---|
| P-01 | OTP-19 | `update_pos_settings` as uit-cashier with `otp_max_sends_per_hour = 100000`; then the same as uit-manager. | Cashier: the stored value stays 5. Manager: it persists. Set it back to 5. | P2-T8e C1 |
| P-02 | ELG-08 | Unpaid `update_invoice` on `UIT-NOFF Profile`, F&F customer, UIT-A carrying F&F markers at 30%. | Saved re-priced to list, with the markers cleared. | §6.5 |
| P-03 | MAN-05 | Under S2: `submit_invoice` with UIT-A at rate 85. | Refused: "Row 1: item UIT-A is reduced from 100.0 to 85.0 (15.0%), above the maximum allowed discount of 10.0%." | R87 |
| P-04 | MAN-08 | Under S2: rate 0 without `is_free_item`. | Refused: "Item UIT-A cannot be sold at zero price. Free items must come from an offer." | R71/R72/R74 |
| P-05 | HDR-03 | Under S4: a 200 cart with a 15% header. | Refused: "…the manual part 30.0 is 15.0% of 200.0, above the maximum allowed invoice discount of 10.0%." | P2-T8m |
| P-06 | OFR-15 | With `UIT-PR-FREE` disabled: `submit_invoice` carrying the UIT-GIFT free row. | Refused, plus `ERR("Unbacked free item")` after the flush. | P2-T8i |
| P-07 | SEC-01 | Online `submit_invoice` adds a free row UIT-B ×1, `is_free_item` 1, with no offer. | Refused: "Row {n}: free item UIT-B is not backed by an offer (free qty 0 expected, 1 sent)." | P2-T8i |
| P-08 | SEC-07 | UIT-A with `price_list_rate` 1000, `discount_percentage` 99 and rate 10, to reach the cart-gift minimum. | Refused. In any saved variant, `price_list_rate` is overwritten with the server price. | R62, R88 |
| P-09 | SEC-12 | F&F customer, markers at 60% (rate 40). (a) Unpaid `update_invoice`. (b) Paid `submit_invoice`. | (a) Saved, re-stamped to 30% (rate 70). (b) Refused (over_discount). | P1-T6c |
| P-10 | SEC-19 | A row with a forged `posnext_fnf_replaced_discount`: a well-formed v2 envelope claiming 90% with a bad `sig`, and also a legacy unsigned JSON. | Ignored: the line is re-priced from its rules, never at 90%, and there is no 500. | P1-T4, R25 |
| P-11 | SEC-20 | `pos_profile` blank; `pos_profile` = a profile the user is not on (`Main POS Profile`); an existing invoice `name` from another profile. | `PermissionError` ("POS Profile is required" / "You don't have access to this POS Profile" / "This document cannot be changed from this POS Profile."). | P2-T8e I2 |
| P-12 | SEC-23 | The cashier writes `custom_email_verified = 1` through `update_customer`, or with a Desk save. | The field stays 0. | gap C |

Optional: run SEC-24 (UOM factor forced) only if UOM is a release risk. Seeding a Box UOM for it is not part of the seed.

---

## 5. Open questions (5, each with a proposed default: **pending user**)

| # | Question | What the code does today | Proposed default (pending user) |
|---|---|---|---|
| Q1 | Does `allow_free_gift_with_ff` apply only to gift kinds? | **Yes, but GWP depends on how the rule is built.** The checkbox governs `CONFIGURABLE_GIFT_KINDS` = free_item (Gift Pool included), gwp, cart_total_gift and brand_gift (`friends_and_family_gifts.py`). BXGY and Item Level lines are always blocked, whatever the checkbox says, and price rules compete. `classify_promotion` tests "Product + same_item" **before** the GWP type. ERPNext sets `same_item = 1` on any Product rule saved with no free item and no mixed conditions, so such a "GWP" classifies as **bxgy**: its lines get no F&F and its gift is always kept. A mixed-SKU GWP with a free item classifies as **gwp** and follows the checkbox. U-22 (ii) tests the gwp shape; the seed checks the kind. | The checkbox applies only to gift kinds. Update the Phase 1 UI step (P1-T8 Step 3(b)) to say so, and to note that a same-item GWP counts as Buy X Get Y. |
| Q2 | Desk Sales Invoices that are not POS (`is_pos = 0`) for an F&F customer? | **No F&F, and no counting either.** `apply_friends_and_family_on_invoice` returns early when the invoice is not POS (`friends_and_family_apply.py`, the `is_pos_doc` check). The ledger counts only `is_pos = 1` (`ff_ledger.py`). So there is **no "applied but not counted" gap.** **Flag:** unlike Sales Orders and Quotations (`ff_non_invoice.strip_ff`), nothing strips F&F markers from an `is_pos = 0` Sales Invoice. A Desk or API user can save `posnext_*` markers with a manual discount, and it stays as an uncounted manual discount. Returns behave the same: `ledger_rows` is gated by `is_tracked`, so they are not counted either. | No F&F on Desk non-POS invoices until Phase 3. Decide whether Phase 3 adds a strip and log for them, as SO/Quotation have. |
| Q3 | With Block submit, does the refusal come before payment? | **No. It comes after the payment is entered.** The throw is in `ff_ledger.on_submit`. In the POS the payment dialog completes first; then `useInvoice.submitInvoice` saves the draft with its payments (`update_invoice`) and calls `submit_invoice`, which throws. Offline sales are never blocked. The refusal is reachable only when the cap was used up between pricing and submit (U-38 b), because the cart already caps F&F at pricing time. The step-1 draft appears to stay behind; U-38 (b) records this. | The refusal comes before payment. That needs a re-check when Payment opens (§13b, the DPS-09 idea, Phase 4). Until then it is a known gap: the refusal comes after payment. |
| Q4 | Buy X Get Y below its minimum? | **F&F applies, as the default says.** `ff_compatibility.block_ineligible_lines` skips a BXGY rule when the line qty is below its `min_qty`. Only `min_qty` is checked: a BXGY gated by `min_amt` or a `condition` still over-blocks. A line that already carries the rule in `pricing_rules` is blocked at any qty. U-21 (b) asserts the qty case. | Follow ERPNext: the rule does not apply, so F&F applies. Extend the check to `min_amt` and `condition` later. |
| Q5 | Gift threshold basis (`allow_free_gift_with_ff = 1`)? | **After F&F.** In promotions' `apply_offers`, F&F runs first. `_fold_line_discounts` then feeds the post-F&F rates to ERPNext's transaction engine, so a cart-total gift's `min_amt` is measured on the net after line discounts, F&F included. When F&F loses to an order promotion, the cart without F&F is used. pos_next's free-row backing check (`invoices._offer_payload`) re-runs the evaluator on the rows at the rates charged, so the server agrees with the cart. With the checkbox off, the cart-total gift is dropped whenever any line has F&F. | Test as built (After F&F; U-22 iii). The Phase 3 setting `gift_threshold_basis` decides it later (Miraaya R11 wanted After; the neutral default in §7 is Before). |

Questions dropped from the old E.4:
- **Folded into checks the code answers:**
  - old Q8, a customer verified while a cart is open: U-03, U-07;
  - old Q15, walk-in per-customer limits: server tests.
- **Dropped, because no kept check depends on them:** old Q6, Q7 and Q9–Q14.

---

## 6. Small Playwright smoke harness (after §3–§4 pass)

- **Location:** `POS/e2e/`. Install with `cd POS && yarn add -D @playwright/test` (yarn, not npm). It is not installed today.
- **Files:** one spec file and one `global-setup.js`. The setup logs in with `POST /api/method/login` using the passwords the seed printed, and writes one `storageState` per user (`uit-cashier`, `uit-cashier2`).
- **Selectors:** only the existing `data-testid`s and `getByRole`. No page objects and no fixture framework.
- **Data:** the seed script only. No reset between tests beyond clearing the cart.
- **Mailpit:** read with `GET /api/v1/search?query=to:"<email>"`, take the code with `/\b\d{6}\b/`.
- **Paths, one test each (11):**
  1. U-01 OTP;
  2. U-06 badge + reload;
  3. U-09 F&F submit + INV-1;
  4. U-15 (a) line coupon;
  5. U-18 (b) CVF-03 + reload;
  6. U-23 (a) BXGY free row;
  7. U-25 stale offer;
  8. U-29 (a) offline missing F&F (`context.setOffline`);
  9. U-33 (a) receipt HTML artifact;
  10. U-35 RTL screenshot;
  11. U-38 (a) two-context race.
- **Growth rule:** add a path only when the same regression has escaped twice.

---

## Appendix A. Later: tracked, not in this run (40)

Each line gives the ID, the title and the phase.

- ELG-15 Badge "F&F – verify email" with inline Verify; grey badge with reason — P4
- ELG-16 Eligibility call fails → "Could not check F&F — Retry" — P4
- ELG-17 Several programs; program selection; tooltip lists the others — P3
- ELG-18 Program by Customer Group / Customer List — P3
- ELG-19 F&F code in the Coupon dialog (valid / invalid / exhausted / not needed / needs customer) — P3
- ELG-20 `ff_enabled` master switch stamps `ff_disabled_on` — P3
- FFP-24 `cap_period` Week / Year / Program lifetime — P3
- FFP-25 `cap_scope` All companies (same currency only) — P3
- FFP-26 `price_floor` + `min_margin_percent` note — P3
- FFP-27 `earn_loyalty_on_ff` / `sales_commission_on_ff` — P3
- BST-09 Global `tie_breaker` = Other discount — P3
- BST-10 Re-compare after a cart/customer change with a coupon applied — P4
- CMP-13 Compatibility matrix per kind, cart and invoice parity — P3
- CMP-14 "Gift wins, cancel F&F on whole order" — P3
- CMP-15 Promotional Scheme `ff_compatibility` override + effective-policy display — P3
- CMP-16 Neutral defaults on a fresh site — P3
- CMP-17 Whole-invoice rule condition "no gifts for F&F members" — P3
- GFT-03 `gift_threshold_basis` = Before F&F — P3
- GFT-04 `gift_threshold_basis` = After F&F — P3
- GFT-05 `mixed_trigger_policy` = Drop gift if any trigger has F&F — P3
- GFT-06 `mixed_trigger_policy` = Evaluate on non-F&F lines only — P3
- GFT-07 `mixed_trigger_policy` = Keep gift — P3
- CPN-25 Offline Coupon dialog "coupon unavailable" — P4
- CPN-26 Coupon re-compared after a cart change — P4
- CVF-17 `coupon_vs_ff_granularity` = Whole order — P3
- CVF-18 Both savings shown before confirming — P4
- CVF-19 One code per cart (F&F code + coupon) — P3
- SO-10 Full Sales Order F&F support — P3
- DPS-09 Opening Payment forces eligibility refresh + re-price — P4
- OFL-12 Offline posting date = device date, clamped to the shift — core
- OFL-13 Offline F&F from cached rules + banners — P4
- OFL-14 `offline_after_disable` reason — P3
- RET-07 `on_return_gift` Warn / Require gift back — P3
- RET-15 `release_coupon_on_full_return` — P3
- RCP-05 Program label, savings total and currency formatting on both receipts — P4
- RCP-06 Cap balance on the receipt (`show_balance_on_receipt`) — P4
- CLS-05 "Discounts by source" on closing shift; cashier score excludes F&F — P4
- I18N-07 Single `message` + translations table on F&F Message — P3
- I18N-08 POS reads only `message` — P4
- CUR-06 POS `currency.js` locale/symbol/precision from the currency — P4

The cut current-phase rows are covered by the server suites:
- the rest of OTP, ELG, FFP, BST, CPN, CVF, CMP, OFR, MAN, HDR, SO, DPS, PAY, RET, CAN, SEC, CUR and I18N;
- the test files are `test_email_verification.py`, `test_otp_frappe_email.py`, `test_discount_enforcement.py`, `test_free_rows.py`, `test_ff_markers.py`, `test_security_hardening.py`, `test_coupon_usage.py`, `test_return_safety.py`, and the promotions F&F suites.

## Appendix B. Manual ops checklist (not in the 52; the tester does these by hand)

- **O-1 Code and build.**
  - The apps are on their reviewed feature tips.
  - Run `bench --site nexus.local migrate`, then `cd apps/pos_next/POS && yarn build`, then `bench --site nexus.local clear-cache`, then restart bench.
  - The seed refuses to run on an unmigrated site (missing fields).
- **O-2 Mailpit.**
  - Start it with `~/bin/mailpit --smtp 127.0.0.1:1025 --listen 127.0.0.1:8025`. It does not survive a reboot.
  - Check: `curl -s localhost:8025` returns HTML.
  - Check: Email Account "Dev Mailpit" has `enable_outgoing` = 1 and `default_outgoing` = 1.
- **O-3 Fake Magento (U-05).**
  - Needs `developer_mode` 1.
  - Run `bench --site nexus.local execute magento_integration.dev.fake_magento.enable --kwargs "{'pos_profile': 'UIT-NOFF Profile'}"`.
  - It changes only that profile's POS Settings row, which teardown deletes, plus Magento OTP Settings: note its values before and restore them after.
- **O-4 Service failures (old OTP-14, OTP-15).**
  - Disable the Dev Mailpit Email Account, then Verify. Expect "Email verification is not set up. Ask an administrator."
  - Stop Mailpit, then Send. Expect "Could not send the code, please try again."
  - Restore both.
- **O-5 developer_mode off (old OTP-M9).**
  - Run `bench set-config developer_mode 0` and restart, then Verify on UIT-NOFF. Expect "not set up".
  - Restore `developer_mode` 1.
- **O-6 True races (old CON-03, CON-07).**
  - Two people press Submit in the same second. Expect at most "Friends & Family usage is busy for customer {0}, please retry.", and no duplicate `USG`.
- **O-7 Desk cancel, return and closing.** Do these only if they are in the release scope.
  - Cancel the U-09 invoice: `USG` is cancelled and `UT` drops by 30.
  - Return it from the POS: refund 70, and a negative `USG` in the original period.
  - Close the shift: expected = Σ payments, and free rows add 0.
- **O-8 Print dialog and printers.** The browser print dialog itself is not automated; U-33 captures the HTML instead.

## Appendix C. Concerns found while writing

- **`PRLE-0023` and `PRLE-0289` are disabled for the whole company during the run.** They are Transaction rules that also reach Main POS Profile carts. Another agent testing on nexus.local at the same time will see them off until teardown.
- **F&F Settings is a site Single, and the seed's restore rewrites it whole.** That includes the child tables, rebuilt with new row names. If another agent or test (`ff_settings_guard`) changes it during the run, teardown overwrites that change.
- **POS Next lists UIT items only on the UIT profiles** (`item_groups`). The UIT rules are limited to `UIT-Selling SAR`. ERPNext's rule query filters `for_price_list` (`pricing_rule/utils.py`), and that covers the transaction pass too. Still, check once that the offers panel on Main POS Profile shows no `UIT-PR-*` rule.
- **No Gift Pool scheme and no Box UOM are seeded**, so OFR-06 and SEC-24 are skipped unless they are added.
