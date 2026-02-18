import { ref, readonly } from "vue"
import { call } from "@/utils/apiWrapper"
import { userData } from "@/data/user"
import { usePOSCartStore } from "@/stores/posCart"

// Lock timeout: 5 minutes
const LOCK_TIMEOUT_MS = 5 * 60 * 1000
// Throttle: ignore activity events within 1 second of last reset
const THROTTLE_MS = 1000
// Defer lock retry when submission in progress
const DEFER_MS = 30 * 1000

const STORAGE_KEY = "pos_session_lock"

// Restore lock state from sessionStorage (survives page reload, scoped to tab)
function restoreLockState() {
	try {
		const saved = sessionStorage.getItem(STORAGE_KEY)
		if (saved) {
			const data = JSON.parse(saved)
			return { locked: true, user: data.user || null }
		}
	} catch {
		// Corrupted data — clear it
		sessionStorage.removeItem(STORAGE_KEY)
	}
	return { locked: false, user: null }
}

function persistLock(user) {
	try {
		sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ user }))
	} catch {
		// Storage full or unavailable — lock still works in-memory
	}
}

function clearPersistedLock() {
	try {
		sessionStorage.removeItem(STORAGE_KEY)
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
let wasHiddenWhileUnlocked = false
let listenersAttached = false

const ACTIVITY_EVENTS = ["mousedown", "mousemove", "keydown", "touchstart", "scroll", "click"]

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
	lockedUser.value = {
		name: userData.getDisplayName(),
		image: userData.getImageUrl(),
		initials: userData.getInitials(),
	}

	persistLock(lockedUser.value)

	if (inactivityTimer) {
		clearTimeout(inactivityTimer)
		inactivityTimer = null
	}
}

function handleVisibilityChange() {
	if (document.hidden) {
		if (!isLocked.value) {
			wasHiddenWhileUnlocked = true
		}
	} else {
		if (wasHiddenWhileUnlocked && !isLocked.value) {
			lock()
		}
		wasHiddenWhileUnlocked = false
	}
}

async function unlock(password) {
	isVerifying.value = true
	verifyError.value = ""

	try {
		await call("pos_next.api.auth.verify_session_password", { password })
		isLocked.value = false
		lockedUser.value = null
		isVerifying.value = false
		clearPersistedLock()
		// Restart inactivity tracking
		lastActivityTime = Date.now()
		resetTimer()
		return { success: true }
	} catch (error) {
		isVerifying.value = false

		const status = error?.httpStatus || error?.status || error?.exc_type
		if (status === 401 || status === 403 || error?.exc_type === "AuthenticationError") {
			// Check if it's a session expiry (not just wrong password)
			if (status === 401 || status === 403) {
				return { sessionExpired: true }
			}
			verifyError.value = __("Incorrect password")
			return { success: false }
		}

		// Network or other error
		verifyError.value = __("Could not verify password. Please try again.")
		return { success: false }
	}
}

function startActivityTracking() {
	if (listenersAttached) return

	for (const event of ACTIVITY_EVENTS) {
		document.addEventListener(event, resetTimer, { passive: true, capture: true })
	}
	document.addEventListener("visibilitychange", handleVisibilityChange)

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

	if (inactivityTimer) {
		clearTimeout(inactivityTimer)
		inactivityTimer = null
	}

	listenersAttached = false
	wasHiddenWhileUnlocked = false
}

export function useSessionLock() {
	return {
		isLocked: readonly(isLocked),
		isVerifying: readonly(isVerifying),
		verifyError: readonly(verifyError),
		lockedUser: readonly(lockedUser),
		lock,
		unlock,
		startActivityTracking,
		stopActivityTracking,
	}
}
