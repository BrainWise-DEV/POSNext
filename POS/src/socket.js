import { io } from "socket.io-client"
import { runtimeConfig } from "./utils/runtimeConfig"

let socket = null

function noopSocket() {
	return {
		on: () => {},
		off: () => {},
		emit: () => {},
		connect: () => {},
		disconnect: () => {},
	}
}

function readSocketioPort() {
	// __SOCKETIO_PORT__ is injected at build time by vite.config.js. In web
	// builds it reads sites/common_site_config.json; in desktop builds it
	// defaults to 9000 (we don't use the socket there anyway).
	if (typeof __SOCKETIO_PORT__ !== "undefined" && __SOCKETIO_PORT__) {
		return __SOCKETIO_PORT__
	}
	return 9000
}

export function initSocket(siteNameOverride) {
	// Desktop builds skip realtime entirely — no cookie auth across origins,
	// and the existing realtime composables already tolerate a no-op socket.
	if (!runtimeConfig.hasRealtime) {
		if (!socket) {
			socket = noopSocket()
		}
		return socket
	}

	if (socket) {
		console.log("Socket already initialized")
		return socket
	}

	try {
		const siteName =
			siteNameOverride ||
			window.site_name ||
			(window.frappe && window.frappe.boot && window.frappe.boot.sitename) ||
			window.location.hostname

		const socketioPort = readSocketioPort()
		const host = window.location.hostname
		const port = window.location.port ? `:${socketioPort}` : ""
		const protocol = port ? "http" : "https"
		const url = `${protocol}://${host}${port}/${siteName}`

		console.log("Initializing socket (lazy connection):", url)

		socket = io(url, {
			withCredentials: true,
			reconnectionAttempts: 3,
			autoConnect: false,
		})

		socket.on("connect_error", (error) => {
			console.warn("Socket connection error:", error.message)
		})

		socket.on("connect", () => {
			console.log("Socket connected successfully")
		})

		return socket
	} catch (error) {
		console.error("Failed to initialize socket:", error)
		return noopSocket()
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
