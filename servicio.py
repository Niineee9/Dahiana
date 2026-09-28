"""Dahiana como servicio para la interfaz (Tauri).

La interfaz lanza este proceso y se comunican con una línea JSON por mensaje.
  Entrada (stdin):  {"tipo": "mensaje", "texto": "...", "hablar": true | false}
                    {"tipo": "escuchar"}                     (graba el micrófono; responde con voz)
                    {"tipo": "cancelar"}                     (deja de escuchar)
                    {"tipo": "reiniciar"}
                    {"tipo": "motor", "accion": "encender" | "apagar"}   (apagar = modo juego)
                    {"tipo": "preferencias", "voz": bool, "orbe": bool, "atenta": bool}
  Salida (stdout):  {"tipo": "motor", "estado": "cargando" | "encendido" | "apagado" | "fallo"}
                    {"tipo": "listo"}
                    {"tipo": "escuchando"}
                    {"tipo": "transcripcion", "texto": "..."}   (lo que dijo Nine)
                    {"tipo": "no_escuche"}   |   {"tipo": "escucha_cancelada"}
                    {"tipo": "pensando"}
                    {"tipo": "accion", "nombre": "...", "argumentos": "...", "resultado": "..."}
                    {"tipo": "respuesta", "texto": "...", "animo": "alegre" | "tierna" | ...}
                    {"tipo": "iniciativa", "texto": "...", "animo": "..."}   (Dahiana habla primero)
                    {"tipo": "voz", "audio": "data:audio/mpeg;base64,..."}   (después de "respuesta"/"iniciativa")
                    {"tipo": "vista", "vista": "orbe" | "chat"}   (Nine pidió ocultar o mostrar el chat)
                    {"tipo": "error", "texto": "..."}

stdout queda reservado para el protocolo: nada más debe imprimir ahí (los registros van a stderr).
Si cambias el protocolo, actualiza también interfaz/src/estado.ts y interfaz/src-tauri/src/lib.rs.
"""

import base64
import datetime
import json
import queue
import sys
import threading
import time
from dataclasses import dataclass, field

import openai

import spotify
import tools
from brain import Dahiana
from config import MODELO, NOMBRE_USUARIO, URL_SERVIDOR
from iniciativa import Motivo, Vigia, observar
from motor import Motor, esta_activo
from voz import Oido, sintetizar

REVISAR_CADA = 60  # segundos entre revisiones del vigía
ESPERA_INICIAL = 20  # segundos antes de la primera revisión (la interfaz termina de arrancar)
CONSULTAR_CANCION_CADA = 5 * 60  # segundos entre consultas a Spotify de lo que suena


@dataclass
class Sesion:
    """Lo que comparten el hilo de peticiones y el del vigía."""

    dahiana: Dahiana
    motor: Motor
    oido: Oido
    vigia: Vigia
    # Lo que la interfaz dice de sí misma: si la voz está activa, si está en modo orbe y si Dahiana
    # puede comentar lo que Nine hace (juego, código, música).
    preferencias: dict = field(default_factory=lambda: {"voz": True, "orbe": False, "atenta": True})
    candado: threading.Lock = field(default_factory=threading.Lock)  # protege al vigía

    def registrar_interaccion(self) -> None:
        """Nine le habló: el vigía reinicia la cuenta del silencio."""
        with self.candado:
            self.vigia.registrar_interaccion(datetime.datetime.now())


def _enviar(evento: dict) -> None:
    """Envía un evento a la interfaz (una línea JSON por stdout)."""
    sys.stdout.write(json.dumps(evento, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _avisar_accion(nombre: str, argumentos: str, resultado: str) -> None:
    """Avisa a la interfaz que Dahiana usó una herramienta."""
    _enviar({"tipo": "accion", "nombre": nombre, "argumentos": argumentos, "resultado": resultado})


def _encender(motor: Motor) -> bool:
    """Enciende el modelo avisando a la interfaz cómo va. Devuelve True si quedó encendido."""
    _enviar({"tipo": "motor", "estado": "cargando"})
    encendido = motor.encender()
    _enviar({"tipo": "motor", "estado": "encendido" if encendido else "fallo"})
    return encendido


def _hablar(texto: str, animo: str) -> None:
    """Envía a la interfaz el audio con el tono del ánimo; si falla la voz, Dahiana solo responde por texto."""
    try:
        audio, tipo = sintetizar(texto, animo)
    except RuntimeError as error:
        _enviar({"tipo": "error", "texto": str(error)})
        return
    _enviar({"tipo": "voz", "audio": f"data:{tipo};base64,{base64.b64encode(audio).decode()}"})


def _responder(sesion: Sesion, texto: str, hablar: bool) -> None:
    """Responde un mensaje de Nine; los errores del modelo llegan a la interfaz como eventos."""
    sesion.registrar_interaccion()
    # Si estaba en modo juego, escribirle la despierta.
    if not esta_activo() and not _encender(sesion.motor):
        _enviar({"tipo": "error", "texto": "No pude encender el modelo. Revisa MOTOR en config.py."})
        return
    _enviar({"tipo": "pensando"})
    try:
        respuesta = sesion.dahiana.responder(texto)
    except openai.APIConnectionError:
        _enviar({"tipo": "error", "texto": f"No pude conectarme al modelo en {URL_SERVIDOR}."})
        return
    except (openai.NotFoundError, openai.BadRequestError) as error:
        _enviar({"tipo": "error", "texto": f"Problema con el modelo '{MODELO}': {error}"})
        return
    except openai.APIError as error:
        _enviar({"tipo": "error", "texto": f"Error del servidor de modelos: {error}"})
        return
    _enviar({"tipo": "respuesta", "texto": respuesta, "animo": sesion.dahiana.animo})
    if hablar and respuesta:
        _hablar(respuesta, sesion.dahiana.animo)
    try:  # después de responder, para no hacer esperar a Nine
        sesion.dahiana.actualizar_memoria(texto)
    except openai.APIError:
        pass  # si falla, solo se pierde lo de este mensaje; no vale la pena molestar a Nine


def _escuchar(sesion: Sesion, cancelar: threading.Event) -> None:
    """Graba lo que dice Nine, lo muestra y lo responde en voz alta."""
    cancelar.clear()
    _enviar({"tipo": "escuchando"})
    try:
        texto = sesion.oido.escuchar(cancelar)
    except Exception as error:  # sin micrófono, dispositivo ocupado, etc.
        _enviar({"tipo": "error", "texto": f"No pude usar el micrófono: {error}"})
        return
    if cancelar.is_set():  # Nine la interrumpió: no es que no lo haya escuchado
        _enviar({"tipo": "escucha_cancelada"})
        return
    if not texto:
        _enviar({"tipo": "no_escuche"})
        return
    _enviar({"tipo": "transcripcion", "texto": texto})
    _responder(sesion, texto, hablar=True)


def _tomar_iniciativa(sesion: Sesion, motivo: Motivo) -> None:
    """Dahiana le habla primero a Nine.

    Con el modelo encendido, lo escribe él. En modo juego (modelo apagado) no lo despierta para no
    quitarle VRAM al juego: usa la frase lista del motivo, si tiene, y la voz de Edge (sin GPU).
    """
    if esta_activo():
        try:
            texto, animo = sesion.dahiana.iniciar(motivo.indicacion), sesion.dahiana.animo
        except openai.APIError:
            return  # no pasa nada por perder una iniciativa
    elif motivo.plantilla:
        texto, animo = motivo.plantilla, "tierna"
    else:
        return
    _enviar({"tipo": "iniciativa", "texto": texto, "animo": animo})
    if sesion.preferencias["voz"] or sesion.preferencias["orbe"]:  # en modo orbe, oírla es la única forma
        _hablar(texto, animo)


def _vigilar(sesion: Sesion, pendientes: queue.Queue, detener: threading.Event) -> None:
    """Hilo del vigía: cada minuto mira el PC y, si hay motivo, pide una iniciativa a la cola."""
    detener.wait(ESPERA_INICIAL)
    ultima_consulta_cancion = float("-inf")
    while not detener.is_set():
        cancion = None
        # Solo si puede comentar lo que hace y Spotify ya está autorizado (si no, abriría el navegador).
        if sesion.preferencias["atenta"] and spotify.conectado() \
                and time.monotonic() - ultima_consulta_cancion >= CONSULTAR_CANCION_CADA:
            ultima_consulta_cancion = time.monotonic()
            try:
                cancion = spotify.sonando()
            except spotify.ErrorSpotify:
                pass
        try:
            observacion = observar(cancion)
        except OSError:
            observacion = None
        if observacion:
            with sesion.candado:
                sesion.vigia.atenta = sesion.preferencias["atenta"]
                motivo = sesion.vigia.revisar(observacion)
                if motivo:
                    sesion.vigia.guardar()
            if motivo:
                pendientes.put({"tipo": "iniciativa", "motivo": motivo})
        detener.wait(REVISAR_CADA)


def _leer_peticiones(pendientes: queue.Queue, cancelar: threading.Event) -> None:
    """Hilo lector: pasa las peticiones de la interfaz a la cola.

    "cancelar" se atiende aquí mismo para poder interrumpir una grabación en curso.
    Al cerrarse la entrada (la interfaz salió) deja None en la cola.
    """
    for linea in sys.stdin:
        linea = linea.lstrip("\uFEFF")  # algunas consolas anteponen un BOM invisible
        if not linea.strip():
            continue
        try:
            peticion = json.loads(linea)
        except json.JSONDecodeError:
            _enviar({"tipo": "error", "texto": "Mensaje inválido (no es JSON)."})
            continue
        if peticion.get("tipo") == "cancelar":
            cancelar.set()
        else:
            pendientes.put(peticion)
    pendientes.put(None)


def _atender(sesion: Sesion, vigilar: bool = True) -> None:
    """Atiende las peticiones de la interfaz y las iniciativas, una a la vez, hasta que cierre la entrada.

    Args:
        sesion: Lo compartido entre hilos.
        vigilar: Si se arranca el hilo del vigía (las pruebas lo apagan).
    """
    pendientes: queue.Queue = queue.Queue()
    cancelar, detener = threading.Event(), threading.Event()
    threading.Thread(target=_leer_peticiones, args=(pendientes, cancelar), daemon=True).start()
    if vigilar:
        threading.Thread(target=_vigilar, args=(sesion, pendientes, detener), daemon=True).start()

    try:
        while (peticion := pendientes.get()) is not None:
            tipo = peticion.get("tipo")
            if tipo == "mensaje":
                _responder(sesion, str(peticion.get("texto", "")), bool(peticion.get("hablar")))
            elif tipo == "escuchar":
                _escuchar(sesion, cancelar)
            elif tipo == "iniciativa":
                _tomar_iniciativa(sesion, peticion["motivo"])
            elif tipo == "preferencias":
                sesion.preferencias.update(
                    {clave: bool(peticion[clave]) for clave in sesion.preferencias if clave in peticion})
            elif tipo == "reiniciar":
                sesion.dahiana.reiniciar()
            elif tipo == "motor" and peticion.get("accion") == "apagar":
                sesion.motor.apagar()
                _enviar({"tipo": "motor", "estado": "apagado"})
            elif tipo == "motor" and peticion.get("accion") == "encender":
                _encender(sesion.motor)
            else:
                _enviar({"tipo": "error", "texto": f"Tipo de mensaje desconocido: {tipo}"})
    finally:
        detener.set()


def main() -> None:
    """Arranca el servicio: enciende el modelo, atiende a la interfaz y lo apaga al terminar."""
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")

    vigia = Vigia(nombre=NOMBRE_USUARIO)
    vigia.cargar()  # para no volver a saludar si Dahiana se reinició hace poco
    sesion = Sesion(Dahiana(al_usar_herramienta=_avisar_accion), Motor(), Oido(), vigia)
    tools.avisar_a_la_interfaz = _enviar  # herramientas como cambiar_vista hablan con la interfaz
    _enviar({"tipo": "listo"})
    # Whisper se carga en paralelo con el modelo para que la primera escucha no espere.
    threading.Thread(target=sesion.oido.preparar, daemon=True).start()
    _encender(sesion.motor)

    try:
        _atender(sesion)
    finally:
        with sesion.candado:
            sesion.vigia.guardar()
        sesion.motor.apagar()  # al cerrar la interfaz se libera la VRAM


if __name__ == "__main__":
    main()
