// Copyright (c) 2026 Ubion ax center
//
// Tauri 외피 — Phase 3 PC 트레이 앱의 *최소 PoC*.
// PROJECT_SPEC v0.4 §2.7 — Rust 외피 + Python 알맹이.
//
// 책임:
//   1. Python FastAPI 백엔드 spawn (시스템 python)
//   2. 메인 webview 가 :9000 (or UBION_PORT) 가리키게
//   3. 트레이 아이콘 + 메뉴 (열기 / 숨기기 / 종료)
//   4. RunEvent::Exit 에서 Python 자식 정리
//
// 패턴 출처: Tauri 2 공식 문서 (v2.tauri.app)
//   - 트레이: /learn/system-tray, /start/migrate/from-tauri-1
//   - 자식 프로세스 정리: /develop/plugins on_event RunEvent::Exit
//   - state: /develop/state-management (Mutex 직접 manage)

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::sync::Mutex;
use std::thread;
use std::time::Duration;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{Manager, RunEvent, WindowEvent};

mod supervisor;

/// Tracks the Python sidecar across spawn / idle-exit / respawn cycles.
///
/// `child` is `Some` whenever the backend is alive. The supervisor's
/// idle-shutdown self-terminates the process when the user is gone for
/// 30 min; the watchdog thread spawned below notices via `try_wait()`,
/// clears this slot, and the next webview activity (or a periodic
/// re-spawn) brings it back. `port` is updated on each respawn because
/// the OS may hand us a different free port.
#[derive(Default)]
struct PythonBackend {
    child: Option<std::process::Child>,
    port: u16,
}

type PythonState = Mutex<PythonBackend>;

/// Expose the live backend port to the webview. The frontend's API
/// client calls this once on startup and uses the returned port to
/// build `http://127.0.0.1:<port>` for all subsequent requests. The
/// command never fails — a zero return means "backend not ready yet,
/// retry in a moment."
#[tauri::command]
fn get_backend_port(state: tauri::State<'_, PythonState>) -> u16 {
    state.lock().map(|g| g.port).unwrap_or(0)
}

fn main() {
    env_logger::init();

    tauri::Builder::default()
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![get_backend_port])
        .setup(|app| {
            app.manage::<PythonState>(Mutex::new(PythonBackend::default()));

            // 1) Initial spawn. The handshake's port is stored into the
            //    managed state so frontend / webview-load logic can read it.
            let handle = app.handle().clone();
            if let Some(spawned) = supervisor::spawn_python_backend(&handle) {
                let state = app.state::<PythonState>();
                let mut guard = state.lock().unwrap();
                guard.port = spawned.port;
                guard.child = Some(spawned.child);
                log::info!("python backend spawned on port {}", spawned.port);
            } else {
                log::warn!("python backend spawn skipped — relying on external server");
            }

            // 2) Watchdog. Polls every 5 s; when the Python child has
            //    exited (idle-shutdown after 30 min, or crash) we spawn
            //    a fresh one so the next webview interaction is instant.
            let watchdog_handle = app.handle().clone();
            thread::spawn(move || loop {
                thread::sleep(Duration::from_secs(5));
                let state = match watchdog_handle.try_state::<PythonState>() {
                    Some(s) => s,
                    None => continue,
                };
                let mut guard = state.lock().unwrap();
                let need_respawn = match guard.child.as_mut() {
                    Some(child) => supervisor::child_exited(child).is_some(),
                    None => true,
                };
                if !need_respawn {
                    continue;
                }
                // Drop the stale child handle first so the new spawn
                // starts from a clean slot.
                if let Some(mut dead) = guard.child.take() {
                    let _ = dead.wait();
                    log::info!("python backend exited — respawning");
                }
                drop(guard);
                if let Some(spawned) = supervisor::spawn_python_backend(&watchdog_handle) {
                    let mut guard = state.lock().unwrap();
                    guard.port = spawned.port;
                    guard.child = Some(spawned.child);
                    log::info!("python backend respawned on port {}", spawned.port);
                } else {
                    log::warn!("respawn failed — will retry on next watchdog tick");
                }
            });

            // 2) 트레이 아이콘 + 메뉴 (공식 패턴, /learn/system-tray)
            let show_item = MenuItem::with_id(app, "show", "창 열기", true, None::<&str>)?;
            let hide_item = MenuItem::with_id(app, "hide", "창 숨기기", true, None::<&str>)?;
            let quit_item = MenuItem::with_id(app, "quit", "종료", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show_item, &hide_item, &quit_item])?;

            let _tray = TrayIconBuilder::new()
                .tooltip("Ubion 에이전트")
                .menu(&menu)
                .show_menu_on_left_click(true)
                .on_menu_event(|app, event| match event.id().as_ref() {
                    "show" => {
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.show();
                            let _ = w.set_focus();
                        }
                    }
                    "hide" => {
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.hide();
                        }
                    }
                    "quit" => {
                        app.exit(0);
                    }
                    _ => {}
                })
                .build(app)?;

            // 3) X 버튼 = 트레이로 숨기기 (진짜 종료는 메뉴 quit 에서만)
            if let Some(window) = app.get_webview_window("main") {
                let app_handle = app.handle().clone();
                window.on_window_event(move |event| {
                    if let WindowEvent::CloseRequested { api, .. } = event {
                        if let Some(w) = app_handle.get_webview_window("main") {
                            let _ = w.hide();
                        }
                        api.prevent_close();
                    }
                });
            }

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("tauri build failed")
        .run(|app_handle, event| {
            // 공식 패턴: 자식 정리는 RunEvent::Exit (진짜 종료 직전).
            // ExitRequested 는 prevent 가능한 시점이라 부적합.
            if let RunEvent::Exit = event {
                let state = app_handle.state::<PythonState>();
                let taken = state.lock().unwrap().child.take();
                if let Some(mut child) = taken {
                    log::info!("terminating python backend (pid={})", child.id());
                    let _ = child.kill();
                    let _ = child.wait();
                }
            }
        });
}
