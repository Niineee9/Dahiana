"""El cerebro de Dahiana: conversa con el modelo y ejecuta las herramientas que pida."""

import datetime
import json
import re
from collections.abc import Callable

from openai import OpenAI

from config import MAX_HISTORIAL, MODELO, PERSONALIDAD, URL_SERVIDOR
from tools import ESQUEMAS, MAPA_HERRAMIENTAS, hora_y_fecha

MAX_PASOS = 5  # rondas máximas de herramientas por cada mensaje

# El servidor local no pide clave, pero la librería necesita una cualquiera.
cliente = OpenAI(base_url=URL_SERVIDOR, api_key="local")

# Emojis y símbolos gráficos: el modelo a veces los usa y la voz (Fase 2) no debe leerlos.
_EMOJIS = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]")


def _limpiar(texto: str) -> str:
    return re.sub(r" {2,}", " ", _EMOJIS.sub("", texto)).strip()


def _momento_del_dia(hora: int) -> str:
    if hora < 5:
        return "madrugada"
    if hora < 12:
        return "mañana"
    if hora < 19:
        return "tarde"
    return "noche"


def _contexto() -> str:
    """Hora actual para que Dahiana pueda cuidar sin preguntar (descanso, comidas...)."""
    momento = _momento_del_dia(datetime.datetime.now().hour)
    return f"[Contexto: {hora_y_fecha()} Es de {momento}.]"


def _mostrar_accion(nombre: str, argumentos: str, resultado: str) -> None:
    print(f"   ⚙ {nombre}({argumentos}) → {resultado}")


# Se llama cada vez que Dahiana usa una herramienta: (nombre, argumentos_json, resultado).
AvisoAccion = Callable[[str, str, str], None]


class Dahiana:
    def __init__(self, al_usar_herramienta: AvisoAccion | None = _mostrar_accion):
        self.historial = [{"role": "system", "content": PERSONALIDAD}]
        self.al_usar_herramienta = al_usar_herramienta

    def reiniciar(self) -> None:
        """Olvida la conversación actual (conserva la personalidad)."""
        self.historial = self.historial[:1]

    def _recortar_historial(self) -> None:
        if len(self.historial) <= MAX_HISTORIAL + 1:
            return
        resto = self.historial[-MAX_HISTORIAL:]
        # Empezar siempre en un mensaje del usuario para no dejar herramientas huérfanas.
        while resto and resto[0]["role"] != "user":
            resto.pop(0)
        self.historial = [self.historial[0], *resto]

    def _ejecutar(self, nombre: str, argumentos_json: str) -> str:
        funcion = MAPA_HERRAMIENTAS.get(nombre)
        if funcion is None:
            return f"La herramienta '{nombre}' no existe."
        try:
            argumentos = json.loads(argumentos_json or "{}")
            return str(funcion(**argumentos))
        except Exception as error:  # que un fallo no tumbe a Dahiana
            return f"Error ejecutando {nombre}: {error}"

    def responder(self, texto: str) -> str:
        self._recortar_historial()
        # El contexto va en el mensaje (no en el prompt de sistema) para no invalidar la caché del servidor.
        self.historial.append({"role": "user", "content": f"{_contexto()}\n{texto}"})

        for _ in range(MAX_PASOS):
            respuesta = cliente.chat.completions.create(
                model=MODELO, messages=self.historial, tools=ESQUEMAS
            )
            mensaje = respuesta.choices[0].message

            if not mensaje.tool_calls:
                contenido = _limpiar(mensaje.content or "")
                self.historial.append({"role": "assistant", "content": contenido})
                return contenido

            self.historial.append({
                "role": "assistant",
                "content": mensaje.content or "",
                "tool_calls": [
                    {"id": llamada.id, "type": "function",
                     "function": {"name": llamada.function.name,
                                  "arguments": llamada.function.arguments}}
                    for llamada in mensaje.tool_calls
                ],
            })

            for llamada in mensaje.tool_calls:
                nombre = llamada.function.name
                resultado = self._ejecutar(nombre, llamada.function.arguments)
                if self.al_usar_herramienta:
                    self.al_usar_herramienta(nombre, llamada.function.arguments, resultado)
                self.historial.append(
                    {"role": "tool", "tool_call_id": llamada.id, "content": resultado}
                )

        return "Uy, me enredé con eso. ¿Me lo pides de otra forma?"
