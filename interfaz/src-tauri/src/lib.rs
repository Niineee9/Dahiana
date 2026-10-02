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
use tauri::{AppHandle, Emitter, LogicalSize, Manager, PhysicalPosition, RunEvent, WindowEvent};
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(windows)]
const SIN_VENTANA: u32 = 0x0800_0000; // CREATE_NO_WINDOW: Python sin consola
const VENTANA: &str = "principal";
const MARGEN: i32 = 12; // separación del borde de la pantalla, en píxeles
const TAMANO_CHAT: (f64, f64) = (380.0, 580.0); // ancho y alto lógicos (igual que tauri.conf.json)
const TAMANO_ORBE: (f64, f64) = (300.0, 560.0); // Dahiana sola, de cuerpo entero (o el orbe si no hay avatar)

/// El proceso de servicio.py y el último estado del motor (por si la interfaz se lo perdió).
#[derive(Default)]
struct Servicio {
    proceso: Mutex<Option<Child>>,
    entrada: Mutex<Option<ChildStdin>>,
    estado_motor: Mutex<String>,
}

/// Carpeta raíz de Dahiana, donde están servicio.py y config.py.
fn raiz_proyecto() -> PathBuf {
    // En desarrollo: interfaz/src-tauri -> raíz de Dahiana. Se puede cambiar con DAHIANA_RAIZ.
    std::env::var("DAHIANA_RAIZ")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..").join(".."))
}

// ---------------------------------------------------------------- servicio (Python)

/// Lanza servicio.py sin consola y reenvía cada línea JSON que imprime como evento "dahiana".
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

/// Envía una petición JSON a servicio.py por su entrada estándar.
fn enviar_al_servicio(servicio: &Servicio, peticion: Value) -> Result<(), String> {
    let mut entrada = servicio.entrada.lock().map_err(|e| e.to_string())?;
    let entrada = entrada.as_mut().ok_or("El servicio no está en marcha.")?;
    writeln!(entrada, "{peticion}")
        .and_then(|_| entrada.flush())
        .map_err(|e| e.to_string())
}

/// Cierra servicio.py con calma (apaga el modelo) y, si no responde en 10 s, lo mata.
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

/// Comando: envía a Dahiana un mensaje de Nine; con `hablar`, ella responde también en voz alta.
#[tauri::command]
fn enviar_mensaje(texto: String, hablar: bool, servicio: tauri::State<Servicio>) -> Result<(), String> {
    enviar_al_servicio(&servicio, json!({"tipo": "mensaje", "texto": texto, "hablar": hablar}))
}

/// Comando: Dahiana escucha el micrófono hasta que Nine termina de hablar, y responde con voz.
#[tauri::command]
fn escuchar(servicio: tauri::State<Servicio>) -> Result<(), String> {
    enviar_al_servicio(&servicio, json!({"tipo": "escuchar"}))
}

/// Comando: deja de escuchar el micrófono.
#[tauri::command]
fn cancelar_escucha(servicio: tauri::State<Servicio>) -> Result<(), String> {
    enviar_al_servicio(&servicio, json!({"tipo": "cancelar"}))
}

/// Comando: Dahiana olvida la conversación actual.
#[tauri::command]
fn reiniciar_conversacion(servicio: tauri::State<Servicio>) -> Result<(), String> {
    enviar_al_servicio(&servicio, json!({"tipo": "reiniciar"}))
}

/// Comando: enciende o apaga el modelo ("apagar" = modo juego).
#[tauri::command]
fn controlar_motor(accion: String, servicio: tauri::State<Servicio>) -> Result<(), String> {
    if accion != "encender" && accion != "apagar" {
        return Err(format!("Acción de motor desconocida: {accion}"));
    }
    enviar_al_servicio(&servicio, json!({"tipo": "motor", "accion": accion}))
}

/// Comando: le dice al servicio cómo está la interfaz (voz activada, modo orbe) y si Dahiana puede
/// comentar lo que Nine hace (`atenta`). Decide cuándo habla sola y si sus iniciativas suenan.
#[tauri::command]
fn enviar_preferencias(voz: bool, orbe: bool, atenta: bool, servicio: tauri::State<Servicio>) -> Result<(), String> {
    enviar_al_servicio(&servicio, json!({"tipo": "preferencias", "voz": voz, "orbe": orbe, "atenta": atenta}))
}

/// Comando: ajusta la ventana a Dahiana sola, sin chat (`compacta`), o al chat, junto al reloj.
#[tauri::command]
fn ajustar_ventana(compacta: bool, app: AppHandle) -> Result<(), String> {
    let ventana = app.get_webview_window(VENTANA).ok_or("No encontré la ventana de Dahiana.")?;
    let (ancho, alto) = if compacta { TAMANO_ORBE } else { TAMANO_CHAT };
    ventana.set_size(LogicalSize::new(ancho, alto)).map_err(|e| e.to_string())?;
    colocar_junto_al_reloj(&app);
    Ok(())
}

/// Comando: posición del cursor relativa al contenido de la ventana, en píxeles lógicos (como el CSS).
/// Funciona aunque el cursor esté fuera de la ventana: así el orbe puede "mirarlo".
#[tauri::command]
fn cursor_relativo(app: AppHandle) -> Result<(f64, f64), String> {
    let ventana = app.get_webview_window(VENTANA).ok_or("No encontré la ventana de Dahiana.")?;
    let cursor = ventana.cursor_position().map_err(|e| e.to_string())?;
    let origen = ventana.inner_position().map_err(|e| e.to_string())?;
    let escala = ventana.scale_factor().map_err(|e| e.to_string())?;
    Ok(((cursor.x - origen.x as f64) / escala, (cursor.y - origen.y as f64) / escala))
}

/// Comando: muestra la ventana junto al reloj sin quitarle el foco a lo que Nine está usando.
#[tauri::command]
fn mostrar_sin_foco(app: AppHandle) -> Result<(), String> {
    let ventana = app.get_webview_window(VENTANA).ok_or("No encontré la ventana de Dahiana.")?;
    if !ventana.is_visible().unwrap_or(false) {
        colocar_junto_al_reloj(&app);
        ventana.show().map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// Comando: último estado conocido del motor (cargando, encendido, apagado o fallo).
#[tauri::command]
fn estado_motor(servicio: tauri::State<Servicio>) -> String {
    servicio.estado_motor.lock().unwrap().clone()
}

// ---------------------------------------------------------------- ventana

/// Coloca la ventana en la esquina inferior derecha, sobre la barra de tareas.
fn colocar_junto_al_reloj(app: &AppHandle) {
    let Some(ventana) = app.get_webview_window(VENTANA) else { return };
    let monitor = ventana.current_monitor().ok().flatten().or_else(|| ventana.primary_monitor().ok().flatten());
    let (Some(monitor), Ok(tamano)) = (monitor, ventana.outer_size()) else { return };
    let area = monitor.work_area(); // pantalla sin la barra de tareas
    let x = area.position.x + area.size.width as i32 - tamano.width as i32 - MARGEN;
    let y = area.position.y + area.size.height as i32 - tamano.height as i32 - MARGEN;
    let _ = ventana.set_position(PhysicalPosition::new(x, y));
}

/// Muestra la ventana junto al reloj y le da el foco.
fn mostrar_ventana(app: &AppHandle) {
    if let Some(ventana) = app.get_webview_window(VENTANA) {
        colocar_junto_al_reloj(app);
        let _ = ventana.show();
        let _ = ventana.set_focus();
    }
}

/// Muestra la ventana si está oculta, o la oculta si está visible.
fn alternar_ventana(app: &AppHandle) {
    match app.get_webview_window(VENTANA) {
        Some(ventana) if ventana.is_visible().unwrap_or(false) => {
            let _ = ventana.hide();
        }
        _ => mostrar_ventana(app),
    }
}

// ---------------------------------------------------------------- bandeja y atajos

/// Crea el ícono del orbe en la bandeja del sistema con su menú.
fn crear_bandeja(app: &AppHandle) -> tauri::Result<()> {
    let mostrar = MenuItem::with_id(app, "mostrar", "Mostrar / ocultar  (Ctrl+Alt+D)", true, None::<&str>)?;
    let hablarle = MenuItem::with_id(app, "hablarle", "Hablarle  (Ctrl+Alt+H)", true, None::<&str>)?;
    let modo_juego = MenuItem::with_id(app, "modo_juego", "Modo juego (liberar VRAM)", true, None::<&str>)?;
    let salir = MenuItem::with_id(app, "salir", "Salir", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&mostrar, &hablarle, &modo_juego, &salir])?;

    TrayIconBuilder::with_id("dahiana")
        .icon(app.default_window_icon().expect("ícono de la app").clone())
        .tooltip("Dahiana")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, evento| match evento.id.as_ref() {
            "mostrar" => alternar_ventana(app),
            "hablarle" => pedir_que_escuche(app),
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

/// Muestra la ventana y le pide a la interfaz que empiece a escuchar.
/// Lo decide la interfaz (y no Rust) porque ella sabe si hay que cortar una voz que está sonando.
fn pedir_que_escuche(app: &AppHandle) {
    mostrar_ventana(app);
    let _ = app.emit("atajo_escuchar", ());
}

/// Registra los atajos globales: Ctrl+Alt+D (mostrar u ocultar) y Ctrl+Alt+H (hablarle).
/// Si otro programa ya usa uno, se avisa y Dahiana sigue funcionando (la bandeja tiene lo mismo).
fn registrar_atajos(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let mostrar = Shortcut::new(Some(Modifiers::CONTROL | Modifiers::ALT), Code::KeyD);
    let hablarle = Shortcut::new(Some(Modifiers::CONTROL | Modifiers::ALT), Code::KeyH);
    app.plugin(
        tauri_plugin_global_shortcut::Builder::new()
            .with_handler(move |app, pulsado, evento| {
                if evento.state() != ShortcutState::Pressed {
                    return;
                }
                if pulsado == &mostrar {
                    alternar_ventana(app);
                } else if pulsado == &hablarle {
                    pedir_que_escuche(app);
                }
            })
            .build(),
    )?;
    for (atajo, nombre) in [(mostrar, "Ctrl+Alt+D"), (hablarle, "Ctrl+Alt+H")] {
        if let Err(error) = app.global_shortcut().register(atajo) {
            eprintln!("[atajos] No pude registrar {nombre} (¿lo usa otro programa?): {error}");
        }
    }
    Ok(())
}

// ---------------------------------------------------------------- arranque

/// Punto de entrada de la app: configura Tauri, arranca el servicio y maneja el cierre.
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        // Si ya está abierta, un segundo arranque solo la muestra.
        .plugin(tauri_plugin_single_instance::init(|app, _, _| mostrar_ventana(app)))
        .manage(Servicio::default())
        .invoke_handler(tauri::generate_handler![
            enviar_mensaje,
            escuchar,
            cancelar_escucha,
            reiniciar_conversacion,
            controlar_motor,
            ajustar_ventana,
            enviar_preferencias,
            cursor_relativo,
            mostrar_sin_foco,
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
            registrar_atajos(app.handle())?;
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
