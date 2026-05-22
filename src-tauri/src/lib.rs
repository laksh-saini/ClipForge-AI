use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::Manager;

// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

fn safe_file_name(path: &str, index: usize) -> String {
    let source = Path::new(path);
    let stem = source
        .file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or("media")
        .chars()
        .map(|ch| if ch.is_ascii_alphanumeric() || ch == '-' || ch == '_' { ch } else { '_' })
        .collect::<String>();
    let ext = source
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or("bin");
    let millis = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis())
        .unwrap_or(0);
    format!("{stem}_{millis}_{index}.{ext}")
}

#[tauri::command]
fn stage_media_files(app: tauri::AppHandle, paths: Vec<String>) -> Result<Vec<String>, String> {
    let media_dir: PathBuf = app
        .path()
        .app_data_dir()
        .map_err(|err| err.to_string())?
        .join("staged_media");
    std::fs::create_dir_all(&media_dir).map_err(|err| err.to_string())?;

    paths
        .iter()
        .enumerate()
        .map(|(index, path)| {
            let destination = media_dir.join(safe_file_name(path, index));
            std::fs::copy(path, &destination)
                .map_err(|err| format!("Failed to stage {path}: {err}"))?;
            Ok(destination.to_string_lossy().to_string())
        })
        .collect()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .setup(|_app| {
            // Spawn Python Engine in the background
            std::thread::spawn(|| {
                let mut current_dir = std::env::current_dir().unwrap_or_default();
                if current_dir.ends_with("src-tauri") {
                    current_dir = current_dir.parent().unwrap().to_path_buf();
                }
                let python_dir = current_dir.join("python-engine");
                let venv_python = python_dir.join("venv").join("bin").join("python3");
                
                let python_executable = if venv_python.exists() {
                    venv_python.to_str().unwrap().to_string()
                } else {
                    "python3".to_string()
                };

                let _ = std::process::Command::new(python_executable)
                    .current_dir(python_dir)
                    .arg("server.py")
                    .arg("8000") // Port
                    .spawn();
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![greet, stage_media_files])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
