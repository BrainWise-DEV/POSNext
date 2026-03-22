const { contextBridge, ipcRenderer } = require("electron")

/**
 * Secure bridge between renderer (Vue app) and main process.
 * Exposes only specific IPC channels to the frontend.
 */
contextBridge.exposeInMainWorld("electronAPI", {
	// Printing
	getPrinters: () => ipcRenderer.invoke("get-printers"),
	printReceipt: (html, printerName, options) =>
		ipcRenderer.invoke("print-receipt", html, printerName, options),

	// Sync
	getSyncStatus: () => ipcRenderer.invoke("get-sync-status"),
	triggerSync: () => ipcRenderer.invoke("trigger-sync"),

	// App info
	getServerPort: () => ipcRenderer.invoke("get-server-port"),
	getAppVersion: () => ipcRenderer.invoke("get-app-version"),

	// Dialogs
	showMessageBox: (options) => ipcRenderer.invoke("show-message-box", options),

	// Platform detection
	isElectron: true,
	platform: process.platform,
})
