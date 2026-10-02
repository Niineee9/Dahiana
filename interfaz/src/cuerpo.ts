// Lenguaje corporal de Dahiana: mueve los huesos de su avatar VRM sin animaciones grabadas.
// Cada cuadro se suman tres capas:
//   1. Postura (según estado y ánimo), a la que el cuerpo llega suavemente.
//   2. Vida: respiración, cambio de peso entre las piernas, brazos que se mecen y gestos al hablar.
//   3. Gestos puntuales (saludar, saltito de alegría, ladear la cabeza), con entrada y salida suaves.
//
// Convención de ejes (huesos normalizados de VRM: en reposo, pose T mirando a la cámara, +Z):
//   - Brazo: z baja o sube el brazo (izquierdo negativo baja, derecho positivo baja); x negativo lo
//     lleva hacia adelante. Antebrazo: y dobla el codo hacia adelante (izquierdo negativo, derecho positivo)
//     y z lo cruza hacia el cuerpo (izquierdo negativo, derecho positivo).
//   - Cuello y columna: x positivo inclina hacia adelante, y gira, z ladea.
//   - Pierna: x negativo adelanta el muslo; en la rodilla, x positivo la dobla.
import type { VRMHumanBoneName, VRMHumanoid } from "@pixiv/three-vrm";
import type { Animo, EstadoDahiana } from "./estado";

/** Rotaciones (radianes, x/y/z) de algunos huesos, sumadas a la pose T. */
type Pose = Partial<Record<VRMHumanBoneName, [number, number, number]>>;

/** Gestos puntuales que Dahiana puede hacer. */
export type Gesto = "saludar" | "saltito" | "ladear" | "girar" | "porra";

/** Lo que el cuerpo necesita saber en cada cuadro. */
export type Contexto = {
  estado: EstadoDahiana;
  animo: Animo;
  /** Volumen de su voz, de 0 a 1 (0 = callada). */
  voz: number;
  /** Cursor relativo a su cara, de -1 a 1 en cada eje. */
  mouse: { x: number; y: number };
};

const BRAZOS_ABAJO = 1.4; // VRoid exporta en pose T; así los brazos quedan relajados junto al cuerpo
const CODOS = 0.25; // un codo recto se ve de maniquí
const VELOCIDAD_POSTURA = 4; // qué tan rápido llega a una postura nueva (1/s)
const UMBRAL_VOZ = 0.04; // por debajo, se considera que está callada
const CAMBIO_DE_PESO_S = 7; // cada cuánto pasa el peso de una pierna a la otra

/** Pose relajada de pie: brazos abajo, codos y dedos un poco doblados, cadera algo ladeada. */
const POSE_BASE: Pose = {
  leftUpperArm: [0, 0, -BRAZOS_ABAJO],
  rightUpperArm: [0, 0, BRAZOS_ABAJO],
  leftLowerArm: [0, -CODOS, 0],
  rightLowerArm: [0, CODOS, 0],
  ...dedosDoblados(0.35),
};

/** Postura según lo que está haciendo (se suma a la base). */
const POSTURA_POR_ESTADO: Partial<Record<EstadoDahiana, Pose>> = {
  // Atenta: se inclina un poco hacia ti, ladea la cabeza y junta las manos adelante.
  escuchando: {
    spine: [0.05, 0, 0],
    neck: [0.02, 0, 0.12],
    leftUpperArm: [-0.35, 0, 0.1],
    rightUpperArm: [-0.35, 0, -0.1],
    leftLowerArm: [0, -1.0, -0.5],
    rightLowerArm: [0, 1.0, 0.5],
  },
  // Pensativa: mira hacia arriba, a un lado, con la mano bajo la barbilla (más arriba tapa la boca y
  // parece que tira un beso). En vida() la cabeza se mueve un poco mientras piensa.
  pensando: {
    neck: [-0.15, 0.2, 0.05],
    rightUpperArm: [-0.85, 0, -0.15],
    rightLowerArm: [0, 1.85, 0.5],
    leftUpperArm: [-0.3, 0, 0.15],
    leftLowerArm: [0, -1.2, -0.6],
  },
  // Dormida: cabecea, hombros caídos, brazos sueltos.
  dormida: {
    neck: [0.35, 0, 0.08],
    spine: [0.08, 0, 0],
    leftShoulder: [0, 0, -0.08],
    rightShoulder: [0, 0, 0.08],
    leftLowerArm: [0, CODOS * 0.5, 0],
    rightLowerArm: [0, -CODOS * 0.5, 0],
  },
  error: { neck: [0.12, 0, 0], spine: [0.04, 0, 0] },
};

/** Postura según cómo se siente (se suma a la del estado). */
const POSTURA_POR_ANIMO: Partial<Record<Animo, Pose>> = {
  // Preocupada: se encoge un poco, baja la mirada y junta las manos.
  preocupada: {
    spine: [0.05, 0, 0],
    neck: [0.08, 0, 0],
    leftShoulder: [0, 0.1, 0.05],
    rightShoulder: [0, -0.1, -0.05],
    leftLowerArm: [0, -0.5, 0],
    rightLowerArm: [0, 0.5, 0],
  },
  // Tierna: ladea la cabeza y junta las manos adelante, a la altura de la cadera, con algo de timidez.
  // (Con los brazos hacia atrás, las manos se perdían detrás del cuerpo.)
  tierna: {
    neck: [0, 0, -0.1],
    leftUpperArm: [-0.15, 0, 0.12],
    rightUpperArm: [-0.15, 0, -0.12],
    leftLowerArm: [0, -0.6, -0.45],
    rightLowerArm: [0, 0.6, 0.45],
  },
  // Curiosa: se asoma hacia adelante.
  curiosa: { spine: [0.04, 0, 0], neck: [0.03, 0, 0.08] },
  // Emocionada: más erguida y con los brazos algo abiertos.
  emocionada: { spine: [-0.03, 0, 0], leftUpperArm: [0, 0, 0.12], rightUpperArm: [0, 0, -0.12] },
};

/** Cómo es cada gesto: cuánto dura y qué suma en cada instante (`fase` de 0 a 1). */
type DefinicionDeGesto = {
  duracion: number;
  pose: (fase: number, t: number) => Pose;
  sonrisa: number;
  salto?: (fase: number) => number;
  /** Huesos que llegan antes a su pose (x veces más rápido), para que el gesto siga un orden natural. */
  adelanto?: Partial<Record<VRMHumanBoneName, number>>;
  /** Huesos que no pasan por la curva de entrada y salida (la pose ya trae su propio recorrido). */
  sinEnvolvente?: VRMHumanBoneName[];
};

/** Curva suave de 0 a 1 (arranca y termina despacio). */
const suave = (fase: number) => (1 - Math.cos(Math.PI * Math.min(1, Math.max(0, fase)))) / 2;

const GESTOS: Record<Gesto, DefinicionDeGesto> = {
  // Levanta la mano derecha junto a la cabeza y la agita.
  saludar: {
    duracion: 2.4,
    sonrisa: 0.5,
    // El codo se dobla antes de que el brazo termine de subir: si no, pasa estirado hacia el lado.
    adelanto: { rightLowerArm: 3, rightHand: 3 },
    pose: (_fase, t) => ({
      rightUpperArm: [-0.45, 0, -0.95],
      rightLowerArm: [0, -CODOS, -2.1 + Math.sin(t * 11) * 0.3],
      rightHand: [-1.4, 0, 0],
      neck: [0, 0, -0.08],
    }),
  },
  // Un saltito de alegría con los brazos un poco abiertos.
  saltito: {
    duracion: 0.9,
    sonrisa: 0.7,
    pose: () => ({ leftUpperArm: [0, 0, 0.3], rightUpperArm: [0, 0, -0.3], spine: [-0.04, 0, 0] }),
    salto: (fase) => Math.max(0, Math.sin(fase * Math.PI * 2)) * 0.05,
  },
  // Ladea la cabeza con una sonrisa (su gesto espontáneo de siempre).
  ladear: {
    duracion: 1.6,
    sonrisa: 0.35,
    pose: () => ({ neck: [0, 0, 0.12], spine: [0, 0, 0.03] }),
  },
  // Da una vuelta completa para lucir su ropa (al ponerse la de fin de semana).
  girar: {
    duracion: 1.8,
    sonrisa: 0.6,
    sinEnvolvente: ["hips"], // la vuelta entera: escalada por la curva no daría los 360°
    pose: (fase) => ({
      hips: [0, suave(fase) * Math.PI * 2, 0],
      leftUpperArm: [0, 0, 0.25], // los brazos se abren un poco con el giro
      rightUpperArm: [0, 0, -0.25],
    }),
  },
  // Porra de animadora: los dos brazos arriba en V, agitándolos, con dos saltitos.
  porra: {
    duracion: 2.2,
    sonrisa: 0.8,
    adelanto: { leftLowerArm: 2, rightLowerArm: 2 },
    pose: (_fase, t) => {
      const agitar = Math.sin(t * 10) * 0.15;
      return {
        leftUpperArm: [0, 0, 2.2 + agitar],
        rightUpperArm: [0, 0, -2.2 - agitar],
        leftLowerArm: [0, -0.3, 0],
        rightLowerArm: [0, 0.3, 0],
        spine: [-0.05, 0, 0],
        neck: [-0.08, 0, 0],
      };
    },
    salto: (fase) => Math.max(0, Math.sin(fase * Math.PI * 4)) * 0.04,
  },
};

/** Rotaciones de los dedos doblados hacia la palma (0 = estirados). */
function dedosDoblados(cuanto: number): Pose {
  const pose: Pose = {};
  for (const dedo of ["Index", "Middle", "Ring", "Little"] as const) {
    // El meñique se dobla más que el índice: así la mano se ve relajada, no en garra.
    const extra = { Index: 0, Middle: 0.1, Ring: 0.2, Little: 0.3 }[dedo];
    for (const falange of ["Proximal", "Intermediate", "Distal"] as const) {
      pose[`left${dedo}${falange}`] = [0, 0, -(cuanto + extra)];
      pose[`right${dedo}${falange}`] = [0, 0, cuanto + extra];
    }
  }
  pose.leftThumbProximal = [0, 0.3, 0];
  pose.rightThumbProximal = [0, -0.3, 0];
  return pose;
}

/** Suma poses hueso por hueso. */
function sumar(...poses: (Pose | undefined)[]): Pose {
  const total: Pose = {};
  for (const pose of poses) {
    if (!pose) continue;
    for (const [hueso, [x, y, z]] of Object.entries(pose) as [VRMHumanBoneName, [number, number, number]][]) {
      const actual = total[hueso] ?? [0, 0, 0];
      total[hueso] = [actual[0] + x, actual[1] + y, actual[2] + z];
    }
  }
  return total;
}

/** Curva de entrada y salida de un gesto: 0 al inicio y al final, 1 en el medio. */
const envolvente = (fase: number) => Math.sin(Math.min(1, Math.max(0, fase)) * Math.PI) ** 0.5;

/** El cuerpo de Dahiana: se crea con su esqueleto y se actualiza en cada cuadro. */
export class Cuerpo {
  private readonly humanoide: VRMHumanoid;
  /** Postura actual (suavizada) de cada hueso que alguna vez se movió. */
  private postura: Pose = {};
  private gesto: { nombre: Gesto; inicio: number } | null = null;
  private gestoPendiente: Gesto | null = null;
  private alturaCadera: number;

  /**
   * @param humanoide - Esqueleto del VRM (se usan sus huesos normalizados).
   */
  constructor(humanoide: VRMHumanoid) {
    this.humanoide = humanoide;
    this.alturaCadera = humanoide.getNormalizedBoneNode("hips")?.position.y ?? 0;
    this.postura = sumar(POSE_BASE);
  }

  /**
   * Pide un gesto; empieza en el próximo cuadro y reemplaza al que estuviera en curso.
   * @param nombre - Qué gesto hacer.
   */
  hacer(nombre: Gesto) {
    this.gestoPendiente = nombre;
  }

  /** True si está haciendo algún gesto. */
  ocupada(): boolean {
    return this.gesto !== null;
  }

  /**
   * Mueve el cuerpo un cuadro.
   * @param delta - Segundos desde el cuadro anterior.
   * @param t - Segundos desde que empezó la animación.
   * @param contexto - Estado, ánimo, voz y cursor actuales.
   * @returns Cuánto sonríe por el gesto en curso (de 0 a 1), para sumarlo a su expresión.
   */
  actualizar(delta: number, t: number, contexto: Contexto): number {
    if (this.gestoPendiente) {
      this.gesto = { nombre: this.gestoPendiente, inicio: t };
      this.gestoPendiente = null;
    }

    // 1. Postura: se acerca a la del estado y el ánimo sin saltos.
    // El estado manda sobre el ánimo: si ya mueve un hueso (la mano en la barbilla al pensar), el ánimo no
    // le suma encima; sumadas, las dos posturas cruzaban los brazos.
    const estado = POSTURA_POR_ESTADO[contexto.estado] ?? {};
    const animo = Object.fromEntries(
      Object.entries(POSTURA_POR_ANIMO[contexto.animo] ?? {}).filter(([hueso]) => !(hueso in estado)),
    ) as Pose;
    const objetivo = sumar(POSE_BASE, estado, animo);
    const paso = 1 - Math.exp(-delta * VELOCIDAD_POSTURA);
    const huesos = new Set([...Object.keys(objetivo), ...Object.keys(this.postura)]) as Set<VRMHumanBoneName>;
    for (const hueso of huesos) {
      const actual = this.postura[hueso] ?? [0, 0, 0];
      const meta = objetivo[hueso] ?? [0, 0, 0];
      this.postura[hueso] = [0, 1, 2].map((i) => actual[i] + (meta[i] - actual[i]) * paso) as [number, number, number];
    }

    // 2. Vida y 3. gesto, encima de la postura.
    const { pose: gesto, sonrisa, salto } = this.poseDelGesto(t);
    const final = sumar(this.postura, this.vida(t, contexto), gesto);
    for (const hueso of Object.keys(final) as VRMHumanBoneName[]) {
      const nodo = this.humanoide.getNormalizedBoneNode(hueso);
      const [x, y, z] = final[hueso]!;
      nodo?.rotation.set(x, y, z);
    }
    const cadera = this.humanoide.getNormalizedBoneNode("hips");
    if (cadera) cadera.position.y = this.alturaCadera + salto;
    return sonrisa;
  }

  /** Movimientos continuos: respirar, cambiar el peso de pierna, mecer los brazos, hablar con el cuerpo. */
  private vida(t: number, { estado, voz, mouse }: Contexto): Pose {
    const dormida = estado === "dormida";
    const respiracion = Math.sin(t * (dormida ? 1.1 : 1.6)); // más lenta cuando duerme
    // El peso pasa de una pierna a otra despacio, con una pausa en cada lado (no un péndulo).
    const peso = Math.tanh(Math.sin((t / CAMBIO_DE_PESO_S) * Math.PI * 2) * 2.5) * 0.045;
    const mecer = Math.sin(t * 0.9);
    const hablando = voz > UMBRAL_VOZ;
    // Pensando puede durar varios segundos: la cabeza va y viene despacio para que no parezca congelada.
    const pensar = estado === "pensando" ? 1 : 0;
    // Al hablar, los brazos acompañan el ritmo de la voz, alternando un poco cada mano.
    const energia = hablando ? Math.min(1, voz * 1.5) : 0;
    const ritmo = Math.sin(t * 4.2);

    return {
      hips: [0, peso * 0.5, peso],
      spine: [respiracion * 0.015, 0, -peso * 0.6 + mecer * 0.008],
      chest: [respiracion * 0.02, 0, -peso * 0.4],
      // Los hombros suben un poquito al inhalar.
      leftShoulder: [0, 0, -respiracion * 0.02],
      rightShoulder: [0, 0, respiracion * 0.02],
      // Las piernas compensan la cadera para que los pies sigan en el suelo; la que descansa dobla la rodilla.
      leftUpperLeg: [-Math.max(0, peso) * 1.2, 0, -peso],
      rightUpperLeg: [-Math.max(0, -peso) * 1.2, 0, -peso],
      leftLowerLeg: [Math.max(0, peso) * 2.4, 0, 0],
      rightLowerLeg: [Math.max(0, -peso) * 2.4, 0, 0],
      leftUpperArm: [mecer * 0.03 - energia * 0.2, 0, peso * 0.5 + energia * 0.1 * (1 + ritmo)],
      rightUpperArm: [-mecer * 0.03 - energia * 0.2, 0, peso * 0.5 - energia * 0.1 * (1 - ritmo)],
      leftLowerArm: [0, -energia * (0.5 + ritmo * 0.25), 0],
      rightLowerArm: [0, energia * (0.5 - ritmo * 0.25), 0],
      // La cabeza sigue al cursor y asiente un poco con la voz.
      neck: [mouse.y * 0.15 + energia * Math.sin(t * 7) * 0.04, mouse.x * 0.3 + pensar * Math.sin(t * 0.7) * 0.12, 0],
      head: [pensar * Math.sin(t * 0.5) * 0.04, mouse.x * 0.1, peso * -0.5 + pensar * Math.sin(t * 0.9) * 0.05],
      // Mientras piensa, el índice de la mano en la barbilla tamborilea un poquito.
      rightIndexProximal: [0, 0, pensar * Math.max(0, Math.sin(t * 5)) * 0.3],
    };
  }

  /** La pose del gesto en curso (ya multiplicada por su curva de entrada y salida). */
  private poseDelGesto(t: number): { pose: Pose; sonrisa: number; salto: number } {
    if (!this.gesto) return { pose: {}, sonrisa: 0, salto: 0 };
    const definicion = GESTOS[this.gesto.nombre];
    const fase = (t - this.gesto.inicio) / definicion.duracion;
    if (fase >= 1) {
      this.gesto = null;
      return { pose: {}, sonrisa: 0, salto: 0 };
    }
    const peso = envolvente(fase);
    const pose: Pose = {};
    for (const [hueso, [x, y, z]] of Object.entries(definicion.pose(fase, t)) as [VRMHumanBoneName, [number, number, number]][]) {
      const pesoHueso = definicion.sinEnvolvente?.includes(hueso)
        ? 1
        : Math.min(1, peso * (definicion.adelanto?.[hueso] ?? 1));
      pose[hueso] = [x * pesoHueso, y * pesoHueso, z * pesoHueso];
    }
    return { pose, sonrisa: definicion.sonrisa * peso, salto: definicion.salto?.(fase) ?? 0 };
  }
}
