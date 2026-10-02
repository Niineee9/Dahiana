// Avatar 3D de Dahiana: su modelo VRM (diseñado en VRoid Studio) con three.js y @pixiv/three-vrm.
// Respira, parpadea, sigue el cursor con la mirada, mueve la boca con su voz, cambia de expresión con su
// ánimo, de pose con su estado y de ropa con su atuendo. Si el modelo no está (public/avatar/dahiana.vrm),
// se muestra el orbe.
import { VRMLoaderPlugin, VRMUtils, type VRM } from "@pixiv/three-vrm";
import { invoke } from "@tauri-apps/api/core";
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader, type GLTF } from "three/addons/loaders/GLTFLoader.js";
import { Cuerpo, type Gesto } from "../cuerpo";
import { useDahiana, type Animo, type Atuendo, type EstadoDahiana } from "../estado";
import { nivelDeVoz } from "../reproductor";
import { Orbe } from "./Orbe";

/** Dónde vive el modelo (fuera del repositorio: es el diseño propio de Nine). */
export const RUTA_AVATAR = "/avatar/dahiana.vrm";

/** Un modelo por atuendo (mismo esqueleto y expresiones); si falta uno, se usa RUTA_AVATAR. */
const RUTA_POR_ATUENDO: Record<Atuendo, string> = {
  normal: RUTA_AVATAR,
  fin_de_semana: "/avatar/dahiana_fin_de_semana.vrm",
  animadora: "/avatar/dahiana_animadora.vrm",
};

/** Qué hace al ponerse cada ropa: da una vuelta para lucir la de fin de semana, una porra de animadora... */
const GESTO_AL_CAMBIAR: Record<Atuendo, Gesto> = { normal: "saltito", fin_de_semana: "girar", animadora: "porra" };

const FUNDIDO_MS = 300; // se desvanece mientras carga la ropa nueva (cargar 17 MB traba un instante)
const ESPERA_ATUENDO_S = 3; // al arrancar, cuánto espera a que el servicio diga qué ropa lleva

// Tope de cuadros: aprovecha pantallas de hasta 100 Hz (la de Nine) sin gastar de más en las de 144 Hz
// (cada cuadro cuesta ~1,5 ms).
const CUADROS_POR_SEGUNDO = 100;
const TOLERANCIA_CUADRO_S = 0.002; // requestAnimationFrame no llega exacto: sin margen, se saltaría cuadros
const CAMPO_DE_VISION = 20; // grados; un lente "tele" deforma menos la cara que uno angular
const MIRAR_CADA_MS = 50;
const VELOCIDAD_MIRADA = 8; // qué tan rápido gira hacia el cursor (1/s): suave, sin saltar entre lecturas
const ALCANCE_MIRADA_PX = 350; // a esta distancia de su cara, ya mira del todo hacia el cursor
const SUAVIZADO_EXPRESION = 0.08; // qué tan rápido cambia de expresión (por cuadro)
const UMBRAL_VOZ = 0.04; // volumen de su voz por debajo del cual se considera callada
const CALLADA_TRAS_S = 0.8; // segundos sin voz para cerrar la boca (las pausas entre frases no cuentan)
const FELIZ_CON_BOCA_CERRADA = 0.15; // cuánto "happy" (boca abierta) queda al sonreír callada
const SORPRESA_CON_BOCA_CERRADA = 0.3;
const PARPADEO_CADA_S: [number, number] = [2, 6];
const DURACION_PARPADEO_S = 0.15;
const GESTO_CADA_S: [number, number] = [8, 20];
const SALUDO_CADA_S = 60; // al pasar el mouse saluda con la mano, pero no cada vez: entre medio, ladea la cabeza
const MARGEN = 0.03; // metros de aire sobre la punta del pelo (y bajo los pies, de cuerpo entero)
/** Difumina el borde de abajo para que el cuerpo no termine en un corte recto. */
const DIFUMINADO = "linear-gradient(to bottom, black 70%, transparent 100%)";

/** Cuánto del cuerpo se ve: alto visible en metros del mundo VRM (null = de pies a cabeza). */
const ENCUADRES = { busto: 0.55, cuerpo: null } as const;
export type Encuadre = keyof typeof ENCUADRES;

type Expresion = "happy" | "relaxed" | "surprised" | "sad" | "angry";
const EXPRESIONES: Expresion[] = ["happy", "relaxed", "surprised", "sad", "angry"];

/** Expresión de cada ánimo (pesos de 0 a 1; en VRoid "happy" alto cierra los ojos, por eso no llega a 1). */
const EXPRESION_POR_ANIMO: Record<Animo, Partial<Record<Expresion, number>>> = {
  tranquila: { relaxed: 0.15 },
  alegre: { happy: 0.55 },
  emocionada: { happy: 0.75, surprised: 0.25 },
  tierna: { relaxed: 0.6, happy: 0.15 },
  curiosa: { surprised: 0.35 },
  preocupada: { sad: 0.55 },
};

let comprobacion: Promise<boolean> | null = null;

/** True si el modelo existe (se comprueba una sola vez). */
function hayAvatar(): Promise<boolean> {
  comprobacion ??= fetch(RUTA_AVATAR, { method: "HEAD" }).then((r) => r.ok).catch(() => false);
  return comprobacion;
}

const entre = ([min, max]: [number, number]) => min + Math.random() * (max - min);
const acotar = (valor: number, limite: number) => Math.max(-limite, Math.min(limite, valor));

/**
 * Presencia de Dahiana: su avatar 3D si el modelo existe, o el orbe si no.
 * @param estado - Pose y animación (escuchando, pensando, dormida...).
 * @param animo - Expresión (alegre, tierna...); el orbe lo usa como color.
 * @param ancho - Ancho en píxeles del lienzo del avatar.
 * @param alto - Alto en píxeles del lienzo del avatar.
 * @param encuadre - Cuánto del cuerpo se ve.
 * @param tamanoOrbe - Tamaño del orbe si no hay avatar.
 */
export function Presencia(props: {
  estado: EstadoDahiana;
  animo: Animo;
  ancho: number;
  alto: number;
  encuadre: Encuadre;
  tamanoOrbe: number;
}) {
  const [disponible, setDisponible] = useState<boolean | null>(null);
  const [fallo, setFallo] = useState(false);
  useEffect(() => {
    void hayAvatar().then(setDisponible);
  }, []);

  if (disponible === null) return <div style={{ width: props.ancho, height: props.alto }} />;
  if (!disponible || fallo) return <Orbe estado={props.estado} animo={props.animo} tamano={props.tamanoOrbe} />;
  return <Avatar {...props} alFallar={() => setFallo(true)} />;
}

/** El avatar 3D (ver Presencia). */
function Avatar(props: {
  estado: EstadoDahiana;
  animo: Animo;
  ancho: number;
  alto: number;
  encuadre: Encuadre;
  alFallar: () => void;
}) {
  const lienzo = useRef<HTMLCanvasElement>(null);
  // Lo que cambia sin reconstruir la escena: se lee en cada cuadro.
  const estado = useRef(props.estado);
  const animo = useRef(props.animo);
  const encuadre = useRef(props.encuadre);
  const mouse = useRef({ x: 0, y: 0 }); // posición del cursor relativa al avatar, de -1 a 1 (última lectura)
  const notoMouse = useRef(false); // el mouse acaba de llegar: el bucle decide cómo reaccionar
  const tamano = useRef({ ancho: props.ancho, alto: props.alto });
  estado.current = props.estado;
  animo.current = props.animo;
  encuadre.current = props.encuadre;
  tamano.current = { ancho: props.ancho, alto: props.alto };
  const alFallar = useRef(props.alFallar); // en ref: si fuera dependencia, la escena se rehará en cada render
  alFallar.current = props.alFallar;
  const atuendo = useRef<Atuendo | null>(null);
  atuendo.current = useDahiana((s) => s.atuendo);

  useEffect(() => {
    const canvas = lienzo.current!;
    const renderizador = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
    renderizador.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    const escena = new THREE.Scene();
    const camara = new THREE.PerspectiveCamera(CAMPO_DE_VISION, 1, 0.1, 20);
    const luz = new THREE.DirectionalLight(0xffffff, Math.PI);
    luz.position.set(1, 1, 1).normalize();
    escena.add(luz, new THREE.AmbientLight(0xffffff, 0.4));
    const objetivoMirada = new THREE.Object3D(); // hacia donde miran los ojos
    escena.add(objetivoMirada);

    let vrm: VRM | null = null;
    let cuerpo: Cuerpo | null = null;
    const mirada = { x: 0, y: 0 }; // hacia dónde mira de verdad: sigue a `mouse` suavemente
    let animoAnterior = animo.current;
    let ultimoSaludo = 0;
    let ultimaVoz = -Infinity; // cuándo se oyó su voz por última vez
    let cima = 1.6; // altura de la punta del pelo, en metros
    const cara = new THREE.Vector3(0, 1 / 3, 0); // dónde está la cara en el lienzo (0 a 1, desde arriba a la izquierda)
    let cuadro = 0;
    let cancelado = false;
    let proximoParpadeo = entre(PARPADEO_CADA_S);
    let proximoGesto = entre(GESTO_CADA_S);
    const reloj = new THREE.Timer();
    let acumulado = 0;

    const cargador = new GLTFLoader();
    cargador.register((parser) => new VRMLoaderPlugin(parser));
    let atuendoPuesto: Atuendo | null = null; // la ropa del modelo que está en escena
    let cambiando = false;

    /** Carga el modelo de una ropa y reemplaza al que está en escena (con fundido si ya había uno). */
    const ponerse = (pedido: Atuendo) => {
      cambiando = true;
      const primeraVez = vrm === null;
      canvas.style.opacity = "0";
      window.setTimeout(() => {
        cargador
          .loadAsync(RUTA_POR_ATUENDO[pedido])
          // Si falta el archivo de esa ropa, la de siempre (y si falta esa, el orbe).
          .catch((error) => (pedido === "normal" ? Promise.reject(error) : cargador.loadAsync(RUTA_AVATAR)))
          .then((gltf: GLTF) => {
            if (cancelado) return VRMUtils.deepDispose(gltf.scene);
            const nuevo = gltf.userData.vrm as VRM;
            VRMUtils.removeUnnecessaryVertices(gltf.scene); // más liviano en la GPU
            VRMUtils.combineSkeletons(gltf.scene);
            VRMUtils.rotateVRM0(nuevo); // los VRM 0.x miran al revés; en 1.0 no hace nada
            nuevo.scene.traverse((objeto) => (objeto.frustumCulled = false)); // evita que se "corten" partes
            if (vrm) {
              escena.remove(vrm.scene);
              VRMUtils.deepDispose(vrm.scene);
            }
            vrm = nuevo;
            escena.add(vrm.scene);
            cuerpo = new Cuerpo(vrm.humanoid);
            cuerpo.actualizar(1, 0, { estado: estado.current, animo: animo.current, voz: 0, mouse: mouse.current });
            vrm.update(0);
            cima = new THREE.Box3().setFromObject(vrm.scene).max.y;
            if (vrm.lookAt) vrm.lookAt.target = objetivoMirada;
            cuerpo.hacer(primeraVez ? "saludar" : GESTO_AL_CAMBIAR[pedido]); // te saluda al aparecer
            atuendoPuesto = pedido;
            canvas.style.opacity = "1";
          })
          .catch(() => alFallar.current())
          .finally(() => (cambiando = false));
      }, primeraVez ? 0 : FUNDIDO_MS);
    };

    /** Coloca la cámara para el encuadre y el tamaño actuales. */
    let ultimoEncuadre = "";
    const encuadrar = () => {
      const { ancho, alto } = tamano.current;
      const clave = `${ancho}x${alto}:${encuadre.current}:${cima}`;
      if (clave === ultimoEncuadre) return; // setSize reinicia el lienzo: solo cuando algo cambió
      ultimoEncuadre = clave;
      renderizador.setSize(ancho, alto, false);
      camara.aspect = ancho / alto;
      const altoVisible = ENCUADRES[encuadre.current] ?? cima + 2 * MARGEN;
      const distancia = altoVisible / (2 * Math.tan(THREE.MathUtils.degToRad(CAMPO_DE_VISION / 2)));
      const centro = cima + MARGEN - altoVisible / 2; // la cabeza entera, arriba
      camara.position.set(0, centro, distancia);
      camara.lookAt(0, centro, 0);
      camara.updateProjectionMatrix();
    };

    /** Un cuadro de animación: pose, expresión, boca, mirada y física. */
    const animar = (delta: number, t: number) => {
      if (!vrm || !cuerpo) return;
      const expresiones = vrm.expressionManager!;
      const voz = nivelDeVoz.get();

      // Reacciones: saludo o ladeo al llegar el mouse, saltito cuando se alegra.
      if (notoMouse.current) {
        notoMouse.current = false;
        if (t - ultimoSaludo > SALUDO_CADA_S) {
          ultimoSaludo = t;
          cuerpo.hacer("saludar");
        } else if (!cuerpo.ocupada()) cuerpo.hacer("ladear");
      }
      if (animo.current !== animoAnterior) {
        if (animo.current === "emocionada" || animo.current === "alegre") cuerpo.hacer("saltito");
        animoAnterior = animo.current;
      }

      // Cuerpo: postura, respiración, peso, gestos al hablar y cabeza hacia el cursor.
      const paso = 1 - Math.exp(-delta * VELOCIDAD_MIRADA);
      mirada.x += (mouse.current.x - mirada.x) * paso;
      mirada.y += (mouse.current.y - mirada.y) * paso;
      const sonrisa = cuerpo.actualizar(delta, t, { estado: estado.current, animo: animo.current, voz, mouse: mirada });

      // Ojos: miran hacia el cursor (un objetivo delante de la cámara).
      objetivoMirada.position.set(mirada.x * 0.6, camara.position.y - mirada.y * 0.4, camara.position.z);

      // Expresión del ánimo (y la sonrisa del gesto), con transición suave.
      const deseada = { ...EXPRESION_POR_ANIMO[animo.current] };
      if (estado.current === "escuchando") deseada.surprised = (deseada.surprised ?? 0) + 0.15;
      if (estado.current === "error") deseada.sad = Math.max(deseada.sad ?? 0, 0.4);
      // En VRoid "happy" y "surprised" abren la boca: callada, se quedaba con la boca abierta. Sin hablar,
      // sonríe con la boca cerrada ("relaxed") y la sorpresa se suaviza.
      if (voz > UMBRAL_VOZ) ultimaVoz = t;
      if (t - ultimaVoz > CALLADA_TRAS_S) {
        const feliz = deseada.happy ?? 0;
        deseada.relaxed = Math.max(deseada.relaxed ?? 0, feliz * 0.8);
        deseada.happy = feliz * FELIZ_CON_BOCA_CERRADA;
        deseada.surprised = (deseada.surprised ?? 0) * SORPRESA_CON_BOCA_CERRADA;
      }
      deseada.happy = Math.max(deseada.happy ?? 0, sonrisa); // los gestos (porra, saludo) sí sonríen abierto
      for (const nombre of EXPRESIONES) {
        const actual = expresiones.getValue(nombre) ?? 0;
        expresiones.setValue(nombre, actual + ((deseada[nombre] ?? 0) - actual) * SUAVIZADO_EXPRESION);
      }

      // Parpadeo natural; dormida, ojos cerrados.
      proximoParpadeo -= delta;
      if (proximoParpadeo < 0) proximoParpadeo = entre(PARPADEO_CADA_S);
      const parpadeando = proximoParpadeo < DURACION_PARPADEO_S;
      expresiones.setValue("blink", estado.current === "dormida" ? 1 : parpadeando ? 1 : 0);

      // Boca: sigue el volumen de su voz (con un poco de "o" para que no sea siempre la misma forma).
      expresiones.setValue("aa", Math.min(1, voz * 1.2));
      expresiones.setValue("oh", voz * 0.3 * (1 + Math.sin(t * 9)) * 0.5);

      // Gestos espontáneos en reposo: ladear la cabeza y sonreír.
      if (estado.current === "reposo") {
        proximoGesto -= delta;
        if (proximoGesto < 0) {
          proximoGesto = entre(GESTO_CADA_S);
          if (!cuerpo.ocupada()) cuerpo.hacer("ladear");
        }
      }

      vrm.update(delta); // aplica expresiones, mirada y la física del pelo y la ropa
    };

    const bucle = (instante?: number) => {
      cuadro = requestAnimationFrame(bucle);
      reloj.update(instante);
      acumulado += reloj.getDelta();
      if (acumulado < 1 / CUADROS_POR_SEGUNDO - TOLERANCIA_CUADRO_S || document.visibilityState !== "visible") return;
      const delta = Math.min(acumulado, 0.1); // tras una pausa, que la física no dé un salto
      acumulado = 0; // el tiempo real transcurrido va en `delta`: la animación no pierde ritmo
      // ¿Toca cambiarse de ropa? Al arrancar espera un poco a saber cuál lleva puesta.
      const pedido = atuendo.current ?? (reloj.getElapsed() > ESPERA_ATUENDO_S ? "normal" : null);
      if (pedido && !cambiando && pedido !== atuendoPuesto) ponerse(pedido);
      encuadrar();
      animar(delta, reloj.getElapsed());
      renderizador.render(escena, camara);
      if (vrm) {
        // La mirada se calcula desde la cara, que según el encuadre puede estar arriba o al centro.
        const proyectada = vrm.humanoid.getNormalizedBoneNode("head")!.getWorldPosition(new THREE.Vector3()).project(camara);
        cara.set((proyectada.x + 1) / 2, (1 - proyectada.y) / 2, 0);
      }
    };
    bucle();

    // Mirada: dónde está el cursor respecto del centro del avatar (aunque esté fuera de la ventana).
    const intervalo = window.setInterval(async () => {
      const caja = canvas.getBoundingClientRect();
      if (document.visibilityState !== "visible") return;
      try {
        const [x, y] = await invoke<[number, number]>("cursor_relativo");
        mouse.current = {
          x: acotar((x - (caja.left + caja.width * cara.x)) / ALCANCE_MIRADA_PX, 1),
          y: acotar((y - (caja.top + caja.height * cara.y)) / ALCANCE_MIRADA_PX, 1),
        };
      } catch {
        // sin posición del cursor (ventana oculta): sigue mirando donde estaba
      }
    }, MIRAR_CADA_MS);

    return () => {
      cancelado = true;
      cancelAnimationFrame(cuadro);
      window.clearInterval(intervalo);
      if (vrm) VRMUtils.deepDispose(vrm.scene);
      reloj.dispose();
      renderizador.dispose();
    };
  }, []);

  /** Nota que llegó el mouse (el bucle decide si saluda o ladea la cabeza). */
  const notarMouse = () => {
    notoMouse.current = true;
  };

  return (
    <canvas
      ref={lienzo}
      onMouseEnter={notarMouse}
      style={{
        width: props.ancho,
        height: props.alto,
        maskImage: props.encuadre === "busto" ? DIFUMINADO : undefined,
        opacity: 0, // aparece (y se funde al cambiar de ropa) cuando su modelo terminó de cargar
        transition: `opacity ${FUNDIDO_MS}ms`,
      }}
    />
  );
}
