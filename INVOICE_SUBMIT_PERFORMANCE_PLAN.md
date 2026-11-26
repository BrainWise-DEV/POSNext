# Invoice Submit Performance: status and next steps

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
`REPEATABLE READ`.

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

Tooling (test sites only): `pos_next/benchmarks/submit_benchmark.py` (rollback-only benchmark and
business-result fingerprint), `concurrent_benchmark.py` (committed multi-cashier runs with full
cleanup), `desk_vs_pos.py` (POS cashier path vs standard Desk path, equivalence-checked).

Measured on a dev site (indicative, loaded machine): single-request time down about 30%, queries
down about 27%; 100 lines 5.2 s to 3.3 s. POS vs Desk: no meaningful POSNext overhead
(server save+submit within about +/-5%; POS-only costs are `apply_offers` ~8%, one extra totals pass
~280 ms at 100 lines, API pre-checks ~50 ms).

## 3. Next steps (in priority order)

### 3.1 MariaDB `READ COMMITTED` on the client's server (largest lever)
Only change that moved many-cashier throughput: 8 cashiers, 100-line invoices, about 21 to 40
invoices/min, median 21 s to 10 s, series-lock waiting 294 s to 7 s. Cannot be switched on from inside
a request (the transaction has already started) and Frappe has no setting for it, so it is a server
change: `transaction-isolation = READ-COMMITTED` in the MariaDB config.
- Check `binlog_format` is not `STATEMENT` (writes fail under READ COMMITTED with it).
- Test the client's real flows on staging first; Frappe/ERPNext are tested on the default level.
- Owner: whoever runs the client's database. Not a code change.

### 3.2 Naming series per POS Profile / branch (business decision)
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

## 4. Tried and rejected (do not repeat)

- **Late series naming** (validate first, take the series lock just before the INSERT): no gain at the
  default isolation level and 7 deadlocks in 32 invoices at 8 cashiers (0 without it); it changes the
  order in which locks are taken. It only helped under READ COMMITTED.
- **In-app `pos_next_read_committed` flag** (set the session level inside the request): no effect,
  because the transaction has already started; the only in-app routes are a mid-request commit/rollback
  (forbidden) or patching core.
- **Raising the 60 s timeout**: hides the symptom; the client gives up while the server keeps working,
  which the idempotent retry now handles safely.
- **Moving the stock-update realtime event out of the transaction**: not visible in the profile.

## 5. How to re-measure

```bash
# single request, rolled back
bench --site <test-site> execute pos_next.benchmarks.submit_benchmark.run \
  --kwargs '{"line_counts": [10, 100, 200], "repeat": 3}'
# business-result fingerprint (diff before/after a change; must be identical)
bench --site <test-site> execute pos_next.benchmarks.submit_benchmark.fingerprint \
  --kwargs '{"out_file": "/tmp/fp.json"}'
# POS vs Desk
bench --site <test-site> execute pos_next.benchmarks.desk_vs_pos.check_equivalence
bench --site <test-site> execute pos_next.benchmarks.desk_vs_pos.run --kwargs '{"rounds": 5}'
# committed multi-cashier runs (clean up after themselves; test sites only)
bench --site <test-site> execute pos_next.benchmarks.concurrent_benchmark.run \
  --kwargs '{"cashiers": [1, 4, 8], "invoices_per_cashier": 4, "lines": 100, "disjoint": True}'
bench --site <test-site> execute pos_next.benchmarks.concurrent_benchmark.cleanup   # if a run was interrupted
```
