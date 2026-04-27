// Test stub for @tauri-apps/plugin-http. Real implementation lives in the
// Tauri shell at runtime; vitest aliases this file so Vite can resolve the
// import without requiring the dependency to be installed.
export const fetch = async () => ({
	ok: true,
	status: 200,
	headers: { get: () => "application/json" },
	json: async () => ({ message: {} }),
	text: async () => "",
})
