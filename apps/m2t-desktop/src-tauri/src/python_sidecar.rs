use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

const API_PORT: u16 = 8765;
const API_BASE_URL: &str = "http://127.0.0.1:8765";
const HEALTH_URL: &str = "http://127.0.0.1:8765/api/health";
const CONFIG_URL: &str = "http://127.0.0.1:8765/api/config";
const RUNTIME_URL: &str = "http://127.0.0.1:8765/api/runtime";
const STARTUP_TIMEOUT: Duration = Duration::from_secs(60);
const POLL_INTERVAL: Duration = Duration::from_millis(500);

struct PythonSidecarInner {
    child: Option<Child>,
    reused_external: bool,
}

pub struct PythonSidecarState(Arc<Mutex<PythonSidecarInner>>);

pub fn new_python_sidecar_state() -> PythonSidecarState {
    PythonSidecarState(Arc::new(Mutex::new(PythonSidecarInner {
        child: None,
        reused_external: false,
    })))
}

#[tauri::command]
pub fn get_api_base_url() -> String {
    API_BASE_URL.to_string()
}

pub fn start_python_sidecar(state: &PythonSidecarState) -> Result<(), String> {
    let mut guard = state.0.lock().map_err(|e| e.to_string())?;
    reap_dead_child(&mut guard);

    if guard.child.is_some() {
        return wait_for_health();
    }

    // Reuse manual `media2text serve` only when it exposes desktop config secrets.
    // Single probe — do not use wait_for_health() here (empty port would idle 60s).
    let client = blocking_http_client()?;
    let force_restart = cfg!(debug_assertions);
    if health_ready_now(&client)? {
        if force_restart {
            eprintln!(
                "[python-sidecar] dev mode: restarting existing API on :{API_PORT} to pick up code changes"
            );
            try_kill_media2text_serve_on_port(API_PORT);
            thread::sleep(Duration::from_millis(500));
        } else if existing_api_compatible(&client) {
            guard.reused_external = true;
            return Ok(());
        } else {
            eprintln!(
                "[python-sidecar] API on :{API_PORT} is stale (missing runtime, config secrets, or history APIs); restarting sidecar"
            );
            try_kill_media2text_serve_on_port(API_PORT);
            thread::sleep(Duration::from_millis(500));
        }
    }

    guard.reused_external = false;

    let project_root = resolve_project_root()?;
    let python = resolve_python_executable(&project_root)?;
    let mut cmd = Command::new(&python);
    cmd.args(["-m", "media2text", "serve", "--port", &API_PORT.to_string(), "--host", "127.0.0.1"])
        .current_dir(&project_root)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    apply_playwright_env(&mut cmd);
    cmd.env("M2T_DESKTOP_MANAGED", "1");

    let mut child = cmd
        .spawn()
        .map_err(|e| format!("spawn python sidecar ({python:?}): {e}"))?;

    if let Some(stderr) = child.stderr.take() {
        thread::spawn(move || {
            let reader = BufReader::new(stderr);
            for line in reader.lines().flatten() {
                eprintln!("[python-sidecar stderr] {line}");
            }
        });
    }

    if let Some(stdout) = child.stdout.take() {
        thread::spawn(move || {
            let reader = BufReader::new(stdout);
            for line in reader.lines().flatten() {
                eprintln!("[python-sidecar stdout] {line}");
            }
        });
    }

    guard.child = Some(child);
    drop(guard);

    wait_for_health()
}

pub fn stop_python_sidecar(state: &PythonSidecarState) -> Result<(), String> {
    let mut guard = state.0.lock().map_err(|e| e.to_string())?;
    let had_spawned_child = guard.child.is_some();
    if let Some(mut child) = guard.child.take() {
        let _ = child.kill();
        let _ = child.wait();
    } else if guard.reused_external {
        try_kill_media2text_serve_on_port(API_PORT);
    }
    guard.reused_external = false;
    // Orphan cleanup when the shell was spawned by us but exit did not reap it (e.g. force quit).
    if cfg!(debug_assertions) && had_spawned_child {
        try_kill_media2text_serve_on_port(API_PORT);
    }
    Ok(())
}

fn reap_dead_child(inner: &mut PythonSidecarInner) {
    if let Some(child) = inner.child.as_mut() {
        match child.try_wait() {
            Ok(Some(_)) => inner.child = None,
            Ok(None) => {}
            Err(_) => inner.child = None,
        }
    }
}

fn blocking_http_client() -> Result<reqwest::blocking::Client, String> {
    reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .map_err(|e| e.to_string())
}

fn health_ready_now(client: &reqwest::blocking::Client) -> Result<bool, String> {
    Ok(match client.get(HEALTH_URL).send() {
        Ok(resp) if resp.status().is_success() => true,
        _ => false,
    })
}

fn config_response_compatible(body: &serde_json::Value) -> bool {
    match body
        .get("config")
        .and_then(|c| c.get("llmProviders"))
        .and_then(|p| p.as_array())
    {
        None => true,
        Some(arr) if arr.is_empty() => true,
        Some(arr) => arr
            .first()
            .and_then(|prov| prov.get("api_key"))
            .is_some(),
    }
}

fn runtime_api_available(client: &reqwest::blocking::Client) -> bool {
    matches!(client.get(RUNTIME_URL).send(), Ok(resp) if resp.status().is_success())
}

fn health_api_feature(client: &reqwest::blocking::Client, key: &str) -> bool {
    match client.get(HEALTH_URL).send() {
        Ok(resp) if resp.status().is_success() => resp
            .json::<serde_json::Value>()
            .ok()
            .and_then(|body| {
                body.get("api_features")
                    .and_then(|f| f.get(key))
                    .and_then(|v| v.as_bool())
            })
            .unwrap_or(false),
        _ => false,
    }
}

fn existing_api_compatible(client: &reqwest::blocking::Client) -> bool {
    if !runtime_api_available(client) {
        return false;
    }
    if !health_api_feature(client, "history_summarize")
        || !health_api_feature(client, "history_retry_download")
    {
        return false;
    }
    match client.get(CONFIG_URL).send() {
        Ok(resp) if resp.status().is_success() => resp
            .json::<serde_json::Value>()
            .ok()
            .is_some_and(|body| config_response_compatible(&body)),
        _ => false,
    }
}

fn try_kill_media2text_serve_on_port(port: u16) {
    #[cfg(unix)]
    {
        let Ok(output) = Command::new("lsof")
            .args(["-ti", &format!("tcp:{port}")])
            .output()
        else {
            return;
        };
        let pids = String::from_utf8_lossy(&output.stdout);
        for pid_text in pids.split_whitespace() {
            let Ok(pid) = pid_text.parse::<i32>() else {
                continue;
            };
            let Ok(ps_out) = Command::new("ps")
                .args(["-p", &pid.to_string(), "-o", "command="])
                .output()
            else {
                continue;
            };
            let cmdline = String::from_utf8_lossy(&ps_out.stdout);
            if cmdline.contains("media2text") && cmdline.contains("serve") {
                let _ = Command::new("kill").arg(pid.to_string()).status();
            }
        }
    }
}

fn wait_for_health() -> Result<(), String> {
    let client = blocking_http_client()?;

    let deadline = Instant::now() + STARTUP_TIMEOUT;
    let mut last_error = String::from("sidecar not ready");

    while Instant::now() < deadline {
        match client.get(HEALTH_URL).send() {
            Ok(resp) if resp.status().is_success() => return Ok(()),
            Ok(resp) => last_error = format!("health returned HTTP {}", resp.status()),
            Err(err) => last_error = format!("health poll failed: {err}"),
        }
        thread::sleep(POLL_INTERVAL);
    }

    Err(format!(
        "Python API did not become healthy within {}s ({last_error})",
        STARTUP_TIMEOUT.as_secs()
    ))
}

fn resolve_project_root() -> Result<PathBuf, String> {
    if let Ok(root) = std::env::var("M2T_PROJECT_ROOT") {
        let path = PathBuf::from(root);
        if path.join("pyproject.toml").is_file() {
            return Ok(path);
        }
        return Err(format!(
            "M2T_PROJECT_ROOT does not contain pyproject.toml: {}",
            path.display()
        ));
    }

    find_project_root(Path::new(env!("CARGO_MANIFEST_DIR")))
        .ok_or_else(|| {
            "could not locate media2text project root (set M2T_PROJECT_ROOT or run from repo checkout)".into()
        })
}

fn find_project_root(start: &Path) -> Option<PathBuf> {
    let mut dir = start.to_path_buf();
    loop {
        if dir.join("pyproject.toml").is_file() {
            return Some(dir);
        }
        if !dir.pop() {
            return None;
        }
    }
}

fn resolve_python_executable(project_root: &Path) -> Result<PathBuf, String> {
    if let Ok(path) = std::env::var("M2T_PYTHON") {
        let candidate = PathBuf::from(path);
        if candidate.is_file() {
            return Ok(candidate);
        }
        return Err(format!("M2T_PYTHON is not a file: {}", candidate.display()));
    }

    #[cfg(windows)]
    let venv_candidates = [
        project_root.join(".venv/Scripts/python.exe"),
        project_root.join(".venv/Scripts/python"),
    ];
    #[cfg(not(windows))]
    let venv_candidates = [project_root.join(".venv/bin/python3"), project_root.join(".venv/bin/python")];

    for candidate in venv_candidates {
        if candidate.is_file() {
            return Ok(candidate);
        }
    }

    for fallback in ["python3", "python"] {
        if let Ok(path) = which::which(fallback) {
            return Ok(path);
        }
    }

    Err(format!(
        "no Python executable found (expected {} or M2T_PYTHON)",
        project_root.join(".venv/bin/python").display()
    ))
}

fn playwright_path_untrusted(path: &str) -> bool {
    let lowered = path.to_lowercase();
    lowered.contains("cursor-sandbox-cache") || lowered.contains("/tmp/cursor-")
}

fn default_playwright_browsers_path() -> Option<PathBuf> {
    let home = std::env::var("HOME")
        .ok()
        .or_else(|| std::env::var("USERPROFILE").ok())?;
    #[cfg(target_os = "macos")]
    {
        return Some(PathBuf::from(home).join("Library/Caches/ms-playwright"));
    }
    #[cfg(target_os = "windows")]
    {
        return std::env::var("LOCALAPPDATA")
            .ok()
            .map(|local| PathBuf::from(local).join("ms-playwright"))
            .or_else(|| Some(PathBuf::from(home).join("AppData/Local/ms-playwright")));
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        if let Ok(xdg) = std::env::var("XDG_CACHE_HOME") {
            return Some(PathBuf::from(xdg).join("ms-playwright"));
        }
        return Some(PathBuf::from(home).join(".cache/ms-playwright"));
    }
}

fn apply_playwright_env(cmd: &mut Command) {
    let current = std::env::var("PLAYWRIGHT_BROWSERS_PATH").unwrap_or_default();
    if !current.is_empty() && !playwright_path_untrusted(&current) {
        return;
    }
    if let Some(path) = default_playwright_browsers_path() {
        cmd.env("PLAYWRIGHT_BROWSERS_PATH", path);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn config_response_compatible_accepts_missing_or_empty_providers() {
        assert!(config_response_compatible(&json!({})));
        assert!(config_response_compatible(&json!({"config": {}})));
        assert!(config_response_compatible(&json!({"config": {"llmProviders": []}})));
    }

    #[test]
    fn config_response_compatible_requires_api_key_field_on_first_provider() {
        assert!(config_response_compatible(&json!({
            "config": {"llmProviders": [{"name": "nvidia", "api_key": null}]}
        })));
        assert!(!config_response_compatible(&json!({
            "config": {"llmProviders": [{"name": "nvidia"}]}
        })));
    }

    #[test]
    fn find_project_root_from_manifest_dir() {
        let start = Path::new(env!("CARGO_MANIFEST_DIR"));
        let root = find_project_root(start).expect("repo root");
        assert!(root.join("pyproject.toml").is_file());
        assert!(root.join("src/media2text").is_dir());
    }
}
