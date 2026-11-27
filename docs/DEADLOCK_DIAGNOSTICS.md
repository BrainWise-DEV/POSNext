# Capturing checkout lock failures: deadlocks (1213) and lock wait timeouts (1205)

Cashiers sometimes get **"Internal Server Error"** while paying. There are two different database
failures behind it and they need different evidence. Please keep them apart.

| | **1213 deadlock** | **1205 lock wait timeout** |
|---|---|---|
| Shown by Frappe as | `QueryDeadlockError` | `QueryTimeoutError` |
| What happened | InnoDB found a cycle between transactions and rolled the victim back **completely** | A statement waited longer than the timeout for a lock another transaction **still holds** (no cycle needed) |
| Rolled back by the database | the whole transaction | only the **statement**, unless `innodb_rollback_on_timeout` is on |
| Time it takes | immediate | about `innodb_lock_wait_timeout` (50 s by default) for row locks; `lock_wait_timeout` for metadata locks |
| Evidence that works | `innodb_print_all_deadlocks` (section 2) | live capture **while a request is blocked** (section 3); the deadlock log does NOT cover it |

Frappe also reports MariaDB error **1020** ("Record has changed since last read": snapshot isolation
on newer MariaDB) as `QueryDeadlockError`, so the exception name alone does not prove a deadlock.
The application log (`pos_next_deadlock.log`, below) stores the real error number in `errno` and a
`kind` field to tell them apart.

**Please do not change the transaction isolation level** (`READ COMMITTED` makes this far worse: in
our tests more than half of the sales deadlocked in the stock ledger) **and do not simply raise the
lock timeouts**; both would only hide the problem. Nothing below changes how the database behaves;
it only records more.

## 1. Check the settings (read-only, 1 minute)

On the application server:

```bash
bench --site <site> execute pos_next.diagnostics.db_report
```

Send the output. It shows, as the application's own connection sees them: the global and the
session isolation level, `binlog_format`, whether deadlock logging is on, the server version, and
the counters `Innodb_deadlocks` / `Innodb_row_lock_waits` since the server started (which tells us
how often this really happens).

The SQL equivalent (any account that can read variables). Run it, and also send the values of the
**application's own connection** (the command above prints those), because an administrator's
connection can have different session settings:

```sql
SELECT VERSION(),
       @@GLOBAL.tx_isolation,            @@SESSION.tx_isolation,
       @@GLOBAL.innodb_lock_wait_timeout, @@SESSION.innodb_lock_wait_timeout,
       @@GLOBAL.innodb_rollback_on_timeout,
       @@GLOBAL.lock_wait_timeout,        @@SESSION.lock_wait_timeout;
```

The smaller one, if you only want the deadlock logging state:

```sql
SELECT @@global.tx_isolation, @@session.tx_isolation, @@global.binlog_format,
       @@innodb_print_all_deadlocks, VERSION();
SHOW GLOBAL STATUS WHERE Variable_name IN ('Uptime','Innodb_deadlocks','Innodb_row_lock_waits');
```

The global value matters because Frappe does not set an isolation level on its MariaDB
connections: each connection simply inherits whatever the server's global setting is when it opens.

## 2. Turn on full deadlock logging (needs SUPER; no restart)

```sql
SET GLOBAL innodb_print_all_deadlocks = ON;
```

Every deadlock is then written, with both transactions, to the MariaDB error log. To keep it after
a restart add to the `[mysqld]` section of the MariaDB config:

```ini
innodb_print_all_deadlocks = 1
```

Find the error log: `SHOW VARIABLES LIKE 'log_error';` (an empty value means it goes to the
system journal: `journalctl -u mariadb`).

## 2b. For a 1213 deadlock: after the next occurrence, collect

1. **From the MariaDB error log**, the block that starts at `*** (1) TRANSACTION` and ends at
   `*** WE ROLL BACK TRANSACTION (n)`. It lists both transactions, their SQL statements, the
   tables and indexes, the locks each holds and waits for (gap, insert intention, record), and
   which one was chosen as the victim. Ideally 3 or more blocks, not just one.
2. **The application's own record** of the same moment, written only when a deadlock happens:
   `sites/<site>/logs/pos_next_deadlock.log` (one JSON line per deadlock: operation, the table
   being written, the checkout phase, the real isolation level, a trace id, row counts, payment
   mode names, and a hashed customer id; no amounts and no customer names).
3. **Error Log entries** titled `Submit Invoice Error` / `Update Invoice Error` for the same minutes.
4. Roughly what else was happening: how many cashiers, any POS Closing Shift, stock reposting
   or scheduled jobs running at that moment.

## 3. For a 1205 lock wait timeout: capture it WHILE a request is blocked

The timeout error only says that a statement gave up; it does not say who was holding the lock. The
blocker is gone by then. Evidence has to be taken while a cashier's request is still waiting (the
first 50 seconds). Two ways:

**a) Scheduled snapshot (recommended: nobody has to be watching).** Run this every 5 seconds from
a privileged account (cron or a loop) and keep the output for the busy hours; the files are small
when nothing is blocked:

```sql
-- who is waiting for whom, with the statements and how long
SELECT NOW() AS captured_at,
       r.trx_id AS waiting_trx, r.trx_mysql_thread_id AS waiting_thread,
       TIMESTAMPDIFF(SECOND, r.trx_wait_started, NOW()) AS waited_s,
       r.trx_query AS waiting_query,
       b.trx_id AS blocking_trx, b.trx_mysql_thread_id AS blocking_thread,
       b.trx_started AS blocking_started, b.trx_state AS blocking_state,
       TIMESTAMPDIFF(SECOND, b.trx_started, NOW()) AS blocking_open_s,
       b.trx_rows_locked, b.trx_query AS blocking_current_query
FROM information_schema.INNODB_LOCK_WAITS w
JOIN information_schema.INNODB_TRX r ON r.trx_id = w.requesting_trx_id
JOIN information_schema.INNODB_TRX b ON b.trx_id = w.blocking_trx_id;

-- which lock: table, index, mode (S/X, gap, record)
SELECT lock_trx_id, lock_mode, lock_type, lock_table, lock_index, lock_data
FROM information_schema.INNODB_LOCKS;

-- every connection and what it is doing, including idle ones (sleeping with an open transaction)
SHOW FULL PROCESSLIST;

-- long-open transactions, even idle ones: these are the usual real blockers
SELECT trx_id, trx_mysql_thread_id, trx_state, trx_started,
       TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS open_s, trx_rows_locked, trx_query
FROM information_schema.INNODB_TRX ORDER BY trx_started LIMIT 20;
```

(These `information_schema` tables are the ones MariaDB documents for InnoDB lock waits and need the
`PROCESS` privilege. If the server rejects a table, use whatever lock-wait view your MariaDB version
provides, or `SHOW ENGINE INNODB STATUS`, whose TRANSACTIONS section shows who waits for whom. We could
not run these statements ourselves: the application's database user has no `PROCESS` privilege.)

**b) Live, if you can reproduce.** While a cashier is stuck on "paying", run the four statements
above, plus `SHOW ENGINE INNODB STATUS\G` (its TRANSACTIONS section lists every open transaction and
what it waits for).

**The blocker is often not another cashier.** Look at `blocking_current_query` and
`blocking_open_s`: a blocker that is **Sleep** with a large `open_s` is a connection that left a
transaction open (a script, a console, a report, a background job, a custom hook). Please also say
whether any of these were running at that moment: a `bench migrate`, an `ALTER TABLE` or index
build, stock reposting (`Repost Item Valuation`), POS Closing Shift, a backup, scheduled jobs, other
apps' syncs (Magento, e-commerce integrations).

**Metadata locks** (the other kind of 1205, controlled by `lock_wait_timeout`, not
`innodb_lock_wait_timeout`) come from DDL: an `ALTER TABLE`, `CREATE INDEX` or a table lock waiting
behind a long transaction, and everything queues behind it. If the settings query shows a small
`lock_wait_timeout`, or the blocker is a DDL statement, also capture:

```sql
SELECT * FROM information_schema.METADATA_LOCK_INFO;   -- needs: INSTALL SONAME 'metadata_lock_info';
```

Finally, send the application's record of the same moment. Each failure is one JSON line in
`sites/<site>/logs/pos_next_deadlock.log` with `kind` (`deadlock_1213`, `snapshot_conflict_1020`,
`lock_wait_timeout_1205`), `errno`, the endpoint, the checkout phase, `elapsed_ms` (a 1205 sits near
the lock wait timeout), and the application connection's real `innodb_lock_wait_timeout` and
`tx_isolation`. Browser-side failures are logged separately by kind (`frontend_timeout`, `network`,
`lock_wait_timeout`, `deadlock`) in the cashier screen's console.

## 5. Privacy

The MariaDB block contains the SQL text **with values** (item codes, amounts, customer names).
Please read it before sending and replace anything sensitive; the structure (tables, indexes, lock
modes, which statement waits for which) is what matters, not the values.

## 6. Afterwards

Set `innodb_print_all_deadlocks` back to `OFF` (it only adds a little log volume, so leaving it on
is fine too). Nothing here needs to be undone in the application.
