use std::net::{Ipv4Addr, SocketAddrV4, TcpStream};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

use tauri::{Manager, RunEvent};

const API_PORT: &str = "18473";

struct BackendProcess(Mutex<Option<Child>>);

fn find_python() -> Option<String> {
    if let Ok(candidate) = std::env::var("CLOUDRA_PYTHON") {
        if !candidate.trim().is_empty() {
            return Some(candidate);
        }
    }

    ["python3", "python"].iter().find_map(|candidate| {
        Command::new(candidate)
            .args(["-c", "import cloudra, fastapi, uvicorn"])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .ok()
            .filter(|status| status.success())
            .map(|_| (*candidate).to_string())
    })
}

fn start_backend() -> Result<Child, String> {
    let python = find_python().ok_or_else(|| {
        "未找到安装了 Cloudra、FastAPI 和 Uvicorn 的 Python。可通过 CLOUDRA_PYTHON 指定解释器。"
            .to_string()
    })?;

    Command::new(python)
        .args(["-m", "cloudra.api"])
        .env("CLOUDRA_API_HOST", "127.0.0.1")
        .env("CLOUDRA_API_PORT", API_PORT)
        .stdin(Stdio::null())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn()
        .map_err(|error| format!("Cloudra 后端启动失败：{error}"))
}

fn wait_for_backend(child: &mut Child) -> Result<(), String> {
    let address = SocketAddrV4::new(Ipv4Addr::LOCALHOST, API_PORT.parse().unwrap_or(18473));
    for _ in 0..60 {
        if TcpStream::connect_timeout(&address.into(), Duration::from_millis(100)).is_ok() {
            return Ok(());
        }
        if let Some(status) = child.try_wait().map_err(|error| error.to_string())? {
            return Err(format!("Cloudra 后端提前退出：{status}"));
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    Err("等待 Cloudra 后端就绪超时".to_string())
}

#[tauri::command]
fn backend_process_id(state: tauri::State<'_, BackendProcess>) -> Option<u32> {
    state.0.lock().ok()?.as_ref().map(Child::id)
}

pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let mut child = start_backend().map_err(std::io::Error::other)?;
            wait_for_backend(&mut child).map_err(std::io::Error::other)?;
            app.manage(BackendProcess(Mutex::new(Some(child))));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![backend_process_id])
        .build(tauri::generate_context!())
        .expect("failed to build Cloudra desktop application");

    app.run(|handle, event| {
        if matches!(event, RunEvent::Exit | RunEvent::ExitRequested { .. }) {
            if let Some(state) = handle.try_state::<BackendProcess>() {
                if let Ok(mut guard) = state.0.lock() {
                    if let Some(child) = guard.as_mut() {
                        let _ = child.kill();
                        let _ = child.wait();
                    }
                    *guard = None;
                }
            }
        }
    });
}
