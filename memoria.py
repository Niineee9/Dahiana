"""Memoria a largo plazo de Dahiana, en dos partes:

- "nine": lo que Nine le contó y vale la pena recordar (gustos, planes, personas...).
- "experiencia": lo que Dahiana vivió con Nine (momentos, primeras veces, gustos que se formó).

Se guarda en %APPDATA%\\Dahiana\\memoria.json (fuera del proyecto y de git), como una lista de
{"dato": "...", "fecha": "AAAA-MM-DD", "tipo": "nine" | "experiencia"}. Los recuerdos sin tipo (de
antes de existir las experiencias) cuentan como "nine". Nine puede abrir ese archivo y editarlo.
"""

import datetime
import difflib
import json
import os
from pathlib import Path

ARCHIVO = Path(os.environ.get("APPDATA", Path.home())) / "Dahiana" / "memoria.json"
# Recuerdos más recientes que se le muestran al modelo de cada tipo (caben de sobra en el contexto).
MAX_EN_PROMPT = {"nine": 60, "experiencia": 30}
PARECIDO_REPETIDO = 0.85  # dos recuerdos así de parecidos se consideran el mismo

_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _parecido(a: str, b: str) -> float:
    """Qué tan parecidos son dos textos (0 a 1), sin distinguir mayúsculas."""
    return difflib.SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def cargar() -> list[dict]:
    """Todos los recuerdos guardados (lista vacía si todavía no hay o el archivo está dañado)."""
    try:
        recuerdos = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [r for r in recuerdos if isinstance(r, dict) and r.get("dato")]


def _guardar(recuerdos: list[dict]) -> None:
    ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVO.write_text(json.dumps(recuerdos, ensure_ascii=False, indent=2), encoding="utf-8")


def _tipo(recuerdo: dict) -> str:
    """Tipo de un recuerdo; los antiguos, sin tipo, son de Nine."""
    return recuerdo.get("tipo", "nine")


def agregar(dato: str, tipo: str = "nine") -> bool:
    """Guarda un recuerdo con la fecha de hoy.

    Si ya había uno casi igual del mismo tipo, lo reemplaza (el dato nuevo suele estar más al día).

    Args:
        dato: Lo que hay que recordar, por ejemplo "Le encanta AC/DC".
        tipo: "nine" (algo de Nine) o "experiencia" (algo que Dahiana vivió con él).

    Returns:
        True si era nuevo; False si actualizó uno que ya existía.
    """
    dato = dato.strip()
    recuerdos = cargar()
    repetido = next((r for r in recuerdos
                     if _tipo(r) == tipo and _parecido(r["dato"], dato) >= PARECIDO_REPETIDO), None)
    if repetido:
        recuerdos.remove(repetido)
    recuerdos.append({"dato": dato, "fecha": datetime.date.today().isoformat(), "tipo": tipo})
    _guardar(recuerdos)
    return repetido is None


LARGO_MINIMO_PALABRA = 4  # "de", "mi", "lo", "que" no dicen de qué recuerdo se habla
COINCIDENCIA_PARA_OLVIDAR = 0.5


def _palabras(texto: str) -> set[str]:
    """Palabras con significado de un texto, en minúsculas y sin signos."""
    return {p.strip(".,;:¡!¿?\"'()").lower() for p in texto.split()} - {""}


def _coincidencia(recuerdo: str, descripcion: str) -> float:
    """Qué tan probable es que la descripción hable de ese recuerdo (0 a 1).

    Combina el parecido del texto completo con las palabras importantes en común, para que
    "lo de mi gata" encuentre "Tiene una gata llamada Luna".
    """
    clave = {p for p in _palabras(descripcion) if len(p) >= LARGO_MINIMO_PALABRA}
    en_comun = len(clave & _palabras(recuerdo)) / len(clave) if clave else 0
    return max(_parecido(recuerdo, descripcion), en_comun)


def olvidar(descripcion: str) -> str | None:
    """Borra el recuerdo que mejor coincide con la descripción.

    Args:
        descripcion: Lo que Nine pidió olvidar, con sus palabras (por ejemplo "lo de mi gata").

    Returns:
        El recuerdo borrado, o None si ninguno se parecía lo suficiente.
    """
    recuerdos = cargar()
    puntaje, elegido = max(((_coincidencia(r["dato"], descripcion), r) for r in recuerdos),
                           key=lambda candidato: candidato[0], default=(0, None))
    if elegido is None or puntaje < COINCIDENCIA_PARA_OLVIDAR:
        return None
    recuerdos.remove(elegido)
    _guardar(recuerdos)
    return elegido["dato"]


def _fecha_hablada(fecha_iso: str) -> str:
    """"2026-09-27" -> "27 de septiembre"."""
    try:
        fecha = datetime.date.fromisoformat(fecha_iso)
    except ValueError:
        return "fecha desconocida"
    return f"{fecha.day} de {_MESES[fecha.month - 1]}"


def para_el_prompt(tipo: str = "nine") -> str:
    """Los recuerdos más recientes de un tipo como lista para el prompt de sistema, o "" si no hay."""
    recuerdos = [r for r in cargar() if _tipo(r) == tipo][-MAX_EN_PROMPT[tipo]:]
    return "\n".join(f"- ({_fecha_hablada(r.get('fecha', ''))}) {r['dato']}" for r in recuerdos)
