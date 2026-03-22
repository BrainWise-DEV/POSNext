/**
 * Stub for common_site_config.json which doesn't exist in Electron mode.
 * The socket.js file imports socketio_port from this file.
 * In Electron, we don't use Socket.IO to connect to a Frappe server.
 */
export const socketio_port = 0
