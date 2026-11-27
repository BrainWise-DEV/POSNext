# Capturing a checkout deadlock report (for the database administrator)

Cashiers sometimes get **"Internal Server Error / QueryDeadlockError"** while paying. The
application's own log says *where in the code* it happened but not *which two transactions
collided*. Only MariaDB can tell us that. This page says how to get it, safely.

**Please do not change the transaction isolation level** (`READ COMMITTED` makes this far worse:
in our tests more than half of the sales deadlocked in the stock ledger). Nothing below changes
how the database behaves; it only records more.

## 1. Check the settings (read-only, 1 minute)

On the application server:

```bash
bench --site <site> execute pos_next.diagnostics.db_report
```

Send the output. It shows, as the application's own connection sees them: the global and the
session isolation level, `binlog_format`, whether deadlock logging is on, the server version, and
the counters `Innodb_deadlocks` / `Innodb_row_lock_waits` since the server started (which tells us
how often this really happens).

If you prefer SQL (any account that can read variables):

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

## 3. After the next occurrence, collect

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

## 4. Privacy

The MariaDB block contains the SQL text **with values** (item codes, amounts, customer names).
Please read it before sending and replace anything sensitive; the structure (tables, indexes, lock
modes, which statement waits for which) is what matters, not the values.

## 5. Afterwards

Set `innodb_print_all_deadlocks` back to `OFF` (it only adds a little log volume, so leaving it on
is fine too). Nothing here needs to be undone in the application.
