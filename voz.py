"""La voz de Dahiana: escuchar (micrófono -> texto) y hablar (texto -> audio).

- Escuchar: graba el micrófono hasta que Nine deja de hablar (DetectorDeSilencio) y transcribe con
  faster-whisper en la CPU (local; la GPU AMD no está soportada en Windows).
- Hablar: voz neuronal de Edge TTS (en línea: el texto de la respuesta viaja a Microsoft). Si no hay
  internet, usa la voz de Windows configurada en VOZ["voz_sin_internet"].
"""

import asyncio
import os
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field

import numpy as np

from config import NOMBRE_USUARIO, VOZ

FRECUENCIA = 16_000  # Whisper trabaja con audio mono a 16 kHz
DURACION_BLOQUE = 0.03  # segundos por bloque de micrófono que se analiza
MARGEN_DEL_FILTRO = 0.9  # el filtro corta un poco antes de 8 kHz (el límite de 16 kHz) para dejar transición
RADIO_DEL_FILTRO = 50  # muestras a cada lado del núcleo: más = filtro más preciso pero más lento
HAZ_DE_BUSQUEDA = 5  # beam_size de Whisper: con 5 baja el error frente a 1 (medido) por ~0,2 s más por frase
# Contexto que se le da a Whisper: así espera los nombres y temas de siempre ("Discord", no "el disco").
CONTEXTO_WHISPER = (f"Conversación de {NOMBRE_USUARIO} con Dahiana, su asistente. Hablan de música, Spotify, "
                    "Discord, programación y su día.")
_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # solo existe en Windows


# ---------------------------------------------------------------- escuchar


@dataclass
class DetectorDeSilencio:
    """Decide, bloque a bloque, cuándo empezó y cuándo terminó de hablar Nine.

    Usa la energía (RMS) de cada bloque: los primeros bloques miden el ruido de fondo y el umbral de
    voz es varias veces ese ruido. Así funciona igual en una habitación silenciosa o con ventilador.

    Args:
        calibracion: Segundos iniciales para medir el ruido de fondo.
        espera_maxima: Segundos máximos esperando que empiece a hablar.
        silencio_final: Segundos de silencio que indican que terminó de hablar.
        duracion_maxima: Segundos máximos de grabación.
    """

    calibracion: float = 0.3
    espera_maxima: float = 8.0
    silencio_final: float = 1.2  # con 0,9 cortaba si Nine hacía una pausa corta a mitad de la frase
    duracion_maxima: float = 20.0
    _energias_ruido: list[float] = field(default_factory=list)
    _umbral: float | None = None
    _bloques: int = 0
    _bloques_con_voz: int = 0
    _bloques_en_silencio: int = 0
    _hablando: bool = False

    UMBRAL_MINIMO = 0.006  # energía mínima para considerar voz (evita que el ruido bajo dispare)
    FACTOR_RUIDO = 3.0  # la voz debe superar varias veces el ruido de fondo
    BLOQUES_PARA_EMPEZAR = 3  # bloques seguidos con voz para confirmar que empezó (~90 ms)

    def agregar(self, energia: float) -> str:
        """Procesa la energía de un bloque.

        Args:
            energia: RMS del bloque (0 a 1).

        Returns:
            "esperando", "hablando", "terminado" (dejó de hablar) o "sin_voz" (nunca habló).
        """
        self._bloques += 1
        transcurrido = self._bloques * DURACION_BLOQUE

        if self._umbral is None:
            self._energias_ruido.append(energia)
            if transcurrido >= self.calibracion:
                ruido = float(np.median(self._energias_ruido))
                self._umbral = max(ruido * self.FACTOR_RUIDO, self.UMBRAL_MINIMO)
            return "esperando"

        if transcurrido >= self.duracion_maxima:
            return "terminado" if self._hablando else "sin_voz"

        if not self._hablando:
            self._bloques_con_voz = self._bloques_con_voz + 1 if energia > self._umbral else 0
            if self._bloques_con_voz >= self.BLOQUES_PARA_EMPEZAR:
                self._hablando = True
                return "hablando"
            return "sin_voz" if transcurrido >= self.espera_maxima else "esperando"

        # Ya habla: cuenta el silencio seguido (con un umbral algo menor para no cortar palabras suaves).
        self._bloques_en_silencio = self._bloques_en_silencio + 1 if energia < self._umbral * 0.8 else 0
        if self._bloques_en_silencio * DURACION_BLOQUE >= self.silencio_final:
            return "terminado"
        return "hablando"


def _remuestrear(audio: np.ndarray, origen: int) -> np.ndarray:
    """Convierte audio de la frecuencia del micrófono a 16 kHz.

    Antes de bajar la frecuencia filtra lo que está sobre ~7 kHz (sinc con ventana de Hamming): sin ese
    filtro, los agudos del micrófono se "doblan" sobre la voz (aliasing) y Whisper entiende peor las
    eses, efes y nombres en inglés.
    """
    if origen == FRECUENCIA:
        return audio
    corte = MARGEN_DEL_FILTRO * (FRECUENCIA / 2) / origen  # frecuencia de corte, relativa a la de origen
    n = np.arange(-RADIO_DEL_FILTRO, RADIO_DEL_FILTRO + 1)
    nucleo = 2 * corte * np.sinc(2 * corte * n) * np.hamming(len(n))
    filtrado = np.convolve(audio, nucleo / nucleo.sum(), mode="same")
    tiempos_nuevos = np.arange(0, len(audio) / origen, 1 / FRECUENCIA)
    return np.interp(tiempos_nuevos, np.arange(len(audio)) / origen, filtrado).astype(np.float32)


class Oido:
    """Escucha el micrófono y transcribe lo que dice Nine con Whisper."""

    def __init__(self):
        self._modelo = None
        self._cargando = threading.Lock()

    def preparar(self) -> None:
        """Carga el modelo de Whisper (tarda ~15 s la primera vez); se puede llamar en segundo plano."""
        with self._cargando:
            if self._modelo is None:
                from faster_whisper import WhisperModel  # import tardío: tarda en importarse

                self._modelo = WhisperModel(
                    VOZ["whisper"], device="cpu", compute_type="int8", download_root=VOZ["carpeta_whisper"]
                )

    def escuchar(self, cancelar: threading.Event) -> str:
        """Graba hasta que Nine termina de hablar y devuelve lo que dijo.

        Args:
            cancelar: Si se activa, deja de grabar y devuelve "".

        Returns:
            El texto transcrito, o "" si no habló o se canceló.

        Raises:
            sounddevice.PortAudioError: Si no hay micrófono disponible.
        """
        audio = self._grabar(cancelar)
        return "" if audio is None else self.transcribir(audio)

    def transcribir(self, audio: np.ndarray) -> str:
        """Transcribe audio mono de 16 kHz (float32) a texto en español."""
        self.preparar()
        segmentos, _ = self._modelo.transcribe(
            audio,
            language="es",
            beam_size=HAZ_DE_BUSQUEDA,
            vad_filter=True,
            hotwords=VOZ["palabras_clave"],
            initial_prompt=CONTEXTO_WHISPER,
            condition_on_previous_text=False,  # cada frase es corta: sin esto, un error se arrastra
        )
        return " ".join(s.text.strip() for s in segmentos).strip()

    def _grabar(self, cancelar: threading.Event) -> np.ndarray | None:
        """Graba bloques del micrófono hasta que el detector diga que terminó. None si no habló."""
        import sounddevice as sd

        frecuencia = int(sd.query_devices(kind="input")["default_samplerate"])
        tamano = int(frecuencia * DURACION_BLOQUE)
        detector = DetectorDeSilencio()
        bloques: list[np.ndarray] = []

        with sd.InputStream(samplerate=frecuencia, channels=1, dtype="float32", blocksize=tamano) as microfono:
            while not cancelar.is_set():
                bloque, _ = microfono.read(tamano)
                bloque = bloque[:, 0].copy()
                bloques.append(bloque)
                estado = detector.agregar(float(np.sqrt(np.mean(bloque**2))))
                if estado == "sin_voz":
                    return None
                if estado == "terminado":
                    return _remuestrear(np.concatenate(bloques), frecuencia)
        return None


# ---------------------------------------------------------------- hablar


# Cómo cambia la voz con el ánimo: (velocidad en %, tono en Hz) sumados a los de VOZ.
AJUSTES_POR_ANIMO = {
    "alegre": (5, 6),
    "emocionada": (10, 10),
    "tierna": (-6, 3),
    "tranquila": (0, 0),
    "curiosa": (3, 4),
    "preocupada": (-8, -3),
}


def _ajustar(base: str, unidad: str, cambio: int) -> str:
    """Suma un cambio a un ajuste de Edge ("+0%", "+8Hz") y lo devuelve en el mismo formato."""
    valor = int(base.removesuffix(unidad) or 0) + cambio
    return f"{valor:+d}{unidad}"


def _preparar_texto(texto: str) -> str:
    """Aplica las correcciones de pronunciación de VOZ["pronunciacion"]."""
    for escrito, como_suena in VOZ["pronunciacion"].items():
        texto = texto.replace(escrito, como_suena)
    return texto


async def _edge(texto: str, animo: str = "tranquila") -> bytes:
    """Audio MP3 con la voz neuronal de Edge, con el tono y la velocidad del ánimo."""
    import edge_tts

    velocidad, tono = AJUSTES_POR_ANIMO.get(animo, (0, 0))
    audio = bytearray()
    comunicador = edge_tts.Communicate(texto, VOZ["voz"], rate=_ajustar(VOZ["velocidad"], "%", velocidad),
                                       pitch=_ajustar(VOZ["tono"], "Hz", tono))
    async for parte in comunicador.stream():
        if parte["type"] == "audio":
            audio += parte["data"]
    return bytes(audio)


def _voz_de_windows(texto: str) -> bytes:
    """Audio WAV con la voz de Windows (sin internet). El texto va por stdin: sin riesgo de comillas."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as archivo:
        ruta = archivo.name
    script = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        f"$s.SelectVoice('{VOZ['voz_sin_internet']}');"
        f"$s.SetOutputToWaveFile('{ruta}');"
        "$s.Speak([Console]::In.ReadToEnd()); $s.Dispose()"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", script], input=texto, encoding="utf-8",
            capture_output=True, timeout=30, check=True, creationflags=_SIN_VENTANA,
        )
        with open(ruta, "rb") as wav:
            return wav.read()
    finally:
        os.remove(ruta)


def sintetizar(texto: str, animo: str = "tranquila") -> tuple[bytes, str]:
    """Convierte texto en audio con la voz de Dahiana.

    Args:
        texto: Lo que Dahiana va a decir.
        animo: Su ánimo (brain.ANIMOS); ajusta el tono y la velocidad de la voz de Edge.

    Returns:
        (audio, tipo MIME): MP3 de Edge o, sin internet, WAV de la voz de Windows.

    Raises:
        RuntimeError: Si fallan las dos voces.
    """
    texto = _preparar_texto(texto)
    try:
        audio = asyncio.run(asyncio.wait_for(_edge(texto, animo), timeout=10))
        if audio:
            return audio, "audio/mpeg"
    except Exception:  # sin internet, servicio caído o voz inválida: se usa la de Windows
        pass
    try:
        return _voz_de_windows(texto), "audio/wav"
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(f"No pude generar la voz: {error}") from error
