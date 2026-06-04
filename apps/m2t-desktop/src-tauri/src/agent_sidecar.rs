use std::io::Write;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};

use tauri::{AppHandle, Emitter, Manager, State};

struct AgentSidecarInner {
    child: Option<Child>,
    generation: u64,
}

pub struct AgentSidecarState(Arc<Mutex<AgentSidecarInner>>);

pub fn new_agent_sidecar_state() -> AgentSidecarState {
    AgentSidecarState(Arc::new(Mutex::new(AgentSidecarInner {
        child: None,
        generation: 0,
    })))
}

#[tauri::command]
pub fn resolve_agent_sidecar_script(app: AppHandle) -> Result<String, String> {
    if let Ok(path) = app.path().resolve(
        "agent/start-sidecar.mjs",
        tauri::path::BaseDirectory::Resource,
    ) {
        if path.is_file() {
            return Ok(path.to_string_lossy().into_owned());
        }
    }

    let dev = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("resources/agent/start-sidecar.mjs");
    if dev.is_file() {
        return Ok(dev.to_string_lossy().into_owned());
    }

    Err("找不到 Agent sidecar 启动脚本 resources/agent/start-sidecar.mjs".into())
}

#[tauri::command]
pub fn start_agent_sidecar(
    app: AppHandle,
    state: State<AgentSidecarState>,
    script_path: String,
    env_vars: serde_json::Value,
) -> Result<(), String> {
    spawn_agent_sidecar(app, state, script_path, env_vars)
}

#[tauri::command]
pub fn restart_agent_sidecar(
    app: AppHandle,
    state: State<AgentSidecarState>,
    script_path: String,
    env_vars: serde_json::Value,
) -> Result<(), String> {
    stop_agent_sidecar(state.clone())?;
    spawn_agent_sidecar(app, state, script_path, env_vars)
}

fn reap_dead_child(inner: &mut AgentSidecarInner) {
    if let Some(child) = inner.child.as_mut() {
        match child.try_wait() {
            Ok(Some(_)) => {
                inner.child = None;
            }
            Ok(None) => {}
            Err(_) => {
                inner.child = None;
            }
        }
    }
}

fn spawn_agent_sidecar(
    app: AppHandle,
    state: State<AgentSidecarState>,
    script_path: String,
    env_vars: serde_json::Value,
) -> Result<(), String> {
    let mut guard = state.0.lock().map_err(|e| e.to_string())?;
    reap_dead_child(&mut guard);

    if guard.child.is_some() {
        return Ok(());
    }

    guard.generation = guard.generation.saturating_add(1);
    let generation = guard.generation;

    let mut cmd = Command::new("node");
    cmd.arg(script_path)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    if let Some(map) = env_vars.as_object() {
        for (key, value) in map {
            if let Some(s) = value.as_str() {
                cmd.env(key, s);
            }
        }
    }

    let mut child = cmd.spawn().map_err(|e| format!("spawn agent sidecar: {e}"))?;
    let stdout = child.stdout.take().ok_or("sidecar stdout unavailable")?;
    let stderr = child.stderr.take();

    let app_handle = app.clone();
    let child_slot = Arc::clone(&state.0);
    std::thread::spawn(move || {
        if let Some(stderr) = stderr {
            use std::io::{BufRead, BufReader};
            let reader = BufReader::new(stderr);
            for line in reader.lines().flatten() {
                eprintln!("[agent-sidecar stderr] {line}");
            }
        }
    });

    std::thread::spawn(move || {
        use std::io::{BufRead, BufReader};
        let reader = BufReader::new(stdout);
        for line in reader.lines().flatten() {
            let _ = app_handle.emit("agent-event", line);
        }
        if let Ok(mut slot) = child_slot.lock() {
            if slot.generation == generation {
                slot.child = None;
            }
        }
        let _ = app_handle.emit("agent-sidecar-exited", ());
    });

    guard.child = Some(child);
    Ok(())
}

#[tauri::command]
pub fn stop_agent_sidecar(state: State<AgentSidecarState>) -> Result<(), String> {
    let mut guard = state.0.lock().map_err(|e| e.to_string())?;
    guard.generation = guard.generation.saturating_add(1);
    if let Some(mut child) = guard.child.take() {
        let _ = child.kill();
    }
    Ok(())
}

fn write_stdin_line(state: State<AgentSidecarState>, msg: serde_json::Value) -> Result<(), String> {
    let mut guard = state.0.lock().map_err(|e| e.to_string())?;
    reap_dead_child(&mut guard);
    let child = guard.child.as_mut().ok_or("Agent sidecar 未启动")?;
    let stdin = child.stdin.as_mut().ok_or("sidecar stdin unavailable")?;
    writeln!(stdin, "{msg}").map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub fn send_agent_user_message(
    state: State<AgentSidecarState>,
    payload: serde_json::Value,
) -> Result<(), String> {
    let msg = serde_json::json!({
        "type": "message.user",
        "payload": payload
    });
    write_stdin_line(state, msg)
}

#[tauri::command]
pub fn send_agent_context_refresh(
    state: State<AgentSidecarState>,
    payload: serde_json::Value,
) -> Result<(), String> {
    let msg = serde_json::json!({
        "type": "context.refresh",
        "payload": payload
    });
    write_stdin_line(state, msg)
}
