mod agent_sidecar;
mod python_sidecar;

use tauri::{Manager, RunEvent};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(python_sidecar::new_python_sidecar_state())
        .manage(agent_sidecar::new_agent_sidecar_state())
        .setup(|app| {
            let state = app.state::<python_sidecar::PythonSidecarState>();
            python_sidecar::start_python_sidecar(&state)?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            python_sidecar::get_api_base_url,
            agent_sidecar::resolve_agent_sidecar_script,
            agent_sidecar::start_agent_sidecar,
            agent_sidecar::restart_agent_sidecar,
            agent_sidecar::stop_agent_sidecar,
            agent_sidecar::send_agent_user_message,
            agent_sidecar::send_agent_context_refresh,
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if let RunEvent::Exit = event {
                if let Some(state) = app_handle.try_state::<python_sidecar::PythonSidecarState>() {
                    let _ = python_sidecar::stop_python_sidecar(&state);
                }
                if let Some(state) = app_handle.try_state::<agent_sidecar::AgentSidecarState>() {
                    let _ = agent_sidecar::stop_agent_sidecar(state);
                }
            }
        });
}
