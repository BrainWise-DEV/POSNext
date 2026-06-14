/**
 * Global Logging Utility
 * Centralized logging with environment-aware output
 *
 * Features:
 * - Auto-disable in production
 * - Namespace/module support
 * - Log levels (debug, info, warn, error)
 * - Performance timing
 * - Configurable via localStorage
 *
 * Usage:
 * import { logger } from '@/utils/logger'
 *
 * const log = logger.create('ItemSearch')
 * log.info('Loading items', { count: 50 })
 * log.debug('Cache hit', cacheData)
 * log.error('Failed to load', error)
 */

/**
 * Log levels in order of severity
 */
const LOG_LEVELS = {
	DEBUG: 0,
	INFO: 1,
	WARN: 2,
	ERROR: 3,
	NONE: 4,
}

/**
 * ANSI color codes for console styling
 */
const COLORS = {
	DEBUG: '\x1b[36m', // Cyan
	INFO: '\x1b[34m', // Blue
	WARN: '\x1b[33m', // Yellow
	ERROR: '\x1b[31m', // Red
	SUCCESS: '\x1b[32m', // Green
	RESET: '\x1b[0m',
	BOLD: '\x1b[1m',
	DIM: '\x1b[2m',
}

/**
 * Logger Configuration
 */
class LoggerConfig {
	constructor() {
		// Check if we're in development mode
		this.isDev = import.meta.env?.DEV || import.meta.env?.MODE === 'development'

		// Check for manual override in localStorage
		if (typeof window !== 'undefined' && typeof localStorage !== 'undefined') {
			const manualLevel = localStorage.getItem('POS_LOG_LEVEL')
			const manualEnabled = localStorage.getItem('POS_LOGGING_ENABLED')

			this.currentLevel = manualLevel ? LOG_LEVELS[manualLevel.toUpperCase()] : this.getDefaultLevel()
			this.enabled = manualEnabled !== null ? manualEnabled === 'true' : this.isDev
		} else {
			this.currentLevel = this.getDefaultLevel()
			this.enabled = this.isDev
		}

		// Namespaces to enable/disable (empty = all enabled)
		this.enabledNamespaces = new Set()
		this.disabledNamespaces = new Set()

		// Load namespace config from localStorage
		this.loadNamespaceConfig()
	}

	getDefaultLevel() {
		// Development: DEBUG, Production: WARN
		return this.isDev ? LOG_LEVELS.DEBUG : LOG_LEVELS.WARN
	}

	loadNamespaceConfig() {
		if (typeof window === 'undefined' || typeof localStorage === 'undefined') return

		try {
			const enabled = localStorage.getItem('POS_LOG_NAMESPACES_ENABLED')
			const disabled = localStorage.getItem('POS_LOG_NAMESPACES_DISABLED')

			if (enabled) {
				enabled.split(',').forEach(ns => this.enabledNamespaces.add(ns.trim()))
			}
			if (disabled) {
				disabled.split(',').forEach(ns => this.disabledNamespaces.add(ns.trim()))
			}
		} catch (error) {
			// Ignore localStorage errors
		}
	}

	setLevel(level) {
		const levelValue = typeof level === 'string' ? LOG_LEVELS[level.toUpperCase()] : level
		if (levelValue !== undefined) {
			this.currentLevel = levelValue
			if (typeof localStorage !== 'undefined') {
				localStorage.setItem('POS_LOG_LEVEL', Object.keys(LOG_LEVELS)[levelValue])
			}
		}
	}

	setEnabled(enabled) {
		this.enabled = enabled
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem('POS_LOGGING_ENABLED', enabled.toString())
		}
	}

	enableNamespace(namespace) {
		this.enabledNamespaces.add(namespace)
		this.disabledNamespaces.delete(namespace)
		this.saveNamespaceConfig()
	}

	disableNamespace(namespace) {
		this.disabledNamespaces.add(namespace)
		this.enabledNamespaces.delete(namespace)
		this.saveNamespaceConfig()
	}

	saveNamespaceConfig() {
		if (typeof localStorage === 'undefined') return

		if (this.enabledNamespaces.size > 0) {
			localStorage.setItem('POS_LOG_NAMESPACES_ENABLED', Array.from(this.enabledNamespaces).join(','))
		} else {
			localStorage.removeItem('POS_LOG_NAMESPACES_ENABLED')
		}

		if (this.disabledNamespaces.size > 0) {
			localStorage.setItem('POS_LOG_NAMESPACES_DISABLED', Array.from(this.disabledNamespaces).join(','))
		} else {
			localStorage.removeItem('POS_LOG_NAMESPACES_DISABLED')
		}
	}

	shouldLog(namespace, level) {
		// Logging globally disabled
		if (!this.enabled) return false

		// Check log level
		if (level < this.currentLevel) return false

		// If specific namespaces are enabled, only log those
		if (this.enabledNamespaces.size > 0) {
			return this.enabledNamespaces.has(namespace)
		}

		// If namespace is explicitly disabled, don't log
		if (this.disabledNamespaces.has(namespace)) {
			return false
		}

		return true
	}
}

/**
 * Namespaced Logger Instance
 */
class Logger {
	constructor(namespace, config) {
		this.namespace = namespace
		this.config = config
		this.timers = new Map()
	}

	/**
	 * Format log message with timestamp and namespace
	 */
	format(level, message, ...args) {
		const timestamp = new Date().toISOString().split('T')[1].split('.')[0]
		const levelName = Object.keys(LOG_LEVELS)[level]
		const color = COLORS[levelName] || COLORS.RESET

		if (typeof window !== 'undefined') {
			// Browser console with styling
			return [
				`%c[${timestamp}] %c${levelName}%c [${this.namespace}]%c ${message}`,
				'color: gray; font-size: 0.9em',
				`${color}; font-weight: bold`,
				'color: blue; font-weight: bold',
				'color: inherit',
				...args
			]
		} else {
			// Node.js/SSR with ANSI colors
			return [
				`${COLORS.DIM}[${timestamp}]${COLORS.RESET} ${color}${COLORS.BOLD}${levelName}${COLORS.RESET} ${COLORS.BOLD}[${this.namespace}]${COLORS.RESET} ${message}`,
				...args
			]
		}
	}

	debug(message, ...args) {
		if (this.config.shouldLog(this.namespace, LOG_LEVELS.DEBUG)) {
			console.log(...this.format(LOG_LEVELS.DEBUG, message, ...args))
		}
	}

	info(message, ...args) {
		if (this.config.shouldLog(this.namespace, LOG_LEVELS.INFO)) {
			console.log(...this.format(LOG_LEVELS.INFO, message, ...args))
		}
	}

	warn(message, ...args) {
		if (this.config.shouldLog(this.namespace, LOG_LEVELS.WARN)) {
			console.warn(...this.format(LOG_LEVELS.WARN, message, ...args))
		}
	}

	error(message, ...args) {
		if (this.config.shouldLog(this.namespace, LOG_LEVELS.ERROR)) {
			console.error(...this.format(LOG_LEVELS.ERROR, message, ...args))
		}
	}

	/**
	 * Success message (always shown as INFO level)
	 */
	success(message, ...args) {
		if (this.config.shouldLog(this.namespace, LOG_LEVELS.INFO)) {
			const formatted = this.format(LOG_LEVELS.INFO, message, ...args)

			// In browser context, formatted[1] and formatted[2] are style strings
			// In Node.js/SSR/Worker context, formatted[0] is the message and formatted[1+] are args
			if (typeof window !== 'undefined') {
				// Browser context: modify style strings
				formatted[1] = formatted[1].replace('INFO', '✓ SUCCESS')
				formatted[2] = `${COLORS.SUCCESS}; font-weight: bold`
			} else {
				// Node.js/SSR/Worker context: modify the message string
				formatted[0] = formatted[0].replace('INFO', '✓ SUCCESS')
			}

			console.log(...formatted)
		}
	}

	/**
	 * Group related logs
	 */
	group(label) {
		if (this.config.shouldLog(this.namespace, LOG_LEVELS.DEBUG)) {
			console.group(`[${this.namespace}] ${label}`)
		}
	}

	groupEnd() {
		if (this.config.shouldLog(this.namespace, LOG_LEVELS.DEBUG)) {
			console.groupEnd()
		}
	}

	/**
	 * Table output
	 */
	table(data, columns) {
		if (this.config.shouldLog(this.namespace, LOG_LEVELS.DEBUG)) {
			console.table(data, columns)
		}
	}

	/**
	 * Performance timing
	 */
	time(label) {
		if (this.config.shouldLog(this.namespace, LOG_LEVELS.DEBUG)) {
			this.timers.set(label, performance.now())
		}
	}

	timeEnd(label) {
		if (this.config.shouldLog(this.namespace, LOG_LEVELS.DEBUG)) {
			const startTime = this.timers.get(label)
			if (startTime !== undefined) {
				const duration = performance.now() - startTime
				this.debug(`⏱️  ${label}: ${duration.toFixed(2)}ms`)
				this.timers.delete(label)
			}
		}
	}

	/**
	 * Log with custom color/style
	 */
	custom(level, color, message, ...args) {
		if (this.config.shouldLog(this.namespace, level)) {
			const formatted = this.format(level, message, ...args)
			formatted[2] = `color: ${color}; font-weight: bold`
			console.log(...formatted)
		}
	}
}

/**
 * Global Logger Manager
 */
class LoggerManager {
	constructor() {
		this.config = new LoggerConfig()
		this.loggers = new Map()
	}

	/**
	 * Create or get a namespaced logger
	 */
	create(namespace) {
		if (!this.loggers.has(namespace)) {
			this.loggers.set(namespace, new Logger(namespace, this.config))
		}
		return this.loggers.get(namespace)
	}

	/**
	 * Set global log level
	 */
	setLevel(level) {
		this.config.setLevel(level)
	}

	/**
	 * Enable/disable logging globally
	 */
	setEnabled(enabled) {
		this.config.setEnabled(enabled)
	}

	/**
	 * Enable specific namespace
	 */
	enableNamespace(namespace) {
		this.config.enableNamespace(namespace)
	}

	/**
	 * Disable specific namespace
	 */
	disableNamespace(namespace) {
		this.config.disableNamespace(namespace)
	}

	/**
	 * Get current config
	 */
	getConfig() {
		return {
			enabled: this.config.enabled,
			level: Object.keys(LOG_LEVELS)[this.config.currentLevel],
			isDev: this.config.isDev,
			enabledNamespaces: Array.from(this.config.enabledNamespaces),
			disabledNamespaces: Array.from(this.config.disabledNamespaces),
		}
	}

	/**
	 * Show help in console
	 */
	help() {
		console.log(`
%c🔍 POS Logging System Help

%cControl logging globally:%c
  logger.setLevel('DEBUG')    - Set log level (DEBUG, INFO, WARN, ERROR, NONE)
  logger.setEnabled(true)     - Enable/disable all logging
  logger.getConfig()          - View current configuration

%cControl specific modules:%c
  logger.enableNamespace('ItemSearch')   - Only log from ItemSearch
  logger.disableNamespace('Worker')      - Disable Worker logs

%cExamples:%c
  // Create module logger
  const log = logger.create('MyModule')

  // Log at different levels
  log.debug('Detailed info', { data })
  log.info('General info')
  log.warn('Warning message')
  log.error('Error occurred', error)
  log.success('Operation successful!')

  // Performance timing
  log.time('operation')
  // ... do work ...
  log.timeEnd('operation')  // Logs: ⏱️  operation: 42.35ms

  // Group logs
  log.group('Processing items')
  log.info('Item 1')
  log.info('Item 2')
  log.groupEnd()

%cPersistence:%c
  Settings are saved to localStorage and persist across sessions.

%cCurrent Config:%c
  ${JSON.stringify(this.getConfig(), null, 2)}
		`,
		'font-size: 16px; font-weight: bold',
		'font-weight: bold; color: #2196F3',
		'font-weight: normal',
		'font-weight: bold; color: #4CAF50',
		'font-weight: normal',
		'font-weight: bold; color: #FF9800',
		'font-weight: normal',
		'font-weight: bold; color: #9C27B0',
		'font-weight: normal',
		'font-weight: bold; color: #607D8B',
		'font-weight: normal'
		)
	}
}

// Create singleton instance
export const logger = new LoggerManager()

// Export log levels for external use
export { LOG_LEVELS }

// Expose to window for console debugging
if (typeof window !== 'undefined') {
	window.posLogger = logger
}

// Log initialization (only in dev)
if (logger.config.isDev) {
	const initLog = logger.create('Logger')
	initLog.info('Logger initialized', logger.getConfig())
	initLog.debug('Type posLogger.help() in console for usage guide')
}
