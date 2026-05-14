// Copyright (c) 2026 Ubion ax center
//
// Python supervisor — child FastAPI backend spawn / port management.
//
// Two operating modes:
//
//   1) dev — when the binary is run via `cargo tauri dev`, there's no
//      bundled $RESOURCE directory. We fall back to the system `python`
//      (or whatever `UBION_PYTHON` env var points at) running against
//      the repo's engine/ source. cwd = parent of src-tauri/.
//
//   2) production — when the binary runs from an installed location, we
//      resolve `python/python.exe` and `engine/` out of the resource
//      directory that the Tauri bundler copied next to the executable.
//      PYTHONHOME / PYTHONPATH are pinned so the embedded interpreter
//      cannot accidentally pick up the user's system Python.
//
// Why we do not use `tauri_plugin_shell::Command::sidecar` for the
// embedded interpreter: sidecar is for *single binaries* with a target
// triple suffix. python-build-standalone ships as a directory tree
// (python.exe + DLLs + Lib/...), so we use `bundle.resources` and spawn
// via `std::process::Command` directly.

use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdout, Command, Stdio};
use std::sync::mpsc::{self, Receiver};
use std::thread;
use std::time::Duration;

use tauri::path::BaseDirectory;
use tauri::{AppHandle, Manager};

/// Outcome of a successful spawn: the OS child + the port we should
/// point the webview at.
pub struct SpawnedBackend {
    pub child: Child,
    pub port: u16,
}

/// Check if a previously-spawned child has exited (idle shutdown).
/// Returns the exit status if the process is gone, `None` if it's
/// still running. Non-blocking — used by the main-thread watchdog
/// in main.rs.
pub fn child_exited(child: &mut Child) -> Option<std::process::ExitStatus> {
    match child.try_wait() {
        Ok(Some(status)) => Some(status),
        _ => None,
    }
}

/// Default fallback port when the child fails to announce one within
/// the handshake window. Matches the value `engine.server` falls back
/// to when `UBION_PORT` is unset, so dev-mode (where the developer may
/// have launched the server manually on 9000) still works.
const FALLBACK_PORT: u16 = 9000;

/// Maximum time we wait for the child to print `PORT:<n>`. uvicorn
/// startup on cold Python typically lands in 1–2 s; the embedded
/// interpreter is slower (~3 s in our PoC measurements).
const HANDSHAKE_TIMEOUT: Duration = Duration::from_secs(15);

/// Spawn the Python backend. Returns `None` if spawning was skipped or
/// failed — the caller may then rely on an externally-managed server
/// (developer running `python -m engine.server` in another terminal).
///
/// Env overrides:
///   * `UBION_SKIP_BACKEND_SPAWN=1` — don't spawn at all
///   * `UBION_PYTHON=<path>`        — force a specific interpreter
///                                    (useful for testing prod path locally
///                                    or pointing at a dev venv in dev)
pub fn spawn_python_backend(app: &AppHandle) -> Option<SpawnedBackend> {
    if std::env::var("UBION_SKIP_BACKEND_SPAWN").as_deref() == Ok("1") {
        log::info!("UBION_SKIP_BACKEND_SPAWN=1 — skipping Python spawn");
        return None;
    }

    // Resolve the layout we should use.
    let layout = resolve_layout(app);
    log::info!(
        "python backend layout = {} (python={}, cwd={}, pythonhome={:?})",
        layout.mode,
        layout.python.display(),
        layout.cwd.display(),
        layout.python_home,
    );

    let mut cmd = Command::new(&layout.python);
    cmd.args(["-m", "engine.server"]);
    cmd.current_dir(&layout.cwd);

    // PYTHONUTF8=1 — Windows console codepage is cp949 by default which
    // mangles Korean. The embedded interpreter is also ASCII-default
    // unless we ask for UTF-8 explicitly.
    cmd.env("PYTHONUTF8", "1");
    cmd.env("PYTHONIOENCODING", "utf-8");
    // Ask Python to pick a free port and announce it on stdout.
    cmd.env("UBION_PORT", "0");

    if let Some(home) = layout.python_home.as_ref() {
        cmd.env("PYTHONHOME", home);
        let lib = home.join("Lib");
        let site = lib.join("site-packages");
        let mut pp = std::env::join_paths(
            [layout.cwd.as_path(), site.as_path(), lib.as_path()]
                .into_iter()
                .filter(|p| p.exists()),
        )
        .ok();
        if let Some(joined) = pp.take() {
            cmd.env("PYTHONPATH", &joined);
        }
        cmd.env("PYTHONNOUSERSITE", "1");
    }

    // We need stdout piped to read the PORT handshake. stderr stays
    // inherited so uvicorn's startup log surfaces in the Tauri console.
    cmd.stdout(Stdio::piped());
    cmd.stderr(Stdio::inherit());
    cmd.stdin(Stdio::null());

    let mut child = match cmd.spawn() {
        Ok(c) => c,
        Err(err) => {
            log::warn!(
                "python backend spawn failed: {} ({})",
                layout.python.display(),
                err
            );
            return None;
        }
    };
    log::info!(
        "spawned python backend ({}): pid={}",
        layout.python.display(),
        child.id()
    );

    let stdout = match child.stdout.take() {
        Some(s) => s,
        None => {
            log::warn!("child stdout pipe missing — cannot complete handshake");
            return Some(SpawnedBackend {
                child,
                port: FALLBACK_PORT,
            });
        }
    };

    // Read the handshake on a worker thread so we can apply a timeout
    // without blocking the Tauri setup callback indefinitely. The same
    // thread keeps draining stdout afterwards so the pipe never fills.
    let port = read_port_handshake(stdout);

    Some(SpawnedBackend { child, port })
}

/// Block (up to HANDSHAKE_TIMEOUT) for the child's first stdout line.
/// Returns the parsed port, or FALLBACK_PORT if anything went wrong —
/// the user-facing behavior is the same as the PoC's fixed 9000.
fn read_port_handshake(stdout: ChildStdout) -> u16 {
    let (tx, rx): (mpsc::Sender<Option<u16>>, Receiver<Option<u16>>) = mpsc::channel();
    thread::spawn(move || {
        let mut reader = BufReader::new(stdout);
        let mut first = String::new();
        let parsed = match reader.read_line(&mut first) {
            Ok(0) => None, // EOF before any output
            Ok(_) => parse_port_line(first.trim()),
            Err(err) => {
                log::warn!("failed to read child stdout: {}", err);
                None
            }
        };
        let _ = tx.send(parsed);
        // Drain the rest so uvicorn's logs surface and the pipe never
        // backs up (which would otherwise deadlock the child once its
        // pipe buffer fills).
        let mut line = String::new();
        while reader.read_line(&mut line).map(|n| n > 0).unwrap_or(false) {
            print!("{}", line);
            line.clear();
        }
    });

    match rx.recv_timeout(HANDSHAKE_TIMEOUT) {
        Ok(Some(port)) => {
            log::info!("python backend announced port {}", port);
            port
        }
        Ok(None) => {
            log::warn!(
                "python backend produced no PORT line — falling back to {}",
                FALLBACK_PORT
            );
            FALLBACK_PORT
        }
        Err(_) => {
            log::warn!(
                "python backend handshake timed out after {:?} — falling back to {}",
                HANDSHAKE_TIMEOUT,
                FALLBACK_PORT
            );
            FALLBACK_PORT
        }
    }
}

fn parse_port_line(line: &str) -> Option<u16> {
    line.strip_prefix("PORT:")
        .and_then(|rest| rest.trim().parse::<u16>().ok())
}

/// Resolved paths the spawn command needs. Computed once per spawn —
/// we never cache because the embedded resource location depends on the
/// AppHandle the caller passes.
struct Layout {
    mode: &'static str,
    /// Path to the interpreter executable.
    python: PathBuf,
    /// Working directory the child is launched from. In dev this is the
    /// repo root; in prod it's the directory that contains the bundled
    /// `engine/` and `python/` resource trees.
    cwd: PathBuf,
    /// PYTHONHOME (the prefix of the embedded interpreter), or None
    /// when relying on the developer's system Python.
    python_home: Option<PathBuf>,
}

fn resolve_layout(app: &AppHandle) -> Layout {
    // 1. Explicit override wins (lets us flip into "prod-like" mode for
    //    local testing without doing a full bundle).
    if let Ok(explicit) = std::env::var("UBION_PYTHON") {
        let p = PathBuf::from(&explicit);
        let cwd = repo_root_dev().unwrap_or_else(|| PathBuf::from("."));
        return Layout {
            mode: "override",
            python: p,
            cwd,
            python_home: None,
        };
    }

    // 2. Try the bundled embedded interpreter via Tauri's resource
    //    resolver. This succeeds whenever the binary runs from an
    //    installed location with resources/ next to it.
    if let Some(layout) = try_embedded(app) {
        return layout;
    }

    // 3. Dev fallback — use the system python against the source tree.
    let cwd = repo_root_dev().unwrap_or_else(|| PathBuf::from("."));
    let python = if cfg!(windows) { "python" } else { "python3" };
    Layout {
        mode: "dev-system",
        python: PathBuf::from(python),
        cwd,
        python_home: None,
    }
}

fn try_embedded(app: &AppHandle) -> Option<Layout> {
    let resolver = app.path();
    let python = resolver
        .resolve(
            if cfg!(windows) {
                "python/python.exe"
            } else {
                "python/bin/python3"
            },
            BaseDirectory::Resource,
        )
        .ok()?;
    if !python.exists() {
        return None;
    }
    let python_home = python.parent().map(Path::to_path_buf);
    // engine/ sits alongside python/ in the resource directory.
    let resource_root = python
        .parent()
        .and_then(Path::parent)
        .map(Path::to_path_buf)?;
    Some(Layout {
        mode: "embedded",
        python,
        cwd: resource_root,
        python_home,
    })
}

/// In dev (`cargo tauri dev`) cargo invokes us with cwd = src-tauri/,
/// so the project root is one level up.
fn repo_root_dev() -> Option<PathBuf> {
    std::env::current_dir()
        .ok()
        .and_then(|d| d.parent().map(Path::to_path_buf))
}
