const { app, BrowserWindow, ipcMain, dialog } = require("electron")
const path = require("node:path")
const { startServer, stopServer } = require("./server/index")
const { getDatabase, closeDatabase } = require("./server/db/connection")
const { runMigrations } = require("./server/db/migrations")

const isDev = process.env.NODE_ENV === "development"
const SERVER_PORT = 18420 // Local Express server port

let mainWindow = null

function createWindow() {
	mainWindow = new BrowserWindow({
		width: 1280,
		height: 800,
		minWidth: 1024,
		minHeight: 600,
		title: "POSNext",
		icon: path.join(__dirname, "../resources/icon.png"),
		webPreferences: {
			preload: path.join(__dirname, "preload.js"),
			contextIsolation: true,
			nodeIntegration: false,
			sandbox: false,
		},
		show: false,
	})

	mainWindow.once("ready-to-show", () => {
		mainWindow.maximize()
		mainWindow.show()
	})

	// Load the Vue frontend
	if (isDev) {
		// In dev mode, load from the Vite dev server or built files
		mainWindow.loadURL(`http://localhost:${SERVER_PORT}/index.html`)
		mainWindow.webContents.openDevTools()
	} else {
		mainWindow.loadFile(path.join(__dirname, "../renderer/index.html"))
	}

	mainWindow.on("closed", () => {
		mainWindow = null
	})
}

// ============================================================================
// IPC Handlers
// ============================================================================

function setupIPC() {
	// Printer: list available printers
	ipcMain.handle("get-printers", () => {
		if (!mainWindow) return []
		return mainWindow.webContents.getPrintersAsync()
	})

	// Printer: print receipt HTML
	ipcMain.handle("print-receipt", async (_event, html, printerName, options = {}) => {
		const printWindow = new BrowserWindow({
			show: false,
			webPreferences: { contextIsolation: true, nodeIntegration: false },
		})

		await printWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`)

		return new Promise((resolve, reject) => {
			printWindow.webContents.print(
				{
					silent: true,
					printBackground: true,
					deviceName: printerName || "",
					...options,
				},
				(success, failureReason) => {
					printWindow.close()
					if (success) resolve({ success: true })
					else reject(new Error(failureReason))
				},
			)
		})
	})

	// Sync: get connection status
	ipcMain.handle("get-sync-status", () => {
		const { getSyncStatus } = require("./server/sync/engine")
		return getSyncStatus()
	})

	// Sync: trigger manual sync
	ipcMain.handle("trigger-sync", async () => {
		const { triggerSync } = require("./server/sync/engine")
		return triggerSync()
	})

	// App: get server port
	ipcMain.handle("get-server-port", () => SERVER_PORT)

	// App: get app version
	ipcMain.handle("get-app-version", () => app.getVersion())

	// Dialog: show message box
	ipcMain.handle("show-message-box", (_event, options) => {
		return dialog.showMessageBox(mainWindow, options)
	})
}

// ============================================================================
// Application Lifecycle
// ============================================================================

app.whenReady().then(async () => {
	try {
		// 1. Initialize database and run migrations
		console.log("[Main] Initializing database...")
		const db = getDatabase()
		runMigrations(db)
		console.log("[Main] Database ready")

		// 2. Start the local Express API server
		console.log(`[Main] Starting API server on port ${SERVER_PORT}...`)
		await startServer(SERVER_PORT)
		console.log(`[Main] API server running at http://localhost:${SERVER_PORT}`)

		// 3. Set up IPC handlers
		setupIPC()

		// 4. Create the main window
		createWindow()
	} catch (error) {
		console.error("[Main] Failed to start:", error)
		dialog.showErrorBox("POSNext - Startup Error", error.message)
		app.quit()
	}

	app.on("activate", () => {
		if (BrowserWindow.getAllWindows().length === 0) {
			createWindow()
		}
	})
})

app.on("window-all-closed", () => {
	if (process.platform !== "darwin") {
		app.quit()
	}
})

app.on("before-quit", () => {
	console.log("[Main] Shutting down...")
	stopServer()
	closeDatabase()
})

// Handle uncaught exceptions
process.on("uncaughtException", (error) => {
	console.error("[Main] Uncaught exception:", error)
})

process.on("unhandledRejection", (reason) => {
	console.error("[Main] Unhandled rejection:", reason)
})
