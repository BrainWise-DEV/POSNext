# F&F Phase 1 — Foundation + Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the F&F engine one config resolver, one promotion classifier, one compatibility evaluator shared by cart and invoice, a locked usage ledger, and fix the verified correctness bugs — with no behaviour change for an existing F&F site.

**Architecture:** All work is in `posnext_promotions` (repo `apps/posnext_promotions`, branch `feature/friends-family-fixes` from `main`). New focused modules under `posnext_promotions/promotions/` (`ff_config.py`, `ff_classifier.py`, `ff_compatibility.py`, `ff_ledger.py`, `ff_snapshot.py`, `ff_money.py`, `ff_non_invoice.py`, `ff_scope.py`); existing modules delegate to them. The Single `Friends and Family Settings` keeps its name and gains global fields; programs come in Phase 3.

**Tech Stack:** Frappe/ERPNext v15, Python 3.10, FrappeTestCase.

**Spec:** `docs/superpowers/specs/2026-11-16-friends-and-family-generic-design.md` (§6.1, §7, §10, §11 after_install, §12b contract constant). Background: `~/ff_study.md`.

## Global Constraints

- Tabs for indentation (Python and JS). Never `bench run-tests` on a dev site (it wipes data); run tests with `bench --site nexus.local execute posnext_promotions.dev_tests.run --kwargs '{"module": "<dotted.module>"}'` (Task 0).
- No new code mentions a client name (`miraaya`), country or vendor; no import of `pos_next` or `magento_integration` from promotions.
- Existing site behaviour unchanged: every pre-existing F&F test module stays green (baseline from Task 0).
- Options lists live once in `posnext_promotions/promotions/ff_constants.py`; DocType Select options must equal them (test in Task 1).
- Money via existing `best_discount.money()`; precision 2.
- Commit after every task; message style `feat(ff): …` / `fix(ff): …`, ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Dependency for UI testing:** customers become verifiable through the UI only after Phase 2 Task 4 (Frappe Email OTP) is merged on nexus.local. Phase 1's UI check (Task 8) runs after that; until then automated tests use `friends_and_family_testing.give_verified_email`.

## Review Focus

1. A line stamped F&F in an old invoice (unsigned `posnext_fnf_replaced_discount` from before this release) is re-saved → it must not crash and must not restore anything; F&F is re-decided normally. (Task 4 test `test_legacy_unsigned_snapshot_ignored`.)
2. Same invoice submitted twice through hooks (retry / double click) → usage counted once. (Task 5 `test_submit_hook_idempotent`.)
3. Return of a partially returned F&F invoice → ledger gets a negative row proportional to the returned qty, not the full line. (Task 6 `test_partial_return_usage`.)
4. A Pricing Rule the classifier cannot place (deleted rule, blank discount type) → `unclassified`, policy Compete, never crashes. (Task 2 `test_missing_rule_is_unclassified`.)
5. Cart and invoice give the same F&F lines for the same BXGY + GWP cart. (Task 3 `test_cart_invoice_parity`.)
6. A **paid** online invoice whose lines carry more F&F than the server allows → save refused, the row named; a paid invoice's totals never change silently (loyalty audit). (Task 6c `test_online_paid_over_discount_throws`.)
7. POS Sales Order with F&F lines → saved without the F&F discount, nothing counted against the cap (gap audit A C1 / B C1). (Task 6e `test_sales_order_ff_line_stripped`.)
8. Invoice in a foreign currency → ledger stores `base_amount`, caps compare in company currency (gap audit A I1). (Task 5 `test_caps_compare_in_company_currency`.)
9. First migrate on an existing site → the ledger unique key exists before the backfill; a rerun adds no rows (gap audit C I6). (Task 5 `test_backfill_patch_adds_key_first`.)

**Test hygiene (all tasks):** every test that edits `Friends and Family Settings` snapshots it in `setUp` and restores it in `tearDown` (helper `ff_settings_guard()` in `friends_and_family_testing.py`, Task 0). "Green" means: no failure that is not in the Task 0 baseline.

---

### Task 0: Dev test runner + baseline

**Files:**
- Create: `posnext_promotions/dev_tests.py`

**Interfaces:**
- Produces: `ff_settings_guard()` context manager in `posnext_promotions/promotions/friends_and_family_testing.py` (saves the Single's field values and child rows, restores them on exit).
- Produces: `run(module: str) -> dict` returning `{"tests_run": int, "failures": list[str], "errors": list[str], "was_successful": bool}` (same shape as `test_promotions.run_all`).

- [ ] **Step 1:** Create branch: `cd apps/posnext_promotions && git checkout -b feature/friends-family-fixes`.
- [ ] **Step 2:** Implement `run(module)`: `importlib.import_module(module)`, `unittest.TestLoader().loadTestsFromModule`, `TextTestRunner(verbosity=2)`; return the dict. Frappe-only callable (no `@frappe.whitelist`).
- [ ] **Step 3:** Run baseline for each existing F&F module and save the summary into the PR description:
  `for m in test_friends_and_family_settings test_friends_and_family_apply test_friends_and_family_best_discount test_friends_and_family_eligibility test_friends_and_family_gifts test_friends_and_family_scheme_rules test_friends_and_family_scheme_profile test_friends_and_family_acceptance; do bench --site nexus.local execute posnext_promotions.dev_tests.run --kwargs "{\"module\": \"posnext_promotions.posnext_promotions.doctype.friends_and_family_settings.$m\"}"; done` plus `...doctype.friends_and_family_log.test_friends_and_family_log` and `posnext_promotions.promotions.test_friends_and_family_caps` (locate with `find posnext_promotions -name 'test_friends_and_family_caps*'`).
  Output artifact: `docs/ff_phase1_baseline.md` in the promotions repo (module → run/failed/errored, failure names).
  Expected: record pass/fail counts; any pre-existing failure is listed, not fixed here.
- [ ] **Step 4:** Commit `chore(ff): dev test runner`.

### Task 1: Constants + effective-config resolver

**Files:**
- Create: `posnext_promotions/promotions/ff_constants.py`, `posnext_promotions/promotions/ff_config.py`
- Modify: `posnext_promotions/posnext_promotions/doctype/friends_and_family_settings/friends_and_family_settings.json` (new fields), `friends_and_family_settings.py` (on_update clears resolver cache)
- Test: `posnext_promotions/posnext_promotions/doctype/friends_and_family_settings/test_ff_config.py`

**Interfaces:**
- Produces (`ff_constants`): `USE_GLOBAL = "Use Global"`; `PROMOTION_KINDS = ("bxgy", "item_level", "free_item", "gwp", "cart_total_gift", "brand_gift", "price", "unclassified")`; `CAP_BREACH_POLICIES = ("Allow and log", "Block submit")`; `COMPAT_POLICIES = ("Compete", "Block F&F on line", "Both apply", "F&F wins, remove gift", "Gift wins, cancel F&F")`.
- Produces (`ff_config`): `@dataclass(frozen=True) class Value: value; source: str` (`"scheme" | "program" | "global" | "default"`); `class EffectiveConfig` with attributes `allow_free_gift_with_ff: Value`, `on_cap_breach_at_submit: Value`, `unclassified_promotion_policy: Value`; `resolve(program: str | None = None, scheme: str | None = None) -> EffectiveConfig` (final §6.1 signature now; `program` is accepted and ignored until Phase 3); `clear_cache() -> None`.
- Deferred to Phase 3 on purpose: `compatibility` table, `gift_threshold_basis`, `mixed_trigger_policy` (they belong with the matrix and Program). Phase 1 keeps today's rules (`allow_free_gift_with_ff`, BXGY / Item Level blocked) and only moves them behind the resolver and classifier.
- `unclassified_promotion_policy` options: `Compete`, `Block F&F on line` only (gift policies make no sense for an unknown rule) → own constant `UNCLASSIFIED_POLICIES`.

- [ ] **Step 1: Failing tests** in `test_ff_config.py`:
  - `test_defaults_when_unset`: blank Settings → `resolve().on_cap_breach_at_submit == Value("Allow and log", "default")`, `unclassified_promotion_policy.value == "Compete"`.
  - `test_global_value_wins_over_default`: set Settings `on_cap_breach_at_submit = "Block submit"` → `.source == "global"`.
  - `test_existing_allow_free_gift_preserved`: Settings `allow_free_gift_with_ff = 1` → `resolve().allow_free_gift_with_ff.value is True`.
  - `test_doctype_options_match_constants`: options of the two new Select fields split by `\n` equal `CAP_BREACH_POLICIES` / `UNCLASSIFIED_POLICIES`.
  - `test_cache_cleared_on_save`: resolve, change Settings, save → new value returned.
- [ ] **Step 2:** Run via `dev_tests.run` → FAIL (module missing).
- [ ] **Step 3:** Add Settings fields `on_cap_breach_at_submit` (Select, `CAP_BREACH_POLICIES`, default `Allow and log`) and `unclassified_promotion_policy` (Select, `COMPAT_POLICIES`, default `Compete`) in a new section "Global Rules". Implement resolver reading `get_settings()` (cached via `frappe.cache` key `ff:effective_config`); `FriendsandFamilySettings.on_update` (`friends_and_family_settings.py:24-30`) calls `ff_config.clear_cache()`.
- [ ] **Step 4:** Run → PASS. `bench --site nexus.local migrate` first so fields exist.
- [ ] **Step 5:** Commit `feat(ff): effective-config resolver and constants`.

### Task 2: Central promotion classifier

**Files:**
- Create: `posnext_promotions/promotions/ff_classifier.py`
- Modify: `posnext_promotions/promotions/friends_and_family_gifts.py:122-167` (`classify_gift_rule`, `scheme_blocking_kind` become thin wrappers over the classifier, same return values as today)
- Test: `.../friends_and_family_settings/test_ff_classifier.py`

**Interfaces:**
- Consumes: `ff_constants.PROMOTION_KINDS`; `friends_and_family_gifts._rule_values(rule_or_name)` (move it into the classifier module and import it back in gifts).
- Produces: `classify_promotion(rule_or_name) -> str` (one of `PROMOTION_KINDS`); `is_gift_kind(kind: str) -> bool` (free_item, gwp, cart_total_gift, brand_gift); `unclassified_rules(rule_names: list[str]) -> list[str]` (for the Phase 5 health check).

- [ ] **Step 1: Failing tests** — a table test `test_kinds` with rule dicts → kind:
  `{price_or_product_discount:"Product", same_item:1}` → `bxgy`; `{promotion_type:"GWP", price_or_product_discount:"Product", same_item:0}` → `gwp`; `{promotion_type:"Gift Pool"}` → `free_item`; `{price_or_product_discount:"Product", apply_on:"Transaction"}` → `cart_total_gift`; `{price_or_product_discount:"Product", apply_on:"Brand"}` → `brand_gift`; `{price_or_product_discount:"Product", apply_on:"Item Code", same_item:0}` → `free_item`; scheme `promotion_type:"Item Level Discount"` non-accumulative, non-coupon → `item_level`; `{price_or_product_discount:"Price", apply_on:"Item Code"}` → `price`.
  `test_missing_rule_is_unclassified`: rule name that does not exist → `unclassified`; `{}` → `unclassified`.
  `test_product_unknown_apply_on_stays_free_item`: `{price_or_product_discount:"Product", apply_on:"Unknown", same_item:0}` → `free_item` (today's behaviour of `classify_gift_rule`, `friends_and_family_gifts.py:122-147`, kept on purpose).
  `test_wrappers_frozen`: **before touching gifts.py**, run the current `classify_gift_rule` / `scheme_blocking_kind` over the fixture table and paste the literal outputs into the test as constants (including the coupon / accumulative / Price cases of `scheme_blocking_kind`, `:150-167`); the test then asserts the wrappers still return those literals.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement `classify_promotion` (order: missing/blank → unclassified, bxgy, item_level (with `scheme_blocking_kind`'s coupon/accumulative exclusions), gwp, gift pool, product-by-apply_on (Transaction → cart_total_gift, Brand → brand_gift, else free_item), Price → price); wrappers map kinds back to the frozen outputs.
- [ ] **Step 4:** Run new tests + Task 0 gifts baseline → PASS.
- [ ] **Step 5:** Commit `refactor(ff): central promotion classifier`.

### Task 3: Shared compatibility evaluator (cart **and** invoice)

**Files:**
- Create: `posnext_promotions/promotions/ff_compatibility.py`
- Modify: `posnext_promotions/api/apply_offers.py:1774,1852` (call the new functions), `posnext_promotions/promotions/friends_and_family_apply.py:1102-1182` (`apply_friends_and_family_on_invoice` calls `block_ineligible_lines` before F&F and `enforce_gift_policy` after)
- Test: `.../friends_and_family_settings/test_ff_compatibility.py`

**Interfaces:**
- Consumes: `ff_classifier.classify_promotion`, `ff_config.resolve`, existing `friends_and_family_gifts.mark_fnf_ineligible_lines`, `suppress_incompatible_gifts`, `fnf_stamped_indices`.
- Produces: `normalize(items, free_rows) -> GiftSnapshot` — one shape for cart and invoice: lines keyed by `row_key` (cart `idx` / invoice row `name` or `idx`, never list position), each with `item_code, qty, pricing_rules(list), is_free_item, fnf_stamped`; gifts as `(rule_name, item_code, qty)` with the trigger row keys. All later functions take a `GiftSnapshot`.
- Produces: `block_ineligible_lines(items, rule_map=None) -> set[int]` (lines whose rules' kind is bxgy/item_level get `fnf_blocked_by_scheme`; works when `rule_map` is None by loading rule rows); `enforce_gift_policy(items, free_rows, config=None) -> list[str]` (returns names of suppressed rules; `free_rows` = cart `free_items_map` values **or** invoice rows with `is_free_item=1`; removes suppressed invoice rows from `doc.items` via the caller).

- [ ] **Step 1: Failing tests:**
  - `test_invoice_blocks_bxgy_line`: POS Invoice dict with a line tagged by a same-item Product rule + eligible customer → after `apply_friends_and_family_on_invoice`, that line has no F&F; another line has F&F.
  - `test_invoice_removes_gift_when_not_allowed`: Settings `allow_free_gift_with_ff=0`, trigger line F&F-stamped, GWP free row → free row removed from `doc.items`.
  - `test_invoice_keeps_gift_when_allowed`: same with `allow_free_gift_with_ff=1` → free row kept.
  - `test_cart_invoice_parity`: run `apply_offers` for a BXGY + GWP cart; build the POS Invoice from its **output rows** exactly as the POS submits them (paid + free rows); run validate; compare semantic tuples `(item_code, is_free_item, qty, discount_source, round(discount_amount, 2))` as multisets — not indexes or row names.
- [ ] **Step 2:** Run → FAIL (invoice path ignores gifts today).
- [ ] **Step 3:** Implement by moving the bodies of `mark_fnf_ineligible_lines` / `suppress_incompatible_gifts` into `ff_compatibility` working on a normalised list (`dict` per line with `idx`, `pricing_rules`, `is_free_item`, `item_code`, F&F stamp), keep the old names as wrappers. In the invoice path: block before `apply_friends_and_family_to_items`; after it, `enforce_gift_policy` on the rows the cart already produced (the invoice never generates gifts — it only removes ones the policy forbids); if any gift row removed, clear GWP stamps on its trigger rows and re-run `apply_friends_and_family_to_items` (mirrors `apply_offers.py:1857-1867`). On a **paid** invoice (Task 6c `is_paid`) these corrections never mutate the doc — Task 6c decides (online → throw, offline → log).
- [ ] **Step 4:** Run new + gifts + scheme_rules + apply baselines → PASS.
- [ ] **Step 5:** Commit `fix(ff): enforce gift and BXGY rules on invoice validate`.

### Task 4: Signed replaced-discount snapshot

**Files:**
- Create: `posnext_promotions/promotions/ff_snapshot.py`
- Modify: `posnext_promotions/promotions/friends_and_family_apply.py:316-352` (`_replaced_snapshot`, `_restore_replaced_discount`, `_restored_copy` use it)
- Test: `.../friends_and_family_settings/test_ff_snapshot.py`

**Interfaces:**
- Produces: `sign(item, data: dict, program: str = "", ttl_seconds: int = 86400) -> str` (JSON `{"v":1,"exp":<epoch>,"program":…,"data":{…},"sig":"<hex>"}`; HMAC-SHA256 over `"pos-ff-snapshot-v1|" + item_code|qty|price_list_rate|program|exp|canonical(data)` (canonical = `json.dumps(sort_keys=True, separators=(",", ":"))`), key = `sha256(b"pos-ff-snapshot|" + get_encryption_key().encode())` — domain-separated); `verify(item, raw: str, program: str = "") -> dict | None` (None for unsigned, expired, tampered, other program or other item values; key errors → None + Error Log). Phase 1 passes `program=""`; Phase 3 passes the program name.
- Restore gate (gap audit B I2 — a held cart restored an expired promotion through the snapshot): the signed `data` carries `pricing_rules` (list of rule names). `_restore_replaced_discount` restores only when **every** rule in it exists, is not disabled and is valid on the invoice's `posting_date` (`frappe.get_cached_value("Pricing Rule", rule, ["disable", "valid_from", "valid_upto"])`); otherwise the snapshot is dropped and the line is re-priced from today's rules. An empty `pricing_rules` list (manual discount) passes.

- [ ] **Step 1: Failing tests:** `test_signed_snapshot_restores` (signed snapshot of a 40 % promotion → restored and competes); `test_bad_signature_ignored` (well-formed v1 snapshot, `discount_percentage: 90`, wrong `sig` → line does **not** carry 90 %); `test_tamper_each_bound_field` (item_code, qty, price_list_rate, program each → None); `test_canonical_order` (same data, different key order → same sig); `test_key_error_returns_none`; `test_tampered_qty_discards` (sign at qty 1, change line qty to 5 → `verify` None); `test_legacy_unsigned_snapshot_ignored` (old plain JSON → no crash, nothing restored); `test_expired_snapshot_ignored`; `test_snapshot_dropped_when_rule_disabled` (signed snapshot of a 40 % rule, rule then disabled → line not at 40 %, re-priced); `test_snapshot_dropped_when_rule_expired_on_posting_date` (cart held 30 Nov, rule `valid_upto` 30 Nov, invoice `posting_date` 1 Dec → not restored); `test_snapshot_kept_when_all_rules_valid` (two rules, both valid → restored).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement; `_replaced_snapshot` returns `sign(...)`; `_restore_replaced_discount` uses `verify` and returns False when None. Use `hmac.compare_digest`. The rule check runs after `verify` (a bad signature never reaches the DB lookups).
- [ ] **Step 4:** Run new + apply + best_discount baselines → PASS.
- [ ] **Step 5:** Commit `fix(ff): sign replaced-discount snapshot so clients cannot inject discounts`.

### Task 5: Usage ledger with row lock + cap-breach policy

**Files:**
- Create: DocType `Friends and Family Usage` (`posnext_promotions/posnext_promotions/doctype/friends_and_family_usage/`, not submittable, read-only to users): `customer` Link Customer (reqd, in_standard_filter), `company` Link Company (reqd; the invoice's company — gap audit A I1 / B I3), `program` Data (holds the program name; becomes a Link in Phase 3 by changing fieldtype only — same column), `invoice_doctype` Link DocType, `invoice` Dynamic Link, `invoice_item` Data, `posting_date` Date, `period_key` Data (e.g. `2026-11` for Month; computed from the invoice's **`posting_date`**, never `nowdate()` — a return uses its original invoice's `posting_date` (gap audit B C2); `cap_period` Month only in Phase 1), `currency` Link Currency (invoice currency), `amount` Currency (options `currency`; F&F in invoice currency), `base_amount` Currency (company currency: `amount × conversion_rate`, company-currency precision; **caps compare on this** — gap audit A I1), `is_return` Check, `is_cancelled` Check. Unique key: helper `ff_ledger.ensure_ledger_unique_key()` (idempotent) wrapping `frappe.db.add_unique("Friends and Family Usage", ["invoice_doctype", "invoice", "invoice_item"], constraint_name="ff_usage_line")`, called by the backfill patch **before** it backfills (gap audit C I6: `post_model_sync` patches run before `after_migrate`, so the key cannot wait for install) and by `install.after_migrate`/`after_install` (columns are varchar(140); index length fits MariaDB utf8mb4 limit of 3072 bytes). Index on (`customer`, `period_key`). Permissions: Sales Manager, Accounts Manager read; no role gets write or delete (gap audit C M2).
- Create: `posnext_promotions/promotions/ff_ledger.py`
- Modify: `posnext_promotions/promotions/friends_and_family_caps.py:135-174` (`get_monthly_usage` → ledger), `posnext_promotions/hooks.py` doc_events (on_submit / on_cancel for Sales Invoice and POS Invoice add `ff_ledger.on_submit` / `ff_ledger.on_cancel`; validate keeps F&F), `posnext_promotions/patches.txt` + new patch `patches/v3_0_0/build_ff_usage_ledger.py`
- Test: `.../friends_and_family_usage/test_ff_ledger.py`

**Interfaces:**
- Produces: `lock_customer(customer: str) -> None` (`select name from tabCustomer where name=%s for update`), taken **only in `on_submit`** (short: one indexed SUM + inserts), never in validate; validate computes the allowance without a lock (fast, may be stale — submit is the authority). On `frappe.QueryDeadlockError` retry the lock+check up to 3 times.
- `get_usage(customer, period_key, exclude_invoice=None) -> float` (sum of `base_amount` of non-cancelled rows, company currency; **shared across programs** — owner decision; summed across companies in Phase 1, which equals the Phase 3 `cap_scope` default "All companies", design §13a).
- Caps `max_discount_per_order` and `max_discount_per_customer_period` are company-currency amounts: validate and submit convert the invoice's F&F with `doc.conversion_rate` before comparing; messages show the cap in company currency (gap audit A I1).
- `ensure_ledger_unique_key() -> None` (adds `ff_usage_line` when missing; no-op otherwise).
- `on_submit(doc, method=None)`: lock → usage → if this invoice's F&F would exceed the allowance and policy is `Block submit` → `frappe.throw`; else insert rows (each insert in try/except `frappe.UniqueValidationError` / `frappe.db.is_duplicate_entry` → skip; no check-then-insert) + F&F Log cap-breach row when exceeded.
- `on_cancel(doc, method=None)`: mark rows `is_cancelled`.
- `backfill(period_key, batch_size=500, dry_run=False) -> dict` (`{"invoices": n, "rows": m}`; pages by `name`, commits per batch, idempotent via the unique key, which it ensures first).
- Consumes: `ff_config.resolve().on_cap_breach_at_submit`.

- [ ] **Step 1: Failing tests:** `test_submit_writes_rows`; `test_submit_hook_idempotent` (call `on_submit` twice → one row per line); `test_cancel_reverses` (usage back to 0); `test_shared_allowance_between_invoices` (cap 1000, invoice A uses 800 → invoice B priced with ≤ 200); `test_block_policy_throws` (Settings `Block submit`, usage forced over cap between validate and submit → `frappe.ValidationError`); `test_allow_policy_logs` (default → submit ok, an F&F Log row with cap breach); `test_return_next_month_credits_original_period` (return posted in December for a November invoice → negative row with `period_key` of November); `test_non_pos_sales_invoice_ignored` (plain Sales Invoice, `is_pos=0` → no rows); `test_backfill_current_month` (existing submitted F&F invoice → `backfill` creates its rows, rerun creates none; `dry_run=True` creates none and returns counts); `test_ledger_row_has_company_and_base_amount` (row `company == doc.company`, `base_amount == money(amount × conversion_rate)`); `test_caps_compare_in_company_currency` (company currency IQD, invoice USD with `conversion_rate` 1300, monthly cap 26000 IQD, earlier usage 13000 IQD → this invoice allowed at most 10 USD F&F); `test_period_key_from_posting_date` (invoice `posting_date` 2026-10-31 submitted with today = 2026-11-01 → `period_key == "2026-10"`); `test_backfill_patch_adds_key_first` (drop `ff_usage_line`, run `build_ff_usage_ledger.execute()` → constraint present; run again → row count unchanged).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement; `get_monthly_usage(customer, on_date, exclude)` keeps its signature and calls `get_usage` with `month_bounds(on_date)`; validate path calls `lock_customer` before computing caps (only when caps active). Patch `build_ff_usage_ledger` (post_model_sync) → `ensure_ledger_unique_key()` **then** `backfill(current period_key)`; prints the counts. Before migrating nexus.local run `bench --site nexus.local execute posnext_promotions.promotions.ff_ledger.backfill --kwargs '{"period_key": "<yyyy-mm>", "dry_run": true}'`.
- [ ] **Step 4:** Run new + caps-related baselines (`test_friends_and_family_apply`, `test_friends_and_family_log`) → PASS.
- [ ] **Step 5:** Commit `feat(ff): usage ledger with customer row lock and cap-breach policy`.

### Task 6: Line snapshot, consolidated skip, returns from original row

**Files:**
- Modify: `posnext_promotions/promotions/friends_and_family_caps.py:58-105` (`ensure_invoice_item_fields` adds `posnext_fnf_percentage` Percent and `posnext_fnf_program` Data, both read-only, no_copy 0), `friends_and_family_apply.py:397-431` (stamp writes them), `:489-503` (`_looks_like_fnf_stamp` → `cstr(item.get("posnext_discount_source")) == "friends_and_family"` or `flt(item.get("posnext_fnf_percentage")) > 0`; percentage-equality heuristic removed), `:1085-1100` (`_stamp_return_usage` — returns audit 2026-11-16: today every POS return writes 0 credit because the return row has no source, and a crafted `price_list_rate` can write unlimited negative usage. New rule: original row = `row.sales_invoice_item` for Sales Invoice, `row.pos_invoice_item` for POS Invoice; **gate on the ORIGINAL row's** `posnext_discount_source` / `posnext_fnf_discount_amount`, never on return-row fields; credit = `money(orig_amount × cumulative_returned_qty / orig_qty) − already_credited_for_that_original_row` (last return takes the remainder; cumulative credit clamped to the original amount). Link missing, original row gone or original qty 0 → **credit 0** + F&F Log warning (no fallback to client rates). Return log rows also store the original invoice's POS profile; the return row also gets `posnext_discount_source = "friends_and_family"`, `posnext_fnf_program` and `posnext_fnf_percentage` copied from the original row so reports see returns), `:1102` (return early when `cint(doc.get("is_consolidated"))`).
- Test: `.../friends_and_family_settings/test_ff_invoice_rows.py`

- [ ] **Step 1: Failing tests:** `test_stamp_records_percentage`; `test_manual_discount_equal_to_ff_pct_not_treated_as_ff` (manual 30 % line, program 30 %, customer not eligible → line keeps manual 30 %, not stripped); `test_legacy_row_without_markers_left_alone` (old saved row with a 30 % discount and no `posnext_*` markers → neither stripped nor restored); `test_consolidated_invoice_skipped` for **both** Sales Invoice and POS Invoice (`is_consolidated=1` → no item changes, no ledger rows); `test_partial_return_usage` (**submitted** original POS Invoice, line qty 4, F&F 400; return qty -1 → `posnext_fnf_discount_amount == -100` and ledger −100); `test_return_from_pos_payload_credits` (return row exactly as ReturnInvoiceDialog sends it: item_code, qty, rate, warehouse, uom, sales_invoice_item — no source/plr → still credited from the original); `test_partial_returns_sum_to_original` (capped line 10.00 over 3 units, three single returns → total credit exactly −10.00); `test_crafted_return_cannot_reset_cap` (return row with source=friends_and_family and price_list_rate 1e9 → credit equals the original-derived amount only); `test_return_without_link_credits_zero` (no sales_invoice_item → 0 credit, warning log).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run + baselines → PASS.
- [ ] **Step 5:** Commit `fix(ff): store line F&F snapshot; skip consolidated; returns from original row`.

### Task 6b: Currency-aware money in the engine

**Files:**
- Create: `posnext_promotions/promotions/ff_money.py`
- Modify: `posnext_promotions/promotions/best_discount.py:120-131,361` (`money()` and amount labels), `friends_and_family_caps.py:117-123,240-285` (`floor_cents`, `ceil_cents`, `_fmt`), `friends_and_family_apply.py` call sites of `ceil_cents` / `bd.money` that know the document currency
- Test: `.../friends_and_family_settings/test_ff_money.py`

**Interfaces:**
- Produces: `precision_for(currency: str | None = None) -> int` (from Currency doctype via `frappe.utils.get_field_precision(frappe.get_meta("Sales Invoice Item").get_field("discount_amount"), currency=currency)`; `None` → company default currency; cached per request); `money(value, currency=None) -> float`; `floor_money(value, currency=None) -> float`; `ceil_money(value, currency=None) -> float`; `fmt(value, currency=None) -> str` (`frappe.utils.fmt_money(value, currency=currency)`).
- `best_discount.money(value)` keeps its signature for existing callers and delegates to `ff_money.money(value, _current_currency())`, where the current currency is set by the invoice/cart entry points (`frappe.local` context) — no hard-coded 2.

- [ ] **Step 1: Failing tests:** `test_two_decimal_currency` (USD: `money(1.005) == 1.01`, `floor_money(1.239) == 1.23`); `test_three_decimal_currency` (KWD or JOD — create the Currency row's precision via `smallest_currency_fraction_value`/`number_format` fixture if missing: `floor_money(1.2349) == 1.234`); `test_zero_decimal_currency` (currency with `number_format` `#,###`: `money(1234.6) == 1235`); `test_messages_use_currency_format` (cap message for KWD contains `fmt_money(…, currency="KWD")`, not `.2f`); `test_existing_two_decimal_behaviour_unchanged` (run caps allocation fixture from test_friends_and_family_caps on a 2-decimal currency → same numbers as before).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement; replace every `f"{…:,.2f}"` / `:.2f` amount format in F&F messages with `ff_money.fmt`. **Step 4:** Run + caps/apply/best_discount baselines → PASS.
- [ ] **Step 5:** Commit `fix(ff): money precision and formatting follow the invoice currency`.

### Task 6c: Paid-invoice freeze — never re-price a paid invoice (offline or online)

Widened 2026-11-17 (loyalty audit; commission check; gap audit C I7 / M11). Commission is built from the client lines before save on the net-after-discount base (`sales_person_commission.py:262-300`); it stays consistent only if validate never changes the lines of a paid invoice. Loyalty and wallet redemptions are checked against the final total.

**Files:**
- Modify: `posnext_promotions/promotions/friends_and_family_apply.py:1102` (`apply_friends_and_family_on_invoice` branches on `is_paid(doc)`), `posnext_promotions/posnext_promotions/doctype/friends_and_family_settings/friends_and_family_settings.py:33-37` (return early from the percentage check when `enabled=0`, so a disable always saves — gap audit C M11)
- Test: `.../friends_and_family_settings/test_ff_offline_sync.py` (offline cases), `.../friends_and_family_settings/test_ff_paid_freeze.py` (online cases)

**Interfaces:**
- Produces: `is_paid(doc) -> bool` = `doc.get("offline_id")` or `getattr(doc.flags, "pos_offline_sync", False)` or `getattr(doc.flags, "pos_payment_collected", False)`. The last flag is set by pos_next `update_invoice` / `submit_invoice` when the POS payload's payments sum to > 0 (the cashier has taken the money) — Phase 2 Task 8e; reading `doc.flags` is not an import. Until Phase 2 merges, only the offline half is live. **Not** "any payments row > 0": Desk invoices and the acceptance tests (`test_friends_and_family_acceptance.py:173-174`) prefill payments with the pre-F&F total and rely on validate applying F&F, and ERPNext does not fill payments on validate for non-return invoices (`taxes_and_totals.py:1096-1102`).
- Paid invoice: compute the entitlement read-only with `compute_friends_and_family_discounts` twice — uncapped and capped — and never mutate items, totals or header discount. Tasks 3 and 6d invoice-side corrections are skipped on a paid invoice and reported here.
  - **Offline:** never throws (the customer has left). One F&F Log row per disagreement, type `offline_disagreement`, `details.reason` one of `not_eligible`, `program_inactive`, `compatibility`, `cap_exceeded`, `missing_fnf`, `over_discount`, `header_discount`.
  - **Online:** a line carrying more F&F than the **uncapped** entitlement (plus one smallest currency unit) → `frappe.throw` naming the row (reasons `over_discount`, `compatibility`, `header_discount`); F&F above the **capped** but within the uncapped entitlement → cap breach, handled by `on_cap_breach_at_submit` (Allow and log → log `cap_exceeded`; Block submit → Task 5 `on_submit` throws); less F&F than the entitlement → lines kept, log `paid_under_discount`.
- Unpaid invoice: today's re-pricing. After the F&F step on **any** invoice: `flt(doc.loyalty_amount) <= flt(doc.grand_total)` (ERPNext fields), else `frappe.throw(_("Loyalty redemption exceeds the total after the Friends & Family discount."))`. The wallet half of the loyalty note needs pos_next's wallet mode of payment, which promotions cannot know → design §13d item 5.
- Consumes: Task 5 ledger (`on_submit` still records the F&F carried by the lines), F&F Log helpers in `friends_and_family_log.py`.

- [ ] **Step 1: Failing tests:**
  - offline: `test_offline_invoice_without_fnf_not_repriced` (eligible customer, `offline_id` set, lines at full price → totals unchanged after validate; one log row `missing_fnf`); `test_offline_invoice_with_fnf_over_cap_kept` (F&F-stamped lines, cap already used → lines and totals unchanged; log `cap_exceeded`; ledger records the amount on submit); `test_offline_over_discount_logged_not_thrown` (lines at 40 %, program 30 % → saved unchanged, log `over_discount`).
  - online: `test_unpaid_online_invoice_still_repriced` (no flag → today's behaviour); `test_desk_invoice_with_payments_still_repriced` (payments prefilled with the pre-F&F total, no `pos_payment_collected` flag → F&F applied, as the acceptance suite expects); `test_online_paid_over_discount_throws` (`flags.pos_payment_collected`, line F&F 40 % vs program 30 % → `frappe.ValidationError` naming the row, no change saved); `test_online_paid_under_discount_kept_and_logged` (eligible, lines at full price, paid → lines unchanged, log `paid_under_discount`); `test_online_paid_cap_breach_follows_policy` (Allow and log → saved + log `cap_exceeded`; Block submit → submit raises); `test_paid_invoice_compatibility_disagreement_throws` (paid online, BXGY line carries F&F → throws, line not stripped); `test_paid_header_discount_not_rewritten` (paid online, header 500 for a coupon worth 50 → throws `header_discount`, header unchanged).
  - redemption: `test_loyalty_amount_above_total_after_ff_throws` (unpaid, `loyalty_amount` 900, F&F brings `grand_total` to 800 → ValidationError).
  - kill switch (gap audit C I7): `test_disable_during_open_cart` (cart priced with F&F, Settings `enabled=0`: unpaid → next validate strips F&F; paid online → throws `over_discount`, totals not silently changed); `test_disable_with_blank_percentage_saves` (`enabled=0`, `discount_percentage` blank → save succeeds).
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS + apply/caps/coupon-integrity baselines.
- [ ] **Step 5:** Commit `fix(ff): paid-invoice freeze — never re-price a paid invoice; redemption re-check`.

### Task 6d: Coupon vs F&F integrity (coupon audit 2026-11-16)

**Files:**
- Modify: `posnext_promotions/coupon_engine.py:474-535` (`apply_coupon_discount` honours the coupon's `apply_scope` — eligible base = only in-scope lines, same as `apply_coupon_to_items`), `posnext_promotions/api/offers.py:1124-1262` (`calculate_coupon_discount`) and `promotions/best_discount_coupon.py:119-200` (`resolve_coupon_best_discount`) → both call **one** resolver `best_discount_coupon.decide_coupon_vs_fnf(cart, coupon, customer, pos_profile) -> Decision` (same granularity rule in validate and calculate; cart payload includes `total_taxes_and_charges`), `promotions/friends_and_family_apply.py:1011-1069` (`_resolve_order_level`: when `coupon_code` is set, always cap header `discount_amount` at `_pos_coupon_value` even if F&F applied nowhere; when header discount is 0 and no line carries `posnext_coupon_code`, clear `coupon_code`), `best_discount.py:356` (capped F&F shows its money value, not the program %); header comparison base (gap audit A I3): taxes with `included_in_print_rate=1` are already inside line amounts, so the coupon/F&F header base adds only the **exclusive** tax rows (never the whole `total_taxes_and_charges`), identically in validate and calculate. On a **paid** invoice the header cap does not mutate — Task 6c decides (online → throw, offline → log).
- Test: `.../friends_and_family_settings/test_ff_coupon_integrity.py`

- [ ] **Step 1: Failing tests:** `test_scoped_coupon_values_only_scope_lines` (brand-scoped 20 % coupon, cart with in-scope 100 + out-of-scope 900, F&F customer → coupon candidate value 20, not 200); `test_validate_and_calculate_agree` (same cart → same winner from both endpoints, incl. a tax-inclusive "Grand Total" coupon near a tie); `test_header_discount_capped_without_fnf_lines` (customer eligible but all lines excluded; client sends header 500 for a coupon worth 50 → saved 50); `test_zero_discount_clears_coupon_code`; `test_capped_fnf_message_uses_amount` (message contains the capped money value, not "30%"); `test_inclusive_tax_not_double_counted` (one 10 % tax with `included_in_print_rate=1`, lines total 110.00, "Grand Total" 10 % coupon → candidate 11.00, not 12.10, in validate **and** calculate); `test_exclusive_tax_still_added` (same with an exclusive 10 % tax, lines 100.00 → candidate 11.00).
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS + best_discount / acceptance baselines.
- [ ] **Step 5:** Commit `fix(ff): coupon vs F&F — scope-aware value, one resolver, server caps header discount`.

### Task 6e: Sales Order / non-invoice guard (gap audit A C1, B C1)

A POS Sales Order carries F&F lines that no hook checks and no cap counts. Until Phase 3 adds full Sales Order support (design §13a), the server strips F&F from non-invoice documents; Phase 2 Task 8f strips it in the POS first.

**Files:**
- Create: `posnext_promotions/promotions/ff_non_invoice.py`
- Modify: `posnext_promotions/hooks.py` (doc_events `Sales Order` and `Quotation` `validate` → `ff_non_invoice.strip_ff`)
- Test: `.../friends_and_family_settings/test_ff_non_invoice.py`

**Interfaces:**
- Produces: `strip_ff(doc, method=None) -> int` (number of lines stripped). Sales Order Item / Quotation Item have no `posnext_*` columns in Phase 1, so detection reads the **in-memory** payload keys: a line is F&F when `cstr(item.get("posnext_discount_source")) == "friends_and_family"` or `flt(item.get("posnext_fnf_percentage")) > 0` or `flt(item.get("posnext_fnf_discount_amount")) > 0`. Such a line gets `discount_percentage = 0`, `discount_amount = 0`, `rate = price_list_rate`; the `posnext_*` keys are removed; header `posnext_fnf_*` keys are removed. When `n > 0`: `frappe.msgprint(_("Friends & Family discounts apply to invoices only; removed from {0} lines.").format(n))` and one F&F Log row `non_invoice_stripped` (doctype, name, n).
- Behaviour chosen: **strip + log**, not throw (pairs with the Phase 2 client strip; a Desk user is never blocked).

- [ ] **Step 1: Failing tests:** `test_sales_order_ff_line_stripped` (SO line with source F&F at 30 % → saved with `discount_percentage == 0`, `rate == price_list_rate`; one log row); `test_quotation_ff_line_stripped`; `test_manual_discount_kept` (line with a manual 30 % and no `posnext_*` keys → kept); `test_sales_order_without_ff_untouched` (no log row); `test_no_usage_rows_for_sales_order` (no `Friends and Family Usage` rows after submit); `test_hooks_declared` (`frappe.get_hooks("doc_events")` has the two validate entries).
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS + apply baseline.
- [ ] **Step 5:** Commit `fix(ff): strip F&F from Sales Orders and Quotations until they are supported`.

### Task 6f: Scope integrity + performance (gap audit A I2 / M1, B I4 / M2, C I2)

**Files:**
- Create: `posnext_promotions/promotions/ff_scope.py`
- Modify: `posnext_promotions/promotions/friends_and_family_apply.py` (scope and exclusion matching — locate with `grep -n "applicable_items\|excluded_items\|item_group\|brand" friends_and_family_apply.py`; eligibility passed in), `friends_and_family_eligibility.py` (cached check), `friends_and_family_caps.py` (`profile_allows_ff`, usage lookups), `ff_classifier.py` / `friends_and_family_gifts.py` (`_rule_values`), `friends_and_family_log.py` (bulk insert), `posnext_promotions/hooks.py` (doc_events `Item Group` `on_update` / `on_trash` → `ff_scope.clear_item_group_cache`), `posnext_promotions/api/apply_offers.py:1271-1306` (`apply_offers`), `posnext_promotions/api/friends_and_family.py:35-49` (`get_friends_and_family_program`)
- Test: `.../friends_and_family_settings/test_ff_scope_perf.py`

**Interfaces:**
- Produces (`ff_scope`): `item_scope_fields(item_codes: list[str]) -> dict[str, dict]` (one query on Item for all lines: `item_group`, `brand`, `variant_of`; request-cached); `scope_keys(item_code) -> tuple[str, ...]` (the item code and, for a variant, its `variant_of` template); `clear_item_group_cache(doc=None, method=None) -> None` (drops the descendants cache that today lives 300 s).
- Rules: a variant matches a scope or exclusion row of its template (items, and the template's group/brand when the variant's own is blank); scope fields (`item_group`, `brand`, `variant_of`) are **always overwritten from Item**, never taken from the client line (audit A M1).
- Performance (audit B I4): Pricing Rule / Promotional Scheme flags via `frappe.get_cached_value`; `frappe.utils.caching.request_cache` on the eligibility check, `profile_allows_ff` and usage lookups; `apply_friends_and_family_on_invoice` computes eligibility once and passes it into `apply_friends_and_family_to_items(..., eligibility=…)`; F&F Log rows of one validate are written with one `frappe.db.bulk_insert` (rows carry `name`, `owner`, `creation`, `modified`). Redis-compiled programs are Phase 3 (design §13a).
- Access (gap audit C I2): `apply_offers` calls `frappe.has_permission("Customer", "read", doc=customer, throw=True)` when a customer is passed (as the two sibling endpoints do); `get_friends_and_family_program` requires a selling role (`Sales User`, `Sales Manager`, `System Manager`, or a POS Profile User assignment), else `frappe.PermissionError`.

- [ ] **Step 1: Failing tests:** `test_variant_matches_template_scope` (scope items = template T; variant V with `variant_of = T` → V gets F&F); `test_variant_excluded_via_template_exclusion` (excluded_items = T → V gets none); `test_scope_fields_from_item_not_client` (client line says `item_group` "Promo", Item master says "Other", scope = "Promo" → no F&F); `test_item_group_cache_cleared_on_update` (add a child group under a scoped group, save → an item in the child gets F&F at once); `test_pricing_rule_flags_use_cached_value` (patch `frappe.get_doc`: classifying a rule by name never calls it); `test_eligibility_computed_once_per_validate` (spy on the uncached eligibility function: one call for a 10-line invoice); `test_profile_allows_ff_once_per_request`; `test_log_rows_bulk_inserted` (5 disagreement rows → one `frappe.db.bulk_insert` call, 5 rows stored); `test_apply_offers_requires_customer_read` (user without Customer read → `frappe.PermissionError`); `test_ff_program_payload_requires_selling_role` (user with no selling role → PermissionError; Sales User → payload). Tests clear `frappe.local` request caches in `setUp`.
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS + every Task 0 baseline.
- [ ] **Step 5:** Commit `fix(ff): variants follow template scope, scope from Item, fewer queries, access checks`.

### Task 6g: Free goods only as free-item rows (user decision 2026-11-17)

Product rule: a free good is always an `is_free_item` row backed by a Product Discount rule; no paid line may reach a
100 % discount or a zero rate (pos_next Task 8i refuses such rows online). Today promotions' custom Gift with Purchase
for mixed items (min/max price basis) gives the gift as a line discount on a paid row instead.

**Files:** the GWP strategy in `posnext_promotions/api/` (find the mixed-items / `gwp_paid_qty_basis` branch of
`apply_offers`): emit the gift as a free-item row (`is_free_item = 1`, rate 0, the GWP rule name in `pricing_rules`,
qty as today) instead of discounting the paid line; the paid line keeps its price. Any other promotions path that can set
a line to 100 % / rate 0 (grep `discount_percentage.*100`, `rate = 0`) does the same or is removed. F&F percentage is
validated `< 100` in Friends and Family Settings. Bump `FF_CONTRACT = 2` in `posnext_promotions/__init__.py`
(pos_next's Phase 2 gate requires it). **Tests** `test_gwp_free_row.py`: `test_mixed_gwp_gift_is_free_row`,
`test_paid_line_keeps_price`, `test_no_promotion_returns_zero_rate_paid_line` (every strategy fixture),
`test_ff_percentage_100_rejected`, `test_contract_is_2`; update existing GWP tests that expected a line discount.
Commit `fix(promotions): gifts are free-item rows, never a 100% line discount`.

### Task 7: after_install parity + contract constant + docs

**Files:**
- Modify: `posnext_promotions/hooks.py` (`after_install = "posnext_promotions.install.after_install"`), `posnext_promotions/install.py` (`after_install()` runs the three `_ensure_*` functions + `ff_ledger.ensure_ledger_unique_key()` (the same helper the Task 5 patch calls); `_backfill_coupon_promotion_conflict()` (`install.py:38`) stays migrate-only — it repairs data that cannot exist on a fresh install), `posnext_promotions/__init__.py` (`FF_CONTRACT = 1` — exported now so Phase 2's pos_next gate can check it; promotions' own gate arrives in Phase 3, the first phase where promotions needs new pos_next code), `docs/friends_and_family_acceptance.md` (replace every `run-tests` command with the `dev_tests.run` form; add a "Phase 1 changes" section: signed snapshot, usage ledger, gift rules on invoice; mark the Group/Flag and `apply_with_ff` sections "superseded — see design doc")
- Test: `.../friends_and_family_settings/test_ff_install.py`

- [ ] **Step 1: Failing tests:** `test_after_install_hook_declared` (`frappe.get_hooks("after_install", app_name="posnext_promotions")` contains the path); `test_after_install_idempotent` (call twice, no error; invoice item fields exist; event codes == `set(friends_and_family_messages.STANDARD_EVENTS)`; ledger unique key exists); `test_contract_constant` (`posnext_promotions.FF_CONTRACT == 1`).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `fix(ff): create F&F fields and events on install; export FF_CONTRACT`.

### Task 8: Full run + UI check on nexus.local

- [ ] **Step 1:** `bench --site nexus.local migrate` → no errors; ledger backfill patch logged.
- [ ] **Step 2:** Run every module from Task 0 plus all new `test_ff_*` modules → all PASS (or only the pre-existing failures recorded in Task 0).
- [ ] **Step 3: UI on nexus.local.** Verification: if Phase 2 Task 4 is merged on the bench, verify `staff@acme.example` through OTP (Mailpit); otherwise seed it: `bench --site nexus.local execute posnext_promotions.promotions.friends_and_family_testing.give_verified_email --kwargs '{"customer": "FF UI Staff", "domain": "acme.example"}'`. Enable F&F with domain `acme.example`, then check in the POS cart: (a) BXGY item gets no F&F, (b) GWP gift removed when *Allow Free Gift* off, kept when on, (c) submit; open the invoice in Desk — line shows `posnext_fnf_percentage`; `Friends and Family Usage` list has the rows; cancel → rows marked cancelled.
- [ ] **Step 4: CI (gap audit C I8 / M13).** Create `posnext_promotions/.github/workflows/ci.yml` (the repo has no workflow today): triggers push to `main` and pull requests; services MariaDB 10.6 + Redis; `bench init` (frappe `version-15`), `get-app` erpnext `version-15`, pos_next (`develop`, overridable by input `pos_next_ref`) and this checkout; fresh site; `install-app erpnext pos_next posnext_promotions`; `bench --site test_site migrate` **twice** (gate + patch idempotency); then `bench --site test_site execute posnext_promotions.dev_tests.run_ci --kwargs '{"modules": [...]}'` with every Task 0 module plus every `test_ff_*` module. Add to `dev_tests.py`: `run_ci(modules: list[str]) -> dict` — runs each with `run`, raises `AssertionError` listing the failed modules (bench exits non-zero). Tests that need a POS Profile / Company (`test_friends_and_family_acceptance.py:53-60`, `test_friends_and_family_scheme_profile.py:162-165`) create their own fixtures and **fail** instead of skipping when setup fails. Expected: the workflow passes on the PR.
- [ ] **Step 5:** Push branch, open PR to `main` with the baseline + results.
