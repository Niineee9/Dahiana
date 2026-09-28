// Estado de la interfaz y conexión con el cuerpo (Rust) y el cerebro (servicio.py).
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { create } from "zustand";
import { detener, reproducir } from "./reproductor";

/** Cómo se ve el orbe. */
export type EstadoDahiana = "cargando" | "reposo" | "escuchando" | "pensando" | "hablando" | "dormida" | "error";

export type Mensaje = {
  id: number;
  autor: "nine" | "dahiana" | "accion" | "aviso" | "error";
  texto: string;
};

/** Eventos que envía servicio.py (ver su docstring). */
type EventoServicio =
  | { tipo: "listo" }
  | { tipo: "motor"; estado: EstadoMotor }
  | { tipo: "escuchando" }
  | { tipo: "transcripcion"; texto: string }
  | { tipo: "no_escuche" }
  | { tipo: "escucha_cancelada" }
  | { tipo: "pensando" }
  | { tipo: "accion"; nombre: string; argumentos: string; resultado: string }
  | { tipo: "respuesta"; texto: string; animo: Animo }
  | { tipo: "iniciativa"; texto: string; animo: Animo }
  | { tipo: "voz"; audio: string }
  | { tipo: "vista"; vista: Vista }
  | { tipo: "error"; texto: string };

/** "chat": panel completo · "orbe": solo el orbe flotante, sin la conversación. */
export type Vista = "chat" | "orbe";

/** Ánimo de Dahiana (brain.ANIMOS en Python): cambia el color del orbe. */
export type Animo = "alegre" | "emocionada" | "tierna" | "tranquila" | "curiosa" | "preocupada";

type EstadoMotor = "cargando" | "encendido" | "apagado" | "fallo";

const ESTADO_POR_MOTOR: Record<EstadoMotor, EstadoDahiana> = {
  cargando: "cargando",
  encendido: "reposo",
  apagado: "dormida",
  fallo: "error",
};

// Preferencias guardadas en el navegador interno.
const CLAVE_VOZ = "dahiana.voz";
const CLAVE_VISTA = "dahiana.vista";
const CLAVE_ATENTA = "dahiana.atenta";

type Almacen = {
  estado: EstadoDahiana;
  animo: Animo;
  mensajes: Mensaje[];
  /** Si Dahiana responde en voz alta a los mensajes escritos (a los hablados, siempre). */
  vozActivada: boolean;
  /** Si Dahiana puede comentar lo que Nine hace (horas jugando, programar de madrugada, música). */
  atenta: boolean;
  vista: Vista;
  alternarAtenta: () => void;
  /** Cambia entre el chat y el orbe solo (achica o agranda la ventana). */
  cambiarVista: (vista: Vista) => void;
  enviar: (texto: string) => void;
  /** Empieza a escuchar el micrófono o, si ya escucha, deja de hacerlo. */
  alternarEscucha: () => void;
  alternarVoz: () => void;
  reiniciar: () => void;
  alternarModoJuego: () => void;
};

/** Estado global de la interfaz (Zustand): cómo está Dahiana, la conversación y las acciones. */
export const useDahiana = create<Almacen>((set, get) => ({
  estado: "cargando",
  animo: "tranquila",
  mensajes: [],
  vozActivada: leerPreferencia(CLAVE_VOZ, "true") !== "false",
  atenta: leerPreferencia(CLAVE_ATENTA, "true") !== "false",
  vista: leerPreferencia(CLAVE_VISTA, "chat") === "orbe" ? "orbe" : "chat",

  alternarAtenta: () => {
    const atenta = !get().atenta;
    set({ atenta });
    guardarPreferencia(CLAVE_ATENTA, String(atenta));
    enviarPreferencias();
  },

  cambiarVista: (vista) => {
    set({ vista });
    guardarPreferencia(CLAVE_VISTA, vista);
    invoke("ajustar_ventana", { compacta: vista === "orbe" }).catch(mostrarError);
    enviarPreferencias();
  },

  enviar: (texto) => {
    const limpio = texto.trim();
    if (!limpio || estaOcupada()) return;
    detener();
    agregarMensaje("nine", limpio);
    // Sin el chat a la vista, la única forma de enterarse de la respuesta es oírla.
    const hablar = get().vozActivada || get().vista === "orbe";
    invoke("enviar_mensaje", { texto: limpio, hablar }).catch(mostrarError);
  },

  alternarEscucha: () => {
    if (get().estado === "escuchando") {
      invoke("cancelar_escucha").catch(mostrarError);
      return;
    }
    if (estaOcupada()) return;
    detener();
    invoke("escuchar").catch(mostrarError);
  },

  alternarVoz: () => {
    const vozActivada = !get().vozActivada;
    if (!vozActivada) detener();
    set({ vozActivada });
    guardarPreferencia(CLAVE_VOZ, String(vozActivada));
    enviarPreferencias();
  },

  reiniciar: () => {
    detener();
    set({ mensajes: [] });
    invoke("reiniciar_conversacion").catch(mostrarError);
  },

  alternarModoJuego: () => {
    const accion = get().estado === "dormida" ? "encender" : "apagar";
    invoke("controlar_motor", { accion }).catch(mostrarError);
  },
}));

let siguienteId = 0; // identificador único de cada mensaje (clave de React)

/** Lee una preferencia guardada, o `porDefecto` si no hay (o no hay almacenamiento). */
function leerPreferencia(clave: string, porDefecto: string): string {
  try {
    return localStorage.getItem(clave) ?? porDefecto;
  } catch {
    return porDefecto;
  }
}

/** Guarda una preferencia; sin almacenamiento, dura hasta cerrar la app. */
function guardarPreferencia(clave: string, valor: string) {
  try {
    localStorage.setItem(clave, valor);
  } catch {
    // sin almacenamiento disponible: no pasa nada
  }
}

/** Le cuenta al servicio cómo está la interfaz: decide si las iniciativas suenan y si puede comentar lo que Nine hace. */
function enviarPreferencias() {
  const { vozActivada, vista, atenta } = useDahiana.getState();
  invoke("enviar_preferencias", { voz: vozActivada, orbe: vista === "orbe", atenta }).catch(mostrarError);
}

/** True mientras Dahiana no puede atender algo nuevo (cargando el modelo o pensando). */
function estaOcupada(): boolean {
  const { estado } = useDahiana.getState();
  return estado === "pensando" || estado === "cargando";
}

/** Agrega un mensaje al final de la conversación. */
function agregarMensaje(autor: Mensaje["autor"], texto: string) {
  useDahiana.setState((s) => ({ mensajes: [...s.mensajes, { id: siguienteId++, autor, texto }] }));
}

/** Muestra un error en la conversación (errores de Rust, de Python o del modelo). */
function mostrarError(error: unknown) {
  agregarMensaje("error", String(error));
}

/** Actualiza el estado según un evento de servicio.py. */
function atenderEvento(evento: EventoServicio) {
  const cambiarEstado = (estado: EstadoDahiana) => useDahiana.setState({ estado });
  const estadoActual = () => useDahiana.getState().estado;

  switch (evento.tipo) {
    case "motor":
      cambiarEstado(ESTADO_POR_MOTOR[evento.estado]);
      if (evento.estado === "fallo") mostrarError("No pude encender el modelo. Revisa MOTOR en config.py.");
      break;
    case "escuchando":
      cambiarEstado("escuchando");
      break;
    case "transcripcion":
      agregarMensaje("nine", evento.texto);
      break;
    case "no_escuche":
      cambiarEstado("reposo");
      agregarMensaje("aviso", "No te escuché bien, ¿me lo repites?");
      break;
    case "escucha_cancelada":
      cambiarEstado("reposo");
      break;
    case "pensando":
      cambiarEstado("pensando");
      break;
    case "accion":
      agregarMensaje("accion", evento.resultado);
      break;
    case "respuesta":
      useDahiana.setState({ estado: "reposo", animo: evento.animo });
      agregarMensaje("dahiana", evento.texto);
      break;
    case "iniciativa": {
      // Dahiana habla primero. Si no va a sonar (voz apagada con el chat a la vista), se asoma sin
      // quitarle el foco a lo que Nine está haciendo.
      useDahiana.setState({ animo: evento.animo });
      agregarMensaje("dahiana", evento.texto);
      const { vozActivada, vista } = useDahiana.getState();
      if (!vozActivada && vista === "chat") invoke("mostrar_sin_foco").catch(mostrarError);
      break;
    }
    case "voz":
      reproducir(
        evento.audio,
        () => cambiarEstado("hablando"),
        () => estadoActual() === "hablando" && cambiarEstado("reposo"),
      );
      break;
    case "vista":
      useDahiana.getState().cambiarVista(evento.vista);
      break;
    case "error":
      if (["pensando", "escuchando"].includes(estadoActual())) cambiarEstado("reposo");
      mostrarError(evento.texto);
      break;
  }
}

/** Escucha los eventos del servicio y del atajo de voz. Se llama una sola vez al arrancar. */
export async function conectarConDahiana() {
  // La ventana arranca en tamaño de chat: si la última vez quedó en modo orbe, se achica.
  if (useDahiana.getState().vista === "orbe") useDahiana.getState().cambiarVista("orbe");
  await listen<EventoServicio>("dahiana", ({ payload }) => atenderEvento(payload));
  // Ctrl+Alt+H (o "Hablarle" en la bandeja): empieza a escuchar.
  await listen("atajo_escuchar", () => {
    if (useDahiana.getState().estado !== "escuchando") useDahiana.getState().alternarEscucha();
  });
  enviarPreferencias(); // el servicio arranca con valores por defecto: se le cuentan los guardados
  // Por si el motor cambió de estado antes de que la interfaz empezara a escuchar.
  const estado = await invoke<string>("estado_motor");
  if (estado in ESTADO_POR_MOTOR) {
    useDahiana.setState({ estado: ESTADO_POR_MOTOR[estado as EstadoMotor] });
  }
}
