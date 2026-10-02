// Vista principal: Dahiana de cuerpo entero (o el orbe si no hay avatar) junto al reloj, sin el chat.
import { getCurrentWindow } from "@tauri-apps/api/window";
import type { MouseEvent, ReactNode } from "react";
import { useDahiana } from "../estado";
import { Presencia } from "./Avatar";

// Del tamaño de la ventana en esta vista (TAMANO_ORBE en lib.rs), menos un respiro para los botones.
// Más ancho que su cuerpo: al saludar o gesticular, las manos no deben salirse del lienzo.
const ANCHO = 300;
const ALTO = 520;

/** Mover la ventana arrastrando a Dahiana (con el botón izquierdo). */
const arrastrar = (e: MouseEvent) => {
  if (e.button === 0) void getCurrentWindow().startDragging();
};

/**
 * Vista sin chat: solo Dahiana. Al pasar el mouse aparecen los botones para hablarle o abrir el chat.
 * @param textoEstado - Descripción del estado (se muestra como ayuda al pasar el mouse).
 */
export function VistaOrbe({ textoEstado }: { textoEstado: string }) {
  const { estado, animo, alternarEscucha, cambiarVista } = useDahiana();
  const escuchando = estado === "escuchando";

  return (
    <div className="group relative grid h-full place-items-center">
      <div title={`Dahiana · ${textoEstado}`} onMouseDown={arrastrar} className="cursor-grab active:cursor-grabbing">
        <Presencia estado={estado} animo={animo} ancho={ANCHO} alto={ALTO} encuadre="cuerpo" tamanoOrbe={76} />
      </div>

      <div
        className={`absolute bottom-2 flex gap-2 transition-opacity ${
          escuchando ? "opacity-100" : "opacity-0 group-hover:opacity-100 focus-within:opacity-100"
        }`}
      >
        <BotonFlotante
          titulo={escuchando ? "Dejar de escuchar (Esc)" : "Hablarle (Ctrl+Alt+H)"}
          onClick={alternarEscucha}
          activo={escuchando}
        >
          <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
            <rect x="9" y="3" width="6" height="11" rx="3" />
            <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
          </svg>
        </BotonFlotante>
        <BotonFlotante titulo="Abrir el chat" onClick={() => cambiarVista("chat")}>
          <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
            <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
          </svg>
        </BotonFlotante>
      </div>
    </div>
  );
}

/** Botón redondo que flota a los pies de Dahiana. */
function BotonFlotante(props: { titulo: string; onClick: () => void; activo?: boolean; children: ReactNode }) {
  return (
    <button
      type="button"
      title={props.titulo}
      aria-label={props.titulo}
      onClick={props.onClick}
      className={`grid size-8 place-items-center rounded-full border border-white/10 shadow-lg shadow-black/40 backdrop-blur transition ${
        props.activo ? "animate-pulse bg-fuchsia-500 text-white" : "bg-noche/90 text-violet-200 hover:bg-fuchsia-500/40 hover:text-white"
      }`}
    >
      {props.children}
    </button>
  );
}
