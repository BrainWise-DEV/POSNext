# Invoice Submit Performance: status and next steps

> **Correction:** the READ COMMITTED recommendation in earlier versions of this file is withdrawn (see 3.1).

Context: a client with large POS invoices and many cashiers hit
`Invoice Submit: Operation timed out after 60000ms`. It did not reproduce locally.
This file records what was done, what was measured, what was rejected and why,
and what is left.

## 1. Where the time goes (100-line invoice, one cashier)

| Share | What | Controllable from POSNext? |
|---|---|---|
| ~35% | Stock ledger posting on submit (`repost_current_voucher` per item) | No, ERPNext core |
| ~30% | ERPNext item-detail lookups (`set_missing_item_details`), 2 passes remain | Partly (see 3.3) |
| ~8% | `apply_offers` (promotion engine) | Yes (see 3.5) |
| ~8% | `calculate_taxes_and_totals`, 4 runs | Partly (see 3.4) |
| rest | inserts, GL, hooks | Mostly inherent |

With many cashiers the limit is not CPU: submits queue on the Sales Invoice naming-series
row lock (`SELECT ... FOR UPDATE` on `tabSeries`, taken before validate and held until
commit) and on slow item INSERTs that wait on InnoDB gap locks under the default
`REPEATABLE READ`. Changing the isolation level is NOT a safe fix (see 3.1).

## 2. Done (this branch)

Code:
- Step timing logs per request (`pos_next/perf.py`): slow calls (`pos_next_slow_submit_ms`,
  default 5000) go to `sites/<site>/logs/pos_next_perf.log`; `pos_next_perf_log_all` logs all.
- Commission code: item-master lookups cached per request (~1,200 queries per 100 lines).
- `submit_invoice` no longer calls `.save()` right before `.submit()` (a full duplicate validate).
- `update_invoice`: validate skips the repeat of its own item-detail pass
  (`CustomSalesInvoice.set_missing_values`, one-shot flag). The submit-time validate still runs in full.
- Idempotent checkout: `client_request_id` (separate from `offline_id`, which relaxes Sales Person
  rules) makes a retry after a client timeout return the existing invoice. The dedupe lookup does
  not use `FOR UPDATE` (gap-lock deadlocks).
- `check_offline_invoice_synced` also returns the invoice totals when the sale exists.
- Frontend: `SkipIfBusyMutex` (a double-click is dropped, not re-run against a cleared cart);
  timeout recovery checks the server by key before showing an error; a stale first request can no
  longer clear a new cart.
- POS Coupon: `increment_coupon_usage` no longer commits mid-submit (it leaked partial work and could
  leave the retry key stuck as Pending); atomic UPDATE; counted after the sale is final.

Measurement tooling (test sites only) was used for every number in this document and has since been
removed from the repository, because it only ever ran on test sites and creates and deletes data. Its
last version is in commit `70089575` (`git show 70089575:pos_next/benchmarks/<file>`): `submit_benchmark.py`
(rollback-only benchmark and fingerprint), `concurrent_benchmark.py`, `workload_probe.py`, `gap_lock_probe.py`,
`race_probe.py`, `lock_timeline.py`, `deadlock_probe.py`, `dup_submit_probe.py`, `desk_vs_pos.py`. References
to `benchmarks/...` below point at those files.

Measured on a dev site (indicative, loaded machine): single-request time down about 30%, queries
down about 27%; 100 lines 5.2 s to 3.3 s. POS vs Desk: no meaningful POSNext overhead
(server save+submit within about +/-5%; POS-only costs are `apply_offers` ~8%, one extra totals pass
~280 ms at 100 lines, API pre-checks ~50 ms).

## 3. Next steps (in priority order)

### 3.1 MariaDB `READ COMMITTED`: DO NOT USE (earlier recommendation withdrawn)
An earlier version of this plan recommended `transaction-isolation = READ-COMMITTED` because it roughly
doubled throughput (8 cashiers, 100-line invoices: about 21 to 40 invoices/min). That test gave every
cashier DIFFERENT items. With cashiers selling OVERLAPPING items (the normal case in a shop) it is
harmful: 16 cashiers, 192 sales, 40 shared items: **106 of 192 sales failed with deadlocks in ERPNext's
stock-ledger posting** (`get_previous_sle_of_current_voucher`, `get_next_stock_reco`), against 0 of 192
at the default `REPEATABLE READ`. ERPNext's stock posting relies on the default level's locking, so this is
also a stock-accuracy risk, not only an availability one. Keep the default isolation level.
(`benchmarks/deadlock_probe.py`, `isolation` option.)

### 3.2 Naming series per POS Profile / branch (business decision; next best lever)
Locks are per series, so branches stop queuing behind each other. Cashiers on the same series still
queue. Changes invoice numbering, so needs the client's sign-off.

### 3.3 Skip the submit-time item-detail pass, guarded by a comparison
~9% of single-request time. `submit_invoice` re-reads items from the client, so skipping blindly would
trust client data. Skip only when the client's items equal the saved draft's items field for field
(and the header fields that feed item details match). Needs fingerprint tests including tampered
payloads. Medium risk.

### 3.4 Remove the explicit `calculate_taxes_and_totals` in `update_invoice` (~4-5%)
It runs before the stock pre-check and sales-team build. Moving those after the save needs care
(commission rows depend on net amounts). Verify with the fingerprint scenarios.

### 3.5 `apply_offers` cost (~8% at 100 lines)
Look at how often the cashier screen calls it per cart change and whether the final pass before
checkout can reuse the last result.

### 3.6 Server tuning and observability
- `innodb_buffer_pool_size`, `innodb_flush_log_at_trx_commit`, disk speed: 100-row inserts slow
  sharply under load.
- Enable the MariaDB slow query log on the client; grant PROCESS to a diagnostics user to inspect lock waits.
- Roll out with `pos_next_slow_submit_ms` and watch `pos_next_perf.log` for the slow step.

### 3.7 Verification we could not do here
- Double-click and timeout recovery on a real till (only mocked requests were tested).
- Concurrency of the ORIGINAL code for a true before/after (only single-request before/after exists).
- Real browser timings (Chrome tools) for POS vs Desk; the comparison measured server time only.
- Re-run the multi-cashier benchmarks on a quiet machine; the dev machine had background load.

### 3.8 Follow-ups found on the way (separate PRs)
- `decrement_coupon_usage` has the same mid-request `frappe.db.commit()` on the cancel path.
- 8 existing backend test modules fail on `main` (unchanged by this branch): credit_linked_returns,
  customers, offers, rename_location_doctypes, pos_coupon, pos_closing_print, no_promotions_import,
  promotions. The full-app test run also aborts in ERPNext record setup (`_Test Account VAT`).
- Ruff reports 3 findings on untouched lines (`__future__` import, one `isinstance` tuple, one
  `.format` index in the commission module).
- `main`'s wallet account belongs to another company, so every submit there logs
  "Loyalty to Wallet Conversion Error"; fix the data before benchmarking again.

## 3b. Lock failures reported by the client: 1213 deadlocks and 1205 lock wait timeouts (OPEN)

Two different failures, classified by the real MariaDB error number (`pos_next/db_errors.py`):

| | 1213 deadlock (`QueryDeadlockError`) | 1205 lock wait timeout (`QueryTimeoutError`) |
|---|---|---|
| Frappe also maps | 1020 (snapshot conflict) to the same type | nothing else |
| DB rolls back | the whole transaction | the statement only (`innodb_rollback_on_timeout` off) |
| Auto-retry from the cashier screen | **yes, up to 3 times** (the victim is fully rolled back) | **no**: the cashier already waited ~50 s, the blocker is probably still there; a retry would block again inside the 60 s limit. A manual retry is safe (same key) |

**Confirmed (reproduced here, default isolation, `benchmarks/workload_probe.py`)**
- 1213: about 1-2% of sales, in `submit_invoice`, victim statement `INSERT INTO tabStock Ledger Entry`
  (14 located cases). Not explained by item order, loyalty customers or item overlap. The OTHER
  transaction and the lock type are unknown (need the MariaDB report).
- 1205 (session `innodb_lock_wait_timeout` lowered to 4 s, 12 cashiers, 2 hot items): in `update_invoice`
  creating a new draft, the blocked statement is `SELECT ... FROM tabSeries ... FOR UPDATE` (the invoice-number
  series row), 22 of 22. That row is locked before validate and held until the request ends:
  ~70 ms (10 lines) to ~300 ms (100 lines) per request, plus whatever validate costs.
  The holder here is another cashier's `update_invoice`. The default 50 s needs a far longer hold or queue.
- Lock hold times in `submit_invoice` (100 lines): stock rows (`tabBin`) ~1.3 s, `tabCompany` row 55-130 ms,
  `tabCustomer` row 50-120 ms, all until the request commits.
- Cost inside that hold: `get_pending_wallet_payments` (run by wallet/loyalty-point payments in validate) costs
  ~2 queries and 0.5 ms per open (`outstanding_amount > 0`) POS invoice of the customer, linearly
  (300 open invoices = 151 ms). Whether this matters depends on the client's data: run
  `SELECT customer, COUNT(*) c FROM \`tabSales Invoice\` WHERE is_pos=1 AND docstatus IN (0,1) AND
  outstanding_amount>0 GROUP BY customer ORDER BY c DESC LIMIT 20;`. Hypothesis only.

**Data-integrity defect found and fixed (not a hypothesis; reproduced with an emulated lock error)**
Twelve broad `except Exception` blocks on the checkout path swallowed database lock errors. After a
swallowed 1213 the request continued in a NEW transaction (InnoDB had rolled the old one back):
`submit_invoice` returned success while the invoice was still a draft with 0 stock entries and 0 GL
entries. After a swallowed 1205 the sale committed but the wallet credit was silently dropped. Fix:
`reraise_if_lock_error` first in each such handler (wallet hook, customer auto-create, coupon, retry-key
bookkeeping, wallet-reversal paths...), so the error reaches Frappe's request handler, which rolls the whole
transaction back (`app.py`: `rollback` stays True and the `finally` block rolls back for POST).
Regression tests fail without the guard (mutation-checked).

**Retry safety, verified by test:** a victim leaves no draft and no retry-key row; a retry with the same
`client_request_id` yields exactly one sale and one stock movement; after a 1205 the earlier statements of the
request are still in the open transaction until the request-level rollback, then everything is gone; the retry
after the blocker releases succeeds with no duplicate; realtime events are deferred until commit; ambiguous
failures (no answer) are not auto-retried.

**Not done / unknown (needs a database administrator: `docs/DEADLOCK_DIAGNOSTICS.md`)**
- Both transactions, statements, indexes and lock types of the client's deadlocks (`innodb_print_all_deadlocks`).
- For 1205: the actual BLOCKER, captured while a request waits (`INNODB_TRX` / `INNODB_LOCK_WAITS`, processlist),
  whether it is another cashier, an idle open transaction, a background job, a hook, or DDL (metadata lock;
  the error is also 1205 but governed by `lock_wait_timeout`).
- The client's real settings: `innodb_lock_wait_timeout`, `innodb_rollback_on_timeout`, `lock_wait_timeout`, global and
  session `tx_isolation` (`bench --site <site> execute pos_next.diagnostics.db_report` prints the application
  connection's own values).
- Wallet/loyalty payments end to end: `main` cannot run them (its `Redeem Points` mode maps to a Cash account;
  POSNext rejects a wallet mode equal to the invoice receivable account).
- The smallest root-cause fix is NOT proposed: candidates (shorten the series lock hold; reduce `tabBin` hold) cannot be ranked
  until the blocker is known, and none may change the isolation level, raise timeouts, or bypass ERPNext stock/GL logic.

## 3c. Draft saves, Sales Team writes and the locks between submit and draft creation

**Draft saves (traced, not assumed).** In this code the server draft (`update_invoice`) is created ONLY at
checkout: once per payment attempt (`submitInvoice`). `useInvoice.saveDraft` is exported but has no caller;
the drafts saved while editing a cart (`draftsStore.saveDraftInvoice`) go to the browser's IndexedDB, not the
server. Git history has no cart-edit server autosave. If the client sees many `update_invoice` calls per sale
they either run a different frontend version or are retrying; count them with `pos_next_perf_log_all` (the
`pos_next_perf.log` has one line per call).
Real waste found and fixed: every manual retry of the same, unchanged cart created a NEW draft (orphaning the
previous one, plus another invoice-number lock). Now an unchanged retry reuses its draft; an edited or cleared
cart gets a new draft and a new key; the server recreates a draft that has vanished instead of failing.

**`tabSales Team` writes (traced).** A new draft inserts exactly one `tabSales Team` row per sales person, once.
Editing a draft updates the rows in place (the only `DELETE` is Frappe's no-op delete, see below); submit does
one `UPDATE` per row. Nothing is deleted and re-created without cause; no change was made. No Sales Team
statement appeared as a blocked or victim statement in any run.

**Confirmed (controlled two-process test, `benchmarks/gap_lock_probe.py`).** While another cashier's real
`submit_invoice` holds its locks, a new draft blocks and times out (1205) on
`INSERT INTO tabSales Invoice Item` (374 ms alone vs blocked for the whole submit). Two sources inside Frappe's
save of an existing document hold the range locks: the `FOR UPDATE` load of the stored copy (every child table)
and the no-op `DELETE ... WHERE parent = ...` per child table. Removing only one does not stop the blocking; removing
both does (draft created in 172 ms during the submit).

**Tried and REJECTED: removing both (override `load_doc_before_save` + `update_child_table` for POS invoices).**
Outcome identical on 5 scenarios and a same-invoice double submit / edit-vs-submit race stayed safe (24 rounds), BUT:

| 12 cashiers, 2 hot items, 144 sales | ok | deadlocks 1213 | lock timeouts 1205 |
|---|--:|--:|--:|
| Frappe locking, 50 s wait | 143 | 1 | 0 |
| locks removed, 50 s wait | **48** | **96** (stock ledger) | 0 |
| Frappe locking, 4 s wait | 64 | 1 | 79 (series row) |
| locks removed, 4 s wait | **45** | **97** (stock ledger) | 2 |

Those range locks also serialise submits of adjacent invoices, which ERPNext's stock-ledger posting depends on
(likely mechanism: the scan's next-key lock on the neighbouring invoice's first row; not proven). Removing them
trades draft blocking for a stock-ledger deadlock storm. Reverted; `TestSaveKeepsFrappesChildTableLocking`
guards against reintroducing it.

**Where that leaves the 1205s and 1213s.** The two failures are linked: the locks that make a draft wait for a
submit (1205) are the same locks that keep concurrent submits from deadlocking in the stock ledger (1213). Any
fix has to shorten how long a submit holds them (see 2 and 3.3), not remove them.

## 3d. Where a submit's time and locks go, and what could be moved (`benchmarks/lock_timeline.py`)

One `submit_invoice` (median of 5; locks are held from the first statement until the request commits):

| 100 lines (2.0 s) | When | Duration | Share |
|---|--:|--:|--:|
| child tables loaded `FOR UPDATE` (the lock that blocks other cashiers' new drafts) | +32 ms | held to the end | 98% |
| validation inside the lock | +106 ms | 465 ms | 23% |
| of which item-detail refresh (`set_missing_values`) | +107 ms | 379 ms | 19% |
| saving child rows | +611 ms | 61 ms | 3% |
| stock ledger posting (ERPNext core) | +728 ms | 1,141 ms | 57% |
| GL posting | +1,869 ms | 79 ms | 4% |
| hooks (wallet, realtime stock event, offer usage, gate): all together | | ~40 ms | 2% |
| `tabBin` stock rows held / `tabCompany` / `tabCustomer` | | ~1.3 s / ~55 ms / ~50 ms | |

So the only phase that is not core ERPNext and not stock posting is the item-detail refresh (19%); the
POSNext hooks are negligible (the realtime stock event takes 3 ms: moving it out is not worth it).

**Tried and REJECTED: refresh the item details just before the save, so validation skips it inside the
locks** (same work, same result: identical on 5 scenarios, 43 tests green). It shortened the locked window by
13% and halved draft latency, but multiplied stock deadlocks about 80 times:

| 12 cashiers, 2 hot items, 12 sales each, seeds 51-53 | sales ok | 1213 | draft p50 |
|---|--:|--:|--:|
| refresh inside the save (current) | 430 / 432 | 2 | 6.6 s |
| refresh before the locks | 273 / 432 | 159 (all stock ledger) | 3.6 s |

At a 4 s lock wait it cut 1205s from 110 to 41 but brought 86 deadlocks. Reverted;
`TestItemDetailsStayInsideTheSave` guards against it.

**What this establishes.** Whether concurrent submits collide in the stock ledger depends on their TIMING
relative to each other, not only on which locks exist. Two changes that keep the locks (this one) or remove them
(3c) both expose ERPNext's stock-ledger deadlocks. Stock posting is only safe with the present ordering, so
no work may be moved across the point where the save takes its locks without a concurrency benchmark that
counts 1213s. Stock-ledger creation is core ERPNext (57% of the window) and not something POSNext can change.

## 4. Tried and rejected (do not repeat)

- **Late series naming** (validate first, take the series lock just before the INSERT): no gain at the
  default isolation level and 7 deadlocks in 32 invoices at 8 cashiers (0 without it); it changes the
  order in which locks are taken. It only helped under READ COMMITTED, which is itself unsafe (3.1).
- **In-app `pos_next_read_committed` flag** (set the session level inside the request): no effect,
  because the transaction has already started; the only in-app routes are a mid-request commit/rollback
  (forbidden) or patching core.
- **Raising the 60 s timeout**: hides the symptom; the client gives up while the server keeps working,
  which the idempotent retry now handles safely.
- **Refreshing item details before the save takes its locks** (3d): halves draft latency but multiplies stock-ledger deadlocks ~80x (2 -> 159 per 432 sales).
- **Removing Frappe's child-table locking on save for POS invoices** (3c): fixes draft blocking, causes a stock-ledger deadlock storm (96 of 144 sales).
- **Moving the stock-update realtime event out of the transaction**: not visible in the profile.

## 5. How to re-measure

The tools are no longer in the tree (see the note near the top). To re-measure, restore them on a TEST
site checkout, for example:

```bash
git checkout 70089575 -- pos_next/benchmarks
bench --site <test-site> execute pos_next.benchmarks.submit_benchmark.run \
  --kwargs '{"line_counts": [10, 100, 200], "repeat": 3}'
bench --site <test-site> execute pos_next.benchmarks.concurrent_benchmark.cleanup   # after an interrupted run
git rm -rf --cached pos_next/benchmarks && rm -rf pos_next/benchmarks               # do not commit them back
```

What they measured: single-request time and query counts (rolled back), a business-result fingerprint to
prove an optimisation changes nothing visible, POS-vs-Desk equivalence, and committed multi-cashier runs
that report sales, deadlocks (1213), lock timeouts (1205) and draft latency.
