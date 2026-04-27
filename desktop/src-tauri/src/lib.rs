use tauri::Manager;

#[tauri::command]
fn get_app_info() -> serde_json::Value {
	serde_json::json!({
		"name": env!("CARGO_PKG_NAME"),
		"version": env!("CARGO_PKG_VERSION"),
	})
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
	tauri::Builder::default()
		.plugin(tauri_plugin_shell::init())
		.plugin(tauri_plugin_dialog::init())
		.plugin(tauri_plugin_process::init())
		.plugin(tauri_plugin_store::Builder::default().build())
		.plugin(tauri_plugin_http::init())
		.plugin(tauri_plugin_updater::Builder::new().build())
		.plugin(
			tauri_plugin_stronghold::Builder::new(|password| {
				use std::hash::{DefaultHasher, Hash, Hasher};
				let mut hasher = DefaultHasher::new();
				password.hash(&mut hasher);
				let key = hasher.finish().to_le_bytes();
				key.repeat(4)[..32].to_vec()
			})
			.build(),
		)
		.invoke_handler(tauri::generate_handler![get_app_info])
		.setup(|app| {
			#[cfg(debug_assertions)]
			{
				let window = app.get_webview_window("main").unwrap();
				window.open_devtools();
			}
			Ok(())
		})
		.run(tauri::generate_context!())
		.expect("error while running tauri application");
}
