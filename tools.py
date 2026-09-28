"""Herramientas de Dahiana.

Cada función pública es una herramienta que el modelo puede llamar.
La descripción que ve el modelo se genera sola a partir de los type hints
y del docstring (sección Args), así que mantenlos claros. Para agregar una
herramienta nueva: escribe la función y añádela a HERRAMIENTAS al final.
"""

import ctypes
import datetime
import difflib
import inspect
import os
import re
import subprocess
import webbrowser
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

import psutil

from config import APPS, SITIOS

# ---------------------------------------------------------------- utilidades


@lru_cache(maxsize=1)
def _accesos_directos() -> dict[str, Path]:
    """Indexa los accesos directos del Menú Inicio y del Escritorio."""
    carpetas = [
        Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
        Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        Path.home() / "Desktop",
        Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop",
    ]
    accesos: dict[str, Path] = {}
    for carpeta in carpetas:
        if not carpeta.exists():
            continue
        for archivo in carpeta.rglob("*"):
            if archivo.suffix.lower() in (".lnk", ".url"):
                nombre = archivo.stem.lower()
                if "uninstall" in nombre or "desinstalar" in nombre:
                    continue
                accesos.setdefault(nombre, archivo)
    return accesos


def _lanzar(objetivo: str) -> None:
    if objetivo.startswith(("http://", "https://")):
        webbrowser.open(objetivo)
        return
    try:
        os.startfile(objetivo)  # type: ignore[attr-defined]  (solo existe en Windows)
    except OSError:
        subprocess.Popen(objetivo, shell=True)


def _nivel(porcentaje: float) -> str:
    if porcentaje < 60:
        return "normal"
    if porcentaje < 85:
        return "algo alto"
    return "muy alto"


def _tecla(codigo_vk: int) -> None:
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    user32.keybd_event(codigo_vk, 0, 0, 0)  # presionar
    user32.keybd_event(codigo_vk, 0, 2, 0)  # soltar


# Procesos que Dahiana nunca debe cerrar (incluye su interfaz y su motor de modelos).
_PROTEGIDOS = {
    "explorer.exe", "python.exe", "pythonw.exe", "ollama.exe", "ollama app.exe",
    "dahiana.exe", "llama-server.exe",
    "svchost.exe", "csrss.exe", "winlogon.exe", "lsass.exe", "services.exe",
    "system", "smss.exe", "dwm.exe",
}

_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

# ---------------------------------------------------------------- herramientas


def abrir_programa(nombre: str) -> str:
    """Abre un programa o aplicación instalada en el PC.

    Args:
        nombre: Nombre del programa, por ejemplo "Steam", "Discord" o "bloc de notas".

    Returns:
        Resultado de la operación.
    """
    clave = nombre.lower().strip()

    if clave in APPS:
        _lanzar(APPS[clave])
        return f"Abrí {nombre}."

    accesos = _accesos_directos()
    candidatos = [k for k in accesos if clave in k]
    if not candidatos:
        candidatos = difflib.get_close_matches(clave, list(accesos), n=1, cutoff=0.6)
    if candidatos:
        mejor = min(candidatos, key=len)  # el nombre más corto suele ser el principal
        os.startfile(accesos[mejor])  # type: ignore[attr-defined]
        return f"Abrí '{accesos[mejor].stem}'."

    return f"No encontré ningún programa llamado '{nombre}'."


def cerrar_programa(nombre: str) -> str:
    """Cierra un programa que esté abierto.

    Args:
        nombre: Nombre del programa a cerrar, por ejemplo "Chrome" o "Discord".

    Returns:
        Resultado de la operación.
    """
    clave = nombre.lower().strip().removesuffix(".exe")
    if len(clave) < 3:
        return "El nombre es muy corto; dime el nombre completo del programa."

    cerrados = set()
    for proceso in psutil.process_iter(["name"]):
        nombre_proc = (proceso.info["name"] or "").lower()
        if clave in nombre_proc and nombre_proc not in _PROTEGIDOS:
            try:
                proceso.terminate()
                cerrados.add(proceso.info["name"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    if cerrados:
        return f"Cerré: {', '.join(sorted(cerrados))}."
    return f"No encontré ningún programa abierto llamado '{nombre}'."


def abrir_sitio_web(sitio: str) -> str:
    """Abre un sitio web en el navegador.

    Args:
        sitio: Nombre del sitio (por ejemplo "YouTube") o su dirección (por ejemplo "reddit.com").

    Returns:
        Resultado de la operación.
    """
    clave = sitio.lower().strip()
    if clave in SITIOS:
        url = SITIOS[clave]
    elif "." in clave and " " not in clave:
        url = clave if clave.startswith("http") else f"https://{clave}"
    else:
        return buscar_en_internet(sitio)
    webbrowser.open(url)
    return f"Abrí {url}."


def buscar_en_internet(consulta: str) -> str:
    """Busca algo en Google y abre los resultados en el navegador.

    Args:
        consulta: Lo que hay que buscar.

    Returns:
        Resultado de la operación.
    """
    webbrowser.open(f"https://www.google.com/search?q={quote_plus(consulta)}")
    return f"Busqué '{consulta}' en Google."


def buscar_en_youtube(consulta: str) -> str:
    """Busca videos en YouTube y abre los resultados en el navegador.

    Args:
        consulta: El video o tema que hay que buscar.

    Returns:
        Resultado de la operación.
    """
    webbrowser.open(f"https://www.youtube.com/results?search_query={quote_plus(consulta)}")
    return f"Busqué '{consulta}' en YouTube."


def controlar_volumen(accion: str, cantidad: int = 5) -> str:
    """Sube, baja o silencia el volumen del PC.

    Args:
        accion: Una de estas: "subir", "bajar" o "silenciar" (silenciar también sirve para quitar el silencio).
        cantidad: Cuántos pasos subir o bajar; cada paso es aproximadamente 2%. Por defecto 5.

    Returns:
        Resultado de la operación.
    """
    accion = accion.lower().strip()
    cantidad = max(1, min(int(cantidad), 50))
    if accion == "silenciar":
        _tecla(0xAD)
        return "Alterné el silencio."
    if accion in ("subir", "bajar"):
        vk = 0xAF if accion == "subir" else 0xAE
        for _ in range(cantidad):
            _tecla(vk)
        return f"Volumen: {accion} unos {cantidad * 2}%."
    return f"No entiendo la acción '{accion}'. Usa subir, bajar o silenciar."


def hora_y_fecha() -> str:
    """Devuelve la hora y la fecha actuales.

    Returns:
        La fecha y hora actuales.
    """
    ahora = datetime.datetime.now()
    return (f"Son las {ahora:%I:%M %p} del {_DIAS[ahora.weekday()]} "
            f"{ahora.day} de {_MESES[ahora.month - 1]} de {ahora.year}.")


def estado_del_pc() -> str:
    """Informa el uso actual de CPU, memoria RAM y disco del PC.

    Returns:
        Resumen del estado del PC.
    """
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    disco = psutil.disk_usage(os.environ.get("SYSTEMDRIVE", "C:") + "\\" if os.name == "nt" else "/")
    # El nivel va ya calificado para que el modelo no tenga que interpretar los porcentajes.
    return (f"CPU al {cpu:.0f}% (uso {_nivel(cpu)}). "
            f"RAM: {ram.used / 1e9:.1f} de {ram.total / 1e9:.1f} GB, {ram.percent:.0f}% (uso {_nivel(ram.percent)}). "
            f"Disco principal al {disco.percent:.0f}% (uso {_nivel(disco.percent)}, "
            f"{disco.free / 1e9:.0f} GB libres).")


HERRAMIENTAS = [
    abrir_programa,
    cerrar_programa,
    abrir_sitio_web,
    buscar_en_internet,
    buscar_en_youtube,
    controlar_volumen,
    hora_y_fecha,
    estado_del_pc,
]

MAPA_HERRAMIENTAS = {f.__name__: f for f in HERRAMIENTAS}

# ---------------------------------------------------------------- esquemas para el modelo

_TIPOS_JSON = {str: "string", int: "integer", float: "number", bool: "boolean"}


def _esquema(funcion) -> dict:
    """Convierte una función con docstring estilo Google en una herramienta de la API de OpenAI."""
    doc = inspect.getdoc(funcion) or ""
    descripcion = doc.split("\n\n")[0].strip()
    args_doc = {}
    bloque = re.search(r"Args:\n(.*?)(?:\n\n|\nReturns:|$)", doc, re.S)
    if bloque:
        for nombre, texto in re.findall(r"^\s*(\w+):\s*(.+)$", bloque.group(1), re.M):
            args_doc[nombre] = texto.strip()

    propiedades, requeridos = {}, []
    for nombre, param in inspect.signature(funcion).parameters.items():
        propiedades[nombre] = {
            "type": _TIPOS_JSON.get(param.annotation, "string"),
            "description": args_doc.get(nombre, ""),
        }
        if param.default is inspect.Parameter.empty:
            requeridos.append(nombre)

    return {
        "type": "function",
        "function": {
            "name": funcion.__name__,
            "description": descripcion,
            "parameters": {"type": "object", "properties": propiedades, "required": requeridos},
        },
    }


ESQUEMAS = [_esquema(f) for f in HERRAMIENTAS]
