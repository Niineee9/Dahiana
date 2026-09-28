//! Cuerpo de Dahiana: ventana flotante, bandeja del sistema, atajo global
//! y el proceso de Python (servicio.py) que hace de cerebro.

use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::Duration;

use serde_json::{json, Value};
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager, PhysicalPosition, RunEvent, WindowEvent};
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(windows)]
const SIN_VENTANA: u32 = 0x0800_0000; // CREATE_NO_WINDOW: Python sin consola
const VENTANA: &str = "principal";
const MARGEN: i32 = 12; // separación del borde de la pantalla, en píxeles

/// El proceso de servicio.py y el último estado del motor (por si la interfaz se lo perdió).
#[derive(Default)]
struct Servicio {
    proceso: Mutex<Option<Child>>,
    entrada: Mutex<Option<ChildStdin>>,
    estado_motor: Mutex<String>,
}

fn raiz_proyecto() -> PathBuf {
    // En desarrollo: interfaz/src-tauri -> raíz de Dahiana. Se puede cambiar con DAHIANA_RAIZ.
    std::env::var("DAHIANA_RAIZ")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join(".."))
}

// ---------------------------------------------------------------- servicio (Python)

fn iniciar_servicio(app: &AppHandle) -> std::io::Result<()> {
    let mut comando = Command::new("python");
    comando
        .args(["-u", "servicio.py"])
        .current_dir(raiz_proyecto())
        .env("PYTHONIOENCODING", "utf-8")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(windows)]
    comando.creation_flags(SIN_VENTANA);
    let mut proceso = comando.spawn()?;

    // Cada línea JSON de servicio.py se reenvía a la interfaz como evento "dahiana".
    let salida = proceso.stdout.take().expect("stdout del servicio");
    let app_salida = app.clone();
    thread::spawn(move || {
        for linea in BufReader::new(salida).lines().map_while(Result::ok) {
            let Ok(evento) = serde_json::from_str::<Value>(&linea) else {
                eprintln!("[servicio] {linea}");
                continue;
            };
            if evento["tipo"] == "motor" {
                if let Some(estado) = evento["estado"].as_str() {
                    *app_salida.state::<Servicio>().estado_motor.lock().unwrap() = estado.into();
                }
            }
            let _ = app_salida.emit("dahiana", evento);
        }
        let _ = app_salida.emit(
            "dahiana",
            json!({"tipo": "error", "texto": "El servicio de Dahiana se cerró."}),
        );
    });

    let errores = proceso.stderr.take().expect("stderr del servicio");
    thread::spawn(move || {
        for linea in BufReader::new(errores).lines().map_while(Result::ok) {
            eprintln!("[servicio] {linea}");
        }
    });

    let servicio = app.state::<Servicio>();
    *servicio.entrada.lock().unwrap() = proceso.stdin.take();
    *servicio.proceso.lock().unwrap() = Some(proceso);
    Ok(())
}

fn enviar_al_servicio(servicio: &Servicio, peticion: Value) -> Result<(), String> {
    let mut entrada = servicio.entrada.lock().map_err(|e| e.to_string())?;
    let entrada = entrada.as_mut().ok_or("El servicio no está en marcha.")?;
    writeln!(entrada, "{peticion}")
        .and_then(|_| entrada.flush())
        .map_err(|e| e.to_string())
}

fn detener_servicio(servicio: &Servicio) {
    // Cerrar su entrada hace que servicio.py termine limpio y apague el modelo (libera la VRAM).
    servicio.entrada.lock().unwrap().take();
    if let Some(mut proceso) = servicio.proceso.lock().unwrap().take() {
        for _ in 0..100 {
            if let Ok(Some(_)) = proceso.try_wait() {
                return;
            }
            thread::sleep(Duration::from_millis(100));
        }
        let _ = proceso.kill();
    }
}

// ---------------------------------------------------------------- comandos para la interfaz

#[tauri::command]
fn enviar_mensaje(texto: String, servicio: tauri::State<Servicio>) -> Result<(), String> {
    enviar_al_servicio(&servicio, json!({"tipo": "mensaje", "texto": texto}))
}

#[tauri::command]
fn reiniciar_conversacion(servicio: tauri::State<Servicio>) -> Result<(), String> {
    enviar_al_servicio(&servicio, json!({"tipo": "reiniciar"}))
}

#[tauri::command]
fn controlar_motor(accion: String, servicio: tauri::State<Servicio>) -> Result<(), String> {
    if accion != "encender" && accion != "apagar" {
        return Err(format!("Acción de motor desconocida: {accion}"));
    }
    enviar_al_servicio(&servicio, json!({"tipo": "motor", "accion": accion}))
}

#[tauri::command]
fn estado_motor(servicio: tauri::State<Servicio>) -> String {
    servicio.estado_motor.lock().unwrap().clone()
}

// ---------------------------------------------------------------- ventana

fn colocar_junto_al_reloj(app: &AppHandle) {
    let Some(ventana) = app.get_webview_window(VENTANA) else { return };
    let monitor = ventana.current_monitor().ok().flatten().or_else(|| ventana.primary_monitor().ok().flatten());
    let (Some(monitor), Ok(tamano)) = (monitor, ventana.outer_size()) else { return };
    let area = monitor.work_area(); // pantalla sin la barra de tareas
    let x = area.position.x + area.size.width as i32 - tamano.width as i32 - MARGEN;
    let y = area.position.y + area.size.height as i32 - tamano.height as i32 - MARGEN;
    let _ = ventana.set_position(PhysicalPosition::new(x, y));
}

fn mostrar_ventana(app: &AppHandle) {
    if let Some(ventana) = app.get_webview_window(VENTANA) {
        colocar_junto_al_reloj(app);
        let _ = ventana.show();
        let _ = ventana.set_focus();
    }
}

fn alternar_ventana(app: &AppHandle) {
    match app.get_webview_window(VENTANA) {
        Some(ventana) if ventana.is_visible().unwrap_or(false) => {
            let _ = ventana.hide();
        }
        _ => mostrar_ventana(app),
    }
}

// ---------------------------------------------------------------- bandeja y atajo

fn crear_bandeja(app: &AppHandle) -> tauri::Result<()> {
    let mostrar = MenuItem::with_id(app, "mostrar", "Mostrar / ocultar  (Ctrl+Alt+D)", true, None::<&str>)?;
    let modo_juego = MenuItem::with_id(app, "modo_juego", "Modo juego (liberar VRAM)", true, None::<&str>)?;
    let salir = MenuItem::with_id(app, "salir", "Salir", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&mostrar, &modo_juego, &salir])?;

    TrayIconBuilder::with_id("dahiana")
        .icon(app.default_window_icon().expect("ícono de la app").clone())
        .tooltip("Dahiana")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, evento| match evento.id.as_ref() {
            "mostrar" => alternar_ventana(app),
            "modo_juego" => {
                let peticion = json!({"tipo": "motor", "accion": "apagar"});
                let _ = enviar_al_servicio(&app.state::<Servicio>(), peticion);
            }
            "salir" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|bandeja, evento| {
            if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = evento {
                alternar_ventana(bandeja.app_handle());
            }
        })
        .build(app)?;
    Ok(())
}

fn registrar_atajo(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let atajo = Shortcut::new(Some(Modifiers::CONTROL | Modifiers::ALT), Code::KeyD);
    app.plugin(
        tauri_plugin_global_shortcut::Builder::new()
            .with_handler(move |app, pulsado, evento| {
                if pulsado == &atajo && evento.state() == ShortcutState::Pressed {
                    alternar_ventana(app);
                }
            })
            .build(),
    )?;
    app.global_shortcut().register(atajo)?;
    Ok(())
}

// ---------------------------------------------------------------- arranque

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        // Si ya está abierta, un segundo arranque solo la muestra.
        .plugin(tauri_plugin_single_instance::init(|app, _, _| mostrar_ventana(app)))
        .manage(Servicio::default())
        .invoke_handler(tauri::generate_handler![
            enviar_mensaje,
            reiniciar_conversacion,
            controlar_motor,
            estado_motor
        ])
        .on_window_event(|ventana, evento| {
            // Cerrar la ventana (Alt+F4) solo la oculta: Dahiana sigue en la bandeja.
            if let WindowEvent::CloseRequested { api, .. } = evento {
                api.prevent_close();
                let _ = ventana.hide();
            }
        })
        .setup(|app| {
            crear_bandeja(app.handle())?;
            registrar_atajo(app.handle())?;
            iniciar_servicio(app.handle())?;
            mostrar_ventana(app.handle());
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("no se pudo iniciar Dahiana");

    app.run(|app, evento| {
        if let RunEvent::Exit = evento {
            detener_servicio(&app.state::<Servicio>());
        }
    });
}
