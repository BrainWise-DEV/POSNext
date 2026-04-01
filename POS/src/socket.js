import { io } from "socket.io-client"
import { socketio_port } from "../../../../sites/common_site_config.json"

let socket = null

export function initSocket() {
	if (socket) return socket

	try {
		const host = window.location.hostname
		const isLocal =
			host === "localhost" ||
			host === "127.0.0.1" ||
			window.location.protocol === "http:"

		const port = isLocal ? `:${socketio_port}` : ""
		const protocol = isLocal ? "http" : "https"

		// Use root domain only — no sitename suffix
		const url = `${protocol}://${host}${port}`

		socket = io(url, {
			withCredentials: true,
			reconnectionAttempts: 3,
			autoConnect: false,
		})

		socket.on("connect_error", () => {})
		socket.on("connect", () => {})

		return socket
	} catch (error) {
		console.error("Failed to initialize socket:", error)
		return {
			on: () => {},
			emit: () => {},
			connect: () => {},
			disconnect: () => {},
		}
	}
}

export function disconnectSocket() {
	if (socket) {
		socket.disconnect()
		socket = null
	}
}

export function useSocket() {
	return socket
}