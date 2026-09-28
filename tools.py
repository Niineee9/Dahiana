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
import json
import os
import re
import subprocess
import typing
import unicodedata
import webbrowser
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, quote_plus

import psutil

import spotify
from config import APPS, SITIOS

# ---------------------------------------------------------------- utilidades

_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # solo existe en Windows

# Constantes de la API de Windows.
_VK_SILENCIO, _VK_BAJAR_VOLUMEN, _VK_SUBIR_VOLUMEN = 0xAD, 0xAE, 0xAF  # teclas multimedia
_VK_SIGUIENTE, _VK_ANTERIOR, _VK_REPRODUCIR_PAUSAR = 0xB0, 0xB1, 0xB3
_KEYEVENTF_KEYUP = 2  # keybd_event: soltar la tecla
_GW_OWNER = 4  # GetWindow: ventana dueña (las ventanas secundarias tienen una)
_DWMWA_CLOAKED = 14  # DwmGetWindowAttribute: ventana "encubierta" (apps de la Store suspendidas)

# Entradas del Menú Inicio que no son programas para abrir.
_IGNORAR = ("uninstall", "desinstalar", "support", "soporte", "readme", "leeme", "help", "ayuda",
            "telemetr", "preferencias de idioma")

# Herramientas del sistema que solo se abren si las piden por su nombre exacto.
_SENSIBLES = {
    "configuracion del sistema", "system configuration", "editor del registro", "registry editor",
    "simbolo del sistema", "command prompt", "windows powershell", "powershell",
    "administracion de discos", "disk management", "servicios", "services",
}


def _normalizar(texto: str) -> str:
    """Minúsculas y sin tildes, para que "configuracion" encuentre "Configuración"."""
    sin_tildes = unicodedata.normalize("NFD", texto)
    return "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn").lower().strip()


def _apps_del_menu_inicio() -> dict[str, tuple[str, str]]:
    """Todas las apps del Menú Inicio, incluidas las de la Microsoft Store (WhatsApp, Spotify...)."""
    comando = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress"
    try:
        salida = subprocess.run(
            ["powershell", "-NoProfile", "-Command", comando],
            capture_output=True, encoding="utf-8", timeout=15, creationflags=_SIN_VENTANA,
        ).stdout
        apps = json.loads(salida or "[]")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return {}
    if isinstance(apps, dict):  # una sola app: ConvertTo-Json no devuelve lista
        apps = [apps]
    return {_normalizar(a["Name"]): (a["Name"], f"shell:AppsFolder\\{a['AppID']}") for a in apps}


def _accesos_del_escritorio() -> dict[str, tuple[str, str]]:
    """Accesos directos del Escritorio (juegos y programas que no están en el Menú Inicio)."""
    carpetas = [Path.home() / "Desktop", Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop"]
    return {
        _normalizar(archivo.stem): (archivo.stem, str(archivo))
        for carpeta in carpetas if carpeta.exists()
        for archivo in carpeta.iterdir() if archivo.suffix.lower() in (".lnk", ".url")
    }


@lru_cache(maxsize=1)
def _indice_programas() -> dict[str, tuple[str, str]]:
    """nombre normalizado -> (nombre visible, qué abrir). Se arma una vez y se rehace si algo no aparece."""
    indice = {**_accesos_del_escritorio(), **_apps_del_menu_inicio()}
    return {clave: valor for clave, valor in indice.items() if not any(p in clave for p in _IGNORAR)}


def _puntaje(consulta: str, clave: str) -> int:
    """Qué tan bien coincide un nombre instalado con lo pedido (0 = nada)."""
    if clave == consulta:
        return 100
    if clave.startswith(consulta):
        return 80
    if all(re.search(rf"\b{re.escape(palabra)}", clave) for palabra in consulta.split()):
        return 60
    if consulta in clave:
        return 50
    parecido = difflib.SequenceMatcher(None, consulta, clave).ratio()
    return int(parecido * 40) if parecido >= 0.75 else 0  # parecido: como mucho una sugerencia


def _buscar(consulta: str) -> list[tuple[int, str, str]]:
    """Programas instalados que coinciden, del mejor al peor: (puntaje, nombre, objetivo)."""
    clave = _normalizar(consulta)
    resultados = []
    for nombre_normal, (nombre, objetivo) in _indice_programas().items():
        puntos = _puntaje(clave, nombre_normal)
        if puntos and (nombre_normal not in _SENSIBLES or puntos == 100):
            resultados.append((puntos, nombre, objetivo))
    return sorted(resultados, key=lambda r: (-r[0], len(r[1])))


# Procesos cuyas ventanas no le interesan a Nine (o que son la propia Dahiana).
_VENTANAS_IGNORADAS = {"dahiana.exe", "textinputhost.exe", "shellexperiencehost.exe",
                       "searchhost.exe", "startmenuexperiencehost.exe", "lockapp.exe"}


def _ventanas() -> list[tuple[str, str]]:
    """Ventanas principales visibles: (proceso, título)."""
    user32, dwmapi = ctypes.windll.user32, ctypes.windll.dwmapi  # type: ignore[attr-defined]
    ventanas: list[tuple[str, str]] = []

    def revisar(hwnd, _):
        largo = user32.GetWindowTextLengthW(hwnd)
        if not largo or not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, _GW_OWNER):
            return True
        oculta = ctypes.c_int(0)
        dwmapi.DwmGetWindowAttribute(hwnd, _DWMWA_CLOAKED, ctypes.byref(oculta), ctypes.sizeof(oculta))
        if oculta.value:
            return True
        titulo = ctypes.create_unicode_buffer(largo + 1)
        user32.GetWindowTextW(hwnd, titulo, largo + 1)
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            proceso = psutil.Process(pid.value).name()
        except psutil.Error:
            proceso = "?"
        if proceso.lower() not in _VENTANAS_IGNORADAS:
            ventanas.append((proceso, titulo.value))
        return True

    tipo = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows(tipo(revisar), 0)
    return ventanas


def _ya_abierto(nombre: str) -> bool:
    """True si algún proceso o título de ventana abierta contiene ese nombre."""
    clave = _normalizar(nombre)
    return any(clave in _normalizar(proceso) or clave in _normalizar(titulo) for proceso, titulo in _ventanas())


def _lanzar(objetivo: str) -> None:
    """Abre una URL, una app del Menú Inicio (shell:AppsFolder), un archivo o un comando."""
    if objetivo.startswith(("http://", "https://")):
        webbrowser.open(objetivo)
        return
    if objetivo.startswith("shell:AppsFolder"):  # apps del Menú Inicio y de la Store
        subprocess.Popen(["explorer.exe", objetivo])
        return
    try:
        os.startfile(objetivo)  # type: ignore[attr-defined]  (solo existe en Windows)
    except OSError:
        subprocess.Popen(objetivo, shell=True)


def _nivel(porcentaje: float) -> str:
    """Califica un uso en porcentaje para que el modelo no tenga que interpretarlo."""
    if porcentaje < 60:
        return "normal"
    if porcentaje < 85:
        return "algo alto"
    return "muy alto"


def _tecla(codigo_vk: int) -> None:
    """Simula presionar y soltar una tecla (código virtual de Windows)."""
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    user32.keybd_event(codigo_vk, 0, 0, 0)
    user32.keybd_event(codigo_vk, 0, _KEYEVENTF_KEYUP, 0)


# Procesos que Dahiana nunca debe cerrar (incluye su interfaz y su motor de modelos).
_PROTEGIDOS = {
    "explorer.exe", "python.exe", "pythonw.exe", "dahiana.exe", "llama-server.exe",
    "svchost.exe", "csrss.exe", "winlogon.exe", "lsass.exe", "services.exe",
    "system", "smss.exe", "dwm.exe",
}

_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

# ---------------------------------------------------------------- herramientas


def abrir_programa(nombre: str) -> str:
    """Abre un programa o aplicación instalada en el PC (también apps de la Microsoft Store).

    Si hay varias opciones parecidas no abre nada y devuelve la lista para que le preguntes a Nine.

    Args:
        nombre: Nombre del programa, por ejemplo "Steam", "WhatsApp" o "bloc de notas".

    Returns:
        Resultado de la operación, o las opciones encontradas.
    """
    atajos = {_normalizar(alias): objetivo for alias, objetivo in APPS.items()}
    if _normalizar(nombre) in atajos:
        ya_estaba = _ya_abierto(nombre)
        _lanzar(atajos[_normalizar(nombre)])
        return f"{nombre} ya estaba abierto; lo traje al frente." if ya_estaba else f"Abrí {nombre}."

    resultados = _buscar(nombre)
    if not resultados:  # quizá se instaló hace poco: rehacer el índice una vez
        _indice_programas.cache_clear()
        resultados = _buscar(nombre)
    if not resultados:
        return f"No encontré ningún programa instalado llamado '{nombre}'."

    mejor, *resto = resultados
    empatados = [r for r in resto if r[0] == mejor[0]]
    if mejor[0] == 100 or (mejor[0] >= 50 and not empatados):
        ya_estaba = _ya_abierto(mejor[1])
        _lanzar(mejor[2])  # si ya estaba abierto, Windows normalmente lo trae al frente
        return f"{mejor[1]} ya estaba abierto; lo traje al frente." if ya_estaba else f"Abrí {mejor[1]}."

    # Si hay coincidencias reales, no se mezclan con las que solo se parecen por las letras.
    minimo = 50 if mejor[0] >= 50 else 0
    opciones = ", ".join([r[1] for r in resultados if r[0] >= minimo][:5])
    if mejor[0] < 50:
        return f"No encontré '{nombre}' exacto. Lo más parecido: {opciones}. Pregúntale si se refiere a alguno."
    return f"No abrí nada: hay varias opciones ({opciones}). Pregúntale cuál quiere."


def buscar_programas(consulta: str) -> str:
    """Busca qué programas hay instalados en el PC, sin abrir ninguno. Úsala para saber si algo está instalado o ver opciones.

    Args:
        consulta: Parte del nombre del programa, por ejemplo "office", "steam" o "adobe".

    Returns:
        Los programas instalados que coinciden.
    """
    resultados = _buscar(consulta)
    if not resultados:
        return f"No hay ningún programa instalado que coincida con '{consulta}'."
    nombres = [r[1] for r in resultados[:8]]
    extra = f" (y {len(resultados) - 8} más)" if len(resultados) > 8 else ""
    return f"Instalados que coinciden con '{consulta}': {', '.join(nombres)}{extra}."


def ventanas_abiertas() -> str:
    """Dice qué ventanas tiene abiertas Nine y sus títulos. El título suele decir el chat o la página: en Discord "@Nombre" es la persona con quien habla y "#canal" un canal de un servidor.

    Returns:
        Lista de programas abiertos con el título de su ventana.
    """
    lineas: list[str] = []
    for proceso, titulo in _ventanas():
        programa = proceso.removesuffix(".exe")
        if titulo == "Program Manager":  # el escritorio de Windows
            continue
        # Las apps de la Store corren dentro de ApplicationFrameHost: basta con el título.
        linea = titulo if programa == "ApplicationFrameHost" else f"{programa}: {titulo}"
        if linea not in lineas:
            lineas.append(linea)
    if not lineas:
        return "No hay ventanas abiertas."
    return "Ventanas abiertas: " + " | ".join(lineas)


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


def controlar_volumen(accion: typing.Literal["subir", "bajar", "silenciar"], cantidad: int = 5) -> str:
    """Sube, baja o silencia el volumen del PC.

    Args:
        accion: Qué hacer; "silenciar" también sirve para quitar el silencio.
        cantidad: Cuántos pasos subir o bajar (1 a 50); cada paso es aproximadamente 2%. Por defecto 5.

    Returns:
        Resultado de la operación.
    """
    accion = accion.lower().strip()
    cantidad = max(1, min(int(cantidad), 50))
    if accion == "silenciar":
        _tecla(_VK_SILENCIO)
        return "Alterné el silencio."
    if accion in ("subir", "bajar"):
        vk = _VK_SUBIR_VOLUMEN if accion == "subir" else _VK_BAJAR_VOLUMEN
        for _ in range(cantidad):
            _tecla(vk)
        return f"Volumen: {accion} unos {cantidad * 2}%."
    return f"No entiendo la acción '{accion}'. Usa subir, bajar o silenciar."


# Canal para dar órdenes a la interfaz: servicio.py lo conecta al protocolo JSON.
# En la terminal (main.py) queda en None y las herramientas de interfaz lo dicen.
avisar_a_la_interfaz: Callable[[dict], None] | None = None


def cambiar_vista(vista: typing.Literal["orbe", "chat"]) -> str:
    """Oculta el chat y deja solo el orbe flotante, o vuelve a mostrar el chat. Úsala solo si Nine lo pide.

    Args:
        vista: "orbe" para ver solo el orbe (sin la conversación) o "chat" para volver a verla.

    Returns:
        Resultado de la operación.
    """
    if avisar_a_la_interfaz is None:
        return "Eso solo funciona en la interfaz, no en la terminal."
    avisar_a_la_interfaz({"tipo": "vista", "vista": vista})
    return "Listo: ahora solo se ve el orbe." if vista == "orbe" else "Listo: el chat se ve otra vez."


def controlar_musica(accion: typing.Literal["pausar", "reanudar", "siguiente", "anterior"]) -> str:
    """Controla la música que esté sonando (Spotify, YouTube en el navegador...) con las teclas multimedia.

    Args:
        accion: Pausar, reanudar, pasar a la siguiente canción o volver a la anterior.

    Returns:
        Resultado de la operación.
    """
    if accion in ("pausar", "reanudar"):
        _tecla(_VK_REPRODUCIR_PAUSAR)  # una sola tecla alterna entre pausar y reanudar
        return "Pulsé pausar/reanudar."
    if accion in ("siguiente", "anterior"):
        _tecla(_VK_SIGUIENTE if accion == "siguiente" else _VK_ANTERIOR)
        return f"Pasé a la canción {accion}."
    return f"No entiendo la acción '{accion}'. Usa pausar, reanudar, siguiente o anterior."


def reproducir_en_spotify(
    nombre: str, tipo: typing.Literal["cancion", "artista", "album", "playlist"] = "cancion", artista: str = ""
) -> str:
    """Pone en Spotify una canción, un artista, un álbum o una playlist (también las playlists de Nine).

    Args:
        nombre: Solo el nombre de lo que quiere oír, sin el artista, por ejemplo "Tití me preguntó".
        tipo: Qué es: una canción (por defecto), un artista, un álbum o una playlist.
        artista: El artista, si Nine lo dijo, por ejemplo "Bad Bunny". Vacío si no lo dijo.

    Returns:
        Lo que empezó a sonar (puede no ser exactamente lo pedido), o qué salió mal.
    """
    try:
        elemento = spotify.buscar(nombre, tipo, artista)
        spotify.reproducir(elemento)
    except spotify.ErrorSpotify as error:
        # Respaldo: al menos dejarle la búsqueda abierta para que Nine le dé play.
        busqueda = f"{nombre} {artista}".strip()
        _lanzar(f"spotify:search:{quote(busqueda)}")
        return f"{error} Abrí la búsqueda '{busqueda}' en Spotify para que Nine le dé play."
    sonando = spotify.describir(elemento)
    if not spotify.coincide(nombre, elemento["name"]):  # Spotify devolvió otra cosa
        return f"Ojo: no encontré '{nombre}' exacto; está sonando {sonando}. Díselo a Nine."
    artistas = [a["name"] for a in elemento.get("artists", [])]
    if artista and artistas and not any(spotify.coincide(artista, a) for a in artistas):
        return f"Está sonando {sonando}. Ojo: es de otro artista, no de {artista}; díselo a Nine."
    return f"Está sonando en Spotify: {sonando}."


def que_esta_sonando() -> str:
    """Dice qué canción está sonando ahora en Spotify.

    Returns:
        La canción y su artista, o que no suena nada.
    """
    try:
        actual = spotify.sonando()
    except spotify.ErrorSpotify as error:
        return str(error)
    return f"Suena: {actual}." if actual else "No está sonando nada en Spotify."


def momento_del_dia(hora: int) -> str:
    """Traduce una hora (0-23) a madrugada, mañana, tarde o noche."""
    if hora < 5:
        return "madrugada"
    if hora < 12:
        return "mañana"
    if hora < 19:
        return "tarde"
    return "noche"


def fecha_hablada(fecha: datetime.date) -> str:
    """"domingo 27 de septiembre": una fecha como la diría una persona (sin el año)."""
    return f"{_DIAS[fecha.weekday()]} {fecha.day} de {_MESES[fecha.month - 1]}"


def hora_y_fecha() -> str:
    """Devuelve la hora y la fecha actuales.

    Returns:
        La fecha y hora actuales, dichas como las diría una persona.
    """
    ahora = datetime.datetime.now()
    hora = ahora.hour % 12 or 12
    # "Es la 1:05" pero "Son las 6:39"; sin "PM", que en voz alta suena robótico.
    inicio = "Es la" if hora == 1 else "Son las"
    # Sin el año: el modelo lo repetía al decir la hora en voz alta.
    return f"{inicio} {hora}:{ahora.minute:02d} de la {momento_del_dia(ahora.hour)} del {fecha_hablada(ahora)}."


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
    buscar_programas,
    ventanas_abiertas,
    cerrar_programa,
    abrir_sitio_web,
    buscar_en_internet,
    buscar_en_youtube,
    controlar_volumen,
    controlar_musica,
    reproducir_en_spotify,
    que_esta_sonando,
    cambiar_vista,
    hora_y_fecha,
    estado_del_pc,
]

MAPA_HERRAMIENTAS = {f.__name__: f for f in HERRAMIENTAS}

# ---------------------------------------------------------------- esquemas para el modelo

_TIPOS_JSON = {str: "string", int: "integer", float: "number", bool: "boolean"}


def _esquema(funcion: Callable) -> dict:
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
        propiedad = {"type": _TIPOS_JSON.get(param.annotation, "string"), "description": args_doc.get(nombre, "")}
        if typing.get_origin(param.annotation) is typing.Literal:
            # Literal["a", "b"] -> enum: el modelo solo puede elegir entre esos valores.
            propiedad["enum"] = list(typing.get_args(param.annotation))
        propiedades[nombre] = propiedad
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
