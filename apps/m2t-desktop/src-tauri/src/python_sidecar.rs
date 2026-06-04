use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

const API_PORT: u16 = 8765;
const API_BASE_URL: &str = "http://127.0.0.1:8765";
const HEALTH_URL: &str = "http://127.0.0.1:8765/api/health";
const STARTUP_TIMEOUT: Duration = Duration::from_secs(60);
const POLL_INTERVAL: Duration = Duration::from_millis(500);

struct PythonSidecarInner {
    child: Option<Child>,
}

pub struct PythonSidecarState(Arc<Mutex<PythonSidecarInner>>);

pub fn new_python_sidecar_state() -> PythonSidecarState {
    PythonSidecarState(Arc::new(Mutex::new(PythonSidecarInner { child: None })))
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

    let project_root = resolve_project_root()?;
    let python = resolve_python_executable(&project_root)?;
    let mut cmd = Command::new(&python);
    cmd.args(["-m", "media2text", "serve", "--port", &API_PORT.to_string(), "--host", "127.0.0.1"])
        .current_dir(&project_root)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

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
    if let Some(mut child) = guard.child.take() {
        let _ = child.kill();
        let _ = child.wait();
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

fn wait_for_health() -> Result<(), String> {
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .map_err(|e| e.to_string())?;

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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn find_project_root_from_manifest_dir() {
        let start = Path::new(env!("CARGO_MANIFEST_DIR"));
        let root = find_project_root(start).expect("repo root");
        assert!(root.join("pyproject.toml").is_file());
        assert!(root.join("src/media2text").is_dir());
    }
}
