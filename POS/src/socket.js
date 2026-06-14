import { io } from "socket.io-client"
import { socketio_port } from "../../../../sites/common_site_config.json"

let socket = null

export function initSocket(siteNameOverride) {
	// Don't reinitialize if socket already exists
	if (socket) {
		console.log("Socket already initialized")
		return socket
	}

	try {
		// Try to get site name from various sources, prioritizing override
		const siteName =
			siteNameOverride ||
			window.site_name ||
			(window.frappe && window.frappe.boot && window.frappe.boot.sitename) ||
			window.location.hostname

		const host = window.location.hostname
		const port = window.location.port ? `:${socketio_port}` : ""
		const protocol = port ? "http" : "https"
		const url = `${protocol}://${host}${port}/${siteName}`

		console.log("Initializing socket (lazy connection):", url)

		socket = io(url, {
			withCredentials: true,
			reconnectionAttempts: 3,
			autoConnect: false, // Lazy connect - only connect when explicitly needed
		})

		// Connect with error handling
		socket.on("connect_error", (error) => {
			console.warn("Socket connection error:", error.message)
		})

		socket.on("connect", () => {
			console.log("Socket connected successfully")
		})

		// Don't auto-connect - let components connect when they need realtime features
		// Components can call socket.connect() when they need realtime functionality

		return socket
	} catch (error) {
		console.error("Failed to initialize socket:", error)
		// Return a mock socket object to prevent crashes
		return {
			on: () => { },
			emit: () => { },
			connect: () => { },
			disconnect: () => { },
		}
	}
}

export function disconnectSocket() {
	if (socket) {
		socket.disconnect()
		socket = null
		console.log("Socket disconnected and cleared")
	}
}

export function useSocket() {
	return socket
}
