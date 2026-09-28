// Reproduce la voz de Dahiana y mide su volumen para que el orbe "hable" al ritmo del audio.
import { motionValue } from "motion/react";

/** Volumen actual de la voz (0 a 1), suavizado. El orbe lo usa para latir mientras habla. */
export const nivelDeVoz = motionValue(0);

const SUAVIZADO = 0.35; // 0 = sin cambios, 1 = sigue el audio sin suavizar
const GANANCIA = 4; // el habla normal tiene RMS bajo (~0.1): se amplifica para que se note

let audioActual: HTMLAudioElement | null = null;
let contexto: AudioContext | null = null;
let cuadro = 0; // id de requestAnimationFrame

/**
 * Reproduce un audio (data URL) cortando el que esté sonando.
 * @param audio - `data:audio/...;base64,...` enviado por servicio.py.
 * @param alEmpezar - Se llama cuando empieza a sonar.
 * @param alTerminar - Se llama al terminar, al fallar o al detenerlo.
 */
export function reproducir(audio: string, alEmpezar: () => void, alTerminar: () => void) {
  detener();
  const elemento = new Audio(audio);
  audioActual = elemento;

  contexto ??= new AudioContext();
  const analizador = contexto.createAnalyser();
  analizador.fftSize = 512;
  contexto.createMediaElementSource(elemento).connect(analizador);
  analizador.connect(contexto.destination);
  const muestras = new Uint8Array(analizador.fftSize);

  const medir = () => {
    analizador.getByteTimeDomainData(muestras);
    let suma = 0;
    for (const m of muestras) suma += ((m - 128) / 128) ** 2; // 128 = silencio
    const nivel = Math.min(1, Math.sqrt(suma / muestras.length) * GANANCIA);
    nivelDeVoz.set(nivelDeVoz.get() + (nivel - nivelDeVoz.get()) * SUAVIZADO);
    cuadro = requestAnimationFrame(medir);
  };

  const terminar = () => {
    if (audioActual !== elemento) return; // ya lo reemplazó otro audio
    cancelAnimationFrame(cuadro);
    nivelDeVoz.set(0);
    audioActual = null;
    alTerminar();
  };

  elemento.onplay = () => {
    void contexto?.resume();
    alEmpezar();
    medir();
  };
  elemento.onended = terminar;
  elemento.onerror = terminar;
  elemento.play().catch(terminar);
}

/** Corta la voz si está sonando (por ejemplo, cuando Nine vuelve a hablar). */
export function detener() {
  if (!audioActual) return;
  const elemento = audioActual;
  elemento.pause();
  elemento.onended?.(new Event("ended"));
}
