# Friends & Family — generic, configuration-driven redesign

Date: 2026-11-16 · Status: approved; Phase 1 built, Phase 2 in progress (updated 2026-11-18)
Repos touched: `pos_next` (this repo), `posnext_promotions` (BrainWise-DEV/Promotions), `magento_integration`.
Background study (code, onboarding, cashier walkthrough): `~/ff_study.md`.

---

## 1. Intent — why

Friends & Family (F&F) was built for one client (Miraaya). It works there, but:

- It **cannot work on any other site**: a customer qualifies only with an email verified by OTP, and
  OTP only exists through Miraaya's Magento (`/rest/V1/miraaya/...`, `Magento Setting` from the
  private `masar_miraaya` app). On nexus.local the OTP call returns `not_configured`; nobody can qualify.
- Every client decision is code. The client changed the gift rule three times in two weeks
  (BRD → 8 Nov → 9 Nov) and each change was a 2–3 day paid change request.
- One program per site (a Single doctype).

We want F&F to be a product feature: any company, any number of F&F programs, every business rule the
client argued about is a **setting**, global by default and overridable where it makes sense.
Miraaya must keep exactly today's behaviour after migration, by configuration only.

## 2. Goals / non-goals / anti-goals

**Goals**
1. F&F works on a plain site with no Magento (built-in Frappe e-mail OTP).
2. Many F&F programs per site; one site-wide default set of rules each program inherits.
3. Every rule from the Miraaya thread is configurable (§4 traceability).
4. Trigger per program: by who the customer is, by a typed F&F code, or either.
5. Clear admin onboarding (workspace + checklist + health check) and no cashier dead-ends.
6. Fix the verified correctness bugs (§10).
7. Zero behaviour change for Miraaya after the migration patch.

**Non-goals**
- Stacking F&F with another discount (client: "discounts should not be combined"). Keep best-only.
- Stacking two F&F programs on one invoice.
- Full offline F&F pricing (caps need the server). Offline gets a clear state, not a discount (§9).
- Changing the core discount engine maths (best-discount, caps allocation) beyond keying by program.

**Anti-goals (failure even if it "works")**
- Any client name (`miraaya`), country (Iraq) or vendor (Magento) left in the F&F / OTP code paths of `pos_next` or in the generic F&F
  code (guarded by `test_no_vendor_or_country_strings`, P2 Task 9). Wallet / loyalty and customer-sync references in pos_next are
  outside F&F and tracked in §13d items 5–6.
- `pos_next` importing `posnext_promotions` or `magento_integration` (enforced by `pos_next/test_no_promotions_import.py`).
- A setting that exists in the form but is ignored by the engine (today: Group/Flag, `apply_with_ff`).
- Cart and invoice disagreeing (today the gift rule is only enforced in the cart).
- Miraaya's caps resetting mid-month because usage is re-keyed.

## 3. Constraints

- Frappe / ERPNext v15. Tabs in JS and Python. Yarn, not npm. Never `bench run-tests` (wipes data) — use `bench execute` / site test runners as the repos already do.
- `pos_next` must run without `posnext_promotions` (all F&F UI is skipped when absent — keep that).
- POS works offline; invoices sync later and are validated server-side with their own `posting_date`.
- Existing data on Miraaya: Single settings + child rows, F&F Logs, invoice item F&F fields, Messages, verified customers.

## 4. Requirement traceability (Miraaya thread 29 Oct – 15 Nov 2026)

| # | Client requirement (date) | Becomes | Miraaya value after migration |
|---|---|---|---|
| R1 | Eligible by email domain by default, no flag (29 Oct, 8 Nov) | Program `qualification = Approved Email Domain` | domain list moved as-is |
| R2 | Email must be verified (8 Nov) | Program `require_verified_email` | On |
| R3 | Customer Group / member flag not used (5, 8 Nov) | Group is a *separate* qualification method other sites may pick; flag removed | not selected |
| R4 | Existing customers auto-eligible when conditions met (8 Nov) | Eligibility computed live, never stored | — |
| R5 | Higher discount wins, never combined — coupons, automatic, already discounted (29 Oct, 5, 8 Nov) | Always on (core rule). Global `tie_breaker` | F&F wins tie |
| R6 | "Works with promo codes" (5 Nov) | Coupons compete with F&F (R5). Separate: optional F&F code trigger (§6.3) | trigger = By Customer |
| R7 | BXGY / Routine never get F&F (8, 9 Nov; bug 5 Nov "B1G1 at qty 4 switches to F&F") | Compatibility row per promotion kind (§7) | BXGY, Item Level = *Block F&F on line* |
| R8 | Free gift + F&F configurable by admin (8 Nov) | Compatibility rows Free Item / GWP / Cart Total / Brand Gift | *F&F wins, remove gift* |
| R9 | Setting global, not per promotion (9 Nov) | Global default; program / scheme override optional and empty | global only |
| R10 | Disabled → F&F stays, gift removed (9 Nov) — BRD said the opposite | Policy option per kind, both behaviours exist | *F&F wins, remove gift* |
| R11 | Gift threshold on subtotal after F&F (9 Nov) | Global `gift_threshold_basis` | After F&F |
| R12 | Default OFF (9 Nov) | New sites default = *F&F wins, remove gift* | same |
| R13 | Gift triggered by mixed F&F / non-F&F lines (open question 12 Nov, unanswered) | Global `mixed_trigger_policy` | *Drop gift if any trigger line got F&F* (today's code) |
| R14 | Customer created in POS synced to Magento; show Magento's own error (29 Oct, 5 Nov) | Stays in `magento_integration` via existing customer hooks | unchanged |
| R15 | Remove duplicate-name validation (5, 8 Nov) | Already done in pos_next | — |
| R16 | Verified customer lost F&F badge on retest (1 Nov) | Cashier sees the *reason* + inline Verify (§8); verification reset on email change is logged | — |

## 5. Approaches considered

- **A — Evolve in place (chosen).** Keep the engine; add a `Friends and Family Program` doctype; the
  existing Single becomes the global defaults; pluggable OTP; migration patch. Keeps caps / best-discount
  / audit log that took months to get right; Miraaya continues by configuration.
- B — Rebuild on ERPNext Pricing Rules / POS Coupons. Loses monthly caps, best-discount comparison and
  audit log, which would be rebuilt anyway, fighting the current engine. Rejected.
- C — Keep the Single as the program, add optional extra programs. Two code paths forever. Rejected.

## 6. Configuration model

### 6.1 Three levels, most specific wins

```
Friends and Family Settings   (existing Single → GLOBAL DEFAULTS)
  └─ Friends and Family Program  (NEW, many; any field may be "Use Global")
       └─ Promotional Scheme      (optional per-scheme compatibility override)
```

One **effective-config resolver** (single module, used by cart, invoice, report, UI and health check):
`resolve(program, scheme=None) -> EffectiveConfig` where every value carries its source
(`scheme` / `program` / `global` / `default`). The Program and Scheme forms show "Inherited from Global: X"
next to each inheritable field, so admins see the effective value, not a blank.
- Inheritable scalars: Select with an explicit literal option **`Use Global`** (never a blank meaning inherit). Checks become Select `Use Global / Yes / No`.
- Inheritable tables: explicit Check `override_global_<table>`; unticked = global rows; ticked = this program's rows, even if empty.
- Option lists (triggers, qualification methods, promotion kinds, policies, cap periods) are defined once in a `constants` module and the DocType JSON options are validated against it by a test.

### 6.2 `Friends and Family Settings` (Single — global)

Keeps its doctype name (no rename = simpler migration). After migration it holds **only** defaults:

| Section | Fields |
|---|---|
| Program selection | `program_selection` (Highest Priority / Highest Percentage) — when a customer qualifies for several programs. Decided once from eligibility (before the cart), not by pricing the cart per program: badge, cart and receipt always show the same program. |
| Discount comparison | `tie_breaker` (F&F / Other discount), `apply_on_non_pos_invoices` (Check, default off) |
| Receipt | `show_balance_on_receipt` (Check, default **off**: remaining cap balance is customer data) |
| Cap breach | `on_cap_breach_at_submit` (Allow and log / Block submit), default Allow and log |
| Promotion compatibility | `compatibility` table (§7), `gift_threshold_basis` (Before F&F / After F&F), `mixed_trigger_policy` (Drop gift if any trigger line has F&F / Evaluate on non-F&F lines only / Keep gift) |
| Defaults for new programs | `default_discount_percentage` (no 30 baked in; blank), `default_cap_period` |
| Unclassified promotions | `unclassified_promotion_policy` (default Compete) + health-check warning listing schemes the classifier cannot place |
| Health (read-only HTML) | live checklist (§11) |

Removed from the Single (moved to Program): enabled, %, dates, caps, approved domains, scope tables,
exclusion tables, `allow_free_gift_with_ff`. Removed outright: `eligibility_basis`, `eligible_customer_groups`
(hidden legacy), Customer field `custom_is_friends_and_family`.

### 6.2b Settings owned by pos_next (POS Settings, per profile)

pos_next must work without promotions, so these live in **POS Settings**; the F&F Global Settings form only
*shows* them read-only with a link: `verification_provider` (Select filled from the `pos_next_email_otp_providers`
hook), `otp_ttl_seconds`, `otp_resend_cooldown`, `otp_max_sends_per_hour`, `default_phone_country`,
`placeholder_email_domain` (replaces `@pos.miraaya`), `require_split_name`. magento_integration writes its
defaults into POS Settings (it depends on pos_next, never on promotions).

### 6.3 `Friends and Family Program` (new, normal doctype, track_changes)

| Section | Fields |
|---|---|
| Identity | `program_name` (autoname), `company` (Link, reqd; POS profiles and invoices must match it), `enabled`, `priority` (Int), `valid_from`, `valid_upto`, `description` |
| Where | `pos_profiles` table (empty = all profiles that have `allow_friends_family`), `apply_on_non_pos_invoices` (inherit) |
| **Trigger** | `trigger` (By Customer / By Code / By Customer or Code) — if a customer qualifies both ways, customer qualification counts and no code use is consumed; `codes` child table: `code` (unique site-wide, case-insensitive), `enabled`, `valid_from/upto`, `max_uses`, `max_uses_per_customer`; `code_requires_customer` (Check — code still needs a named, non-walk-in customer, for caps) |
| **Qualification** (By Customer) | `qualification` (Approved Email Domain / Customer Group / Customer List); tables: `approved_domains` (domain, enabled), `customer_groups` (incl. descendants), `customers` (Link: renames/merges follow automatically; disabled customers never qualify); `require_verified_email` (Yes/No/Use Global — only meaningful for the domain method) |
| Discount | `discount_percentage` (reqd when enabled, 0–100), `discount_scope` + `applicable_brands / item_groups / items` (moved as-is), `excluded_items / item_groups / brands` (moved as-is) |
| Caps | `max_discount_per_order`, `max_discount_per_customer_period`, `cap_period` (Month / Week / Year / Program lifetime / Use Global). **Usage is shared across all programs** per customer (decided 2026-11-16): the allowance left = this program's cap − F&F the customer got from *any* program in the period. Program id is still stored for reporting. |
| Compatibility | optional `compatibility` table override (§7), `gift_threshold_basis`, `mixed_trigger_policy` (inherit) |
| Messages | link to Messages filtered by program |

A **Preview** button on the Program (and on Customer) shows every matching program for a chosen customer, which one wins and why.
Validation: same rules as today's Settings controller (domain normalisation, dedupe, scope table required) moved here.
Two enabled programs may share a domain/group — resolved by `program_selection`.

### 6.4 Promotional Scheme override

`apply_with_ff` (hidden, forced 1) is replaced by one visible Select `ff_compatibility` using the **same policy
vocabulary as the matrix row for the scheme's kind** (the form only offers policies valid for that kind) plus
`Use F&F settings`. Scope: every line matched by any Pricing Rule of the scheme. The form shows the effective policy
and its source. Patch: existing schemes → `Use F&F settings`.

### 6.5 Other configuration surfaces

- POS Profile `allow_friends_family` stays (default stays 1 for backward compat; new profiles default 0 — builder: Property Setter on new installs only).
- `Friends and Family Message`: add `program` (Link, optional); uniqueness becomes (program, event); autoname `hash`; lookup = program message ▸ global (program blank) message. Placeholders add `{program}`, `{company}`; `{brand}` kept as alias of `{company}` of the program.

## 7. Promotion compatibility matrix

Rows (one per promotion kind). **One central classifier** `classify_promotion(rule) -> kind` (merges `classify_gift_rule` + `scheme_blocking_kind`), with a test per supported promotion type; anything it cannot place is `unclassified`, uses Global `unclassified_promotion_policy` and shows in the health check.

| Kind | How detected (existing code) | Policies available |
|---|---|---|
| Buy X Get Y | Product discount, `same_item=1` | Block F&F on line · Compete |
| Item Level (Routine) | scheme `promotion_type = Item Level Discount`, not Accumulative / coupon | Block F&F on line · Compete |
| Free Item / Gift Pool | Product, different SKU, apply on Item/Group; Gift Pool | Both apply · F&F wins, remove gift · Gift wins, cancel F&F on whole order |
| GWP | `promotion_type = GWP` | same as Free Item |
| Cart Total Gift | Product on `apply_on = Transaction` | same as Free Item |
| Brand Gift | Product on `apply_on = Brand` | same as Free Item |
| Price promotions, coupons, manual | everything else | Compete (fixed — R5) |

- "Compete" = existing best-discount (money, `tie_breaker`).
- "Gift wins, cancel F&F on whole order" = the original BRD behaviour.
- **Free goods are only ever ERPNext free-item rows from a Product Discount rule** (user decision 2026-11-17, P1 Task 6g):
  no 100% / zero-price paid lines, no exceptions; the custom GWP line-discount gift became a free-item row. pos_next refuses a
  free or zero-price row no offer backs (P2 Task 8i). GWP stays classified as Buy X Get Y for compatibility.
- **Gifts come on top, read exactly as ERPNext reads the rule** (Rulings 84/85): min qty = paid qty that qualifies, free qty =
  free-item row added (scan 4, pay 4, + gift). No split of scanned units, no extra setting. For Min/Max "Charge Paid Qty By"
  the gift item is picked by that basis among scope items. Release note: live mixed-GWP rules now give the gift on top.
- **Must be enforced identically in `apply_offers` (cart) and `apply_friends_and_family_on_invoice` (validate)** — one shared function.
- **Neutral product defaults on new sites**: BXGY / Item Level = Compete; gift kinds = Both apply; threshold = Before F&F; mixed triggers = Keep gift. Miraaya's 9 Nov answers are written **only by the migration patch** on sites that already run F&F.
- The evaluator works on a normalised promotion snapshot (kind, rule names, trigger lines, gift rows) built the same way from the cart payload and from invoice rows.

## 8. Eligibility, verification and the cashier

### 8.1 Eligibility API (posnext_promotions)

`check_friends_and_family_eligibility(customer, pos_profile, code=None)` returns
`{eligible, reason, program: {name, title, discount_percentage, trigger, ...}, candidates: [...], member: bool, verification: {required, verified, provider_configured}, message}`.
`program_for_invoice(customer, posting_date, pos_profile, code)` is the engine's single entry point.
Reasons keep today's codes plus `code_invalid`, `code_exhausted`, `code_not_needed` (customer already qualifies; shown to the cashier, code not consumed), `provider_not_configured`.
The response carries **comparable candidates** (F&F amount vs best competing discount, in money) so badge, cart, coupon dialog and receipt read one server answer.
Performance: eligibility cached per (customer, profile, date) in redis; cleared on Customer, Program and Settings save.

### 8.2 OTP provider (pos_next)

- New hook `pos_next_email_otp_providers`; each returns a provider honouring a **versioned contract**
  (`OTP_PROVIDER_API = 1`, exported by pos_next): `name, label, requires_phone, health() -> {ok, message, fix_url},
  send(ctx) -> Result, verify(ctx, otp) -> Result`; `Result = {ok, code, message, retry_after?}` with a fixed code list
  (`sent, verified, invalid_otp, expired, rate_limited, not_configured, unavailable, rejected`). The provider's own message
  reaches the cashier only for `rejected` (e.g. Magento "email already registered"); everything else uses pos_next text.
- Verification is a property of the **email address**, provider-agnostic; add `custom_email_verified_via` for audit. Program changes never invalidate it; an email change does (existing hook).
- Provider secrets stay in the provider's own app (Password fields), never in POS Settings.
- Built-in provider **Frappe Email**: random 6-digit OTP, stored **hashed** in cache with TTL, sent with
  `frappe.sendmail` (Email Template `F&F Email Verification`, translatable), compared constant-time.
- Rate limits, lock, audit comment, `_mark_verified`, field protection: kept from `email_verification.py`, provider-agnostic.
- Active provider = Global `verification_provider`; with promotions absent, a POS Settings field of the same name.
- Phone normalisation via `phonenumbers` (ships with Frappe) using `default_phone_country`; phone is only required when the provider says so (Magento uses it as lookup key; Frappe Email doesn't).
- Membership check uses a hook `pos_next_customer_benefit_providers` (`is_member`, `requires_verified_email`) instead of `frappe.get_attr("posnext_promotions…")`.

### 8.3 Moves to `magento_integration`

Magento OTP provider (endpoint paths become fields with today's `/rest/V1/miraaya/...` as default value),
`Magento Setting` reading, Magento error-substring mapping, Iraqi messages, `@pos.miraaya` default
(written into Global `placeholder_email_domain` by its install/migrate), split-name requirement
(sets `require_split_name`), its bootstrap flags. `pos_next` keeps backward-compat reading of
`miraaya_installed` for one release, then drops it. `runtime.py` monkey-patches replaced by a
`pos_next_wallet_loyalty_skip` hook (out of F&F scope but same seam — builder may defer).

### 8.4 Cashier UI (pos_next)

1. Customer badge states: `F&F <program> <pct>%` (eligible) · `F&F – verify email` (member, not verified → button opens OTP panel directly) · grey with reason (coupon won / cap reached / profile off).
2. Verify panel: "Save email & send code" in one action; dialog stays open.
3. Code trigger: the existing Coupon dialog accepts F&F codes; server says whether a code is a coupon or an F&F code. One code per cart (coupon **or** F&F code, no stacking); stored on invoice header `posnext_fnf_code`; re-checked on validate and submit; a use counts on submit (net of cancels/returns) in a usage ledger, under the same lock as caps.
4. Coupon vs customer-qualified F&F: show both savings before the cashier confirms.
5. Program name in toast, line label, totals row and receipt (`{program} discount`), plus total F&F saving; remaining balance on the receipt only when `show_balance_on_receipt`.
6. Errors visible (non-blocking "Could not check F&F — Retry") instead of `console.error`.
7. Offline banner (§9).
8. Multiple candidate programs: badge shows the chosen one; tooltip lists others (no cashier choice in v1 — builder's call to add).

## 8.5 Languages and locale (added 2026-11-16 after audit)

Today F&F supports exactly two languages, hard-coded: `Friends and Family Message` has `message_ar` / `message_en`;
`best_discount.py:353-396`, `friends_and_family_caps.py:263-285`, `api/offers.py:1035` build an English + an Arabic
string in Python (literal Arabic in code); every payload carries `message_en` + `message_ar`; the POS picks with
`locale.startsWith("ar")` (`POS/src/utils/friendsAndFamily.js:146-163`). Any other language falls back to English.

Target (standard Frappe i18n, any language):
- Engine / system messages: one English source string wrapped in `_()` with placeholders; translated server-side into the
  requesting user's language (`frappe.local.lang`, set from the POS UI language) via the app's `translations/<lang>.csv`
  (existing `ar.csv` keeps Arabic). Payloads carry a single `message`; `message_en` / `message_ar` are removed.
- Admin-authored customer texts (`Friends and Family Message`): one `message` field (default language) + child table
  `translations` (`language` Link Language, `message` Text). Lookup: row for the user's language ▸ `message`.
  Migration: `message_ar` → translation row `ar`, `message_en` → `message` (or row `en` when the default is Arabic).
- POS: `pickLocalizedMessage` / `normalizeCustomerMessage` reduce to reading `message`; no language branching.
- Numbers/currency/dates: already locale-aware helpers (`useFormatters`, `currency.js`); Arabic-Indic digit input stays
  supported (generic digit folding), not as a language rule.
- Same audit rule for any vendor app: no fixed currency (`IQD` in magento loyalty → company currency) and no fixed
  country phone formats (`+964-…` in magento customer sync → country-aware E.164, Ruling 9).
- Phase placement: engine + Message doctype + migration in **Phase 3**; POS simplification in **Phase 4**;
  magento currency/phone notes in Phase 2 Task 7 (phone) and a separate magento_integration follow-up (currency, outside F&F).

## 8.6 Currency and dates (added 2026-11-16 after audit)

- Engine money is fixed to 2 decimals: `best_discount.py:120` `MONEY_PRECISION = 2`, `friends_and_family_caps.py:117-123`
  `floor_cents`/`ceil_cents`, messages `f"{v:,.2f}"` (`friends_and_family_caps.py:241`, `best_discount.py:361`). Wrong for
  0- and 3-decimal currencies (IQD, JOD, KWD, BHD). Target: precision from the invoice currency
  (`frappe.utils.get_field_precision(meta.get_field("discount_amount"), currency=…)`, falling back to the company default
  currency), floor/ceil to that precision, and amounts in messages via `frappe.utils.fmt_money(value, currency=…)`. **Phase 1, Task 6b.**
- POS: F&F maths `round2` (`POS/src/utils/friendsAndFamily.js:118`) → site precision from `currency.js` `getPrecision()`;
  `currency.js` maps every Arabic UI to `ar-EG` and keeps a fixed symbol table (incl. a broken `SAR` entry) and a `USD`
  fallback → locale from the UI language (+ company country region when known), symbols from `Intl` only, fallback = company
  currency from bootstrap. **Phase 4.**
- Dates: "today" is `nowdate()` (site time zone — dynamic), offline invoices use their own `posting_date`, receipts use
  locale helpers — fine. Cap period becomes a setting (§6.3: Month / Week / Year / Program lifetime); Week starts on
  System Settings `first_day_of_the_week`. **Phase 3.**

## 8.7 Receipts and print formats (added 2026-11-16 after audit)

Today: POS receipt (`POS/src/utils/printInvoice.js:18,191-215`) formats every amount with `toFixed(2)` (no symbol, fixed
decimals), labels F&F lines generically and other discounts with an untranslated literal "Discount"; the Jinja print
format `POS Next Receipt` (`pos_next/pos_next/print_format/pos_next_receipt/pos_next_receipt.json`) never shows F&F
(prints "Discount (x%)"), formats money with `"%.2f"|format` + `currency_symbol`, and leaves most labels untranslated.

Target (**Phase 4**, pos_next):
- Money in both receipts via the invoice currency: Jinja `doc.get_formatted(field)` / `frappe.format_value(v, {"fieldtype": "Currency", "options": "currency"}, doc)`;
  POS via `currency.js` with the invoice currency and site precision. No `toFixed(2)` / `%.2f` for money.
- Every label translatable (`_()` in Jinja, `__()` in JS).
- F&F line label "{program} discount (x%)" from `posnext_fnf_program` + `posnext_fnf_percentage` (Phase 1 Task 6).
- "Friends & Family savings" total whenever F&F applied; remaining balance only when `show_balance_on_receipt`.
- Same labels and order in both receipts; a test renders the Jinja format for an F&F invoice and asserts program name, savings line and currency-formatted amounts (2- and 3-decimal currency).

## 8.8 Closing shift (added 2026-11-16 after audit)

- Reconciliation uses invoice `grand_total` / `net_total` / payments (`pos_next/pos_next/doctype/pos_closing_shift/pos_closing_shift.py:437-490`),
  which already include F&F — correct, provided paid invoices are never re-priced (paid-invoice freeze → Phase 1 Task 6c, widened 2026-11-17 from offline-only to every paid invoice).
- Missing: no discount visibility per shift (closing shift doc, `ShiftClosingDialog.vue`, EOD print format). Target (**Phase 4**):
  child table "Discounts by source" on POS Closing Shift (source, program, invoices, amount) built from invoice-item
  `posnext_discount_source` / `posnext_fnf_program` / discount amounts; same breakdown in the closing dialog, the
  `POS Next EOD Report` print format (currency-formatted, translatable) and the Cashier Performance report.

## 8.9 Stock, cost and margin (added 2026-11-16 after audit)

- F&F changes prices only; quantities, batches, serials, warehouses are unaffected.
- Gap: no cost awareness — F&F can sell below valuation / last purchase rate. With ERPNext *Selling Settings → Validate
  Selling Price* enabled (off on nexus.local) that surfaces only at submit (`erpnext/controllers/selling_controller.py:277`)
  as an error at payment. Target (**Phase 3**): program setting `price_floor` (None / Valuation rate / Last purchase rate)
  + optional `min_margin_percent` (both inheritable from Global); the engine caps the F&F amount per line so the net rate
  never goes below the floor; line reason `price_floor` with cashier note "F&F limited by minimum price".
- Free gifts: stock follows the invoice — Phase 1 Task 3 enforces gift removal on invoice validate (same as cart); paid
  offline invoices are never changed (Task 6c).
- Reporting (**Phase 5**): F&F Performance report gains cost and margin columns (valuation-based) per program / item group.

## 8.10 Returns and refunds (added 2026-11-16 after audit)

Refunds pay back the post-F&F price; returns never re-price F&F. Bugs: POS returns never credit F&F usage (return row
has no source; credit gated on return-row fields) and a crafted return `price_list_rate` can reset the cap → Phase 1
Task 6 (credit from the original row, cumulative + remainder, clamp, no client fallback). Rounding drift across partial
returns → same task. Return rate not locked to the original (Moving Average items, POS Invoice, unlinked rows) and a
possible over-refund with inclusive tax + header discount → Phase 2 Task 8b (pos_next core). Policies → **Phase 3**
program settings: `on_return_gift` (Ignore / Warn / Require gift back) and `release_coupon_on_full_return` (Yes/No).

## 8.11 Reports and analytics (added 2026-11-16 after audit)

- F&F Performance report (promotions): sound (submitted only, company currency, consolidated excluded, returns included).
  Gaps: POS return rows carry no F&F source so returns are invisible (Phase 1 Task 6 stamps source + amount on return rows);
  no program dimension (**Phase 3**: column + filter); no cashier column, no cost/margin, no member funnel
  (approved-domain members → verified → purchased with F&F → cap hit, from F&F Log) (**Phase 5**).
- pos_next Cashier Performance and Sales vs Shifts reports count only header `discount_amount`
  (`cashier_performance_report.py:71`, `sales_vs_shifts_report.py:17`) — line discounts (F&F, promotions, line coupons)
  are missing and the cashier discount score would penalise program-driven F&F. Target (**Phase 4**): line discounts by
  `posnext_discount_source`, F&F as its own column, excluded from the cashier discount score (manual discounts only).
- Workspace dashboard (**Phase 5**): number cards (F&F discount this period, F&F invoices, verified members, cap hits)
  and a chart (F&F vs coupon vs promotion wins), all currency/locale formatted.

## 8.12 Coupons and promo codes (added 2026-11-16 after audit)

Server is authoritative for order coupons (crafted payloads cannot stack). Bugs: scoped coupon valued on the whole cart
for F&F customers; coupon use counted + committed before validation and never released; header discount unchecked when
F&F applies nowhere; `coupon_code` kept with 0 discount; dialog validate (per line) vs calculate (per order) disagree and
omit taxes; capped F&F message shows the % → **Phase 1 Task 6d** (promotions) and **Phase 2 Task 8c** (pos_next usage).
POS: re-compare after cart/customer changes while a coupon is applied, offline "coupon unavailable" state, F&F code entry
in the same dialog with one-code-per-cart → **Phase 4** (+ server rule Phase 3).
Per line is **already the built behaviour** (P1 Task 6d, P2 Task 8j: each line gets exactly one discount, line coupons and F&F
may share a cart, cart and invoice agree). Setting (**Phase 3**, Global, inheritable): `coupon_vs_ff_granularity` = Per line
(default, as built) / Whole order (one discount type for the whole cart) — Phase 3 adds only the Whole order option. Tie-breaker and
messages follow §6.2 / §8.5; money follows §8.6.

## 9. Offline (revised 2026-11-16, user decision: setting per program)

Current behaviour (code reading): `applyOffersOffline()` (`POS/src/stores/posCart.js:1496`) has no F&F; customers picked
offline get no eligibility; stamped lines keep their stamp, caps unchecked; no cashier notice. **Bug:** on sync the
promotions validate hook re-prices F&F (it ignores `flags.pos_offline_sync`, `pos_next/api/invoices.py:1001`), so a
paid invoice's total changes after payment (F&F added or cut by the cap).

Target:
1. **Paid-invoice freeze (Phase 1, Task 6c; widened 2026-11-17 by the loyalty audit):** a *paid* invoice — `offline_id`
   set (existing field), `flags.pos_offline_sync`, or `flags.pos_payment_collected` (set by pos_next when the POS payload
   carries payments, P2 Task 8e) — is never re-priced by F&F. `flags.pos_paid_draft` (set by pos_next only when a stored
   paid draft is re-saved within the header it held, P2 Task 8m) makes promotions log, not throw, a header disagreement;
   row problems still throw online. The hook
   evaluates read-only. Offline: F&F Log rows for every disagreement (not eligible, program off, code exhausted,
   compatibility, cap exceeded, over-discount), never a throw. Online: more F&F than the uncapped entitlement → throw; cap
   breach → `on_cap_breach_at_submit`; less → log. The usage ledger counts the F&F the lines carry. Unpaid invoices are
   re-priced; after F&F, `loyalty_amount` is re-checked against `grand_total` (wallet: core track §13d item 5).
2. **Program setting `offline_mode`** (Phase 3): `Off` / `Apply up to last known balance` (default) / `Apply without cap check`
   (+ `Use Global` default in F&F Settings).
3. **POS offline pricing (Phase 4):** cache per customer (already synced: `custom_email_verified`,
   `custom_verified_email`, `email_id`; add last known cap balance from the last online eligibility call) and the active
   programs' rules (`get_eligibility_rules_payload` + %, scope, exclusions, compatibility) in IndexedDB; `applyOffersOffline`
   applies F&F per the program's `offline_mode`; banner states "F&F applied offline — re-checked on sync" or "F&F
   unavailable offline". Code-triggered F&F works offline only for codes cached with their remaining uses (Phase 3/4).

## 10. Correctness fixes (phase 1)

1. `posnext_fnf_replaced_discount` (client-writable) is restored onto lines without checks (`friends_and_family_apply.py:320-342`). Fix: the server signs the snapshot (HMAC, site secret) over item_code, qty, price_list_rate, program and an expiry; an unsigned or mismatched snapshot is discarded and the line is re-priced from its pricing rules. The builder may replace signing with full server re-pricing if that is cheap enough. A valid signature restores only when every rule in the snapshot is enabled and valid on the invoice's `posting_date` (gap audit B I2).
2. Compatibility (§7) enforced in invoice validate, not only in `apply_offers`.
3. Caps: replace the aggregate SUM (`friends_and_family_caps.py:135-172`) with an **F&F Usage Ledger** doctype
   (customer Link, program, company, invoice, amount, `base_amount` in company currency, period key from the invoice's
   `posting_date`, is_return, is_cancelled; unique per invoice line, key added by the backfill patch before it backfills):
   caps compare in company currency (gap audits A I1, B C2, C I6);
   written on submit, reversed on cancel/return, idempotent. The allowance check locks a counter row keyed
   (customer, company, period_key) with `SELECT … FOR UPDATE` on validate and submit, so concurrent invoices serialise
   (Rulings 30/32: record lock only, fail fast on lock timeout; the ledger stays as audit). Shared across programs (user decision).
   If the allowance is gone at submit: Global `on_cap_breach_at_submit` (default **Allow and log** = today's behaviour; the invoice records the cap decision it was priced with).
4. Skip `is_consolidated` invoices in validate.
5. Returns: F&F amount on a return derives from the original invoice row, not the copied source tag.
6. `_looks_like_fnf_stamp` uses the stored source / program field, never "% equals program %".
7. Invoice line snapshot: `posnext_fnf_program` and `posnext_fnf_percentage` on each F&F line (historical reproducibility).
8. Fields + message events created in `after_install` as well as `after_migrate` (today a fresh install is half-configured until `bench migrate`).

## 11. Onboarding

- Workspace **Friends & Family** (promotions): Programs, Global Settings, Messages, Log, Performance report, Customers with verified email.
- Seed **translated default messages** (en + ar) for every standard event, so a program works before anyone writes text; admins override them.
- Roles: Global Settings = System Manager; Programs, codes, messages = Sales Manager; Log / Ledger / report read = Sales + Accounts Manager.
- Frappe Onboarding module steps: 1) choose verification provider 2) create first program 3) add domain/group/list or codes 4) tick POS profiles 5) write the activation message 6) test with a customer.
- Health check panel on Global Settings and on each Program: provider configured? fields present? at least one qualification row? program in date? profiles allowed? — each with a fix link.
- Docs: rewrite `docs/friends_and_family_acceptance.md` per program model; README section; remove `run-tests` instructions.

## 12. Data and migration (Miraaya)

Patch in `posnext_promotions` (idempotent, `patches.txt` post_model_sync):
0. Dry run first: a whitelisted-free `dry_run()` run via `bench execute` prints what would be created, row counts, company mapping and collisions; the patch logs the same counts.
1. If the Single has `enabled` or any child rows → create one Program per company that has a POS Profile with `allow_friends_family` (one company = one program)
   copying %, dates, caps, scope, inclusion/exclusion and domain rows (re-parented, row names kept), `trigger = By Customer`, `qualification = Approved Email Domain`, `require_verified_email = Yes`, `priority = 0`.
2. Global compatibility table = Miraaya values (§4 R7–R13), `verification_provider = Magento` when magento_integration is installed, else Frappe Email.
3. Add `posnext_fnf_program` to Sales/POS Invoice Item and `program` to F&F Log; backfill existing F&F rows; **build the Usage Ledger from submitted invoices of the current period** so caps keep counting mid-month.
4. Messages: `program` blank (= global).
5. Hide dead Settings fields this release, delete them next release; **hide, do not delete** Customer `custom_is_friends_and_family` (private masar_miraaya / Magento sync may write it); keep a "Migrated" F&F Log row with the before/after.
6. Verified customers untouched.

## 12b. Rollout gate (no fallback code)

Decided 2026-11-16: no temporary compatibility shims. Each app ships a **version-gate patch** that runs first
(`[pre_model_sync]`, top of `patches.txt`) and aborts the migration with a clear message when a companion app
on the site lacks the matching change. Nothing else in that migration runs.

- Each app exports a contract constant `FF_CONTRACT` in its package `__init__` (today: pos_next 1, posnext_promotions **2** —
  bumped by P2 Task 8d for the magento provider `clear(ctx)` change and Ruling 92 — magento_integration 1). Gates land in P2 Task 8. The gate imports each companion package installed on the site and compares; a missing attribute = old version → `frappe.throw("Update <app> to >= <version> before migrating")`. No checks on file paths or hook names.
- posnext_promotions has an empty `[pre_model_sync]` today (`patches.txt:1-3`): the gate is its first entry; same in the other two apps.
- Gate messages name the exact apps and minimum versions; each app bumps `__version__` for this release.
- Ops note: pull all three apps, then one `bench migrate`. A gate failure stops before that app's schema sync; patches of apps earlier in install order may already have run, which is why every app carries its own gate. The builder verifies the order on a test site.

## 13. Phases (each shippable and testable alone)

| Phase | Content | Repos |
|---|---|---|
| 1 Foundation + fixes | §10, effective-config resolver, central classifier + shared evaluator, Usage Ledger, invoice line snapshot | promotions |
| 2 Unlock | versioned OTP provider contract + Frappe Email provider; remove the pos_next → promotions dynamic import (benefit-provider hook); Magento provider and Miraaya specifics moved; placeholder email / split name / phone country as settings | pos_next, magento_integration |
| 3 Programs | Program doctype (multi-company) + preview, global inheritance helper, compatibility matrix, program id everywhere (payload, lines, invoice items, log, caps, messages, report), code trigger, migration patch; audit additions §13a | promotions, pos_next (UI payload) |
| 4 Cashier | §8.4 + §9; audit additions §13b | pos_next |
| 5 Onboarding & cleanup | §11, dead fields, docs; audit additions §13c | promotions, pos_next |
| core track | pos_next changes outside F&F proper, §13d (own PRs, any time) | pos_next, magento_integration |

Acceptance per phase: existing promotions F&F test-suite stays green after each phase (re-pointed to a migrated
program); new tests: inheritance resolution, each compatibility policy in cart **and** invoice, two programs
+ selection rule, code trigger (limits), Frappe Email OTP round trip, migration patch on a copy of the Miraaya settings shape, non-POS invoices, returns, consolidated invoices, duplicate offline sync, provider failure, multi-company, unclassified promotion.

## 13a. Phase 3 additions (audits folded 2026-11-17)

Sources: loyalty audit, commission check, customers audit, gap audits A, B and C (`.superpowers/sdd/2026-11-16-ff-phase2-unlock/`).

- **Master switch (gap C I7):** Global Settings keeps `ff_enabled` (Check, default 1) after `enabled` moves to Program;
  `program_for_invoice` checks it first. `ff_disabled_on` (Datetime) is stamped on every 1 → 0. The paid-invoice freeze logs
  reason `offline_after_disable` when an offline invoice's device timestamp is later than `ff_disabled_on`.
- **`earn_loyalty_on_ff`** (Program, inheritable, default Yes) (loyalty audit): No → validate clears `loyalty_program` on
  invoices carrying F&F, and magento_integration's earn flag is not set for them.
- **`sales_commission_on_ff`** (Program, inheritable): `Normal on net` (default — commission base is the line net after
  discount, `sales_person_commission.py:262-300`, so F&F lowers commission; returns mirror the original sales person) /
  `None` (no commission on F&F lines). Consistent only because paid invoices are frozen (P1 Task 6c) (commission check).
- **`cap_scope`** (Global, inheritable): `Per company` (default; equals Phase 1 behaviour: the usage counter is keyed
  by customer + company + period, Ruling 32) / `All companies (same currency only)` (validation refuses it when the
  companies' currencies differ, because base amounts in different currencies cannot be added). The ledger already
  stores `company` and `base_amount` (P1 Task 5) (gap A, gap B I3). Document the cap basis (F&F money in company
  currency after other discounts) in the Program form help (gap A M2).
- **New POS profiles default `allow_friends_family = 0`** on new installs and new companies (Property Setter, §6.5) (gap B I3).
- **Full Sales Order (and Quotation) support (gap A C1, gap B C1):** F&F fields on Sales Order Item; the validate hook prices
  F&F there when the program allows non-invoice documents; usage is counted when the invoice made from the order is
  submitted, never on the order. Removes the P1 Task 6e server strip and the P2 Task 8f client strip.
- **F&F Log PII (gap C I4):** log the email **domain** and flags (`verified` yes/no) only; promotions declares
  `user_data_fields = [{"doctype": "Friends and Family Log", "filter_by": "customer", "redact_fields": ["details", "message"]}]`;
  a one-time patch strips addresses from existing rows. (P2 Task 8d's new verification-change path already logs domain only.)
- **Profile semantics (gap C I2):** a blank or unknown `pos_profile` on an `is_pos` invoice = not allowed unless
  `apply_on_non_pos_invoices`; program `pos_profiles` enforced against a profile the user may use. (The pos_next invoice
  check itself lands in P2 Task 8e.)
- **Redis-compiled programs (gap B I4):** compile each enabled program (scope sets, exclusions, domains) once into redis,
  cleared on Program / Settings / Item Group save.

## 13b. Phase 4 additions (audits folded 2026-11-17)

- **Payment-open re-check (gap B I1, B M4):** opening the payment dialog forces an eligibility refresh and a re-price (no
  stale "not eligible" cache); the server returns `grand_total`; when it differs from the total shown, the cashier confirms
  before paying. Covers the midnight draft/submit date flip.
- **Offline rules age and push (gap C I7, gap B M1):** cached offline rules carry `fetched_at`; F&F stops offline after
  `offline_rules_max_age_hours` (default 24). Settings or Program save publishes `ff_config_changed` to POS users; an open
  cart re-prices.
- **Realtime re-check (customers audit, gap B M1, gap C I3 POS side):** on `pos_customer_changed` the POS re-fetches the
  customer through the permission-checked `get_customers` and re-checks eligibility; stale customer cache, `lastSync` from
  the server clock (not the device), reconnect fetches the delta since `lastSync`.

## 13c. Phase 5 additions (audits folded 2026-11-17)

- **F&F Log retention (gap B M3, gap C M2):** a scheduled purge (setting `log_retention_days`, blank = keep) is the only
  delete path; it writes its own log line. No role has delete on the Log or the Usage ledger.
- **Setup checklist** (extends §11 health check): `ff_enabled`; provider healthy; no duplicate verified emails (P2 Task 8d
  report); POS Settings verification section manager-only (P2 Task 8e); Global Settings writable by System Manager only
  (gap C M1); default messages and labels translated (gap C M6).
- **Admin mark-verified / revoke with audit (customers audit):** Customer form actions for POS managers, each with an audit
  comment and F&F Log row. Not in Phase 2: the duplicate report (P2 Task 8d) is enough to ship; revoke needs a UI and roles.

## 13d. pos_next core track (outside F&F proper)

pos_next / magento_integration changes found by the F&F audits that are not F&F features. Own small PRs; none blocks a phase
unless stated.

1. **Offline posting date (gap B C2):** the offline queue sends the device's local `posting_date` / `posting_time` from the
   queue timestamp with `set_posting_time = 1`; the server clamps it to [shift opening, now]; the receipt prints the local
   date. (P1 Task 5 already keys the ledger period on `posting_date`.)
2. **Client `price_list_rate` not trusted (gap A I4) — largely done in P2 Task 8k (Ruling 88):** pos_next overwrites
   `price_list_rate` with the server list price on every POS row before promotions runs, so F&F and coupons are measured on the
   server price. Left: price-list currency conversion in `_list_prices`, and rate *increases* are unchecked.
3. **Realtime audience (gap C I3):** `pos_customer_changed` goes to a POS-profile room (or users with Customer read), not the
   site-wide room, and carries only `{name, action, modified}`.
4. **Invoice profile access (gap C I2):** in P2 Task 8e (listed here for completeness).
5. **Loyalty / wallet (loyalty audit):** loyalty → wallet conversion never redeems the points (double value); wallet reversal
   disagrees with ERPNext (program, tier, `loyalty_amount`); Desk returns do not reverse the wallet; 2-decimal rounding;
   source account = first program; `balance_iqd` key name; after F&F, wallet payment rows must not exceed `grand_total`
   (pos_next knows its wallet mode of payment; promotions cannot — split from P1 Task 6c).
6. **Magento follow-ups:**
   - loyalty audit: no return/cancel reversal of Magento points; `lru_cache` leaks across sites; IQD / base currency (§8.5);
     per-profile loyalty mode; delete the `runtime.py` monkey-patches (§8.3 `pos_next_wallet_loyalty_skip` hook);
   - customers audit, **handed to the P2 T7 implementer**: Iraqi phone import broken; verify bound to the sent email;
     provider `clear()`; email writes via `db.set_value` skip the reset (use P2 Task 8d helper); `get_customers` `IN` query;
   - gap C M9: `before_uninstall` blanks `verification_provider = magento` (P2 T7 follow-up).

## 13d-bis. Server-side discount enforcement (built in Phase 2, user 2026-11-17/18)

Not F&F features, but they change what a cashier can do, so they are recorded here.
- **Manual price edits and maximum discount (P2 Task 8k, Ruling 87):** a line discount is allowed by
  `allow_user_to_edit_item_discount`, the remaining gap to the sent rate by `allow_user_to_edit_rate`; `max_discount_allowed` caps
  the sum against the server list price. Only offers, coupons (when the invoice `coupon_code` matches) and F&F explain a discount;
  pos_next never skips a paid row (Ruling 88). Offline sync logs, never refuses; a stored paid draft is lenient only per
  (item_code, uom) at a rate no lower than held.
- **Invoice-level (header) discount cap (P2 Task 8m, Rulings 89–100):** header = coupon value, else offer value, else manual
  (needs `allow_user_to_edit_additional_discount`, capped by `max_discount_allowed` on the pre-header total). **Behaviour change:**
  a manual header discount online now needs that setting (default 0; the POS already hides the field). Promotions caps coupon
  headers on unpaid POS Sales Invoices; on paid invoices pos_next judges them too (whole-cart outer bound) and promotions values
  the coupon on its scoped lines **without F&F** (a line that got F&F gets no coupon), throwing online and logging offline
  above that (Rulings 92, 98). An order-level "Better of the two" coupon only tops a line up to the better of the two
  discounts, using the line's existing discount from its rates, never `discount_amount` (Rulings 93, 96). A stored paid draft
  is lenient (logged) only when re-saved within the header it held, by amount and share (Rulings 90, 97, 99); P2 Task 8n
  also requires the same rows at no lower rate (Ruling 100). Returns are skipped.

## 13e. Deferred minors (by owner)

Nothing is dropped; each line says where it goes or why not.

- **Phase 1:** gap A M1 scope fields from client → folded into P1 Task 6f; gap B M2 item-group cache → folded into P1
  Task 6f; gap C M11 disable blocked by blank % → folded into P1 Task 6c; gap C M13 fixture tests skip silently → folded into
  P1 Task 8 and P2 Task 9.
- **Phase 2:** gap C M6 untranslated `otp.py` "Health check failed" → folded into P2 Task 9; gap C M9 magento uninstall →
  P2 T7 follow-up; gap C M12 OTP-only kill switch (`verification_provider = "Disabled"`) → **deferred to Phase 5**: settings
  are manager-only after Task 8e and an admin can untick `enable_customer_email_verification`; the member path needs the
  explicit option, which is not needed to ship.
- **Phase 3:** gap A M2 cap-basis help (in §13a); gap A M3 `discount_account` — **not acting** (YAGNI: F&F posts as a normal
  line discount; no client asked for a separate account); gap C M3 F&F Performance report bypasses User Permissions
  (`company in get_permitted_companies()`); gap C M5 bilingual event labels → `_()`; gap C M7 OTP mail language follows
  the customer (`Customer.language`) — Phase 3 engine, Phase 4 POS; gap C M8 `str.format_map` → `re.sub` placeholder lookup.
- **Phase 4:** gap B M1 realtime refresh (in §13b); gap B M4 midnight flip (covered by §13b payment-open re-check).
- **Phase 5:** gap C M1 Sales Manager write on Global Settings; gap C M2 Log delete permission (in §13c); gap C M6
  promotions translations seed.
- **core:** gap C M4 cashier `export` on Customer and company scoping in OTP `_prepare`; gap C M9 pos_next verification
  custom fields get `module: "POS Next"`; gap C M10 `after_install` does not run `reclaim_pos_settings_doctype` (low);
  gap C M14 customer name in the `apply_offers` Error Log → drop it; full email in the `_audit` comment — **not acting**
  (it is on the same Customer record the reader can already see).

## 14. Calls I made (please check)

- Existing Single is reused as Global Settings (no rename).
- One program per invoice; selection by priority or highest % at eligibility time (not by pricing the cart per program).
- pos_next-owned settings (OTP provider, phone country, placeholder email, split name) live in POS Settings.
- One code per cart; customer qualification beats code (code not consumed).
- Cap exhausted at submit → submit proceeds, breach logged (no throw).
- Legacy Customer flag hidden, not deleted.
- Caps shared across programs (user decision).
- No compatibility shims; version-gate patches abort mismatched migrations (user decision, §12b).
- F&F codes live in the Program, entered through the existing Coupon dialog.
- Offline: a paid offline invoice is frozen; every disagreement is logged (§9).
- Stacking stays out (client rule R5).
- New sites get neutral product defaults; Miraaya values only via migration (changed after Codex review).

## 14b. Review round 2 (Codex, 2026-11-16): changed / declined

Accepted: source-traced resolver; explicit `Use Global` and table-override checks; one scheme policy field; central classifier + unclassified policy; Usage Ledger with row lock; versioned provider contract; persisted offline origin; line program snapshot; multi-company migration + dry run; contract-constant gates; seeded messages; roles; receipt balance off by default; neutral product defaults; visible `code_not_needed`; phase 1 includes the foundation.
Declined as over-building for now: per-provider / per-program verification state (verification is of the email; provider recorded for audit); provider idempotency keys (send is rate-limited, safe to retry); a metrics/alerting stack (health check + Error Log + F&F Log cover it); a retention policy beyond the existing Comment audit (no OTP or token is stored). (2026-11-17: F&F Log retention is a separate item, now Phase 5, §13c.)

## 15. Left to the builder

Exact field names/labels, Select option wording, test file layout, lock implementation details, how the
health check renders, whether `pos_next_wallet_loyalty_skip` lands in this project or later (§13d), Arabic translations beyond the Phase 2 strings (P2 Task 9 adds those; promotions strings are Phase 5).
