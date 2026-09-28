// La conversación: burbujas de Nine y Dahiana, acciones y errores.
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef } from "react";
import type { Mensaje } from "../estado";

const ESTILOS: Record<Mensaje["autor"], string> = {
  nine: "self-end rounded-br-md bg-violet-600/80 text-white",
  dahiana: "self-start rounded-bl-md bg-white/10 text-violet-50",
  accion: "self-start bg-transparent px-1 py-0 text-xs text-fuchsia-300/80",
  error: "self-center bg-rose-500/15 text-xs text-rose-200",
};

export function Chat({ mensajes, pensando }: { mensajes: Mensaje[]; pensando: boolean }) {
  const final = useRef<HTMLDivElement>(null);

  useEffect(() => {
    final.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensajes.length, pensando]);

  if (mensajes.length === 0) {
    return (
      <div className="grid flex-1 place-items-center px-8 text-center text-sm text-violet-200/60">
        Escríbeme lo que necesites, aquí estoy para ti 💜
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col gap-2 overflow-y-auto px-4 py-2">
      <AnimatePresence initial={false}>
        {mensajes.map((m) => (
          <motion.div
            key={m.id}
            layout
            initial={{ opacity: 0, y: 8, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            className={`max-w-[85%] rounded-2xl px-3.5 py-2 text-sm leading-snug select-text ${ESTILOS[m.autor]}`}
          >
            {m.autor === "accion" ? `⚙ ${m.texto}` : m.texto}
          </motion.div>
        ))}
        {pensando && (
          <motion.div
            key="pensando"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex gap-1 self-start rounded-2xl rounded-bl-md bg-white/10 px-3.5 py-3"
          >
            {[0, 1, 2].map((i) => (
              <motion.span
                key={i}
                className="size-1.5 rounded-full bg-fuchsia-300"
                animate={{ opacity: [0.3, 1, 0.3] }}
                transition={{ duration: 1, repeat: Infinity, delay: i * 0.2 }}
              />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
      <div ref={final} />
    </div>
  );
}
