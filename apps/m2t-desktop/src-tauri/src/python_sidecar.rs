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
const DESKTOP_APP_SUPPORT_ID: &str = "dev.media2text.desktop";
const RUNTIME_BUNDLE_REVISION: &str = "2";

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
            try_kill_all_media2text_serve(None);
            thread::sleep(Duration::from_millis(500));
        } else if existing_api_compatible(&client) {
            guard.reused_external = true;
            return Ok(());
        } else {
            eprintln!(
                "[python-sidecar] API on :{API_PORT} is stale (missing runtime, config secrets, or history APIs); restarting sidecar"
            );
            try_kill_all_media2text_serve(None);
            thread::sleep(Duration::from_millis(500));
        }
    }

    guard.reused_external = false;

    if !cfg!(debug_assertions) {
        warn_if_running_from_dmg_mount();
    }
    // Orphan sidecars (e.g. previous Desktop session) may hold monitor lock without the port.
    try_kill_all_media2text_serve(None);
    thread::sleep(Duration::from_millis(300));
    let runtime_root = resolve_runtime_root()?;
    let python = resolve_python_executable(&runtime_root)?;
    let desktop_layout = prepare_desktop_layout(&runtime_root)?;

    let mut cmd = Command::new(&python);
    cmd.args(["-m", "media2text", "serve", "--port", &API_PORT.to_string(), "--host", "127.0.0.1"])
        .current_dir(&runtime_root)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    apply_playwright_env(&mut cmd);
    cmd.env("M2T_DESKTOP_MANAGED", "1");
    cmd.env("M2T_PROJECT_ROOT", &runtime_root);
    cmd.env("MEDIA2TEXT_CONFIG", &desktop_layout.config_path);
    if let Some(dotenv) = desktop_layout.dotenv_path {
        cmd.env("M2T_DOTENV_PATH", dotenv);
    }

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
        try_kill_all_media2text_serve(None);
    }
    guard.reused_external = false;
    // Orphan cleanup when the shell was spawned by us but exit did not reap it (e.g. force quit).
    if cfg!(debug_assertions) && had_spawned_child {
        try_kill_all_media2text_serve(None);
    }
    Ok(())
}

struct DesktopLayout {
    config_path: PathBuf,
    dotenv_path: Option<PathBuf>,
}

fn prepare_desktop_layout(runtime_root: &Path) -> Result<DesktopLayout, String> {
    if cfg!(debug_assertions) {
        let config_path = std::env::var("MEDIA2TEXT_CONFIG")
            .map(PathBuf::from)
            .unwrap_or_else(|_| runtime_root.join("config.yaml"));
        let dotenv_path = std::env::var("M2T_DOTENV_PATH")
            .ok()
            .map(PathBuf::from)
            .or_else(|| {
                let root_dotenv = runtime_root.join(".env");
                root_dotenv.is_file().then_some(root_dotenv)
            });
        return Ok(DesktopLayout {
            config_path,
            dotenv_path,
        });
    }

    let support = desktop_app_support_dir()?;
    std::fs::create_dir_all(&support)
        .map_err(|e| format!("create app support dir {}: {e}", support.display()))?;
    let data_dir = support.join("data");
    std::fs::create_dir_all(&data_dir)
        .map_err(|e| format!("create data dir {}: {e}", data_dir.display()))?;

    let config_path = support.join("config.yaml");
    if !config_path.is_file() {
        seed_desktop_config(runtime_root, &config_path, &data_dir)?;
        eprintln!(
            "[python-sidecar] seeded config at {} (workspace={})",
            config_path.display(),
            data_dir.display()
        );
    }

    let dotenv_path = support.join(".env");
    Ok(DesktopLayout {
        config_path,
        dotenv_path: dotenv_path.is_file().then_some(dotenv_path),
    })
}

fn seed_desktop_config(runtime_root: &Path, config_path: &Path, data_dir: &Path) -> Result<(), String> {
    let template = runtime_root.join("config.example.yaml");
    let content = std::fs::read_to_string(&template).map_err(|e| {
        format!(
            "read bundled config template {}: {e}",
            template.display()
        )
    })?;
    let workspace_line = format!("workspace: {}", data_dir.display());
    let mut seeded = content.replace("workspace: ./data", &workspace_line);
    let bundled_ffmpeg = runtime_root.join("bin/ffmpeg.bin");
    if bundled_ffmpeg.is_file() {
        let ffmpeg_line = format!(
            "ffmpeg_path: {}",
            runtime_root.join("bin/ffmpeg").display()
        );
        seeded = seeded.replace("ffmpeg_path: ffmpeg", &ffmpeg_line);
    }
    std::fs::write(config_path, seeded).map_err(|e| {
        format!(
            "write desktop config {}: {e}",
            config_path.display()
        )
    })
}

fn desktop_app_support_dir() -> Result<PathBuf, String> {
    #[cfg(target_os = "macos")]
    {
        let home = std::env::var("HOME")
            .map_err(|_| "HOME is not set; cannot locate Application Support".to_string())?;
        return Ok(PathBuf::from(home)
            .join("Library/Application Support")
            .join(DESKTOP_APP_SUPPORT_ID));
    }
    #[cfg(not(target_os = "macos"))]
    {
        let base = std::env::var("XDG_DATA_HOME")
            .map(PathBuf::from)
            .or_else(|_| {
                std::env::var("HOME")
                    .ok()
                    .map(|home| PathBuf::from(home).join(".local/share"))
            })
            .ok_or_else(|| "cannot locate desktop app data directory".to_string())?;
        Ok(base.join(DESKTOP_APP_SUPPORT_ID))
    }
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

fn try_kill_all_media2text_serve(except_pid: Option<u32>) {
    #[cfg(unix)]
    {
        let Ok(output) = Command::new("pgrep")
            .args(["-f", "media2text.*serve"])
            .output()
        else {
            try_kill_media2text_serve_on_port(API_PORT);
            return;
        };
        if output.status.success() {
            let pids = String::from_utf8_lossy(&output.stdout);
            for pid_text in pids.split_whitespace() {
                let Ok(pid) = pid_text.parse::<i32>() else {
                    continue;
                };
                if except_pid.is_some_and(|keep| keep as i32 == pid) {
                    continue;
                }
                if !commandline_is_media2text_serve(pid) {
                    continue;
                }
                let _ = Command::new("kill").arg(pid.to_string()).status();
            }
            thread::sleep(Duration::from_millis(400));
        }
        try_kill_media2text_serve_on_port(API_PORT);
    }
}

fn commandline_is_media2text_serve(pid: i32) -> bool {
    let Ok(ps_out) = Command::new("ps")
        .args(["-p", &pid.to_string(), "-o", "command="])
        .output()
    else {
        return false;
    };
    let cmdline = String::from_utf8_lossy(&ps_out.stdout).to_lowercase();
    cmdline.contains("media2text") && cmdline.contains("serve")
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

fn resolve_runtime_root() -> Result<PathBuf, String> {
    if let Ok(root) = std::env::var("M2T_PROJECT_ROOT") {
        let path = PathBuf::from(&root);
        if path.join("pyproject.toml").is_file() {
            return Ok(path);
        }
        return Err(format!(
            "M2T_PROJECT_ROOT does not contain pyproject.toml: {}",
            path.display()
        ));
    }

    if let Some(bundled) = resolve_bundled_runtime_root() {
        if cfg!(debug_assertions) {
            return Ok(bundled);
        }
        return materialize_writable_runtime(&bundled);
    }

    find_project_root(Path::new(env!("CARGO_MANIFEST_DIR"))).ok_or_else(|| {
        "could not locate media2text runtime (bundle missing m2t-runtime; rebuild DMG or set M2T_PROJECT_ROOT)".into()
    })
}

fn warn_if_running_from_dmg_mount() {
    let Ok(exe) = std::env::current_exe() else {
        return;
    };
    if exe.to_string_lossy().contains("/Volumes/") {
        eprintln!(
            "[python-sidecar] 检测到从 DMG 卷启动；运行环境将复制到 Application Support。建议安装后拖到「应用程序」文件夹。"
        );
    }
}

fn materialize_writable_runtime(bundled: &Path) -> Result<PathBuf, String> {
    let support = desktop_app_support_dir()?;
    let target = support.join("runtime/m2t-runtime");
    let marker = support.join("runtime/.bundle-version");
    let version = format!("{}:{}", env!("CARGO_PKG_VERSION"), RUNTIME_BUNDLE_REVISION);
    let version_ref = version.as_str();

    let needs_sync = !target.join(".venv/bin/python").is_file()
        || read_runtime_version(&marker).as_deref() != Some(version_ref);

    if needs_sync {
        eprintln!(
            "[python-sidecar] syncing bundled runtime to {} …",
            target.display()
        );
        std::fs::create_dir_all(support.join("runtime"))
            .map_err(|e| format!("create runtime dir under {}: {e}", support.display()))?;
        if target.exists() {
            std::fs::remove_dir_all(&target)
                .map_err(|e| format!("remove stale runtime {}: {e}", target.display()))?;
        }
        copy_dir_recursive(bundled, &target)?;
        relocate_copied_venv(bundled, &target)?;
        write_runtime_version(&marker, version_ref)?;
        eprintln!("[python-sidecar] runtime sync complete");
    }

    Ok(target)
}

fn read_runtime_version(marker: &Path) -> Option<String> {
    std::fs::read_to_string(marker).ok().map(|s| s.trim().to_string())
}

fn write_runtime_version(marker: &Path, version: &str) -> Result<(), String> {
    std::fs::write(marker, version).map_err(|e| format!("write runtime version {}: {e}", marker.display()))
}

fn copy_dir_recursive(src: &Path, dst: &Path) -> Result<(), String> {
    std::fs::create_dir_all(dst).map_err(|e| format!("create dir {}: {e}", dst.display()))?;
    for entry in std::fs::read_dir(src).map_err(|e| format!("read dir {}: {e}", src.display()))? {
        let entry = entry.map_err(|e| e.to_string())?;
        let src_path = entry.path();
        let dst_path = dst.join(entry.file_name());
        let file_type = entry.file_type().map_err(|e| e.to_string())?;
        if file_type.is_dir() {
            copy_dir_recursive(&src_path, &dst_path)?;
        } else if file_type.is_file() {
            if let Some(parent) = dst_path.parent() {
                std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
            }
            std::fs::copy(&src_path, &dst_path).map_err(|e| {
                format!(
                    "copy {} -> {}: {e}",
                    src_path.display(),
                    dst_path.display()
                )
            })?;
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                if entry.file_name() == "ffmpeg.bin" {
                    let unpacked = dst_path.with_file_name("ffmpeg");
                    let _ = std::fs::copy(&dst_path, &unpacked);
                    #[cfg(unix)]
                    {
                        use std::os::unix::fs::PermissionsExt;
                        if let Ok(meta) = std::fs::metadata(&unpacked) {
                            let mut perms = meta.permissions();
                            perms.set_mode(0o755);
                            let _ = std::fs::set_permissions(&unpacked, perms);
                        }
                    }
                } else if entry.file_name() == "ffmpeg"
                    || entry.file_name() == "python"
                    || entry.file_name() == "python3"
                {
                    if let Ok(meta) = std::fs::metadata(&dst_path) {
                        let mut perms = meta.permissions();
                        perms.set_mode(0o755);
                        let _ = std::fs::set_permissions(&dst_path, perms);
                    }
                }
            }
        }
    }
    Ok(())
}

fn relocate_copied_venv(bundled: &Path, target: &Path) -> Result<(), String> {
    let replacements = venv_path_replacements(bundled, target);
    if replacements.is_empty() {
        return Ok(());
    }
    let venv = target.join(".venv");
    let cfg = venv.join("pyvenv.cfg");
    if cfg.is_file() {
        rewrite_path_prefixes(&cfg, &replacements)?;
    }
    let site = venv.join("lib/python3.12/site-packages");
    if site.is_dir() {
        for entry in std::fs::read_dir(&site).map_err(|e| e.to_string())? {
            let entry = entry.map_err(|e| e.to_string())?;
            let path = entry.path();
            if path.extension().and_then(|s| s.to_str()) == Some("pth") {
                rewrite_path_prefixes(&path, &replacements)?;
            }
        }
    }
    let bin = venv.join("bin");
    if bin.is_dir() {
        for entry in std::fs::read_dir(&bin).map_err(|e| e.to_string())? {
            let entry = entry.map_err(|e| e.to_string())?;
            let path = entry.path();
            if entry.file_type().map_err(|e| e.to_string())?.is_file() {
                rewrite_path_prefixes(&path, &replacements)?;
            }
        }
    }
    Ok(())
}

fn venv_path_replacements(bundled: &Path, target: &Path) -> Vec<(String, String)> {
    let mut pairs = vec![
        (bundled.to_string_lossy().into_owned(), target.to_string_lossy().into_owned()),
        (
            bundled.join(".venv").to_string_lossy().into_owned(),
            target.join(".venv").to_string_lossy().into_owned(),
        ),
    ];
    if let Some(resources) = bundled.parent() {
        if resources.ends_with("Resources") {
            let contents = resources.parent().unwrap_or(resources);
            let app_bundle = contents.parent().unwrap_or(contents);
            pairs.push((
                app_bundle.to_string_lossy().into_owned(),
                target.parent()
                    .and_then(|p| p.parent())
                    .map(|p| p.to_string_lossy().into_owned())
                    .unwrap_or_else(|| target.to_string_lossy().into_owned()),
            ));
        }
    }
    pairs.sort_by(|a, b| b.0.len().cmp(&a.0.len()));
    pairs
}

fn rewrite_path_prefixes(path: &Path, replacements: &[(String, String)]) -> Result<(), String> {
    let bytes = std::fs::read(path).map_err(|e| format!("read {}: {e}", path.display()))?;
    let Ok(original) = std::str::from_utf8(&bytes) else {
        // venv bin/ also contains Mach-O python executables; skip binaries.
        return Ok(());
    };
    let mut updated = original.to_string();
    for (from, to) in replacements {
        if from != to {
            updated = updated.replace(from, to);
        }
    }
    if updated != original {
        std::fs::write(path, updated.as_bytes())
            .map_err(|e| format!("write {}: {e}", path.display()))?;
    }
    Ok(())
}

fn resolve_bundled_runtime_root() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    resolve_bundled_runtime_from_exe(&exe)
}

fn resolve_bundled_runtime_from_exe(exe: &Path) -> Option<PathBuf> {
    #[cfg(target_os = "macos")]
    {
        let contents = exe.parent()?.parent()?;
        let runtime = contents.join("Resources/m2t-runtime");
        if runtime.join("pyproject.toml").is_file() {
            return Some(runtime);
        }
    }
    #[cfg(not(target_os = "macos"))]
    {
        let resource = exe.parent()?.join("resources/m2t-runtime");
        if resource.join("pyproject.toml").is_file() {
            return Some(resource);
        }
    }
    None
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
    use std::fs;
    use tempfile::TempDir;

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

    #[test]
    fn seed_desktop_config_rewrites_workspace() {
        let runtime = TempDir::new().expect("runtime tempdir");
        fs::write(
            runtime.path().join("config.example.yaml"),
            "workspace: ./data\nnotify:\n  enabled: false\n",
        )
        .expect("write template");
        let config = runtime.path().join("config.yaml");
        let data = runtime.path().join("data");
        seed_desktop_config(runtime.path(), &config, &data).expect("seed config");
        let content = fs::read_to_string(&config).expect("read config");
        assert!(content.contains(&format!("workspace: {}", data.display())));
        assert!(!content.contains("workspace: ./data"));
    }

    #[test]
    fn rewrite_path_prefixes_skips_binary_files() {
        let dir = TempDir::new().expect("tempdir");
        let binary = dir.path().join("python3");
        fs::write(&binary, [0xCFu8, 0xFA, 0xED, 0xFE, 0x07, 0x00, 0x00, 0x01]).expect("write binary");
        rewrite_path_prefixes(&binary, &[("/old".into(), "/new".into())]).expect("skip binary");
        let script = dir.path().join("media2text");
        fs::write(&script, "#!/old/.venv/bin/python\n").expect("write script");
        rewrite_path_prefixes(&script, &[("/old".into(), "/new".into())]).expect("rewrite script");
        let rewritten = fs::read_to_string(&script).expect("read script");
        assert!(rewritten.contains("/new/.venv/bin/python"));
    }

    #[test]
    #[cfg(target_os = "macos")]
    fn resolve_bundled_runtime_from_macos_layout() {
        let bundle = TempDir::new().expect("bundle tempdir");
        let contents = bundle.path().join("Contents");
        let macos = contents.join("MacOS");
        let resources = contents.join("Resources/m2t-runtime");
        fs::create_dir_all(&macos).expect("macos dir");
        fs::create_dir_all(&resources).expect("resources dir");
        fs::write(resources.join("pyproject.toml"), "[project]\nname = \"media2text\"\n").expect("pyproject");
        let exe = macos.join("lingxi");
        fs::write(&exe, "").expect("fake exe");

        let resolved = resolve_bundled_runtime_from_exe(&exe).expect("bundled runtime");
        assert_eq!(resolved, resources);
    }
}
