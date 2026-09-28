// Estado de la interfaz y conexión con el cuerpo (Rust) y el cerebro (servicio.py).
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { create } from "zustand";

/** Cómo se ve el orbe. */
export type EstadoDahiana = "cargando" | "reposo" | "pensando" | "dormida" | "error";

export type Mensaje = {
  id: number;
  autor: "nine" | "dahiana" | "accion" | "error";
  texto: string;
};

/** Eventos que envía servicio.py (ver su docstring). */
type EventoServicio =
  | { tipo: "listo" }
  | { tipo: "motor"; estado: EstadoMotor }
  | { tipo: "pensando" }
  | { tipo: "accion"; nombre: string; argumentos: string; resultado: string }
  | { tipo: "respuesta"; texto: string }
  | { tipo: "error"; texto: string };

type EstadoMotor = "cargando" | "encendido" | "apagado" | "fallo";

const ESTADO_POR_MOTOR: Record<EstadoMotor, EstadoDahiana> = {
  cargando: "cargando",
  encendido: "reposo",
  apagado: "dormida",
  fallo: "error",
};

type Almacen = {
  estado: EstadoDahiana;
  mensajes: Mensaje[];
  enviar: (texto: string) => void;
  reiniciar: () => void;
  alternarModoJuego: () => void;
};

export const useDahiana = create<Almacen>((set, get) => ({
  estado: "cargando",
  mensajes: [],

  enviar: (texto) => {
    const limpio = texto.trim();
    if (!limpio || get().estado === "pensando") return;
    agregarMensaje("nine", limpio);
    invoke("enviar_mensaje", { texto: limpio }).catch(mostrarError);
  },

  reiniciar: () => {
    set({ mensajes: [] });
    invoke("reiniciar_conversacion").catch(mostrarError);
  },

  alternarModoJuego: () => {
    const accion = get().estado === "dormida" ? "encender" : "apagar";
    invoke("controlar_motor", { accion }).catch(mostrarError);
  },
}));

let siguienteId = 0;

function agregarMensaje(autor: Mensaje["autor"], texto: string) {
  useDahiana.setState((s) => ({ mensajes: [...s.mensajes, { id: siguienteId++, autor, texto }] }));
}

function mostrarError(error: unknown) {
  agregarMensaje("error", String(error));
}

function atenderEvento(evento: EventoServicio) {
  const cambiarEstado = (estado: EstadoDahiana) => useDahiana.setState({ estado });

  switch (evento.tipo) {
    case "motor":
      cambiarEstado(ESTADO_POR_MOTOR[evento.estado]);
      if (evento.estado === "fallo") mostrarError("No pude encender el modelo. Revisa MOTOR en config.py.");
      break;
    case "pensando":
      cambiarEstado("pensando");
      break;
    case "accion":
      agregarMensaje("accion", evento.resultado);
      break;
    case "respuesta":
      cambiarEstado("reposo");
      agregarMensaje("dahiana", evento.texto);
      break;
    case "error":
      if (useDahiana.getState().estado === "pensando") cambiarEstado("reposo");
      mostrarError(evento.texto);
      break;
  }
}

/** Escucha los eventos del servicio. Se llama una sola vez al arrancar. */
export async function conectarConDahiana() {
  await listen<EventoServicio>("dahiana", ({ payload }) => atenderEvento(payload));
  // Por si el motor cambió de estado antes de que la interfaz empezara a escuchar.
  const estado = await invoke<string>("estado_motor");
  if (estado in ESTADO_POR_MOTOR) {
    useDahiana.setState({ estado: ESTADO_POR_MOTOR[estado as EstadoMotor] });
  }
}
