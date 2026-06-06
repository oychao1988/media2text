mod python_sidecar;

use tauri::{Manager, RunEvent};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(python_sidecar::new_python_sidecar_state())
        .setup(|app| {
            let state = app.state::<python_sidecar::PythonSidecarState>();
            python_sidecar::start_python_sidecar(&state)?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![python_sidecar::get_api_base_url])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if let RunEvent::Exit = event {
                if let Some(state) = app_handle.try_state::<python_sidecar::PythonSidecarState>() {
                    let _ = python_sidecar::stop_python_sidecar(&state);
                }
            }
        });
}
