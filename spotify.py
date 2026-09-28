"""Spotify para Dahiana: poner canciones, artistas, álbumes o playlists y saber qué suena.

Usa la API oficial (requiere Premium) solo con la biblioteca estándar. La primera vez abre el
navegador para que Nine autorice (flujo PKCE, sin "client secret"); la autorización se guarda en
%APPDATA%\\Dahiana\\spotify.json y se renueva sola.

Ejecutado directamente (python spotify.py) pide la autorización y muestra qué está sonando.
"""

import base64
import difflib
import hashlib
import json
import os
import secrets
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from config import SPOTIFY

_CUENTAS = "https://accounts.spotify.com"
_API = "https://api.spotify.com/v1"
_RETORNO = f"http://127.0.0.1:{SPOTIFY['puerto_retorno']}/callback"
_PERMISOS = ("user-read-playback-state user-modify-playback-state user-read-currently-playing "
             "playlist-read-private")
_ARCHIVO_TOKEN = Path(os.environ.get("APPDATA", Path.home())) / "Dahiana" / "spotify.json"
_ESPERA_AUTORIZACION = 180  # segundos para que Nine acepte en el navegador
_ESPERA_DISPOSITIVO = 10  # segundos para que la app de Spotify aparezca tras abrirla

# Tipo de la API de búsqueda para cada tipo que entiende Dahiana.
TIPOS = {"cancion": "track", "artista": "artist", "album": "album", "playlist": "playlist"}


class ErrorSpotify(Exception):
    """Algo falló con Spotify; el mensaje está pensado para que Dahiana se lo explique a Nine."""


# ---------------------------------------------------------------- autorización (PKCE)


def _desafio_pkce(verificador: str) -> str:
    """Desafío PKCE: SHA-256 del verificador en base64url sin relleno (RFC 7636)."""
    resumen = hashlib.sha256(verificador.encode("ascii")).digest()
    return base64.urlsafe_b64encode(resumen).rstrip(b"=").decode("ascii")


def _pedir_token(datos: dict) -> dict:
    """Pide o renueva el token en las cuentas de Spotify y lo guarda con su vencimiento."""
    peticion = urllib.request.Request(
        f"{_CUENTAS}/api/token", data=urllib.parse.urlencode(datos).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(peticion, timeout=15) as respuesta:
            token = json.load(respuesta)
    except urllib.error.HTTPError as error:
        raise ErrorSpotify(f"Spotify rechazó la autorización ({error.code}).") from error
    except OSError as error:
        raise ErrorSpotify("No pude conectarme con Spotify (¿hay internet?).") from error
    token["vence"] = time.time() + token.get("expires_in", 3600)
    token.setdefault("refresh_token", datos.get("refresh_token"))  # a veces no manda uno nuevo
    _ARCHIVO_TOKEN.parent.mkdir(parents=True, exist_ok=True)
    _ARCHIVO_TOKEN.write_text(json.dumps(token), encoding="utf-8")
    return token


def autorizar() -> dict:
    """Abre el navegador para que Nine autorice a Dahiana y espera la respuesta en el puerto local.

    Returns:
        El token guardado.

    Raises:
        ErrorSpotify: Si Nine no autoriza a tiempo o Spotify lo rechaza.
    """
    if not SPOTIFY["client_id"]:
        raise ErrorSpotify("Spotify no está configurado: falta el Client ID en config_local.py.")
    verificador = secrets.token_urlsafe(64)
    estado = secrets.token_urlsafe(16)  # evita que otra página se haga pasar por Spotify
    recibido: dict = {}

    class Retorno(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (nombre exigido por http.server)
            consulta = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            recibido.update({clave: valores[0] for clave, valores in consulta.items()})
            listo = "code" in recibido and recibido.get("state") == estado
            mensaje = "Listo, Dahiana ya puede usar tu Spotify. Puedes cerrar esta pestaña." if listo \
                else "No se completó la autorización. Vuelve a intentarlo desde Dahiana."
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<h2 style='font-family:sans-serif'>{mensaje}</h2>".encode())

        def log_message(self, *_):  # silencio: stdout es del protocolo con la interfaz
            pass

    servidor = HTTPServer(("127.0.0.1", SPOTIFY["puerto_retorno"]), Retorno)
    servidor.timeout = 1
    webbrowser.open(f"{_CUENTAS}/authorize?" + urllib.parse.urlencode({
        "client_id": SPOTIFY["client_id"], "response_type": "code", "redirect_uri": _RETORNO,
        "scope": _PERMISOS, "state": estado,
        "code_challenge_method": "S256", "code_challenge": _desafio_pkce(verificador),
    }))
    limite = time.monotonic() + _ESPERA_AUTORIZACION
    with servidor:
        while "code" not in recibido and "error" not in recibido and time.monotonic() < limite:
            servidor.handle_request()

    if recibido.get("state") != estado or "code" not in recibido:
        raise ErrorSpotify("No se completó la autorización de Spotify en el navegador.")
    return _pedir_token({
        "grant_type": "authorization_code", "code": recibido["code"], "redirect_uri": _RETORNO,
        "client_id": SPOTIFY["client_id"], "code_verifier": verificador,
    })


def conectado() -> bool:
    """True si Spotify está configurado y Nine ya autorizó a Dahiana (consultarlo no abrirá el navegador)."""
    return bool(SPOTIFY["client_id"]) and _ARCHIVO_TOKEN.exists()


def _token_vigente() -> str:
    """Token de acceso válido: lo renueva si está por vencer y pide autorización si no hay ninguno."""
    try:
        token = json.loads(_ARCHIVO_TOKEN.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        token = autorizar()
    if token["vence"] - time.time() < 60:
        token = _pedir_token({
            "grant_type": "refresh_token", "refresh_token": token["refresh_token"],
            "client_id": SPOTIFY["client_id"],
        })
    return token["access_token"]


# ---------------------------------------------------------------- API


def _api(metodo: str, ruta: str, parametros: dict | None = None, cuerpo: dict | None = None) -> dict:
    """Llama a la API web de Spotify y devuelve el JSON de la respuesta ({} si viene vacía)."""
    url = f"{_API}{ruta}" + (f"?{urllib.parse.urlencode(parametros)}" if parametros else "")
    peticion = urllib.request.Request(
        url, method=metodo, data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
        headers={"Authorization": f"Bearer {_token_vigente()}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(peticion, timeout=15) as respuesta:
            contenido = respuesta.read()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise ErrorSpotify("No encontré un Spotify abierto para reproducir.") from error
        try:  # Spotify explica el motivo en el cuerpo: {"error": {"message": "..."}}
            motivo = json.loads(error.read())["error"]["message"]
        except (ValueError, KeyError, TypeError):
            motivo = error.reason
        raise ErrorSpotify(f"Spotify no lo permitió ({error.code}: {motivo}).") from error
    except OSError as error:
        raise ErrorSpotify("No pude conectarme con Spotify (¿hay internet?).") from error
    try:  # las órdenes (play, pausa) a veces responden vacío o con texto que no es JSON
        return json.loads(contenido) if contenido else {}
    except ValueError:
        return {}


def _dispositivo() -> str:
    """Id del dispositivo donde reproducir: el que ya está sonando o, si no hay, esta PC.

    Nunca elige otro dispositivo al azar (una TV o el celular de la casa): si esta PC no aparece,
    abre la app de Spotify y la espera.
    """
    for intento in range(_ESPERA_DISPOSITIVO):
        dispositivos = _api("GET", "/me/player/devices").get("devices", [])
        activo = next((d for d in dispositivos if d.get("is_active")), None)
        computadora = next((d for d in dispositivos if d.get("type") == "Computer"), None)
        elegido = activo or computadora
        if elegido:
            return elegido["id"]
        if intento == 0:
            os.startfile("spotify:")  # type: ignore[attr-defined]  (solo existe en Windows)
        time.sleep(1)
    raise ErrorSpotify("Abrí Spotify, pero no apareció a tiempo para reproducir.")


def _mis_playlists(nombre: str) -> dict | None:
    """Busca una playlist propia de Nine por nombre (ignora mayúsculas)."""
    try:
        playlists = _api("GET", "/me/playlists", {"limit": 50}).get("items", [])
    except ErrorSpotify:
        return None
    buscado = nombre.lower()
    return next((p for p in playlists if p and buscado in p.get("name", "").lower()), None)


RESULTADOS_POR_BUSQUEDA = 10  # máximo que permite la API desde 2026


def _simplificar(texto: str) -> str:
    """Solo letras y números, sin tildes ni mayúsculas: "AC/DC", "AC DC" y "acdc" quedan iguales."""
    sin_tildes = unicodedata.normalize("NFD", texto)
    return "".join(c for c in sin_tildes if c.isalnum() and unicodedata.category(c) != "Mn").lower()


PARECIDO_MINIMO = 0.8  # tolera errores de escritura ("Provensa" ~ "Provenza")


def coincide(buscado: str, encontrado: str) -> bool:
    """True si un nombre contiene al otro o se le parece mucho, ignorando signos, espacios y tildes."""
    a, b = _simplificar(buscado), _simplificar(encontrado)
    if not (a and b):
        return False
    return a in b or b in a or difflib.SequenceMatcher(None, a, b).ratio() >= PARECIDO_MINIMO


def _artista_oficial(artista: str) -> str:
    """Nombre exacto del artista en Spotify ("ACDC" -> "AC/DC"), para que el filtro artist: funcione."""
    if not artista:
        return ""
    artistas = _api("GET", "/search", {"q": artista, "type": "artist", "limit": 5}).get("artists", {}).get("items", [])
    return next((a["name"] for a in artistas if a and coincide(artista, a["name"])), artista)


def _consulta(nombre: str, tipo: str, artista: str) -> str:
    """Arma la búsqueda con los filtros de Spotify (track:, album:, artist:), más precisos que texto libre."""
    filtro = {"cancion": "track", "album": "album"}.get(tipo)
    partes = [f'{filtro}:"{nombre}"' if filtro else nombre]
    if artista and tipo != "artista":
        partes.append(f'artist:"{artista}"')
    return " ".join(partes)


def _puntaje(elemento: dict, nombre: str, artista: str) -> int:
    """Qué tan bien coincide un resultado: 2 si coincide el nombre, +1 si coincide el artista."""
    puntos = 2 if coincide(nombre, elemento.get("name", "")) else 0
    if artista and any(coincide(artista, a.get("name", "")) for a in elemento.get("artists", [])):
        puntos += 1
    return puntos


def buscar(nombre: str, tipo: str = "cancion", artista: str = "") -> dict:
    """Mejor resultado de Spotify para una búsqueda.

    Prueba de lo más preciso a lo más flexible y, en cada búsqueda, revisa varios resultados para
    quedarse con el que coincida en nombre y artista (no simplemente el primero).

    Args:
        nombre: Nombre de la canción, artista, álbum o playlist (sin el artista).
        tipo: "cancion", "artista", "album" o "playlist".
        artista: Artista, si Nine lo dijo (mejora mucho la precisión).

    Returns:
        El objeto de Spotify (con "uri", "name", etc.).

    Raises:
        ErrorSpotify: Si no hay resultados o falla la conexión.
    """
    if tipo == "playlist" and (propia := _mis_playlists(nombre)):
        return propia
    tipo_api = TIPOS[tipo]
    oficial = _artista_oficial(artista) if tipo != "artista" else ""
    # Con el artista oficial, en texto libre, y sin el artista (puede venir mal, arrastrado de la charla).
    consultas = dict.fromkeys([
        _consulta(nombre, tipo, oficial), f"{nombre} {oficial or artista}".strip(), _consulta(nombre, tipo, ""),
    ])
    puntaje_perfecto = 2 + (1 if artista and tipo != "artista" else 0)
    mejor, mejor_puntaje = None, -1
    for consulta in consultas:
        resultados = _api("GET", "/search", {"q": consulta, "type": tipo_api, "limit": RESULTADOS_POR_BUSQUEDA})
        for elemento in (e for e in resultados.get(f"{tipo_api}s", {}).get("items", []) if e):
            puntos = _puntaje(elemento, nombre, artista)
            if puntos == puntaje_perfecto:
                return elemento
            if puntos > mejor_puntaje:
                mejor, mejor_puntaje = elemento, puntos
    if mejor is None:
        raise ErrorSpotify(f"No encontré '{nombre}' en Spotify.")
    return mejor


MAX_ARTISTAS = 2  # más nombres no se entienden al leerlos en voz alta


def describir(elemento: dict) -> str:
    """Nombre legible: "Canción de Artista y Artista" (máximo dos artistas) o solo el nombre."""
    artistas = [a["name"] for a in elemento.get("artists", [])]
    if not artistas:
        return elemento["name"]
    nombres = " y ".join(artistas[:MAX_ARTISTAS]) + (" y otros" if len(artistas) > MAX_ARTISTAS else "")
    return f"{elemento['name']} de {nombres}"


def reproducir(elemento: dict) -> None:
    """Reproduce en esta PC una canción, o un artista/álbum/playlist completo."""
    uri = elemento["uri"]
    cuerpo = {"uris": [uri]} if uri.startswith("spotify:track:") else {"context_uri": uri}
    _api("PUT", "/me/player/play", {"device_id": _dispositivo()}, cuerpo)


def sonando() -> str | None:
    """Lo que suena ahora ("Canción de Artista"), o None si no suena nada."""
    actual = _api("GET", "/me/player/currently-playing")
    if not actual.get("item") or not actual.get("is_playing"):
        return None
    return describir(actual["item"])


if __name__ == "__main__":
    _token_vigente()
    print("Spotify conectado. Suena:", sonando() or "nada")
