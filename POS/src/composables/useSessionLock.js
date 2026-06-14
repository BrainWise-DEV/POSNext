import { ref, readonly } from "vue"
import { call } from "@/utils/apiWrapper"
import { userData } from "@/data/user"
import { usePOSCartStore } from "@/stores/posCart"
import { offlineState } from "@/utils/offline/offlineState"

// Throttle: ignore activity events within 1 second of last reset
const THROTTLE_MS = 1000
// Defer lock retry when submission in progress
const DEFER_MS = 30 * 1000

// Configurable settings (module-level, set via configure())
let lockEnabled = true
let lockTimeoutMs = 5 * 60 * 1000

// ---------------------------------------------------------------------------
// localStorage persistence (survives browser close, unlike sessionStorage)
// ---------------------------------------------------------------------------
const STORAGE_KEY = "pos_session_lock"

function restoreLockState() {
	try {
		const saved = localStorage.getItem(STORAGE_KEY)
		if (saved) {
			const data = JSON.parse(saved)
			if (data?.locked && lockEnabled) {
				return { locked: true, user: data.user || null }
			}
		}
	} catch {
		localStorage.removeItem(STORAGE_KEY)
	}
	return { locked: false, user: null }
}

function persistLock(user) {
	try {
		localStorage.setItem(STORAGE_KEY, JSON.stringify({ user, locked: true }))
	} catch {
		// Storage full or unavailable — lock still works in-memory
	}
}

function clearPersistedLock() {
	try {
		localStorage.removeItem(STORAGE_KEY)
	} catch {
		// Ignore
	}
}

// ---------------------------------------------------------------------------
// Cached password hash (offline unlock fallback)
// ---------------------------------------------------------------------------
const PASSWORD_HASH_KEY = "pos_session_pwd_hash"
const ATTEMPT_KEY = "pos_lock_attempts"
const PBKDF2_ITERATIONS = 100_000
const HASH_TTL_MS = 24 * 60 * 60 * 1000 // 24 hours
const MAX_OFFLINE_ATTEMPTS = 5
const LOCKOUT_MS = 60 * 1000 // 1 minute lockout after max attempts

function bytesToHex(bytes) {
	return Array.from(bytes)
		.map((b) => b.toString(16).padStart(2, "0"))
		.join("")
}

function hexToBytes(hex) {
	const bytes = new Uint8Array(hex.length / 2)
	for (let i = 0; i < hex.length; i += 2) {
		bytes[i / 2] = parseInt(hex.substring(i, i + 2), 16)
	}
	return bytes
}

async function hashPassword(password, existingSalt = null) {
	const encoder = new TextEncoder()
	const salt = existingSalt
		? hexToBytes(existingSalt)
		: crypto.getRandomValues(new Uint8Array(16))

	const keyMaterial = await crypto.subtle.importKey(
		"raw",
		encoder.encode(password),
		"PBKDF2",
		false,
		["deriveBits"]
	)

	const bits = await crypto.subtle.deriveBits(
		{
			name: "PBKDF2",
			salt,
			iterations: PBKDF2_ITERATIONS,
			hash: "SHA-256",
		},
		keyMaterial,
		256
	)

	return { hash: bytesToHex(new Uint8Array(bits)), salt: bytesToHex(salt) }
}

function getCurrentUserId() {
	return userData.userId || window.frappe?.session?.user || null
}

function cachePasswordHash(user, hash, salt) {
	try {
		localStorage.setItem(
			PASSWORD_HASH_KEY,
			JSON.stringify({ user, hash, salt, ts: Date.now() })
		)
	} catch {
		// Storage full or unavailable
	}
}

function getCachedPasswordHash() {
	try {
		const raw = localStorage.getItem(PASSWORD_HASH_KEY)
		if (!raw) return null

		const data = JSON.parse(raw)

		// Reject if data is malformed
		if (!data?.hash || !data?.salt || !data?.user || !data?.ts) {
			localStorage.removeItem(PASSWORD_HASH_KEY)
			return null
		}

		// Reject if we can't identify the current user (can't verify ownership)
		const currentUser = getCurrentUserId()
		if (!currentUser) {
			return null
		}

		// Reject if hash belongs to a different user
		if (data.user !== currentUser) {
			localStorage.removeItem(PASSWORD_HASH_KEY)
			return null
		}

		// Reject if expired
		if (Date.now() - data.ts > HASH_TTL_MS) {
			localStorage.removeItem(PASSWORD_HASH_KEY)
			return null
		}

		return { hash: data.hash, salt: data.salt }
	} catch {
		localStorage.removeItem(PASSWORD_HASH_KEY)
		return null
	}
}

function clearCachedPasswordHash() {
	try {
		localStorage.removeItem(PASSWORD_HASH_KEY)
	} catch {
		// Ignore
	}
}

async function cachePasswordHashFromLogin(password) {
	const user = getCurrentUserId()
	const { hash, salt } = await hashPassword(password)
	cachePasswordHash(user, hash, salt)
}

// ---------------------------------------------------------------------------
// Offline brute-force protection
// ---------------------------------------------------------------------------
function checkOfflineAttemptLimit() {
	try {
		const raw = localStorage.getItem(ATTEMPT_KEY)
		if (!raw) return { allowed: true }

		const data = JSON.parse(raw)
		if (data.count >= MAX_OFFLINE_ATTEMPTS) {
			// Escalating lockout: doubles each time the limit is hit again
			// level 1 = 60s, level 2 = 120s, level 3 = 240s, capped at 15 min
			const level = data.level || 1
			const lockoutDuration = Math.min(LOCKOUT_MS * Math.pow(2, level - 1), 15 * 60 * 1000)
			const elapsed = Date.now() - data.lastAttempt
			if (elapsed < lockoutDuration) {
				const remaining = Math.ceil((lockoutDuration - elapsed) / 1000)
				return { allowed: false, remaining }
			}
			// Lockout expired — reset count but escalate level for next lockout
			data.count = 0
			data.level = level + 1
			localStorage.setItem(ATTEMPT_KEY, JSON.stringify(data))
			return { allowed: true }
		}
		return { allowed: true }
	} catch {
		return { allowed: true }
	}
}

function recordFailedAttempt() {
	try {
		const raw = localStorage.getItem(ATTEMPT_KEY)
		const data = raw ? JSON.parse(raw) : { count: 0, level: 1 }
		data.count += 1
		data.lastAttempt = Date.now()
		localStorage.setItem(ATTEMPT_KEY, JSON.stringify(data))
	} catch {
		// Ignore
	}
}

function clearAttemptCounter() {
	try {
		localStorage.removeItem(ATTEMPT_KEY)
	} catch {
		// Ignore
	}
}

// Module-level singleton state (same pattern as useToast.js)
const restored = restoreLockState()
const isLocked = ref(restored.locked)
const isVerifying = ref(false)
const verifyError = ref("")
const lockedUser = ref(restored.user)

let inactivityTimer = null
let lastActivityTime = 0
let listenersAttached = false

const ACTIVITY_EVENTS = ["mousedown", "mousemove", "keydown", "touchstart", "scroll", "click"]

function getUserInfo() {
	return {
		name: userData.getDisplayName(),
		image: userData.getImageUrl(),
		initials: userData.getInitials(),
	}
}

function resetTimer() {
	if (!lockEnabled) return

	const now = Date.now()
	if (now - lastActivityTime < THROTTLE_MS) return
	lastActivityTime = now

	if (inactivityTimer) {
		clearTimeout(inactivityTimer)
	}
	inactivityTimer = setTimeout(tryLock, lockTimeoutMs)
}

function tryLock() {
	const cartStore = usePOSCartStore()
	if (cartStore.isSubmitting) {
		// Defer lock — invoice submission in progress
		inactivityTimer = setTimeout(tryLock, DEFER_MS)
		return
	}
	lock()
}

function lock() {
	if (isLocked.value) return

	isLocked.value = true
	lockedUser.value = getUserInfo()

	persistLock(lockedUser.value)

	if (inactivityTimer) {
		clearTimeout(inactivityTimer)
		inactivityTimer = null
	}
}

function handleVisibilityChange() {
	if (!lockEnabled) return
	if (document.hidden) {
		// Lock immediately when tab loses focus
		lock()
	}
}

function unlockSuccess() {
	isLocked.value = false
	lockedUser.value = null
	isVerifying.value = false
	clearPersistedLock()
	// Restart inactivity tracking
	lastActivityTime = Date.now()
	resetTimer()
}

async function verifyOfflinePassword(password) {
	// Brute-force protection
	const limit = checkOfflineAttemptLimit()
	if (!limit.allowed) {
		return {
			success: false,
			error: __("Too many attempts. Try again in {0} seconds.", [limit.remaining]),
		}
	}

	const cached = getCachedPasswordHash()
	if (!cached) {
		return { success: false, error: __("Cannot verify password offline. No cached credentials available.") }
	}

	const { hash: enteredHash } = await hashPassword(password, cached.salt)
	if (enteredHash === cached.hash) {
		clearAttemptCounter()
		return { success: true }
	}

	recordFailedAttempt()
	return { success: false, error: __("Incorrect password") }
}

async function unlock(password) {
	isVerifying.value = true
	verifyError.value = ""

	// Brute-force gate — applies to both online and offline paths
	const limit = checkOfflineAttemptLimit()
	if (!limit.allowed) {
		isVerifying.value = false
		verifyError.value = __("Too many attempts. Try again in {0} seconds.", [limit.remaining])
		return { success: false }
	}

	// Offline fallback — verify against cached hash
	if (offlineState.isOffline) {
		const result = await verifyOfflinePassword(password)
		if (result.success) {
			unlockSuccess()
			return { success: true }
		}
		isVerifying.value = false
		verifyError.value = result.error
		return { success: false }
	}

	// Online — verify against server
	try {
		const res = await call("pos_next.api.auth.verify_session_password", { password })
		const data = res?.message || res

		if (data?.verified) {
			clearAttemptCounter()
			unlockSuccess()

			// Cache hash for offline use — fire-and-forget so UI unblocks immediately
			const user = getCurrentUserId()
			hashPassword(password).then(({ hash, salt }) => {
				cachePasswordHash(user, hash, salt)
			})

			return { success: true }
		}

		// Wrong password — backend returns { verified: false, message: "..." }
		recordFailedAttempt()
		isVerifying.value = false
		verifyError.value = data?.message || __("Incorrect password")
		return { success: false }
	} catch (error) {
		const httpStatus = error?.status

		// Session expired — 401 or 403 from Frappe's session middleware
		if (httpStatus === 401 || httpStatus === 403) {
			isVerifying.value = false
			return { sessionExpired: true }
		}

		// Network error — fall back to cached hash
		const result = await verifyOfflinePassword(password)
		if (result.success) {
			unlockSuccess()
			return { success: true }
		}
		if (result.error) {
			isVerifying.value = false
			verifyError.value = result.error
			return { success: false }
		}

		isVerifying.value = false
		verifyError.value = __("Could not verify password. Please try again.")
		return { success: false }
	}
}

function clearLock() {
	isLocked.value = false
	lockedUser.value = null
	verifyError.value = ""
	clearPersistedLock()
	clearCachedPasswordHash()
	clearAttemptCounter()
}

function handlePageHide() {
	if (!lockEnabled) return
	// Persist lock state on browser close / navigate away so the session
	// starts locked on reload even if it wasn't locked at the moment of closing
	if (!isLocked.value) {
		persistLock(getUserInfo())
	}
}

function startActivityTracking() {
	if (!lockEnabled) return
	if (listenersAttached) return

	for (const event of ACTIVITY_EVENTS) {
		document.addEventListener(event, resetTimer, { passive: true, capture: true })
	}
	document.addEventListener("visibilitychange", handleVisibilityChange)
	window.addEventListener("pagehide", handlePageHide)

	listenersAttached = true
	lastActivityTime = Date.now()
	resetTimer()
}

function stopActivityTracking() {
	if (!listenersAttached) return

	for (const event of ACTIVITY_EVENTS) {
		document.removeEventListener(event, resetTimer, { capture: true })
	}
	document.removeEventListener("visibilitychange", handleVisibilityChange)
	window.removeEventListener("pagehide", handlePageHide)

	if (inactivityTimer) {
		clearTimeout(inactivityTimer)
		inactivityTimer = null
	}

	listenersAttached = false
}

/**
 * Configure the session lock behavior.
 * @param {Object} options
 * @param {boolean} options.enabled - Whether session lock is enabled
 * @param {number} options.timeoutMinutes - Inactivity timeout in minutes
 */
function configure({ enabled, timeoutMinutes }) {
	lockEnabled = Boolean(enabled)
	lockTimeoutMs = (Number.parseInt(timeoutMinutes) || 5) * 60 * 1000

	if (!lockEnabled) {
		// Disable: stop tracking, clear any active lock
		stopActivityTracking()
		if (isLocked.value) {
			isLocked.value = false
			lockedUser.value = null
			verifyError.value = ""
		}
		clearPersistedLock()
	} else if (listenersAttached) {
		// Already tracking — restart timer with new timeout
		if (inactivityTimer) {
			clearTimeout(inactivityTimer)
		}
		lastActivityTime = Date.now()
		inactivityTimer = setTimeout(tryLock, lockTimeoutMs)
	}
}

export function useSessionLock() {
	return {
		isLocked: readonly(isLocked),
		isVerifying: readonly(isVerifying),
		verifyError: readonly(verifyError),
		lockedUser: readonly(lockedUser),
		lock,
		unlock,
		clearLock,
		configure,
		startActivityTracking,
		stopActivityTracking,
		cachePasswordHashFromLogin,
	}
}
