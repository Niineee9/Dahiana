import { getCurrentWindow } from "@tauri-apps/api/window";
import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";
import { Chat } from "./componentes/Chat";
import { Orbe } from "./componentes/Orbe";
import { type EstadoDahiana, useDahiana } from "./estado";

const TEXTO_ESTADO: Record<EstadoDahiana, string> = {
  cargando: "Despertando…",
  reposo: "Aquí estoy",
  pensando: "Pensando…",
  dormida: "Dormida · modo juego",
  error: "Algo no anda bien",
};

const ocultar = () => getCurrentWindow().hide();

export default function App() {
  const { estado, mensajes, enviar, reiniciar, alternarModoJuego } = useDahiana();
  const [texto, setTexto] = useState("");
  const entrada = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // Esc la oculta; al volver a mostrarse, el cursor queda listo para escribir.
    const alTeclear = (e: KeyboardEvent) => e.key === "Escape" && ocultar();
    const alEnfocar = () => entrada.current?.focus();
    window.addEventListener("keydown", alTeclear);
    window.addEventListener("focus", alEnfocar);
    return () => {
      window.removeEventListener("keydown", alTeclear);
      window.removeEventListener("focus", alEnfocar);
    };
  }, []);

  const alEnviar = (e: FormEvent) => {
    e.preventDefault();
    enviar(texto);
    setTexto("");
  };

  return (
    <div className="h-full p-2">
      <main className="flex h-full flex-col overflow-hidden rounded-3xl border border-white/10 bg-noche shadow-2xl shadow-black/50">
        {/* Barra superior: se puede arrastrar la ventana desde aquí */}
        <header data-tauri-drag-region className="flex items-center gap-1 px-4 pt-3 pb-1">
          <div data-tauri-drag-region className="flex-1">
            <h1 data-tauri-drag-region className="text-sm font-semibold tracking-wide text-violet-100">
              Dahiana
            </h1>
            <p data-tauri-drag-region className="text-xs text-violet-300/70">
              {TEXTO_ESTADO[estado]}
            </p>
          </div>
          <Boton
            titulo={estado === "dormida" ? "Despertar (encender el modelo)" : "Modo juego (liberar VRAM)"}
            onClick={alternarModoJuego}
            activo={estado === "dormida"}
          >
            <IconoLuna />
          </Boton>
          <Boton titulo="Nueva conversación" onClick={reiniciar}>
            <IconoNueva />
          </Boton>
          <Boton titulo="Ocultar (Esc)" onClick={ocultar}>
            <IconoCerrar />
          </Boton>
        </header>

        <div data-tauri-drag-region className="flex justify-center">
          <Orbe estado={estado} tamano={mensajes.length ? 64 : 112} />
        </div>

        <Chat mensajes={mensajes} pensando={estado === "pensando"} />

        <form onSubmit={alEnviar} className="p-3">
          <input
            ref={entrada}
            autoFocus
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder={estado === "dormida" ? "Escríbeme y me despierto…" : "Háblame, Nine…"}
            className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white placeholder-violet-300/40 outline-none transition focus:border-fuchsia-400/50 focus:bg-white/10"
          />
        </form>
      </main>
    </div>
  );
}

function Boton(props: { titulo: string; onClick: () => void; activo?: boolean; children: ReactNode }) {
  return (
    <button
      type="button"
      title={props.titulo}
      onClick={props.onClick}
      onMouseDown={(e) => e.preventDefault()} // no roba el foco: se puede seguir escribiendo
      className={`grid size-8 place-items-center rounded-full transition hover:bg-white/10 ${
        props.activo ? "text-fuchsia-300" : "text-violet-300/70 hover:text-violet-100"
      }`}
    >
      {props.children}
    </button>
  );
}

const trazo = {
  width: 16,
  height: 16,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

const IconoLuna = () => (
  <svg {...trazo}>
    <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
  </svg>
);
const IconoNueva = () => (
  <svg {...trazo}>
    <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
    <path d="M3 3v5h5" />
  </svg>
);
const IconoCerrar = () => (
  <svg {...trazo}>
    <path d="M18 6 6 18M6 6l12 12" />
  </svg>
);
