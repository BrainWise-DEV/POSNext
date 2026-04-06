# Copyright (c) 2026, BrainWise and contributors
# For license information, please see license.txt

"""Centralized defaults for the sync engine."""

DEFAULT_PUSH_INTERVAL_SECONDS = 60
DEFAULT_PULL_MASTERS_INTERVAL_SECONDS = 300
DEFAULT_PULL_FAILOVER_INTERVAL_SECONDS = 120

DEFAULT_BATCH_SIZE = 100
MAX_ATTEMPTS_BEFORE_DEAD = 10
REPLAY_REJECT_HOURS = 24

HTTP_TIMEOUT_SECONDS = 30
LOGIN_TIMEOUT_SECONDS = 10

# Outbox back-pressure thresholds
OUTBOX_WARN_DEPTH = 1000
OUTBOX_CRITICAL_DEPTH = 10000

# Retention
HISTORY_ARCHIVE_AFTER_DAYS = 7
HISTORY_PURGE_AFTER_DAYS = 90
TOMBSTONE_RETAIN_DAYS = 90

# Conflict rules
CONFLICT_RULES = {
	"Last-Write-Wins",
	"Central-Wins",
	"Branch-Wins",
	"Field-Level-LWW",
	"Manual",
}
CDC_STRATEGIES = {"Outbox", "Watermark"}
DIRECTIONS = {"Central→Branch", "Branch→Central", "Bidirectional"}
