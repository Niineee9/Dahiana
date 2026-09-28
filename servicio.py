"""Dahiana como servicio para la interfaz (Tauri).

Protocolo: una línea JSON por mensaje.
  Entrada (stdin):  {"tipo": "mensaje", "texto": "..."}
                    {"tipo": "reiniciar"}
                    {"tipo": "motor", "accion": "encender" | "apagar"}   (apagar = modo juego)
  Salida (stdout):  {"tipo": "motor", "estado": "cargando" | "encendido" | "apagado" | "fallo"}
                    {"tipo": "listo"}
                    {"tipo": "pensando"}
                    {"tipo": "accion", "nombre": "...", "argumentos": "...", "resultado": "..."}
                    {"tipo": "respuesta", "texto": "..."}
                    {"tipo": "error", "texto": "..."}

stdout queda reservado para el protocolo: nada más debe imprimir ahí.
"""

import json
import sys

import openai

from brain import Dahiana
from config import MODELO, URL_SERVIDOR
from motor import Motor, esta_activo


def _enviar(evento: dict) -> None:
    sys.stdout.write(json.dumps(evento, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _avisar_accion(nombre: str, argumentos: str, resultado: str) -> None:
    _enviar({"tipo": "accion", "nombre": nombre, "argumentos": argumentos, "resultado": resultado})


def _encender(motor: Motor) -> bool:
    _enviar({"tipo": "motor", "estado": "cargando"})
    encendido = motor.encender()
    _enviar({"tipo": "motor", "estado": "encendido" if encendido else "fallo"})
    return encendido


def _responder(dahiana: Dahiana, motor: Motor, texto: str) -> None:
    # Si estaba en modo juego, escribirle la despierta.
    if not esta_activo() and not _encender(motor):
        _enviar({"tipo": "error", "texto": "No pude encender el modelo. Revisa MOTOR en config.py."})
        return
    _enviar({"tipo": "pensando"})
    try:
        _enviar({"tipo": "respuesta", "texto": dahiana.responder(texto)})
    except openai.APIConnectionError:
        _enviar({"tipo": "error", "texto": f"No pude conectarme al modelo en {URL_SERVIDOR}."})
    except (openai.NotFoundError, openai.BadRequestError) as error:
        _enviar({"tipo": "error", "texto": f"Problema con el modelo '{MODELO}': {error}"})
    except openai.APIError as error:
        _enviar({"tipo": "error", "texto": f"Error del servidor de modelos: {error}"})


def main() -> None:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")

    dahiana = Dahiana(al_usar_herramienta=_avisar_accion)
    motor = Motor()
    _enviar({"tipo": "listo"})
    _encender(motor)

    try:
        _atender(dahiana, motor)
    finally:
        motor.apagar()  # al cerrar la interfaz se libera la VRAM


def _atender(dahiana: Dahiana, motor: Motor) -> None:
    for linea in sys.stdin:
        linea = linea.lstrip("﻿")  # algunas consolas anteponen un BOM
        if not linea.strip():
            continue
        try:
            peticion = json.loads(linea)
        except json.JSONDecodeError:
            _enviar({"tipo": "error", "texto": "Mensaje inválido (no es JSON)."})
            continue

        tipo = peticion.get("tipo")
        if tipo == "mensaje":
            _responder(dahiana, motor, str(peticion.get("texto", "")))
        elif tipo == "reiniciar":
            dahiana.reiniciar()
        elif tipo == "motor" and peticion.get("accion") == "apagar":
            motor.apagar()
            _enviar({"tipo": "motor", "estado": "apagado"})
        elif tipo == "motor" and peticion.get("accion") == "encender":
            _encender(motor)
        else:
            _enviar({"tipo": "error", "texto": f"Tipo de mensaje desconocido: {tipo}"})


if __name__ == "__main__":
    main()
