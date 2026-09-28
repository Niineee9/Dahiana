// El orbe de Dahiana: respira en reposo, late rápido al pensar y se apaga cuando duerme.
import { motion, type Transition } from "motion/react";
import type { EstadoDahiana } from "../estado";

type Animacion = {
  escala: number[];
  resplandor: number[];
  duracion: number;
  anillo: boolean; // anillo girando (pensando / cargando)
  filtro: string;
};

const ANIMACIONES: Record<EstadoDahiana, Animacion> = {
  reposo: { escala: [1, 1.06, 1], resplandor: [0.45, 0.75, 0.45], duracion: 4, anillo: false, filtro: "none" },
  pensando: { escala: [1, 1.1, 0.97, 1], resplandor: [0.6, 1, 0.6], duracion: 1.1, anillo: true, filtro: "none" },
  cargando: {
    escala: [0.95, 1, 0.95],
    resplandor: [0.2, 0.45, 0.2],
    duracion: 2.5,
    anillo: true,
    filtro: "saturate(0.5)",
  },
  dormida: {
    escala: [0.88, 0.9, 0.88],
    resplandor: [0.1, 0.2, 0.1],
    duracion: 6,
    anillo: false,
    filtro: "saturate(0.3) brightness(0.6)",
  },
  error: { escala: [1, 1.03, 1], resplandor: [0.4, 0.6, 0.4], duracion: 2, anillo: false, filtro: "hue-rotate(60deg)" },
};

export function Orbe({ estado, tamano = 112 }: { estado: EstadoDahiana; tamano?: number }) {
  const a = ANIMACIONES[estado];
  const bucle: Transition = { duration: a.duracion, repeat: Infinity, ease: "easeInOut" };

  return (
    <div className="relative grid place-items-center" style={{ width: tamano * 1.6, height: tamano * 1.6 }}>
      {/* Resplandor */}
      <motion.div
        className="absolute rounded-full"
        style={{
          width: tamano * 1.6,
          height: tamano * 1.6,
          filter: a.filtro,
          background: "radial-gradient(circle, rgba(217, 70, 239, 0.8) 30%, rgba(168, 85, 247, 0.3) 50%, transparent 70%)",
        }}
        animate={{ opacity: a.resplandor, scale: a.escala }}
        transition={bucle}
      />

      {/* Anillo que gira mientras piensa */}
      <motion.div
        className="absolute rounded-full"
        style={{
          width: tamano * 1.18,
          height: tamano * 1.18,
          background: "conic-gradient(from 0deg, transparent 0%, #e879f9 25%, transparent 50%, #a78bfa 75%, transparent 100%)",
          mask: "radial-gradient(farthest-side, transparent calc(100% - 3px), black calc(100% - 2px))",
        }}
        animate={{ opacity: a.anillo ? 1 : 0, rotate: 360 }}
        transition={{ opacity: { duration: 0.4 }, rotate: { duration: 1.6, repeat: Infinity, ease: "linear" } }}
      />

      {/* Esfera */}
      <motion.div
        className="relative rounded-full"
        style={{
          width: tamano,
          height: tamano,
          filter: a.filtro,
          background: "radial-gradient(circle at 35% 30%, #f5d0fe 0%, #c084fc 28%, #7e22ce 62%, #3b0764 100%)",
          boxShadow: "inset -10px -14px 30px rgba(24, 0, 48, 0.6), 0 0 40px rgba(192, 132, 252, 0.35)",
        }}
        animate={{ scale: a.escala }}
        transition={bucle}
      >
        {/* Brillo */}
        <div
          className="absolute rounded-full bg-white/60 blur-md"
          style={{ width: tamano * 0.28, height: tamano * 0.18, left: "22%", top: "16%" }}
        />
      </motion.div>
    </div>
  );
}
