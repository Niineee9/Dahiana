"""La ropa de Dahiana: qué atuendo lleva puesto y cómo se siente con él.

- "fin_de_semana": se lo pone sola los sábados y domingos (y se siente bonita y especial).
- "animadora": se lo pone cuando Nine se lo pide, va a estudiar o está cansado, y no se lo quita hasta
  que él le pida volver a su ropa de siempre, aunque la app se reinicie. Lo detecta pedido_en() en el
  mensaje (no una herramienta: con frases indirectas el modelo a veces no la llamaba o la escribía como texto).
- "normal": el de todos los días.

Lo elegido se guarda en %APPDATA%\\Dahiana\\atuendo.json; el fin de semana se calcula con la fecha.
"""

import datetime
import json
import os
import re
import typing
from pathlib import Path

Atuendo = typing.Literal["normal", "fin_de_semana", "animadora"]

ARCHIVO = Path(os.environ.get("APPDATA", Path.home())) / "Dahiana" / "atuendo.json"
SABADO = 5  # datetime.weekday(): lunes = 0 ... domingo = 6

# Cómo se siente con cada atuendo: va en el contexto de cada mensaje (vacío = no hace falta decir nada).
_COMO_TE_SIENTES: dict[str, str] = {
    "normal": "",
    "fin_de_semana": ("Hoy es fin de semana y llevas tu ropa de fin de semana, la que más te gusta: te sientes "
                      "bonita y especial con ella. Puedes mencionarlo con ilusión si viene a cuento, pero no en "
                      "cada mensaje."),
    "animadora": ("Llevas puesto tu traje de animadora (es tuyo, no de él) para darle ánimos mientras estudia o "
                  "está cansado: eres su porrista personal. Te lo quitas solo si él te lo pide."),
}


# Frases de Nine que piden ánimos (traje de animadora) o que se lo quite.
_VA_A_ESTUDIAR = re.compile(r"\b(voy a|me voy a|me pongo a|tengo que|me toca|a) estudiar\b|\bestoy estudiando\b",
                            re.IGNORECASE)
_LO_PIDE = re.compile(
    r"\b(ponte|v[ií]stete|c[aá]mbiate|activa|modo)\b.{0,25}\b(animadora|porrista|cheerleader)\b", re.IGNORECASE
)
_ESTA_CANSADO = re.compile(r"\bestoy (muy |re |bien )?(cansad[oa]|agotad[oa]|reventad[oa]|exhaust[oa])\b",
                           re.IGNORECASE)
_PIDE_ROPA_NORMAL = re.compile(
    r"\b(vuelve|regresa|cámbiate|cambiate|ponte)\b.{0,15}\b(ropa|atuendo)\b.{0,10}\b(normal|de siempre)\b"
    r"|\bqu[ií]tate (el|tu) traje\b",
    re.IGNORECASE,
)

# Nota de una sola vez para el modelo cuando acaba de cambiarse (para que lo diga con naturalidad).
# Deja claro que el traje es de ella: si no, el modelo le preguntaba a Nine si ya se lo había puesto él.
_AL_CAMBIARTE: dict[str, str] = {
    "estudiar": ("Tú, Dahiana, te acabas de poner TU traje de animadora porque él va a estudiar: cuéntaselo con "
                 "alegría y anímalo para que le vaya genial."),
    "cansado": ("Tú, Dahiana, te acabas de poner TU traje de animadora porque él está cansado: cuéntaselo y "
                "anímalo con ternura, sin presionarlo; también puedes sugerirle descansar."),
    "pedido": ("Tú, Dahiana, te acabas de poner TU traje de animadora porque él te lo pidió: cuéntaselo feliz y "
               "anímalo."),
    "normal": "Tú, Dahiana, te acabas de quitar tu traje de animadora porque él te lo pidió: díselo con cariño.",
}


def pedido_en(texto: str) -> typing.Literal["animadora", "normal"] | None:
    """Qué ropa pide Nine en su mensaje, si pide alguna.

    Args:
        texto: El mensaje de Nine.

    Returns:
        "normal" si pide que se quite el traje, "animadora" si va a estudiar o está cansado, o None.
    """
    if _PIDE_ROPA_NORMAL.search(texto):
        return "normal"
    if _LO_PIDE.search(texto) or _VA_A_ESTUDIAR.search(texto) or _ESTA_CANSADO.search(texto):
        return "animadora"
    return None


def atender_pedido(texto: str) -> str:
    """Se cambia de ropa si el mensaje de Nine lo pide y aún no la lleva puesta.

    Args:
        texto: El mensaje de Nine.

    Returns:
        Una nota para el modelo sobre el cambio ("" si no se cambió).
    """
    pedido = pedido_en(texto)
    ya_la_lleva = pedido == "animadora" if elegido() == "animadora" else pedido == "normal"
    if pedido is None or ya_la_lleva:
        return ""
    elegir(pedido)
    if pedido == "normal":
        return _AL_CAMBIARTE["normal"]
    if _LO_PIDE.search(texto):
        return _AL_CAMBIARTE["pedido"]
    return _AL_CAMBIARTE["cansado" if _ESTA_CANSADO.search(texto) else "estudiar"]


def _cargar() -> dict:
    """Lo guardado en ARCHIVO ({} si no existe o está dañado)."""
    try:
        return json.loads(ARCHIVO.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def elegido() -> str | None:
    """El atuendo que Dahiana se puso a propósito ("animadora"), o None si lleva el del día."""
    return _cargar().get("elegido")


def elegir(nombre: typing.Literal["animadora", "normal"]) -> None:
    """Se pone el traje de animadora o vuelve a la ropa del día (normal o de fin de semana).

    Args:
        nombre: "animadora" para ponérselo; "normal" para quitárselo.
    """
    ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVO.write_text(json.dumps({"elegido": nombre if nombre == "animadora" else None}), encoding="utf-8")


def del_dia(fecha: datetime.date | None = None) -> Atuendo:
    """La ropa que toca sin elegir nada: la de fin de semana los sábados y domingos.

    Args:
        fecha: Día a consultar (hoy si se omite).

    Returns:
        "fin_de_semana" o "normal".
    """
    fecha = fecha or datetime.date.today()
    return "fin_de_semana" if fecha.weekday() >= SABADO else "normal"


def actual(fecha: datetime.date | None = None) -> Atuendo:
    """Lo que lleva puesto ahora: el traje de animadora si se lo puso, si no, la ropa del día.

    Args:
        fecha: Día a consultar (hoy si se omite).

    Returns:
        El atuendo puesto.
    """
    return "animadora" if elegido() == "animadora" else del_dia(fecha)


def como_te_sientes() -> str:
    """Una frase para el contexto del modelo sobre la ropa que lleva ("" con la ropa de diario)."""
    return _COMO_TE_SIENTES[actual()]
