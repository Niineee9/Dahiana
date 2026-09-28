import { getCurrentWindow } from "@tauri-apps/api/window";
import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";
import { Chat } from "./componentes/Chat";
import { Orbe } from "./componentes/Orbe";
import { VistaOrbe } from "./componentes/VistaOrbe";
import { type EstadoDahiana, useDahiana } from "./estado";

const TEXTO_ESTADO: Record<EstadoDahiana, string> = {
  cargando: "Despertando…",
  reposo: "Aquí estoy",
  escuchando: "Te escucho…",
  pensando: "Pensando…",
  hablando: "Hablando…",
  dormida: "Dormida · modo juego",
  error: "Algo no anda bien",
};

/** Oculta la ventana; Dahiana sigue viva en la bandeja. */
const ocultar = () => getCurrentWindow().hide();

/** Panel principal: barra superior, orbe, conversación y campo de texto. */
export default function App() {
  const {
    estado, animo, mensajes, vozActivada, atenta, vista,
    enviar, alternarEscucha, alternarVoz, alternarAtenta, cambiarVista, reiniciar, alternarModoJuego,
  } = useDahiana();
  const [texto, setTexto] = useState("");
  const entrada = useRef<HTMLInputElement>(null);
  const escuchando = estado === "escuchando";

  useEffect(() => {
    // Esc deja de escuchar o, si no escucha, oculta la ventana.
    // Al volver a mostrarse, el cursor queda listo para escribir.
    const alTeclear = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      const { estado, alternarEscucha } = useDahiana.getState();
      if (estado === "escuchando") alternarEscucha();
      else void ocultar();
    };
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

  if (vista === "orbe") return <VistaOrbe textoEstado={TEXTO_ESTADO[estado]} />;

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
            titulo={vozActivada ? "Voz activada: también te respondo en voz alta" : "Voz desactivada: solo texto"}
            onClick={alternarVoz}
            activo={vozActivada}
          >
            {vozActivada ? <IconoVoz /> : <IconoSinVoz />}
          </Boton>
          <Boton
            titulo={atenta ? "Atenta: puede comentar lo que haces (juegos, música...)" : "No comenta lo que haces"}
            onClick={alternarAtenta}
            activo={atenta}
          >
            {atenta ? <IconoOjo /> : <IconoOjoCerrado />}
          </Boton>
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
          <Boton titulo="Ocultar el chat (solo el orbe)" onClick={() => cambiarVista("orbe")}>
            <IconoSoloOrbe />
          </Boton>
          <Boton titulo="Ocultar (Esc)" onClick={ocultar}>
            <IconoCerrar />
          </Boton>
        </header>

        <div data-tauri-drag-region className="flex justify-center">
          <Orbe estado={estado} animo={animo} tamano={mensajes.length ? 64 : 112} />
        </div>

        <Chat mensajes={mensajes} pensando={estado === "pensando"} />

        <form onSubmit={alEnviar} className="flex items-center gap-2 p-3">
          <input
            ref={entrada}
            autoFocus
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder={
              escuchando ? "Te escucho… (Esc para cancelar)" : estado === "dormida" ? "Escríbeme y me despierto…" : "Háblame, Nine…"
            }
            className="min-w-0 flex-1 rounded-2xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white placeholder-violet-300/40 outline-none transition focus:border-fuchsia-400/50 focus:bg-white/10"
          />
          <button
            type="button"
            title={escuchando ? "Dejar de escuchar (Esc)" : "Hablarle (Ctrl+Alt+H)"}
            onClick={alternarEscucha}
            onMouseDown={(e) => e.preventDefault()} // no roba el foco del campo de texto
            className={`grid size-10 shrink-0 place-items-center rounded-full transition ${
              escuchando
                ? "animate-pulse bg-fuchsia-500 text-white"
                : "bg-white/5 text-violet-200 hover:bg-fuchsia-500/30 hover:text-white"
            }`}
          >
            <IconoMicrofono />
          </button>
        </form>
      </main>
    </div>
  );
}

/** Botón redondo de ícono para la barra superior. */
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

/** Atributos comunes de los íconos SVG (estilo de trazo, 16 px). */
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
const IconoMicrofono = () => (
  <svg {...trazo} width={18} height={18}>
    <rect x="9" y="3" width="6" height="11" rx="3" />
    <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
  </svg>
);
const IconoVoz = () => (
  <svg {...trazo}>
    <path d="M11 5 6 9H3v6h3l5 4z" />
    <path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13" />
  </svg>
);
const IconoSinVoz = () => (
  <svg {...trazo}>
    <path d="M11 5 6 9H3v6h3l5 4z" />
    <path d="m16 9 6 6M22 9l-6 6" />
  </svg>
);
const IconoOjo = () => (
  <svg {...trazo}>
    <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
);
const IconoOjoCerrado = () => (
  <svg {...trazo}>
    <path d="M3 10c2.5 3 5.5 4.5 9 4.5s6.5-1.5 9-4.5M8 14.5l-1.5 2.5M16 14.5l1.5 2.5M12 15v3" />
  </svg>
);
const IconoSoloOrbe = () => (
  <svg {...trazo}>
    <path d="M4 14h6v6M20 10h-6V4M14 10l7-7M3 21l7-7" />
  </svg>
);
const IconoCerrar = () => (
  <svg {...trazo}>
    <path d="M18 6 6 18M6 6l12 12" />
  </svg>
);
