import { ref, readonly } from "vue"
import { call } from "@/utils/apiWrapper"
import { userData } from "@/data/user"
import { usePOSCartStore } from "@/stores/posCart"
import { offlineState } from "@/utils/offline/offlineState"

// Lock timeout: 5 minutes
const LOCK_TIMEOUT_MS = 5 * 60 * 1000
// Throttle: ignore activity events within 1 second of last reset
const THROTTLE_MS = 1000
// Defer lock retry when submission in progress
const DEFER_MS = 30 * 1000

// ---------------------------------------------------------------------------
// localStorage persistence (survives browser close, unlike sessionStorage)
// ---------------------------------------------------------------------------
const STORAGE_KEY = "pos_session_lock"

function restoreLockState() {
	try {
		const saved = localStorage.getItem(STORAGE_KEY)
		if (saved) {
			const data = JSON.parse(saved)
			if (data?.locked) {
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

async function hashPassword(password) {
	const encoded = new TextEncoder().encode(password)
	const buffer = await crypto.subtle.digest("SHA-256", encoded)
	return Array.from(new Uint8Array(buffer))
		.map((b) => b.toString(16).padStart(2, "0"))
		.join("")
}

function cachePasswordHash(hash) {
	try {
		localStorage.setItem(PASSWORD_HASH_KEY, hash)
	} catch {
		// Storage full or unavailable
	}
}

function getCachedPasswordHash() {
	try {
		return localStorage.getItem(PASSWORD_HASH_KEY)
	} catch {
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
	const hash = await hashPassword(password)
	cachePasswordHash(hash)
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
	const now = Date.now()
	if (now - lastActivityTime < THROTTLE_MS) return
	lastActivityTime = now

	if (inactivityTimer) {
		clearTimeout(inactivityTimer)
	}
	inactivityTimer = setTimeout(tryLock, LOCK_TIMEOUT_MS)
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
	const cachedHash = getCachedPasswordHash()
	if (!cachedHash) {
		return { success: false, error: __("Cannot verify password offline. No cached credentials available.") }
	}
	const enteredHash = await hashPassword(password)
	if (enteredHash === cachedHash) {
		return { success: true }
	}
	return { success: false, error: __("Incorrect password") }
}

async function unlock(password) {
	isVerifying.value = true
	verifyError.value = ""

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
			// Cache hash on successful online unlock
			const hash = await hashPassword(password)
			cachePasswordHash(hash)

			unlockSuccess()
			return { success: true }
		}

		// Wrong password — backend returns { verified: false, message: "..." }
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
		if (result.error === __("Incorrect password")) {
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
}

function handlePageHide() {
	// Persist lock state on browser close / navigate away so the session
	// starts locked on reload even if it wasn't locked at the moment of closing
	if (!isLocked.value) {
		persistLock(getUserInfo())
	}
}

function startActivityTracking() {
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

export function useSessionLock() {
	return {
		isLocked: readonly(isLocked),
		isVerifying: readonly(isVerifying),
		verifyError: readonly(verifyError),
		lockedUser: readonly(lockedUser),
		lock,
		unlock,
		clearLock,
		startActivityTracking,
		stopActivityTracking,
		cachePasswordHashFromLogin,
	}
}
