// El orbe de Dahiana: respira en reposo, late al pensar, ondea al escuchar, habla al ritmo de su voz
// y se apaga cuando duerme. Además tiene vida propia: su color sigue su ánimo, mira hacia el cursor,
// nota cuando pasas el mouse y de vez en cuando hace un gesto espontáneo.
// No se desactiva con "reducir movimiento" de Windows: Nine pidió expresamente que el orbe tenga vida
// propia, y son movimientos suaves y lentos (sin destellos rápidos ni desplazamientos bruscos).
import { invoke } from "@tauri-apps/api/core";
import {
  animate,
  motion,
  type Transition,
  useMotionValue,
  useSpring,
  useTransform,
} from "motion/react";
import { useEffect, useRef } from "react";
import type { Animo, EstadoDahiana } from "../estado";
import { nivelDeVoz } from "../reproductor";

/** Parámetros de la animación de un estado (los arreglos son fotogramas clave de Motion). */
type Animacion = {
  escala: number[];
  resplandor: number[];
  duracion: number;
  anillo: boolean; // anillo girando (pensando / cargando)
  filtro: string;
};

const ANIMACIONES: Record<EstadoDahiana, Animacion> = {
  reposo: { escala: [1, 1.06, 1], resplandor: [0.45, 0.75, 0.45], duracion: 4, anillo: false, filtro: "" },
  escuchando: { escala: [1, 1.04, 1], resplandor: [0.6, 0.9, 0.6], duracion: 1.6, anillo: false, filtro: "brightness(1.15)" },
  pensando: { escala: [1, 1.1, 0.97, 1], resplandor: [0.6, 1, 0.6], duracion: 1.1, anillo: true, filtro: "" },
  // Al hablar, el tamaño lo marca la voz (nivelDeVoz); aquí solo un vaivén suave de fondo.
  hablando: { escala: [1, 1.02, 1], resplandor: [0.7, 0.9, 0.7], duracion: 2, anillo: false, filtro: "" },
  cargando: { escala: [0.95, 1, 0.95], resplandor: [0.2, 0.45, 0.2], duracion: 2.5, anillo: true, filtro: "saturate(0.5)" },
  dormida: { escala: [0.88, 0.9, 0.88], resplandor: [0.1, 0.2, 0.1], duracion: 6, anillo: false, filtro: "saturate(0.3) brightness(0.6)" },
  error: { escala: [1, 1.03, 1], resplandor: [0.4, 0.6, 0.4], duracion: 2, anillo: false, filtro: "hue-rotate(60deg)" },
};

// Color del ánimo como giro de tono sobre el morado base (así la transición entre colores es suave).
const TONO_POR_ANIMO: Record<Animo | "noche", string> = {
  tranquila: "",
  alegre: "hue-rotate(55deg)", // rosado cálido
  tierna: "hue-rotate(30deg) saturate(0.85)", // lila rosado suave
  emocionada: "hue-rotate(140deg) saturate(1.3)", // dorado
  curiosa: "hue-rotate(-110deg)", // turquesa
  preocupada: "hue-rotate(-55deg) saturate(0.8)", // azul
  noche: "hue-rotate(-45deg) brightness(0.85)", // azul suave y tranquilo
};

const ONDAS = [0, 0.6]; // retraso (s) de cada onda mientras escucha
const MIRAR_CADA_MS = 120; // cada cuánto consulta dónde está el cursor
const MIRADA_MAXIMA = 0.07; // cuánto se inclina hacia el cursor (fracción del tamaño)
const GESTO_CADA_S: [number, number] = [8, 20]; // gestos espontáneos: entre cuántos segundos

/** De noche (21 h a 6 h) su calma se vuelve azul. */
const esDeNoche = () => {
  const hora = new Date().getHours();
  return hora >= 21 || hora < 6;
};

/**
 * Orbe animado que representa a Dahiana.
 * @param estado - Define la animación (respirar, latir, escuchar, hablar, dormir...).
 * @param animo - Define el color (alegre, tierna, emocionada...).
 * @param tamano - Diámetro de la esfera en píxeles; el componente ocupa 1.6 veces eso.
 */
export function Orbe({ estado, animo, tamano = 112 }: { estado: EstadoDahiana; animo: Animo; tamano?: number }) {
  const a = ANIMACIONES[estado];
  const bucle: Transition = { duration: a.duracion, repeat: Infinity, ease: "easeInOut" };
  const contenedor = useRef<HTMLDivElement>(null);

  // Capa externa que crece con la voz (vale 1 cuando no habla); la interna sigue respirando.
  const escalaPorVoz = useTransform(nivelDeVoz, [0, 1], [1, 1.22]);
  const resplandorPorVoz = useTransform(nivelDeVoz, [0, 1], [1, 1.35]);

  // Mirada: desplazamiento hacia el cursor, con resorte para que se mueva con suavidad.
  const miradaX = useSpring(useMotionValue(0), { stiffness: 60, damping: 14 });
  const miradaY = useSpring(useMotionValue(0), { stiffness: 60, damping: 14 });
  const brilloX = useTransform(miradaX, (x) => x * 1.8); // el brillo se mueve más: parece que gira
  const brilloY = useTransform(miradaY, (y) => y * 1.8);

  // Gestos: saltito, "parpadeo" de luz y destello.
  const salto = useMotionValue(0);
  const achatado = useMotionValue(1);
  const destello = useMotionValue(0);

  const tono = animo === "tranquila" && esDeNoche() ? TONO_POR_ANIMO.noche : TONO_POR_ANIMO[animo];
  const filtro = [a.filtro, tono].filter(Boolean).join(" ") || "none";
  const transicionDeColor = { transition: "filter 1.5s ease" };

  useEffect(() => {
    const maximo = tamano * MIRADA_MAXIMA;
    const intervalo = window.setInterval(async () => {
      const caja = contenedor.current?.getBoundingClientRect();
      if (!caja || document.visibilityState !== "visible") return;
      try {
        const [x, y] = await invoke<[number, number]>("cursor_relativo");
        const dx = x - (caja.left + caja.width / 2);
        const dy = y - (caja.top + caja.height / 2);
        const distancia = Math.hypot(dx, dy) || 1;
        const intensidad = Math.min(1, distancia / 300); // de cerca mira menos exagerado
        miradaX.set((dx / distancia) * maximo * intensidad);
        miradaY.set((dy / distancia) * maximo * intensidad);
      } catch {
        // sin posición del cursor (ventana oculta): se queda mirando donde estaba
      }
    }, MIRAR_CADA_MS);
    return () => window.clearInterval(intervalo);
  }, [tamano, miradaX, miradaY]);

  useEffect(() => {
    if (estado !== "reposo") return;
    let temporizador = 0;
    const programar = () => {
      const [min, max] = GESTO_CADA_S;
      temporizador = window.setTimeout(() => {
        const gestos = [
          () => animate(salto, [0, -tamano * 0.08, 0], { duration: 0.6, ease: "easeOut" }),
          () => animate(achatado, [1, 0.88, 1], { duration: 0.35 }),
          () => animate(destello, [0, 0.55, 0], { duration: 0.9 }),
        ];
        gestos[Math.floor(Math.random() * gestos.length)]();
        programar();
      }, (min + Math.random() * (max - min)) * 1000);
    };
    programar();
    return () => window.clearTimeout(temporizador);
  }, [estado, tamano, salto, achatado, destello]);

  /** Nota que llegó el mouse: un pequeño brinco de alegría. */
  const notarMouse = () => {
    void animate(salto, [0, -tamano * 0.05, 0], { duration: 0.45 });
  };

  return (
    <div
      ref={contenedor}
      onMouseEnter={notarMouse}
      className="relative grid place-items-center"
      style={{ width: tamano * 1.6, height: tamano * 1.6 }}
    >
      {/* Resplandor */}
      <motion.div className="absolute" style={{ scale: resplandorPorVoz, x: miradaX, y: miradaY }}>
        <motion.div
          className="rounded-full"
          style={{
            width: tamano * 1.6,
            height: tamano * 1.6,
            filter: filtro,
            ...transicionDeColor,
            background: "radial-gradient(circle, rgba(217, 70, 239, 0.8) 30%, rgba(168, 85, 247, 0.3) 50%, transparent 70%)",
          }}
          animate={{ opacity: a.resplandor, scale: a.escala }}
          transition={bucle}
        />
      </motion.div>

      {/* Ondas mientras escucha */}
      {estado === "escuchando" &&
        ONDAS.map((retraso) => (
          <motion.div
            key={retraso}
            className="absolute rounded-full border-2 border-fuchsia-300"
            style={{ width: tamano, height: tamano, filter: tono || "none" }}
            initial={{ scale: 1, opacity: 0.7 }}
            animate={{ scale: 1.6, opacity: 0 }}
            transition={{ duration: 1.2, repeat: Infinity, delay: retraso, ease: "easeOut" }}
          />
        ))}

      {/* Anillo que gira mientras piensa */}
      <motion.div
        className="absolute rounded-full"
        style={{
          width: tamano * 1.18,
          height: tamano * 1.18,
          filter: tono || "none",
          background: "conic-gradient(from 0deg, transparent 0%, #e879f9 25%, transparent 50%, #a78bfa 75%, transparent 100%)",
          mask: "radial-gradient(farthest-side, transparent calc(100% - 3px), black calc(100% - 2px))",
        }}
        animate={{ opacity: a.anillo ? 1 : 0, rotate: 360 }}
        transition={{ opacity: { duration: 0.4 }, rotate: { duration: 1.6, repeat: Infinity, ease: "linear" } }}
      />

      {/* Esfera: voz (escala) > mirada y gestos (posición, saltito, parpadeo) > respiración */}
      <motion.div className="relative" style={{ scale: escalaPorVoz }}>
        <motion.div style={{ x: miradaX, y: salto, scaleY: achatado }}>
          <motion.div style={{ y: miradaY }}>
            <motion.div
              className="relative overflow-hidden rounded-full"
              style={{
                width: tamano,
                height: tamano,
                filter: filtro,
                ...transicionDeColor,
                background: "radial-gradient(circle at 35% 30%, #f5d0fe 0%, #c084fc 28%, #7e22ce 62%, #3b0764 100%)",
                boxShadow: "inset -10px -14px 30px rgba(24, 0, 48, 0.6), 0 0 40px rgba(192, 132, 252, 0.35)",
              }}
              animate={{ scale: a.escala }}
              transition={bucle}
            >
              {/* Brillo: sigue la mirada un poco más que la esfera */}
              <motion.div
                className="absolute rounded-full bg-white/60 blur-md"
                style={{ width: tamano * 0.28, height: tamano * 0.18, left: "22%", top: "16%", x: brilloX, y: brilloY }}
              />
              {/* Destello espontáneo */}
              <motion.div className="absolute inset-0 rounded-full bg-white" style={{ opacity: destello }} />
            </motion.div>
          </motion.div>
        </motion.div>
      </motion.div>
    </div>
  );
}
