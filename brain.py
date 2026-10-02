"""El cerebro de Dahiana: conversa con el modelo y ejecuta las herramientas que pida.

Flujo de cada mensaje (tool calling de la API de OpenAI):
  1. Se agrega el mensaje de Nine al historial, con la hora como contexto.
  2. Se envía el historial y los esquemas de las herramientas al modelo.
  3. Si el modelo pide herramientas, se ejecutan y sus resultados vuelven al modelo (paso 2).
  4. Cuando responde sin pedir herramientas, esa es la respuesta final.
"""

import datetime
import json
import re
from collections.abc import Callable

from openai import OpenAI

import atuendo
import memoria
from config import MAX_HISTORIAL, MODELO, NOMBRE_USUARIO, PERSONALIDAD, URL_SERVIDOR
from tools import ESQUEMAS, MAPA_HERRAMIENTAS, fecha_hablada, hora_y_fecha

MAX_PASOS = 5  # rondas máximas de herramientas por mensaje (evita bucles infinitos)

# El servidor local no pide clave, pero la librería necesita una cualquiera.
cliente = OpenAI(base_url=URL_SERVIDOR, api_key="local")

# Emojis y símbolos gráficos: el modelo a veces los usa y la voz no debe leerlos.
# Rangos: emojis, símbolos varios y dingbats, flechas y figuras, selector de variante, unión invisible.
_EMOJIS = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]")

# Se llama cada vez que Dahiana usa una herramienta: (nombre, argumentos_json, resultado).
AvisoAccion = Callable[[str, str, str], None]

# El modelo casi nunca decide solo guardar recuerdos mientras conversa, así que tras cada mensaje una
# consulta aparte (con salida JSON forzada por el servidor) extrae qué recordar y qué olvidar.
_PROMPT_MEMORIA = f"""Extraes recuerdos para la memoria a largo plazo de Dahiana, la asistente de {NOMBRE_USUARIO}.
Del último mensaje de {NOMBRE_USUARIO}, anota solo lo que valga la pena recordar otro día: gustos, planes
y fechas, personas y mascotas, cómo se siente con algo importante, metas.
No anotes órdenes (abrir programas, poner música, la hora), saludos, preguntas de cultura general ni lo
que ya está en la memoria. Si pide olvidar algo, ponlo en "olvidar" con sus palabras.
Nunca pongas en "recordar" algo que ya está en la memoria actual.
Su nombre es {NOMBRE_USUARIO} y no cambia: nunca anotes que se llama de otra forma ni que cambió de nombre
(si el mensaje trae otro nombre, casi siempre es un error al entender su voz).
Escribe cada recuerdo breve y en tercera persona. Convierte las fechas relativas ("el viernes",
"mañana") en fechas concretas usando el calendario que te doy.
En "experiencias" anota, desde el punto de vista de Dahiana y en primera persona, un momento que ella
vivió con {NOMBRE_USUARIO} y querría recordar: una primera vez, algo especial que hicieron juntos o un
gusto propio que se formó por algo concreto de este intercambio. Casi siempre va vacío: solo lo
memorable, nunca lo rutinario, y como mucho uno. Si no hay nada, listas vacías.
Al referirte a {NOMBRE_USUARIO} usa "él" (Dahiana es "ella").

Ejemplos:
"mi gata se llama Luna" -> {{"recordar": ["Su gata se llama Luna"], "olvidar": [], "experiencias": []}}
"olvida lo de mi gata" -> {{"recordar": [], "olvidar": ["gata"], "experiencias": []}}
"abre spotify" -> {{"recordar": [], "olvidar": [], "experiencias": []}}"""

DIAS_DE_CALENDARIO = 8  # hoy y la semana siguiente: basta para "mañana", "el viernes", etc.

_ESQUEMA_MEMORIA = {
    "type": "json_schema",
    "json_schema": {
        "name": "memoria",
        "schema": {
            "type": "object",
            "properties": {
                "recordar": {"type": "array", "items": {"type": "string"}},
                "olvidar": {"type": "array", "items": {"type": "string"}},
                "experiencias": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["recordar", "olvidar", "experiencias"],
        },
    },
}
PALABRAS_MINIMAS_PARA_RECORDAR = 3  # "abre steam" o "hola" no traen nada que recordar

# Recuerdos que dicen que Nine se llama de otra forma. Su nombre está en config.py y no cambia: casi
# siempre es Whisper entendiendo mal ("Tim" por "Nine"), y el modelo lo guarda aunque el prompt lo prohíba.
_CAMBIO_DE_NOMBRE = re.compile(
    rf"^(ahora\s+)?(se llama|su nombre)\b|\bnombre de {NOMBRE_USUARIO}\b|\b{NOMBRE_USUARIO} se llama\b"
    r"|\bcambi\w*\s+(de\s+|su\s+|el\s+)?nombre|\bse identific\w*\s+como|\bllamarlo\b|\bsu nombre\s+(como|es|ahora)\b",
    re.IGNORECASE,
)


def _cambia_su_nombre(dato: str) -> bool:
    """True si el recuerdo dice que Nine se llama de otra forma (ver _CAMBIO_DE_NOMBRE).

    Args:
        dato: Recuerdo propuesto por el extractor.

    Returns:
        Si hay que descartarlo.
    """
    return bool(_CAMBIO_DE_NOMBRE.search(dato.strip()))


# Marcas de formato Markdown (*cursiva*, **negrita**, `código`, # títulos): no se leen en voz alta.
_FORMATO = re.compile(r"[*`#]")

# Pedidos de música ("pon música de Bad Bunny"): con todas las herramientas a mano, el modelo a veces
# contestaba "¡Ahí va!" sin poner nada o elegía YouTube. Para estos, el primer paso solo ofrece Spotify.
_PIDE_MUSICA = re.compile(
    r"^\W*(oye\W+)?(dahiana\W+)?(pon|ponme|ponnos|reproduce|reprodúceme|pásame|quiero (oír|escuchar))\b",
    re.IGNORECASE,
)
_NO_ES_MUSICA = re.compile(r"\b(volumen|chat|alarma|recordatorio|traje|animadora|ropa|atuendo|youtube|v[ií]deo)\b",
                           re.IGNORECASE)
_SOLO_SPOTIFY = [e for e in ESQUEMAS if e["function"]["name"] == "reproducir_en_spotify"]
MAX_TOKENS_PASO_FORZADO = 150  # solo pide la herramienta; sin tope, a veces se enredaba escribiendo sin parar


def _pide_musica(texto: str) -> bool:
    """True si el mensaje pide poner música (ver _PIDE_MUSICA)."""
    return bool(_PIDE_MUSICA.search(texto)) and not _NO_ES_MUSICA.search(texto)


# Herramientas "escritas" en vez de usadas ("[reproducir_en_spotify("Lullaby")]"): a veces el modelo imita
# el formato de los ejemplos del prompt. No hacen nada y se leerían en voz alta, así que se quitan.
_HERRAMIENTA_ESCRITA = re.compile(r"\[\s*\w+\([^\]]*\)\s*\]\s*")


# Preguntas de relleno con que el modelo cierra casi todo ("¿Te gustaría que te cuente algo más?").
# Qwen3 14B las agrega aunque el prompt lo prohíba, así que se quitan del final de la respuesta.
_OFRECIMIENTO_FINAL = re.compile(
    r"\s*¿\s*(te gustaría|te apetece|quieres que|quieres (hablar|contarme|saber)|necesitas|deseas|prefieres que"
    r"|qué te parece si|hay algo más|(en qué )?(más )?(te )?puedo ayudar)[^¿?]*\?\s*$",
    re.IGNORECASE,
)


# Ánimos de Dahiana: el modelo empieza cada respuesta con uno entre corchetes ("[tierna] Ay, Nine...").
# La interfaz lo usa para el color del orbe y voz.py para el tono.
ANIMOS = ("alegre", "emocionada", "tierna", "tranquila", "curiosa", "preocupada")
_ETIQUETA_ANIMO = re.compile(r"\[\s*(" + "|".join(ANIMOS) + r")\s*\]\s*", re.IGNORECASE)


def _separar_animo(texto: str) -> tuple[str | None, str]:
    """Quita las etiquetas de ánimo del texto y devuelve (primer ánimo encontrado, texto limpio)."""
    encontrado = _ETIQUETA_ANIMO.search(texto)
    return (encontrado.group(1).lower() if encontrado else None), _ETIQUETA_ANIMO.sub("", texto)


def _limpiar(texto: str) -> str:
    """Quita emojis, marcas de formato, herramientas escritas, la pregunta de relleno del final y espacios sobrantes."""
    texto = _HERRAMIENTA_ESCRITA.sub("", texto)
    texto = re.sub(r" {2,}", " ", _FORMATO.sub("", _EMOJIS.sub("", texto))).strip()
    sin_ofrecimiento = _OFRECIMIENTO_FINAL.sub("", texto).strip()
    return sin_ofrecimiento or texto  # si la respuesta era solo esa pregunta, se deja


def _calendario() -> str:
    """Hoy y los próximos días con su fecha: los modelos pequeños calculan mal "el viernes" por su cuenta."""
    hoy = datetime.date.today()
    dias = [hoy + datetime.timedelta(days=n) for n in range(DIAS_DE_CALENDARIO)]
    return "\n".join(f"{'hoy' if n == 0 else 'mañana' if n == 1 else '-'}: {fecha_hablada(d)} de {d.year}"
                     for n, d in enumerate(dias))


def _prompt_de_sistema() -> str:
    """Personalidad más los recuerdos de conversaciones anteriores (se arma al empezar cada conversación)."""
    prompt = PERSONALIDAD
    if recuerdos := memoria.para_el_prompt("nine"):
        prompt += (f"\nLo que recuerdas de conversaciones anteriores con {NOMBRE_USUARIO} "
                   f"(con la fecha en que te lo contó):\n{recuerdos}\n")
    if experiencias := memoria.para_el_prompt("experiencia"):
        prompt += (f"\nMomentos que has vivido con {NOMBRE_USUARIO} (son tuyos: úsalos para recordar cosas juntos "
                   f"y para tus propios gustos):\n{experiencias}\n")
    return prompt


def _contexto() -> str:
    """Hora actual (para cuidar sin preguntar: descanso, comidas...) y cómo se siente con su ropa."""
    ropa = atuendo.como_te_sientes()
    return f"[Contexto: {hora_y_fecha()}{' ' + ropa if ropa else ''}]"  # la hora ya dice si es de mañana, tarde...


def _mostrar_accion(nombre: str, argumentos: str, resultado: str) -> None:
    """Aviso por defecto: imprime en la terminal cada herramienta usada."""
    print(f"   ⚙ {nombre}({argumentos}) → {resultado}")


class Dahiana:
    """Una conversación con Dahiana: guarda el historial y habla con el modelo.

    Args:
        al_usar_herramienta: Función que se llama tras cada herramienta usada (para mostrarla
            en la terminal o enviarla a la interfaz). None para no avisar.
    """

    def __init__(self, al_usar_herramienta: AvisoAccion | None = _mostrar_accion):
        # Los recuerdos nuevos de esta conversación ya están en el historial; el prompt de sistema no se
        # cambia a mitad de camino para no invalidar la caché del servidor.
        self.historial: list[dict] = [{"role": "system", "content": _prompt_de_sistema()}]
        self.al_usar_herramienta = al_usar_herramienta
        self.animo = "tranquila"  # se actualiza con cada respuesta

    def iniciar(self, indicacion: str) -> str:
        """Dahiana le habla primero a Nine (saludo, un silencio largo, horas jugando...).

        Args:
            indicacion: Por qué y cómo hablarle; se le da al modelo como nota interna.

        Returns:
            Lo que Dahiana le dice, ya limpio.
        """
        self._recortar_historial()
        self.historial.append({"role": "user", "content": (
            f"{_contexto()}\n[Nota interna, no la escribió {NOMBRE_USUARIO}: {indicacion} Háblale tú primero, "
            "breve y natural, como si se te ocurriera a ti; no menciones esta nota.]")})
        respuesta = cliente.chat.completions.create(model=MODELO, messages=self.historial)  # sin herramientas
        return self._guardar_respuesta(respuesta.choices[0].message.content or "")

    def reiniciar(self) -> None:
        """Empieza una conversación nueva: olvida la actual, pero conserva la memoria a largo plazo."""
        self.historial = [{"role": "system", "content": _prompt_de_sistema()}]

    def responder(self, texto: str) -> str:
        """Envía un mensaje de Nine y devuelve la respuesta final de Dahiana.

        Args:
            texto: Lo que escribió Nine.

        Returns:
            La respuesta de Dahiana, ya sin emojis.

        Raises:
            openai.APIError: Si el servidor del modelo no responde o rechaza la petición.
        """
        self._recortar_historial()
        # Si va a estudiar o está cansado se pone el traje de animadora (antes de armar el contexto, que lo dice).
        if cambio := atuendo.atender_pedido(texto):
            cambio = f"\n[Nota interna, no la escribió {NOMBRE_USUARIO}: {cambio}]"
        # El contexto va en el mensaje (no en el prompt de sistema) para no invalidar la caché del servidor.
        self.historial.append({"role": "user", "content": f"{_contexto()}{cambio}\n{texto}"})

        forzar_spotify = _pide_musica(texto)
        for _ in range(MAX_PASOS):
            mensaje = None
            if forzar_spotify:
                forzar_spotify = False  # solo el primer paso
                forzado = cliente.chat.completions.create(
                    model=MODELO, messages=self.historial, tools=_SOLO_SPOTIFY, tool_choice="required",
                    max_tokens=MAX_TOKENS_PASO_FORZADO,
                ).choices[0].message
                mensaje = forzado if forzado.tool_calls else None  # si no la pidió, sigue como siempre
            if mensaje is None:
                mensaje = cliente.chat.completions.create(
                    model=MODELO, messages=self.historial, tools=ESQUEMAS
                ).choices[0].message

            if not mensaje.tool_calls:
                return self._guardar_respuesta(mensaje.content or "")

            # El pedido de herramientas va al historial para que el modelo vea qué pidió.
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

    def _guardar_respuesta(self, bruto: str) -> str:
        """Separa el ánimo, limpia el texto y lo guarda en el historial (con su etiqueta, para que el
        modelo vea que la sigue usando)."""
        animo, texto = _separar_animo(bruto)
        self.animo = animo or self.animo  # si olvidó la etiqueta, conserva el ánimo anterior
        contenido = _limpiar(texto)
        self.historial.append({"role": "assistant", "content": f"[{self.animo}] {contenido}"})
        return contenido

    def actualizar_memoria(self, texto: str) -> None:
        """Guarda en la memoria a largo plazo lo importante de un mensaje de Nine (y borra lo que pidió olvidar).

        Se llama después de responder, para no demorar la respuesta. Cada cambio se avisa como una
        acción ("recordar" u "olvidar"), así Nine ve en el chat qué quedó guardado.

        Args:
            texto: El mensaje de Nine.

        Raises:
            openai.APIError: Si el servidor del modelo no responde.
        """
        if len(texto.split()) < PALABRAS_MINIMAS_PARA_RECORDAR:
            return
        consulta = (
            f"Calendario:\n{_calendario()}\n\n"
            f"Memoria actual de {NOMBRE_USUARIO}:\n{memoria.para_el_prompt('nine') or '(vacía)'}\n\n"
            f"Experiencias de Dahiana:\n{memoria.para_el_prompt('experiencia') or '(ninguna)'}\n\n"
            f"Último mensaje de {NOMBRE_USUARIO}: {texto}\n"
            f"Lo que pasó después (acciones y respuesta de Dahiana):\n{self._ultimo_intercambio()}"
        )
        respuesta = cliente.chat.completions.create(
            model=MODELO, temperature=0, response_format=_ESQUEMA_MEMORIA,
            messages=[{"role": "system", "content": _PROMPT_MEMORIA}, {"role": "user", "content": consulta}],
        )
        try:
            cambios = json.loads(respuesta.choices[0].message.content or "{}")
        except json.JSONDecodeError:
            return  # sin recuerdos esta vez; no vale la pena interrumpir a Nine por esto
        for dato in cambios.get("olvidar", []):
            if borrado := memoria.olvidar(dato):
                self._avisar("olvidar", dato, f"Olvidé: {borrado}")
        for dato in cambios.get("recordar", []):
            if dato.strip() and not _cambia_su_nombre(dato) and memoria.agregar(dato):  # solo avisa lo nuevo, no lo que ya sabía
                self._avisar("recordar", dato, f"Recordé: {dato.strip()}")
        for dato in cambios.get("experiencias", [])[:1]:  # como mucho una por mensaje
            if dato.strip() and not _cambia_su_nombre(dato) and memoria.agregar(dato, tipo="experiencia"):
                self._avisar("experiencia", dato, f"Guardé este momento: {dato.strip()}")

    def _ultimo_intercambio(self) -> str:
        """Lo que pasó tras el último mensaje de Nine: herramientas usadas y respuesta de Dahiana."""
        ultimo_mensaje = max((i for i, m in enumerate(self.historial) if m["role"] == "user"), default=0)
        lineas = []
        for m in self.historial[ultimo_mensaje + 1:]:
            if m["role"] == "tool":
                lineas.append(f"- Acción: {m['content']}")
            elif m["role"] == "assistant" and m.get("content"):
                lineas.append(f"- Dahiana: {m['content']}")
        return "\n".join(lineas) or "- (nada)"

    def _avisar(self, nombre: str, argumento: str, resultado: str) -> None:
        """Avisa un cambio de memoria como si fuera una herramienta usada."""
        if self.al_usar_herramienta:
            self.al_usar_herramienta(nombre, json.dumps({"dato": argumento}, ensure_ascii=False), resultado)

    def _recortar_historial(self) -> None:
        """Deja solo los últimos MAX_HISTORIAL mensajes, además de la personalidad."""
        if len(self.historial) <= MAX_HISTORIAL + 1:
            return
        resto = self.historial[-MAX_HISTORIAL:]
        # Empezar siempre en un mensaje del usuario para no dejar herramientas huérfanas.
        while resto and resto[0]["role"] != "user":
            resto.pop(0)
        self.historial = [self.historial[0], *resto]

    def _ejecutar(self, nombre: str, argumentos_json: str) -> str:
        """Ejecuta una herramienta pedida por el modelo; los errores vuelven como texto."""
        funcion = MAPA_HERRAMIENTAS.get(nombre)
        if funcion is None:
            return f"La herramienta '{nombre}' no existe."
        try:
            argumentos = json.loads(argumentos_json or "{}")
            return str(funcion(**argumentos))
        except Exception as error:  # que un fallo no tumbe a Dahiana: el modelo recibe el error
            return f"Error ejecutando {nombre}: {error}"
