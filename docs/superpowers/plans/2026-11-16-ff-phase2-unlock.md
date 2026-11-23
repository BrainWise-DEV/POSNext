# F&F Phase 2 — Unlock (pluggable OTP, Miraaya code out of pos_next) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Customer email OTP works on any site through a built-in Frappe Email provider; Magento/Miraaya OTP becomes a provider inside `magento_integration`; `pos_next` holds no client, country or vendor specifics; mismatched app versions stop the migration.

**Architecture:** `pos_next` defines a versioned provider contract and registry (`pos_next/integrations/otp.py`) fed by the hook `pos_next_email_otp_providers`, ships the Frappe Email provider, and keeps rate limiting / locking / audit / verified-field protection in `api/email_verification.py`. `magento_integration` registers the Magento provider and writes its defaults into POS Settings. Membership comes from a `pos_next_customer_benefit_providers` hook that `posnext_promotions` implements.

**Tech Stack:** Frappe/ERPNext v15, Python 3.10, Vue 3 + Pinia, Vitest (`yarn test:run` in `POS/`), `phonenumbers` (ships with Frappe).

**Spec:** `docs/superpowers/specs/2026-11-16-friends-and-family-generic-design.md` (§6.2b, §8.2, §8.3, §12b, anti-goals). Background: `~/ff_study.md`.

**Repos / branches:** `apps/pos_next` → `feature/friends-family-email-otp` from `develop`; `apps/magento_integration` → `feature/friends-family-magento-otp` from `main`; `apps/posnext_promotions` → `feature/friends-family-fixes` from `main` (Tasks 5 and 8d only; rebase onto Phase 1 before merge).

## Global Constraints

- Tabs; yarn (never npm); never `bench run-tests` on a dev site — use `bench --site nexus.local execute pos_next.dev_tests.run --kwargs '{"module": "<dotted.module>"}'` (Task 0) and `cd POS && yarn test:run <file>`.
- `pos_next` must not import `posnext_promotions` or `magento_integration` (existing `pos_next/test_no_promotions_import.py`); `magento_integration` may import `pos_next`.
- No compatibility shims (user decision): `miraaya_installed` is removed, not kept for a release. Mismatched versions are stopped by the gate (Task 8).
- Provider contract values are copied verbatim from the spec: `OTP_PROVIDER_API = 1`; result codes `sent, verified, invalid_otp, expired, rate_limited, not_configured, unavailable, rejected` (plus pass-through codes `disabled, busy, invalid_email, email_not_saved, phone_required, invalid_phone, otp_not_required`, and `email_in_use` from Task 8d, that pos_next itself produces).
- OTP and secrets are never logged, stored in plain text, returned, or written to Comments — including Sentry/telemetry: no `frappe.log_error` inside an `except` around a provider call (Task 8e).
- **Merge blocker:** Task 8e (gap audit C C1 — cashier can rewrite OTP limits) is done before the pos_next PR merges.
- Message contract (spec §8.2): the provider's own text reaches the cashier **only** for `rejected`; `not_configured` / `unavailable` use pos_next's generic text. Provider `health()` text is shown only to admins (POS Settings form, Phase 5 health check).
- **Deploy order** (gates in Task 8 enforce it): Phase 1 promotions merged → promotions benefit hook → magento_integration → pos_next; on a site, pull all three, then one `bench migrate`.
- Commit after every task, ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Site with no outgoing Email Account → Verify shows "Email sending is not configured" (provider health), never a traceback. (Task 3 `test_health_without_email_account`.)
2. Two quick clicks on "Send code" → one email, second gets `busy` or `rate_limited`. (Task 4 `test_double_send_single_email`.)
3. Customer changes email between send and verify → `email_not_saved` / `invalid_otp`, never verifies the new address with the old code. (Task 3 `test_code_bound_to_email`.)
4. Phone stored as `+44 20 7946 0958` on a UK site with a provider that requires phone → accepted (country from `default_phone_country`), not "invalid phone". (Task 4 `test_non_iraqi_phone_accepted`.)
5. Two POS Profiles with different providers → each profile's cashier gets its own provider and limits. (Task 2 `test_two_profiles_two_providers`.)
6. SMTP down while sending → cashier sees "Could not send the code, try again", no stale code left behind. (Task 3 `test_send_failure_cleans_up`.)
7. POS opened on a site where magento_integration is absent → customer dialog has no first/last split, no `@pos.…` placeholder logic unless configured, no Magento wording. (Task 6 vitest `generic site has no vendor text`.)
8. A POSNext Cashier raises `otp_max_sends_per_hour` through Desk or `update_pos_settings` → persisted value unchanged; a POS manager can change it. **Blocks merge.** (Task 8e `test_cashier_cannot_change_otp_limits`.)
9. Two customers verify the same address (any case) → the second gets `email_in_use`; only one is verified (customers audit, critical). (Task 8d `test_second_customer_same_email_rejected`.)
10. OTP send/verify called without `pos_profile` → `PermissionError`, never a fallback to Frappe Email (gap audit C I1). (Task 8e `test_missing_profile_rejected`.)
11. Provider raises during verify with telemetry on → nothing with the code or request body reaches Sentry (gap audit C I5). (Task 8e `test_no_otp_reaches_sentry`.)

---

### Task 0: Dev environment so OTP really works on nexus.local + test runner

**Files:**
- Create: `pos_next/dev_tests.py`: `run(module: str) -> dict` — imports the module, `unittest.TestLoader().loadTestsFromModule`, `TextTestRunner(verbosity=2)`; returns `{"tests_run", "failures", "errors", "was_successful"}`; never whitelisted; failures do not raise (the dict is the result).

- [ ] **Step 1:** Branches as listed above.
- [ ] **Step 2: Mailpit** (local SMTP catcher, web inbox): download the release binary to `~/bin/mailpit`, run `~/bin/mailpit --smtp 127.0.0.1:1025 --listen 127.0.0.1:8025` (background). Expected: `curl -s localhost:8025` returns HTML.
- [ ] **Step 3:** On nexus.local create Email Account "Dev Mailpit": email `pos-dev@nexus.local`, SMTP `127.0.0.1` port `1025`, no SSL/TLS, no auth (`use_ssl=0, use_tls=0, no_smtp_authentication=1`), `enable_outgoing=1`, `default_outgoing=1`. Send a test mail from Desk → visible in Mailpit.
- [ ] **Step 4:** OTP mail is sent with `now=True` (no queue). Still prove SMTP from the Frappe process: `bench --site nexus.local execute frappe.sendmail --kwargs '{"recipients": ["check@acme.example"], "subject": "smtp check", "message": "ok", "now": true}'` → message in Mailpit. The OTP email contains no links, so `host_name` (currently an ngrok URL in nexus.local `site_config.json`) does not matter for OTP; set it to the URL you browse with only if you test link emails.
- [ ] **Step 5:** UI access: the site answers on `http://nexus.local:8000`; add `127.0.0.1 nexus.local` to the Windows hosts file (user action) **or** alias `sites/nexus.localhost → nexus.local` (ask before doing it). The user provides a login; confirm it can open `/pos`, has a POS Profile ("Main POS Profile"), and Customer write permission (needed by `send_email_otp`).
- [ ] **Step 6:** Implement `dev_tests.run`; run baselines: `pos_next.api.test_email_verification`, `pos_next.api.test_customers`, `pos_next.test_no_promotions_import`, `pos_next.test_split_smoke`; and `cd POS && yarn test:run src/components/sale/__tests__ src/utils/__tests__`. Record counts in the PR.
- [ ] **Step 7:** Commit `chore: dev test runner`.

### Task 1: Provider contract + registry

**Files:**
- Create: `pos_next/integrations/otp.py`
- Modify: `pos_next/__init__.py` (`FF_CONTRACT = 1`)
- Test: `pos_next/integrations/test_otp_registry.py`

**Interfaces:**
- Produces:
  - `OTP_PROVIDER_API = 1`; `RESULT_CODES = frozenset({...})` (Global Constraints list).
  - `@dataclass class OtpContext: customer: str; email: str; phone: str | None; pos_profile: str | None`.
  - Provider shape (duck-typed object or module) with: `name: str`, `label: str`, `api: int`, `requires_phone: bool`, `health() -> dict` (`{"ok": bool, "message": str, "fix_url": str | None}`), `send(ctx) -> dict`, `verify(ctx, otp: str) -> dict`; results are `{"ok": bool, "code": str, "message": str, "retry_after"?: int, "expires_in"?: int, "resend_in"?: int}`.
  - `get_providers() -> dict[str, provider]` (from `frappe.get_hooks("pos_next_email_otp_providers")`; each entry is a dotted path to a zero-arg callable; drops and Error-Logs entries that raise, return something without the contract attributes, have `api != OTP_PROVIDER_API`, or duplicate a name; cached on `frappe.local` only — never module-level).
  - `get_active_provider(pos_profile: str | None) -> provider | None` (the POS Settings **row whose `pos_profile` field equals the profile** — POS Settings is a normal per-profile DocType, `pos_settings.json:84-90` — → `verification_provider`; blank → `"frappe_email"`).
  - `call_provider(fn, *args) -> dict`: wraps provider calls; exception or result missing `ok`/`code` or with a code not in `RESULT_CODES` → `{"ok": False, "code": "unavailable"}` + Error Log titled "Customer Email OTP provider" (no customer data in the log).
  - `@frappe.whitelist() get_provider_options() -> list[dict]` (`name`, `label`, `health`) for the POS Settings form.
- [ ] **Step 1: Failing tests:** `test_builtin_provider_listed` (`"frappe_email"` in `get_providers()`); `test_wrong_api_version_dropped` (fake provider `api=2` → not listed); `test_raising_factory_dropped`; `test_duplicate_name_dropped`; `test_active_provider_default` (no setting → frappe_email); `test_call_provider_bad_result` (provider returns `{"foo": 1}` → `unavailable`).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement; **create `pos_next/integrations/otp_frappe_email.py` in this task** with `get_provider()` returning a provider whose `send`/`verify` return `not_configured` (filled in Task 3), and register `pos_next_email_otp_providers = ["pos_next.integrations.otp_frappe_email.get_provider"]` in `pos_next/hooks.py`. **Step 4:** PASS.
- [ ] **Step 5:** Commit `feat(customers): versioned email OTP provider contract`.

### Task 2: POS Settings fields + bootstrap

**Files:**
- Modify: `pos_next/pos_next/doctype/pos_settings/pos_settings.json` (rewrite the existing verification section at `:569-579` — its description says verification needs Magento — into "Customer Verification" with the new fields and a vendor-neutral description), `pos_settings.js` (new `refresh`/`onload` handler: `frappe.call` `get_provider_options` → `frm.set_df_property("verification_provider", "options", …)` and an intro showing each provider's health), `pos_settings.py` (validate provider name exists; `get_pos_settings` at `:88-128` returns the new fields), `pos_next/api/constants.py:70-110` (defaults; **remove** `miraaya_installed`), **every settings field list**: `POS_SETTINGS_FIELDS` used by `pos_next/api/bootstrap.py:245-251` and `pos_next/api/pos_profile.py:77-85`, `POS/src/stores/posSettings.js:15-20,85-90,250-255,365-372` (add `requireSplitName`, `placeholderEmailDomain`; **remove** `miraayaInstalled` and update every consumer: `grep -rn "miraayaInstalled\|miraaya_installed" POS/src pos_next`)
- Test: `pos_next/pos_next/doctype/pos_settings/test_pos_settings_verification.py`, `POS/src/stores/__tests__/posSettings.verification.spec.js`

**Interfaces:**
- Produces fields: `verification_provider` (Select, options set at runtime, stored value = provider `name`, default blank = frappe_email), `otp_ttl_seconds` (Int, 900), `otp_resend_cooldown` (Int, 60), `otp_max_sends_per_hour` (Int, 5), `default_phone_country` (Link Country), `placeholder_email_domain` (Data, blank), `require_split_name` (Check, 0). All returned by `get_pos_settings` / bootstrap through `DEFAULT_POS_SETTINGS`.
- Produces store getters: `requireSplitName: computed<boolean>`, `placeholderEmailDomain: computed<string>`.
- [ ] **Step 1: Failing tests:** python `test_defaults_present` (keys and defaults in `DEFAULT_POS_SETTINGS`; `"miraaya_installed" not in`); `test_all_settings_paths_return_fields` (bootstrap `get_initial_data`, `pos_profile.get_pos_settings`, Desk `pos_settings.get_pos_settings` each return `require_split_name`, `placeholder_email_domain`, `verification_provider`); `test_two_profiles_two_providers` (profile A `frappe_email`, profile B a fake provider → `get_active_provider` differs per profile); `test_unknown_provider_rejected` (save with `verification_provider="nope"` → ValidationError). Vitest: store exposes `requireSplitName` false by default, true when settings say 1.
- [ ] **Step 2:** FAIL. **Step 3:** Implement. Redesign `pos_next/test_split_smoke.py:96-115`: instead of asserting the injected `miraaya_installed`, assert that a `pos_next_bootstrap_settings` hook can set `require_split_name` and it reaches the bootstrap payload (the generic contract). **Step 4:** PASS (+ split_smoke).
- [ ] **Step 5:** Commit `feat(pos-settings): customer verification settings; drop client-named flag`.

### Task 3: Built-in Frappe Email provider

**Files:**
- Create: `pos_next/integrations/otp_frappe_email.py`, `pos_next/templates/emails/customer_email_otp.html` (translatable; shows the 6-digit code, minutes valid, company name)
- Test: `pos_next/integrations/test_otp_frappe_email.py`

**Interfaces:**
- Consumes: Task 1 contract, Task 2 settings (`otp_ttl_seconds`).
- Produces: `get_provider()` → provider `name="frappe_email"`, `label=_("Email (Frappe)")`, `requires_phone=False`.
  - `send(ctx)`: code `f"{secrets.randbelow(10**6):06d}"`; hash `sha256(f"{customer}|{email.lower()}|{code}")` stored in `frappe.cache` (site-namespaced) key `pos_next:email_otp:code:{customer}` with TTL = profile `otp_ttl_seconds` (a new send replaces the old code); then `frappe.sendmail(recipients=[email], subject=_("Your verification code"), template="customer_email_otp", args={"code": code, "minutes": ttl // 60, "company": …}, now=True)`. If sendmail raises (`frappe.OutgoingEmailError` or any exception) → delete the key, return `unavailable` (Error Log without the code).
  - `verify(ctx, otp)`: recompute hash with ctx email; `hmac.compare_digest`; on match delete key → `verified`; key missing → `expired`; else `invalid_otp`.
  - `health()`: ok when `frappe.db.get_value("Email Account", {"default_outgoing": 1, "enable_outgoing": 1}, ["smtp_server"])` returns a non-empty server (or the site uses `mail_server` in site_config); else `{"ok": False, "message": _("Email sending is not configured"), "fix_url": "/app/email-account"}`.
  - `pos_next/api/email_verification.reset_email_verification_on_email_change` also deletes the code key, so a code never survives an email change (Task 8d moves this deletion into the provider's optional `clear()`).
- [ ] **Step 1: Failing tests:** `test_send_then_verify` (patch `frappe.sendmail`, capture args, extract code, verify → `verified`); `test_wrong_code`; `test_expired` (delete cache key → `expired`); `test_code_bound_to_email` (send for a@x, verify with ctx b@x → `invalid_otp`); `test_code_not_in_logs_or_result` (result dict, created Comments, Error Logs and the cache value contain no 6-digit code); `test_template_renders_code` (render `customer_email_otp` with args → HTML contains the code and minutes); `test_send_failure_cleans_up` (sendmail raises → `unavailable`, cache key gone); `test_resend_replaces_code` (old code → `invalid_otp`); `test_health_without_email_account`.
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS.
- [ ] **Step 5:** Commit `feat(customers): built-in Frappe Email OTP provider`.

### Task 4: Provider-agnostic `email_verification.py`

**Files:**
- Modify: `pos_next/api/email_verification.py` (remove `SEND_ENDPOINT`, `VERIFY_ENDPOINT`, `FABRICATED_EMAIL_SUFFIX`, `normalize_iraqi_phone`, `_get_magento_config`, `_post`, `_ERROR_SUBSTRINGS`, `_map_message`, `_error_from`, `_unsynced_aware`, Magento messages; keep `_Lock`, rate-limit state, `_audit`, `_mark_verified`, field protection, `reset_email_verification_on_email_change`), `pos_next/pos_next/custom/customer.json` (add `custom_email_verified_via` Data read-only, in `VERIFICATION_FIELDS`), `pos_next/api/constants.py` (`EMAIL_VERIFICATION_FIELDS` + `custom_email_verified_via`)
- Modify tests: `pos_next/api/test_email_verification.py` (Magento-specific cases move to magento_integration in Task 7; here use a fake provider via `patch("pos_next.integrations.otp.get_active_provider")`)

**Interfaces:**
- Consumes: `otp.get_active_provider`, `otp.call_provider`, `otp.OtpContext`, POS Settings `otp_ttl_seconds`, `otp_resend_cooldown`, `otp_max_sends_per_hour`, `default_phone_country`, `placeholder_email_domain` — **the constants at `email_verification.py:41-46` are replaced by these per-profile values** (`MAX_VERIFY_ATTEMPTS` stays a constant of 10 per issued code; attempts reset on every successful send).
- Produces (whitelisted, signatures unchanged): `send_email_otp(customer, email=None, pos_profile=None) -> dict`, `verify_email_otp(customer, otp, email=None, pos_profile=None) -> dict`, `get_email_verification_status(customer) -> dict` (+ `custom_email_verified_via`). New helpers: `normalize_phone(value, country: str | None) -> str | None` (E.164 via `phonenumbers`; `None` when invalid); `is_placeholder_email(email, pos_profile=None) -> bool` (domain equals `placeholder_email_domain`, blank setting → False).
- [ ] **Step 1: Failing tests:** `test_uses_active_provider`; `test_not_configured_when_no_provider` (provider `health().ok False` → `{"ok": False, "code": "not_configured"}`); `test_double_send_single_email` (two sends inside cooldown → second `rate_limited`, provider.send called once); `test_non_iraqi_phone_accepted` (`default_phone_country="United Kingdom"`, provider `requires_phone=True`, phone `+44 20 7946 0958` → ctx.phone `+442079460958`); `test_phone_not_required_for_email_provider` (no phone, frappe_email → send proceeds); `test_placeholder_email_rejected` (setting `pos.example`, email `x@pos.example` → `invalid_email`); `test_mark_verified_records_provider` (`custom_email_verified_via == "frappe_email"`); `test_rejected_passes_provider_message` (provider returns `rejected` "already registered" → same message to caller); `test_not_configured_uses_generic_text` (provider unhealthy → pos_next message "Email verification is not set up. Ask an administrator.", not the provider's text); `test_ten_wrong_attempts_rate_limited`; `test_limits_from_profile` (profile cooldown 5 s → second send after 6 s allowed).
- [ ] **Step 2:** FAIL. **Step 3:** Implement; `is_verification_allowed` uses Task 5's `registry.is_benefit_member` (until Task 5 lands, keep current `_is_ff_member` call and replace it in Task 5). **Step 4:** PASS.
- [ ] **Step 5:** Commit `refactor(customers): email OTP through providers; no vendor or country logic`.

### Task 5: Benefit-provider hook (replaces dynamic import of promotions)

**Files:**
- Modify (pos_next): `pos_next/integrations/registry.py` (add `is_benefit_member(customer, pos_profile=None) -> bool` over hook `pos_next_customer_benefit_providers`; each provider returns `{"is_member": callable}`; exceptions → False + Error Log titled "Customer benefit provider" with the provider path only, no customer data), `pos_next/api/email_verification.py` (delete `_is_ff_member`, use registry). (`requires_verified_email` from the first draft is cut — eligibility rules live in promotions; YAGNI.)
- Modify (posnext_promotions, branch `feature/friends-family-fixes`): `posnext_promotions/hooks.py` (`pos_next_customer_benefit_providers = ["posnext_promotions.promotions.friends_and_family_eligibility.benefit_provider"]`), `friends_and_family_eligibility.py` (add `benefit_provider() -> dict` wrapping `is_customer_ff_member`)
- Test: `pos_next/integrations/test_benefit_registry.py`; promotions `.../friends_and_family_settings/test_ff_benefit_provider.py`
- [ ] **Step 1: Failing tests:** pos_next `test_no_provider_false`, `test_provider_true`, `test_provider_exception_false_and_logged`, and `test_no_get_attr_of_promotions` (source of `email_verification.py` contains no `posnext_promotions`); promotions `test_benefit_provider_shape` (`set(benefit_provider()) == {"is_member"}` — Task 8d widens it to `{"is_member", "on_verification_change"}` and it returns True for a customer on an approved domain).
- Dependency: works against promotions `main`; merge after Phase 1 (rebase `feature/friends-family-fixes` onto it).
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS.
- [ ] **Step 5:** Commit in each repo `feat: customer benefit provider hook`.

### Task 6: POS customer dialog + verify panel, generic

**Files:**
- Modify: `POS/src/components/sale/CreateCustomerDialog.vue:200-215,505-545,850-910` (`FABRICATED_EMAIL_SUFFIX` (`:512-516`) → `posSettingsStore.placeholderEmailDomain`; `requiresSplitCustomerName` (`:542`) → `posSettingsStore.requireSplitName`; drop Magento wording; save-and-send: the panel gets a "Save email & send code" button that emits `save-and-send`; the dialog handles it by calling `update_customer` and, in `updateCustomerResource.onSuccess` (`:900-908`), **when the save was triggered by `save-and-send`** it does not emit/close but updates `customer.email_id` and calls the panel's exposed `send()`; normal Save keeps today's close behaviour), `POS/src/components/sale/EmailVerificationPanel.vue:30-50,140-160` (remove `FABRICATED_SUFFIX` and `magentoSynced` prop; messages come from result `message`; show provider health message when `not_configured`), `POS/src/utils/customerVerification.js` (unchanged API)
- Test: update `POS/src/components/sale/__tests__/createCustomerDialog.spec.js`, `emailVerificationPanel.spec.js`
- [ ] **Step 1: Failing tests (vitest):** `generic site has no vendor text` (mock the settings store with `requireSplitName=false`, `placeholderEmailDomain=""` and the OTP API returning `not_configured` → rendered HTML has no `Magento`, `miraaya`, `Iraq`, and shows the generic not-set-up text); `split name follows setting` (`requireSplitName` true → first/last inputs rendered); `placeholder email from setting` (`placeholderEmailDomain="pos.example"`, email `a@pos.example` → panel hidden); `save and send keeps dialog open`; `not_configured shows provider message`.
- [ ] **Step 2:** `cd POS && yarn test:run src/components/sale/__tests__` → FAIL. **Step 3:** Implement. **Step 4:** PASS (+ full `yarn test:run`).
- [ ] **Step 5:** Commit `fix(pos): customer verification UI driven by settings, no vendor text`.

### Task 7: Magento OTP provider in magento_integration

**Files (repo `apps/magento_integration`):**
- Create: `magento_integration/install.py` (new file) and `magento_integration/patches/v0_2_0/pos_settings_verification_defaults.py` (one-time patch, so an admin who later blanks a value is not overwritten: for each POS Settings row set `verification_provider="magento"`, `placeholder_email_domain="pos.miraaya"`, `require_split_name=1` **only where the field is blank**), listed in `patches.txt` `[post_model_sync]`
- Create: `magento_integration/integrations/otp_provider.py` (moved from pos_next: `_get_magento_config`, `_post`, `_ERROR_SUBSTRINGS` mapping, `_error_from`, `_unsynced_aware` + `get_customer_sync_error` use, Iraqi `normalize_phone` kept here as the Magento lookup format; endpoints `SEND_PATH` / `VERIFY_PATH` — **superseded by Task 7b**: the paths are fields of the `Magento OTP Settings` Single with today's `/rest/V1/miraaya/...` values as defaults; no `frappe.conf` keys), (defaults are written by the one-time patch above, not on every migrate)
- Modify: `magento_integration/hooks.py` (`pos_next_email_otp_providers = ["magento_integration.integrations.otp_provider.get_provider"]`), `magento_integration/integrations/bootstrap.py:4-13` (stop injecting `miraaya_installed`; it now sets nothing for verification — the patch wrote POS Settings), `magento_integration/api/pos_next_compat.py:183-213` (bootstrap / settings overrides return the new pos_next fields unchanged; remove `miraaya_installed` handling), `magento_integration/__init__.py` (`FF_CONTRACT = 1`)
- Test: `magento_integration/integrations/test_otp_provider.py` (cases moved from `pos_next/api/test_email_verification.py`: HTTP 200 + `status:false`, 401/403 → `not_configured`/`rejected` mapping, 5xx, timeout → `unavailable`, `otp_not_required`, "already registered" → `rejected` with Magento's text, unsynced customer)
**Interfaces:** provider `name="magento"`, `label="Magento"`, `api=1`, `requires_phone=True`; `health()` ok only when `Magento Setting` exists with URL + token. Provider maps Magento's "customer not found" for an unsynced customer to `rejected` with the stored registration error, or `rejected` + "Customer is saved but not synced with Magento yet. Please try again in a moment." (keeps today's `sync_pending` text).
- Regression tests through the **public APIs** (with `requests.post` mocked): `pos_next.api.email_verification.send_email_otp` with POS Settings provider `magento` → `sync_pending` text, "already registered" text, HTTP 200 `status:false` → `invalid_otp`; `pos_next.api.customers.create_customer` via the magento override still requires first/last name when `require_split_name=1`.
- [ ] **Step 1: Failing tests** (requests mocked with `unittest.mock.patch("requests.post")`), plus `test_health_without_magento_setting` (doctype absent → `ok False`).
- [ ] **Step 2:** `bench --site nexus.local execute pos_next.dev_tests.run --kwargs '{"module": "magento_integration.integrations.test_otp_provider"}'` → FAIL. **Step 3:** Implement. **Step 4:** PASS.
- [ ] **Step 5:** Commit `feat: Magento email OTP provider for POS Next`.
- **Follow-ups handed to the T7 implementer** (customers audit 2026-11-16; tracked in design §13d "Magento follow-ups"): Iraqi phone import broken in customer sync; verify bound to the email it was sent to; implement the provider `clear()` (Task 8d); email writes through `db.set_value` skip pos_next's reset hook → use the Task 8d `reset_verification` helper; `get_customers` builds an unbounded `IN` query. Plus gap audit C M9: `before_uninstall` blanks `POS Settings.verification_provider` where it equals `magento`.

### Task 7b: Fake Magento OTP for dev (built — magento_integration `68c39bf`)

Ruling 18 amended (user decision): UI testing of the Magento path on a site with no Magento. Already implemented; listed so the plan matches the code.

**Files (repo `apps/magento_integration`):**
- Created: DocType `Magento OTP Settings` (Single, System Manager): `send_path` (Data, default `/rest/V1/miraaya/email-verification/customer/otp/send`), `verify_path` (Data, default `/rest/V1/miraaya/email-verification/customer/otp/verify`); section **Developer testing** (`depends_on: eval:frappe.boot.developer_mode`): `use_fake_magento` (Check, 0), `fake_code_length` (Int, 6), `fake_base_url` (Data), `fake_scenarios` (Table `Magento OTP Fake Scenario`: `match_text` Data, `outcome` Select `Rejected` / `Unavailable` / `Expired`, `message` Small Text). The two paths replace the `frappe.conf` overrides of Task 7: **no site_config keys, no hard-coded values in code**.
- Created: `magento_integration/dev/fake_magento.py` (whitelisted fake send/verify endpoints answering Magento's response shapes; a new hashed code per send, mailed with `frappe.sendmail(..., redact_message_after_send)` so it lands in **Mailpit**; scenarios only from table rows); `magento_integration/dev/test_fake_magento.py`
- Modified: `magento_integration/integrations/otp_provider.py` (paths from the Single; when fake mode is active the real provider posts to the fake endpoints on this site), `integrations/test_otp_provider.py`

**Interfaces:**
- Fake mode = `use_fake_magento` **and** `developer_mode` (hard guard: a stale `use_fake_magento=1` is ignored when developer_mode is off; every fake endpoint throws `PermissionError`; the Single's validate refuses `use_fake_magento=1` without developer_mode).
- `bench execute` helpers: `magento_integration.dev.fake_magento.enable()` (ticks `use_fake_magento`, needs developer_mode, seeds example scenarios once) and `mark_synced(customer)` (marks the customer as synced so the provider does not answer `sync_pending`).

- [x] **Tests (in `dev/test_fake_magento.py`):** `test_refused_without_developer_mode`, `test_validate_refuses_fake_without_developer_mode`, `test_enable_refused_without_developer_mode`, `test_active_config_and_health`, `test_validate_allows_fake_in_developer_mode`, `test_send_then_verify`, `test_new_code_every_send`, `test_code_length_from_settings`, `test_wrong_token_is_401`, `test_rejected_shows_row_message`, `test_unavailable`, `test_expired_on_verify`, `test_no_builtin_markers`, `test_through_public_api`, `test_enable_seeds_examples_once`, `test_mark_synced`.
- [x] Commit `feat(dev): fake Magento OTP endpoint for UI testing` (`68c39bf`). Remaining: add `dev.test_fake_magento` to the magento CI (Task 9).

### Task 8: Version gates (no shims)

**Files:**
- Create: `pos_next/patches/v2_5_0/ff_contract_gate.py`, `magento_integration/patches/v0_2_0/ff_contract_gate.py`, shared pure helper `pos_next/integrations/contract_gate.py`
- Modify: `pos_next/patches.txt` (first line under `[pre_model_sync]`), `magento_integration/patches.txt` (same)
- Test: `pos_next/integrations/test_contract_gate.py`

**Interfaces:**
- Produces: `check(app_requirements: dict[str, int], installed_apps: list[str], importer=importlib.import_module) -> list[str]` (messages for each installed companion whose `FF_CONTRACT` attribute is missing or lower); gate patch `execute()` calls it with `{"magento_integration": 1, "posnext_promotions": 1}` (pos_next) / `{"pos_next": 1}` (magento) and `frappe.throw("\n".join(messages), title="Update required")` when non-empty.
- [ ] **Step 1: Failing tests:** `test_missing_attribute_reported` (fake module without `FF_CONTRACT`), `test_lower_version_reported`, `test_not_installed_ignored`, `test_ok_returns_empty`, `test_patch_execute_throws` (patch `frappe.get_installed_apps` + importer → `execute()` raises `frappe.ValidationError` whose message names the app and version), `test_gate_is_first_pre_model_sync` (parse `patches.txt`: first entry under `[pre_model_sync]` is the gate).
- Precondition: Phase 1 merged (it exports `posnext_promotions.FF_CONTRACT`). Do not start this task before.
- [ ] **Step 2:** FAIL. **Step 3:** Implement. Note: `posnext_promotions.FF_CONTRACT` comes from Phase 1 Task 7 — merge Phase 1 before migrating a site with this gate. **Step 4:** PASS.
- [ ] **Step 5:** Commit in each repo `chore: F&F contract gate stops mismatched migrations`.

### Task 8b: Return safety in pos_next core (returns audit 2026-11-16)

**Files:**
- Modify: `pos_next/api/invoices.py:825-898` (`validate_return_items`: for every return row require `sales_invoice_item` (Sales Invoice) / `pos_invoice_item` (POS Invoice) and reject when `abs(rate) > original rate` of the linked row; message names the row), `:2790-2817` (`prepare_return_invoice`: when the original has a header discount with inclusive tax, carry the proportional header discount onto the return so the refund equals what was paid; precision from the invoice currency, not System Settings)
- Test: `pos_next/api/test_return_safety.py`

- [ ] **Step 1: Failing tests:** `test_return_rate_above_original_rejected` (POS Invoice and Sales Invoice, incl. a Moving Average item); `test_return_row_without_link_rejected`; `test_inclusive_tax_header_discount_refund_equals_paid` (original with inclusive tax + header coupon discount; full return → refund == original paid); `test_normal_return_unchanged` (exclusive tax, no header discount).
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS + existing return tests (`grep -rln "prepare_return_invoice\|validate_return_items" pos_next --include=test_*.py`).
- [ ] **Step 5:** Commit `fix(returns): lock return rate to the original line; refund equals amount paid`.

### Task 8c: Coupon usage counted only for applied coupons (coupon audit 2026-11-16)

**Files:**
- Modify: `pos_next/api/invoices.py:1683-1690` (remove the pre-save `increment_coupon_usage`), POS Coupon usage moves to Sales/POS Invoice `on_submit` (count when the **saved** `doc.coupon_code` is set — i.e. after the F&F hook decided) and `on_cancel` (decrement); `pos_next/.../pos_coupon.py:181-187` (no `frappe.db.commit()` inside increment/decrement); `check_coupon_code` honours `maximum_use_per_customer` (same rule as promotions `coupon_engine.check_coupon_code`)
- Test: `pos_next/api/test_coupon_usage.py`

- [ ] **Step 1: Failing tests:** `test_usage_not_counted_when_fnf_wins` (coupon entered, server clears coupon_code → used unchanged); `test_usage_counted_once_on_submit`; `test_usage_released_on_cancel`; `test_failed_submit_does_not_count`; `test_max_use_per_customer_enforced`.
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS + existing coupon tests.
- [ ] **Step 5:** Commit `fix(coupons): count usage on submit of the saved coupon, release on cancel`.

### Task 8d: Verified-email uniqueness (customers audit 2026-11-16, critical)

Today one staff address can be verified on N customers → N monthly caps. Also: verification writes use `db.set_value`, which fires no doc events, so promotions never logs them; `update_customer` has no duplicate check; magento_integration keeps its own copy of the verification field list.

**Files:**
- Modify: `pos_next/api/email_verification.py` (`_mark_verified` `:507`, `send_email_otp`, `reset_email_verification_on_email_change` `:558-580`), `pos_next/pos_next/custom/customer.json` (`custom_verified_email` gets `search_index: 1` — **non-unique**: existing duplicates must not abort migrate, uniqueness is enforced in code), `pos_next/integrations/otp.py` + `otp_frappe_email.py` (optional `clear`), `pos_next/integrations/registry.py` (verification-change notice), `pos_next/api/customers.py:423` (`update_customer`), `pos_next/patches.txt` + `pos_next/patches/v2_5_0/report_duplicate_verified_emails.py` (`[post_model_sync]`)
- Modify (magento_integration): `magento_integration/integrations/customers.py:48,1181-1195` (drop the copied field list; call the pos_next helper)
- Modify (posnext_promotions): `friends_and_family_eligibility.benefit_provider()` adds `on_verification_change`
- Test: `pos_next/api/test_verified_email_unique.py`; magento `integrations/test_customers_verification_reset.py`; promotions `test_ff_benefit_provider.py` (extended)

**Interfaces:**
- `_mark_verified(customer, email, provider_name)`: under an extra `_Lock` keyed on `sha256(lower(email))`, refuses when another Customer has `LOWER(custom_verified_email) = lower(email)` → `{"ok": False, "code": "email_in_use", "message": _("This email is already verified for another customer.")}`. `send_email_otp` runs the same check before calling the provider (no mail is sent).
- Provider contract: optional `clear(ctx) -> None`, looked up with `getattr(provider, "clear", None)` — absent is fine, `OTP_PROVIDER_API` stays 1, exceptions → fixed-text Error Log, ignored. Frappe Email's `clear` deletes the code key (replaces Task 3's direct deletion).
- Public helper `pos_next.api.email_verification.reset_verification(customer: str, reason: str, pos_profile: str | None = None) -> None`: clears `EMAIL_VERIFICATION_FIELDS`, calls `clear` of the active provider for `pos_profile` (when blank — Desk save — every registered provider that has `clear`), writes the `_audit` comment, then `registry.notify_verification_change`. `reset_email_verification_on_email_change` calls it.
- `registry.notify_verification_change(customer: str, verified: bool, email_domain: str | None, via: str | None) -> None`: calls each benefit provider's optional `on_verification_change` with the same arguments; an exception in one provider is swallowed + Error Log (provider path only). Promotions' implementation writes `log_customer_eligibility_change` with the **domain and flags only** (design §13a PII).
- `update_customer(...)`: when `email_id` or `mobile_no` changes, reuse `resolve_existing_customer` (same as `create_customer:135`) excluding `name` → return `{"already_exists": True, "message", "existing_customer"}`, nothing saved.
- Patch `report_duplicate_verified_emails`: one Error Log "Duplicate verified emails" with the count and customer names grouped by lowercased email; changes nothing (admin revoke = Phase 5). `find_duplicates() -> dict[str, list[str]]` for a dry run via `bench execute`.

- [ ] **Step 1: Failing tests:** `test_second_customer_same_email_rejected` (A verified `staff@acme.example`; B verifies `Staff@Acme.example` → `email_in_use`, B not verified); `test_send_refused_when_email_verified_elsewhere` (provider.send not called); `test_same_customer_reverify_ok`; `test_email_lock_held_returns_busy`; `test_verified_email_indexed` (`SHOW INDEX FROM tabCustomer WHERE Column_name='custom_verified_email'` non-empty, `Non_unique = 1`); `test_email_change_calls_provider_clear` (fake provider with a `clear` spy); `test_provider_without_clear_ok`; `test_reset_verification_public_helper` (fields cleared, one audit comment, registry notified with `verified=False`); `test_mark_verified_notifies_benefit_providers` (`verified=True`, `email_domain="acme.example"`, `via="frappe_email"`); `test_update_customer_duplicate_email_rejected` (B → A's email → `already_exists`, B unchanged); `test_update_customer_own_email_unchanged_ok`; `test_existing_duplicates_reported` (two customers sharing a verified email → `find_duplicates()` returns them; patch writes one Error Log, data unchanged). magento `test_email_change_uses_pos_next_reset` (patched helper called once; module has no copy of the field list). promotions `test_benefit_provider_shape` (keys `{"is_member", "on_verification_change"}`), `test_verification_change_logged_domain_only` (log `details` contain `acme.example`, not `staff@`).
- [ ] **Step 2:** FAIL. **Step 3:** Implement. **Step 4:** PASS + `test_email_verification`, `test_customers`, `test_otp_frappe_email`.
- [ ] **Step 5:** Commit in each repo `fix(customers): a verified email belongs to one customer; shared reset helper`.

### Task 8e: Security hardening (gap audit C C1, I1, I2, I5) — **blocks the Phase 2 merge**

**Files:**
- Modify: `pos_next/pos_next/doctype/pos_settings/pos_settings.json` (every field of the "Customer Verification" section — `enable_customer_email_verification`, `verification_provider`, `otp_ttl_seconds`, `otp_resend_cooldown`, `otp_max_sends_per_hour`, `default_phone_country`, `placeholder_email_domain`, `require_split_name` — gets `permlevel: 1`; new DocPerm rows permlevel 1: System Manager and Nexus POS Manager read + write; POSNext Cashier read only — roles live only in DocPerm, editable via Role Permissions Manager, no role list in code), `pos_next/api/email_verification.py` or `otp.py` (`can_manage_verification() -> bool`: true when the user has write on POS Settings at permlevel 1, via `frappe.get_meta("POS Settings").get_permlevel_access("write")` containing 1), `pos_settings.py:156-185` (`update_pos_settings`), `pos_settings.js` (call `get_provider_options` only when `__onload.can_manage_verification`; others see the stored value), `pos_next/integrations/otp.py:72-73,101-111,114-116,129-130`, `pos_next/integrations/registry.py:14-15,66-67`, `pos_next/api/email_verification.py:337-342` (`send_email_otp`, `verify_email_otp`), `pos_next/api/invoices.py:973-1013` (`update_invoice`), `:1534-1600` (`submit_invoice`)
- Test: `pos_next/api/test_security_hardening.py`

**Interfaces:**
- C1: Frappe resets higher-permlevel fields the user cannot write on save (`Document.validate_higher_perm_levels`), silently — tests assert the **persisted** value, not an exception. `update_pos_settings` checks row-level `doc.has_permission("write")` and, for non-managers, that the user is a POS Profile User of that profile → else `frappe.PermissionError`. `get_provider_options` throws `frappe.PermissionError` unless `can_manage_verification()`. Cashier POS still gets every verification value through bootstrap / `get_pos_settings` (DB reads, not permlevel-filtered).
- I1: `send_email_otp` / `verify_email_otp` require `pos_profile`: blank → `frappe.throw(_("POS Profile is required."), frappe.PermissionError)`; then `validate_pos_profile_access`.
- I2 (core part, chosen now rather than Phase 3): `update_invoice` and `submit_invoice` call `pos_next.utils.validate_pos_profile_access(pos_profile, frappe.PermissionError)` (`utils.py:91`); a blank `pos_profile` is rejected. Checked: both payload builders set it (`POS/src/composables/useInvoice.js:984` `saveDraft`, `:1047` submit — Sales Order uses the same builders), and the offline queue stores that same payload, so invoices queued before the deploy carry it too; a blank one fails sync with the PermissionError and stays in the offline queue as failed (visible to the cashier), never dropped. Both endpoints also set `invoice_doc.flags.pos_payment_collected = True` when the payload's payments sum to > 0 — the Phase 1 Task 6c freeze trigger. Promotions' blank-profile semantics stay Phase 3 (design §13a).
- I5: in `otp.call_provider`, the other `otp.py` handlers and `registry.py`, the `except` only captures `type(e).__name__`; `frappe.log_error(title=…, message=f"Provider call failed: {cls}")` runs **after** the block (no live `exc_info`, so Sentry gets no request body or frame locals) — the Task 3 pattern.

- [ ] **Step 1: Failing tests:** `test_cashier_cannot_change_otp_limits` (as POSNext Cashier: Desk-style `doc.save()` and `update_pos_settings` with `otp_max_sends_per_hour=100000` → persisted value still 5); `test_manager_can_change_otp_limits`; `test_cashier_cannot_list_provider_health` (`get_provider_options` → PermissionError); `test_update_pos_settings_other_profile_rejected` (cashier of A updates B → PermissionError); `test_cashier_bootstrap_still_gets_verification_fields` (bootstrap returns `require_split_name`, `placeholder_email_domain`, `default_phone_country`); `test_missing_profile_rejected` (send **and** verify); `test_update_invoice_foreign_profile_rejected`; `test_submit_invoice_foreign_profile_rejected`; `test_update_invoice_blank_profile_rejected`; `test_own_profile_invoice_ok`; `test_payment_collected_flag_set` (payload payments 100 → flag True; payments 0 → flag False); `test_no_otp_reaches_sentry` (patch `frappe.utils.sentry.capture_exception` with a spy recording `sys.exc_info()`; provider `verify` raises → never called with live exc_info); `test_error_log_has_class_name_only` (Error Log message `Provider call failed: RuntimeError`, no code, no email).
- [ ] **Step 2:** FAIL. **Step 3:** Implement; `bench --site nexus.local migrate` for the permlevel change. **Step 4:** PASS + `test_pos_settings_verification`, `test_email_verification`, `test_otp_registry`, existing invoice tests.
- [ ] **Step 5:** Commit `fix(security): OTP settings manager-only, profile required for OTP and invoices, no OTP in telemetry`.

### Task 8f: POS Sales Order F&F strip (client) (gap audit A C1, B C1)

Pairs with Phase 1 Task 6e (server strip). Full Sales Order support is Phase 3.

**Files:**
- Modify: `POS/src/utils/friendsAndFamily.js` (new `stripFriendsAndFamilyForOrder(items) -> { items, stripped: number }`), `POS/src/composables/useInvoice.js:972-1000` (`saveDraft`) and `:1006-1070` (submit path) — when `targetDoctype === "Sales Order"` the payload goes through the strip, `POS/src/stores/posCart.js:362-374` (switching `targetDoctype` to Sales Order recomputes totals without F&F and shows the toast)
- Test: `POS/src/utils/__tests__/friendsAndFamily.salesOrder.spec.js`, `POS/src/stores/__tests__/posCart.salesOrder.spec.js`

**Interfaces:** a line is F&F when `posnext_discount_source === "friends_and_family"`; it gets `discount_percentage = 0`, `discount_amount = 0`, `rate = price_list_rate`, and loses every `posnext_fnf_*` key; header `posnext_fnf_*` keys removed. Toast: `__("Friends & Family discounts apply to invoices only")`. Switching back to Sales Invoice re-runs offers (F&F returns).

- [ ] **Step 1: Failing tests (vitest):** `strips ff lines for sales order` (30 % F&F line → discount 0, rate = price_list_rate, no `posnext_fnf_*` keys, `stripped === 1`); `keeps non-ff discounts` (manual 10 % kept); `invoice payload untouched` (Sales Invoice → identical payload); `switching to sales order shows notice` (store with an F&F line → totals without F&F, toast text); `switching back reapplies offers`.
- [ ] **Step 2:** `cd POS && yarn test:run src/utils/__tests__ src/stores/__tests__` → FAIL. **Step 3:** Implement. **Step 4:** PASS.
- [ ] **Step 5:** Commit `fix(pos): Sales Orders carry no F&F discount`.

### Task 8g: Same customer name allowed without a warning (client requirement 2026-11-17, item 4)

Duplicate display names are already allowed (magento `reject_duplicate_customer_name` is a no-op), but ERPNext's
`Customer.get_customer_name` renames the ID to `"<name> - N"` and adds a msgprint note "Changed customer name to … as … already
exists." that the POS shows as a popup, which cashiers read as an error. Reproduced on nexus.local.

**Files:** `pos_next/api/customers.py` (`create_customer`): after `customer.insert()`, drop only that ERPNext note from
`frappe.local.message_log` (match on the translated prefix, not on position); the record keeps ERPNext's unique ID.
`POS/src/components/sale/CreateCustomerDialog.vue`: confirm no error path fires on a successful create with messages.
Test: `pos_next/api/test_customers.py` `test_duplicate_display_name_created_without_message` (two creates with the same
name → both succeed, second ID ends with " - 1", `customer_name` identical, no message about the rename in message_log).
Commit `fix(customers): same display name allowed without a rename warning`.

### Task 8h: POS sends F&F markers and keeps gift rule names (Rulings 42, 45; gift audit 2026-11-17)

The server's F&F audit, ledger, kill switch (gap audit C I7), paid-invoice freeze (P1 6c) and gift policy (P1 Task 3)
read row markers the POS never sends: `formatItemsForSubmission` drops `discount_source`, and `update_invoice` blanks
`pricing_rules` on every row, free gift rows included, so `enforce_gift_policy` cannot recognise a gift.

**Files:** the submission formatter in `POS/src/` (find `formatItemsForSubmission`): a line with
`discount_source === "friends_and_family"` sends `posnext_discount_source: "friends_and_family"` plus the
`posnext_fnf_program` / `posnext_fnf_percentage` the cart already holds (no new client fields; omit what the cart lacks —
the server derives amounts). Other lines send none of these keys. `pos_next/api/invoices.py` `update_invoice` (the
`pricing_rules` blanking): keep `pricing_rules` on free rows (`is_free_item`) only when every name is an existing
Pricing Rule with a free-item / product-discount price_or_product_discount; drop forged or unknown names. Find and keep
the original reason for the blanking (non-free rows unchanged). Delete the dead copies `apply_offers` and
`_evaluate_transaction_offers` in `invoices.py` if nothing references them (grep incl. hooks and POS/src).
**Tests:** vitest `formats F&F markers only on F&F lines`; Python (`pos_next/api/test_ff_markers.py`, skip if
posnext_promotions is not installed): `test_free_row_keeps_gift_rule_name`, `test_forged_rule_name_dropped`,
`test_non_free_row_rules_still_blanked`, and a pipeline test `test_cart_to_submit_gift_policy` (F&F-eligible customer,
gift rule, `allow_free_gift_with_ff` off: draft via `update_invoice` → gift removed; paid via `submit_invoice` → prices
kept and a Paid Disagreement `gift_with_fnf` logged — skip that half if P1 6d has not landed on the bench).
Commit `fix(pos): send F&F markers and keep gift rule names on invoice rows`.

### Task 8i: Free rows must be backed by an offer (Task 8h review, user 2026-11-17)

Today the server trusts every free (rate 0 / `is_free_item`) row the POS sends. A modified client can add free rows, or
send a real gift with a blank rule name so `enforce_gift_policy` never sees it.

**Rule:** before save, the server recomputes the offers for the invoice's paid rows with the same evaluator the cart uses
(resolve `pos_next.api.invoices.apply_offers` through Frappe's `override_whitelisted_methods`, so promotions' evaluator
runs when installed and pos_next's fallback otherwise; never import promotions). Every free row must match an expected
free row by `item_code` and gift rule name, with `qty` ≤ the expected qty; the row's `pricing_rules` is set to the
expected rule names (so a blanked name is restored and the gift policy sees it). A selectable gift (Gift Pool / customer
choice) matches if its item is one of the rule's allowed items.
- **Online** (`update_invoice`, `submit_invoice`): an unbacked or excess free row throws a `frappe.ValidationError`
  naming the row, item and qty (expected → sent).
- **Offline sync** and **paid** invoices: never throw; keep the row and log with `log_error_without_telemetry`
  (title "Unbacked free item", invoice, row, item, qty).
- Returns (`is_return`) are skipped. Free rows on Sales Orders follow the same rule.

**Files:** `pos_next/api/invoices.py` (one helper next to `_reset_row_pricing_rules`, called from both save paths).
**Tests** `pos_next/api/test_free_rows.py`: `test_forged_free_row_refused_online`, `test_excess_free_qty_refused`,
`test_blank_rule_name_restored` (real gift, blank name → name restored, then gift policy removes it for an F&F customer
with `allow_free_gift_with_ff` off), `test_gift_pool_choice_accepted`, `test_offline_unbacked_logged_not_thrown`,
`test_valid_gift_saved_unchanged`, `test_return_skipped`. Each fails before the fix.
Commit `fix(pos): free items on an invoice must come from an offer`.

### Task 8j: POS applies coupon vs F&F per line (P1 Ruling 54, spec §8.12)

`calculate_coupon_discount` (promotions, after P1 6d) decides per line: each line gets exactly one discount, coupon or
F&F, and both may share a cart. The POS today turns any coupon win into a header discount and strips F&F from every
line, so a customer can get less than either alone (line A no-F&F 100 + line B 30 % F&F 100, 20 % coupon → POS gives
20; correct is 20 on A + 30 on B = 50).

**Files:** the coupon apply path in `POS/src/` (find the handler of `calculate_coupon_discount` /
`suppress_friends_and_family`, and `posCart.js` F&F suppression): when the response carries `line_updates`, apply
them per line (coupon lines get the coupon discount and `posnext_coupon_code`; other lines keep their F&F); header
discount only for an order-level coupon. Removing the coupon restores F&F. Keep the 8f Sales Order strip working.
**Tests** (vitest): `per_line_coupon_keeps_fnf_on_other_lines` (the 50 example), `order_level_coupon_uses_header`,
`removing_coupon_restores_fnf`; Python pipeline test in `pos_next/api/test_ff_markers.py`
`test_per_line_coupon_invoice_matches_cart` (skip without promotions): the saved invoice equals the cart's lines and total.
Commit `fix(pos): coupon and F&F apply per line as the server decides`.

### Task 8k: Server enforces manual price edits and the maximum discount (Task 8i re-review, user 2026-11-17)

Today the POS Settings rules `allow_user_to_edit_rate` and `max_discount_allowed` run on the server only when the client
sets `is_rate_manually_edited`. A modified client omits the flag and sells at 0.01.

**Rule:** for every paid row (not a return, not a free row — Task 8i owns those), the server takes the list price from
server data (Task 8i's helper: Item Price on the POS Profile's price list, then the invoice's) and the row's final rate
after all discounts. A reduction below list price must be explained by one of:
- an offer: the server evaluator result Task 8i already computes for this save (no second call) gives this row at least
  that discount;
- F&F or a line coupon: rows marked `posnext_discount_source` F&F or carrying `posnext_coupon_code` are left to the
  promotions server, which validates them (P1 6c / 6d) — but only when promotions is installed; without it these marks
  explain nothing;
- a permitted manual edit: `allow_user_to_edit_rate` is on and the unexplained part is ≤ `max_discount_allowed`
  (0 = no limit, as today).
Client flags never decide. Tolerance: one unit of the rate field's precision per unit sold.
- **Online:** an unexplained reduction throws `frappe.ValidationError` naming row, item, list → sent rate and the limit.
- **Offline sync / paid earlier** (Task 8i's leniency rules): keep and log with `log_error_without_telemetry`
  ("Unexplained discount").
- Header (invoice-level) discounts are out of scope (P1 6d caps coupon headers).

**Files:** `pos_next/api/invoices.py` next to the 8i check (or a new module beside it if 8i moved its check out), called
from the same two save paths. **Tests** `pos_next/api/test_discount_enforcement.py`: `test_unflagged_low_rate_refused`,
`test_manual_edit_within_limit_saved`, `test_manual_edit_over_limit_refused`, `test_edit_rate_off_refused`,
`test_offer_discount_saved`, `test_ff_line_left_to_promotions`, `test_ff_mark_without_promotions_explains_nothing`
(patch the override lookup), `test_offline_logged_not_refused`, `test_return_skipped`. Each fails before the fix.
Commit `fix(pos): server enforces price edits and the maximum discount`.

### Task 8m: Server caps the invoice-level (header) discount (Task 8k review, user 2026-11-18)

A header discount (`additional_discount_percentage` / `discount_amount`, any `apply_discount_on`) without a coupon has
no server limit today. Promotions (P1 6d) already caps a coupon header at the coupon's value on unpaid invoices.

**Rule:** after totals, the header discount must be explained by one of:
- the invoice's coupon: when `coupon_code` is set, promotions' cap is the authority when installed; without promotions,
  pos_next's POS Coupon value for this invoice (same resolver Task 8i/8k use) caps it;
- a server-evaluated transaction offer (the Task 8i evaluator result for this save — no extra call) giving that header
  discount;
- a permitted manual invoice discount: POS Settings `allow_user_to_edit_additional_discount` is on and the manual part,
  as a % of the pre-discount total it applies to, is ≤ `max_discount_allowed` (0 = no limit, as today). Line and header
  manual discounts are capped separately by the same setting (one cap each, not summed).
Client flags never decide. Tolerance: one unit of the currency precision.
- **Online:** an unexplained header discount throws `frappe.ValidationError` naming the amount, what explains it and
  the limit. **Offline sync / paid earlier:** keep and log (Task 8k's leniency rules, Error Log as in 8k).
- Returns skipped. Sales Order / Quotation follow the same rule.

**Files:** next to the 8k check in `pos_next/api/invoices.py` (same two save paths). POS: the invoice-discount UI
respects `allow_user_to_edit_additional_discount` and `max_discount_allowed`. **Tests**
`pos_next/api/test_header_discount.py`: `test_manual_header_discount_off_refused`, `test_manual_header_within_limit`,
`test_manual_header_over_limit_refused`, `test_coupon_header_capped_without_promotions`,
`test_transaction_offer_header_saved`, `test_offline_header_logged`, `test_return_skipped`; vitest for the UI cap.
Commit `fix(pos): server caps the invoice-level discount`.

### Task 8n: Price-list currency in the price check + paid-draft rows (peer audit 2026-11-18, Rulings 94, 100)

**Files:**
- Modify: `pos_next/api/invoices.py` (`_list_prices`, `_check_paid_row_discounts`, `_keeps_held_header` / paid-draft flag)
- Test: `pos_next/api/test_discount_enforcement.py`, `pos_next/api/test_header_discount.py`

- [ ] **Step 1: Failing tests:** `test_foreign_price_list_converted` (price list in another currency than the invoice: a sale at the converted list price passes, `row.price_list_rate` saved = list × `plc_conversion_rate` / `conversion_rate`); `test_foreign_price_list_over_discount_refused`; `test_same_currency_unchanged`; `test_paid_draft_header_moved_to_fnf_line_refused` (paid draft 1×50 at list with coupon header 5 → same line at F&F 35 + header 3.5 refused at re-save and at submit); `test_paid_draft_header_moved_to_other_lines_refused` (Better of the two: 2×B at 32 → A+B at 25 refused at re-save and at submit); `test_paid_draft_smaller_cart_same_rows_logged` (stays lenient). Fix `test_paid_draft_flag_only_on_resaved_paid_draft` re-save-at-6 to assert `{False}`.
- [ ] **Step 2:** FAIL. **Step 3:** Implement: `_list_prices` scales by `plc_conversion_rate / conversion_rate` when `price_list_currency` ≠ invoice currency; `pos_paid_draft` is set only when, on top of Ruling 99, every non-free row matches a stored (item_code, uom) of the held draft at a rate no lower than held (reuse `_paid_draft_rates`). **Step 4:** PASS.
- [ ] **Step 5:** Commit `fix(pos): price-list currency in the price check; paid-draft leniency keeps its rows`.

### Task 9: Anti-goal guard + translations + CI + full verification + UI test

**Files:**
- Modify: `pos_next/test_no_promotions_import.py` (new test `test_no_vendor_or_country_strings`: files `pos_next/api/email_verification.py`, `pos_next/api/constants.py`, `pos_next/integrations/registry.py`, `pos_next/integrations/otp*.py`, `pos_next/pos_next/doctype/pos_settings/pos_settings.json`, `POS/src/components/sale/CreateCustomerDialog.vue`, `POS/src/components/sale/EmailVerificationPanel.vue`, `POS/src/stores/posSettings.js` contain none of `miraaya`, `Iraq`, `/rest/V1`, `Magento Setting` (case-insensitive))
- Modify: `pos_next/translations/ar.csv` (gap audit C I9: `Save email & send code` from `EmailVerificationPanel.vue:50`, plus the 27 server strings — `email_verification.py` 7, `otp_frappe_email.py` 3, `templates/emails/customer_email_otp.html` 2, `pos_settings.py` 4, `pos_settings.js` 2, the 9 POS Settings verification labels — plus every new string of Tasks 8b–8f, e.g. "This email is already verified for another customer.", "POS Profile is required.", "Friends & Family discounts apply to invoices only"); `pos_next/integrations/otp.py:131` "Health check failed" wrapped in `_()` (gap audit C M6)
- Modify: `pos_next/test_ar_translations.py` (also scans `pos_next/api/email_verification.py`, `pos_next/integrations/*.py`, `pos_next/templates/emails/*.html` and the labels of `pos_settings.json`)
- Modify: `pos_next/.github/workflows/ci.yml` (gap audit C I8): add the modules `pos_next.api.test_email_verification`, `pos_next.integrations.test_otp_registry`, `pos_next.integrations.test_otp_frappe_email`, `pos_next.integrations.test_benefit_registry`, `pos_next.integrations.test_contract_gate`, `pos_next.test_no_promotions_import`, `pos_next.pos_next.doctype.pos_settings.test_pos_settings_verification`, `pos_next.api.test_return_safety`, `pos_next.api.test_coupon_usage`, `pos_next.api.test_verified_email_unique`, `pos_next.api.test_security_hardening`; a step `cd POS && yarn install --frozen-lockfile && yarn test:run`; a matrix leg that installs `posnext_promotions` and `magento_integration` too and runs `bench migrate` twice (gates + patch idempotency).
- Create: `magento_integration/.github/workflows/ci.yml` (fresh site with erpnext + pos_next + magento_integration; runs `magento_integration.integrations.test_otp_provider`, `magento_integration.dev.test_fake_magento` with `developer_mode` 1, and the Task 8d magento test).
- Tests needing two POS Profiles or an Email Account (`test_pos_settings_verification.py:38-41`, `test_otp_frappe_email.py:117-119`) create their own fixtures and fail instead of skipping (gap audit C M13), so Review Focus #5 runs in CI.

- [ ] **Step 1:** Write the vendor-string test → run → PASS (FAIL means a leftover; fix it). Run `pos_next.test_ar_translations` → PASS (it fails on this branch today on `Save email & send code`).
- [ ] **Step 2:** `bench --site nexus.local migrate` (all three branches checked out) → gates pass; `cd POS && yarn build`.
- [ ] **Step 3:** Run every module from Task 0 + all new test modules; `yarn test:run` → green. Push and confirm both workflows pass.
- [ ] **Step 4: UI (nexus.local, Mailpit open on :8025):** POS → create customer `staff@acme.example` (no first/last split) → Verify → mail arrives in Mailpit → enter code → badge "Email verified"; wrong code → "Wrong code"; 10 wrong codes → "Too many attempts"; second send within cooldown → retry message; change the email and save → old code rejected, badge cleared; a second customer with `staff@acme.example` → "already verified for another customer"; disable the Dev Mailpit Email Account → Verify shows "Email verification is not set up"; stop Mailpit → "Could not send the code". POS Settings form as manager → provider list shows "Email (Frappe)" ✓ and "Magento" ✗ (not configured on this site); as cashier → verification section read-only.
- [ ] **Step 5: UI, fake Magento path (Task 7b, needs `developer_mode`):** `bench --site nexus.local execute magento_integration.dev.fake_magento.enable`; set the profile's `verification_provider` to `magento`; create a customer, `bench --site nexus.local execute magento_integration.dev.fake_magento.mark_synced --kwargs '{"customer": "<name>"}'` → Verify → code arrives in Mailpit → enter it → verified, `custom_email_verified_via == "magento"`; an email containing a Rejected scenario's `match_text` → the panel shows that row's message; an Unavailable row → "Could not send the code". Reset the provider afterwards.
- [ ] **Step 6:** Negative gate check without touching working trees: `bench --site nexus.local execute pos_next.integrations.contract_gate.check --kwargs '{"app_requirements": {"magento_integration": 99}, "installed_apps": ["magento_integration"]}'` → returns the "Update magento_integration…" message.
- [ ] **Step 7:** Push the three branches; PRs reference each other; merge order: promotions Phase 1 → promotions benefit hook → magento_integration → pos_next (only after Task 8e).
