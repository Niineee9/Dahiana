"""Iniciativa de Dahiana: decide cuándo hablarle primero a Nine y por qué.

Motivos: el saludo al llegar, un silencio largo, muchas horas jugando, programar de madrugada y
comentar una canción. Para no molestar: solo si Nine está frente al PC, con pausas mínimas entre
iniciativas y un máximo por día.

El Vigia solo decide; la observación de Windows (ventana activa, minutos sin tocar el PC) va aparte
en observar(), para poder probar la lógica con situaciones simuladas.
"""

import ctypes
import datetime
import json
import os
import random
from dataclasses import dataclass, field
from pathlib import Path

import psutil

from tools import momento_del_dia

ARCHIVO_ESTADO = Path(os.environ.get("APPDATA", Path.home())) / "Dahiana" / "estado.json"

# Reglas para no molestar (minutos).
AUSENTE_SI_INACTIVO = 10  # sin tocar teclado ni mouse este tiempo = no está frente al PC
PAUSA_ENTRE_INICIATIVAS = 40
MAXIMO_POR_DIA = 8
SALUDO_TRAS_AUSENCIA = 4 * 60  # vuelve a saludar si pasó este tiempo desde el último saludo
SILENCIO_LARGO = 2 * 60
JUEGO_LARGO = 3 * 60
JUEGO_REPETIR_CADA = 60
PAUSA_EN_JUEGO_TOLERADA = 10  # salir un momento del juego no reinicia la cuenta
CANCION_PROBABILIDAD = 0.2  # no comenta todas las canciones: solo algunas, al azar
CANCION_PAUSA = 60

# Carpetas donde viven los juegos: si la ventana activa sale de aquí, Nine está jugando.
_CARPETAS_DE_JUEGOS = ("steamapps\\common", "epic games", "riot games", "xboxgames", "gog galaxy\\games")
_PROGRAMAS_DE_CODIGO = {"code.exe", "devenv.exe", "idea64.exe", "pycharm64.exe", "windowsterminal.exe"}

_PLANTILLAS_JUEGO = [  # sin el modelo (modo juego): frases listas y solo la voz de Edge, sin usar la GPU
    "{nombre}, llevas {horas} horas jugando. ¿Una pausita para estirarte y tomar agua?",
    "Oye, {nombre}, ya van {horas} horas de juego. Tus ojos te agradecerían un respiro cortito.",
    "{horas} horas jugando, {nombre}. Levántate un minuto, estira la espalda y vuelves con todo.",
]


@dataclass
class Observacion:
    """Lo que se ve del PC en un momento dado."""

    ahora: datetime.datetime
    minutos_inactivo: float  # sin tocar teclado ni mouse
    actividad: str  # "juego", "codigo" u "otro"
    programa: str  # nombre de la ventana activa (ej. "Hollow Knight")
    cancion: str | None = None  # lo que suena en Spotify, si se consultó


@dataclass
class Motivo:
    """Razón para que Dahiana hable primero.

    Args:
        tipo: "saludo", "silencio", "juego_largo", "madrugada_codigo" o "cancion".
        indicacion: Qué debe hacer el modelo (se le da como nota interna).
        plantilla: Frase lista para cuando el modelo está apagado (modo juego); None si no hay.
    """

    tipo: str
    indicacion: str
    plantilla: str | None = None


def _minutos(desde: datetime.datetime | None, hasta: datetime.datetime) -> float:
    """Minutos entre dos momentos; infinito si `desde` no ocurrió nunca."""
    return float("inf") if desde is None else (hasta - desde).total_seconds() / 60


@dataclass
class Vigia:
    """Decide si hay un motivo para hablarle a Nine. Recuerda lo necesario entre revisiones.

    Args:
        nombre: Cómo se llama a Nine en los mensajes.
        atenta: Si puede comentar lo que Nine hace (juego, código, música). El saludo y el silencio no dependen de esto.
    """

    nombre: str = "Nine"
    atenta: bool = True
    ultima_interaccion: datetime.datetime | None = None
    ultimo_saludo: datetime.datetime | None = None
    ultima_iniciativa: datetime.datetime | None = None
    iniciativas_hoy: int = 0
    dia: datetime.date | None = None
    inicio_juego: datetime.datetime | None = None
    ultimo_en_juego: datetime.datetime | None = None
    ultimo_aviso_juego: datetime.datetime | None = None
    noche_comentada: datetime.date | None = None
    ultima_cancion: str | None = None
    ultimo_comentario_cancion: datetime.datetime | None = None
    azar: random.Random = field(default_factory=random.Random)

    def registrar_interaccion(self, ahora: datetime.datetime) -> None:
        """Nine habló con Dahiana: reinicia la cuenta del silencio."""
        self.ultima_interaccion = ahora

    def revisar(self, obs: Observacion) -> Motivo | None:
        """Devuelve el motivo para hablar ahora, o None. Si devuelve uno, lo da por usado."""
        self._seguir_juego(obs)
        if obs.minutos_inactivo >= AUSENTE_SI_INACTIVO:
            return None  # no está frente al PC
        if self.dia != obs.ahora.date():
            self.dia, self.iniciativas_hoy = obs.ahora.date(), 0

        motivo = self._saludo(obs)  # el saludo no espera la pausa entre iniciativas
        if motivo is None and self.iniciativas_hoy < MAXIMO_POR_DIA \
                and _minutos(self.ultima_iniciativa, obs.ahora) >= PAUSA_ENTRE_INICIATIVAS:
            motivo = self._juego_largo(obs) or self._madrugada(obs) or self._cancion(obs) or self._silencio(obs)
        if motivo:
            self.ultima_iniciativa = obs.ahora
            self.iniciativas_hoy += 1
        return motivo

    # ------------------------------------------------------------ motivos

    def _saludo(self, obs: Observacion) -> Motivo | None:
        if _minutos(self.ultimo_saludo, obs.ahora) < SALUDO_TRAS_AUSENCIA:
            return None
        self.ultimo_saludo = obs.ahora
        return Motivo("saludo", (
            f"{self.nombre} acaba de llegar al PC. Salúdalo según el momento del día "
            f"({momento_del_dia(obs.ahora.hour)}). Si en tu memoria hay algo para hoy o mañana, o algo "
            "importante que te contó hace poco, menciónalo con cariño."))

    def _silencio(self, obs: Observacion) -> Motivo | None:
        referencia = max((t for t in (self.ultima_interaccion, self.ultima_iniciativa) if t), default=None)
        if obs.actividad == "juego" or _minutos(referencia, obs.ahora) < SILENCIO_LARGO:
            return None
        horas = int(_minutos(referencia, obs.ahora) // 60) if referencia else None
        tiempo = f"{horas} horas" if horas else "un buen rato"
        return Motivo("silencio", (
            f"{self.nombre} lleva {tiempo} sin hablarte, pero está en el PC. Escríbele algo breve y "
            "cariñoso, sin reclamarle ni preguntar si necesita ayuda."))

    def _seguir_juego(self, obs: Observacion) -> None:
        """Lleva la cuenta del tiempo jugando (salir un momento no la reinicia)."""
        if obs.actividad == "juego":
            if _minutos(self.ultimo_en_juego, obs.ahora) > PAUSA_EN_JUEGO_TOLERADA:
                self.inicio_juego, self.ultimo_aviso_juego = obs.ahora, None
            self.ultimo_en_juego = obs.ahora
        elif _minutos(self.ultimo_en_juego, obs.ahora) > PAUSA_EN_JUEGO_TOLERADA:
            self.inicio_juego = None

    def _juego_largo(self, obs: Observacion) -> Motivo | None:
        if not self.atenta or obs.actividad != "juego" or self.inicio_juego is None:
            return None
        jugando = _minutos(self.inicio_juego, obs.ahora)
        if jugando < JUEGO_LARGO or _minutos(self.ultimo_aviso_juego, obs.ahora) < JUEGO_REPETIR_CADA:
            return None
        self.ultimo_aviso_juego = obs.ahora
        horas = int(jugando // 60)
        plantilla = self.azar.choice(_PLANTILLAS_JUEGO).format(nombre=self.nombre, horas=horas)
        return Motivo("juego_largo", (
            f"{self.nombre} lleva {horas} horas jugando {obs.programa}. Sugiérele con cariño una pausa "
            "corta (estirarse, tomar agua, descansar la vista), sin regañarlo."), plantilla)

    def _madrugada(self, obs: Observacion) -> Motivo | None:
        if not self.atenta or obs.actividad != "codigo" or obs.ahora.hour >= 5 \
                or self.noche_comentada == obs.ahora.date():
            return None
        self.noche_comentada = obs.ahora.date()
        return Motivo("madrugada_codigo", (
            f"Es de madrugada ({obs.ahora:%H:%M}) y {self.nombre} está programando en {obs.programa}. "
            "Coméntalo con ternura y un toque de humor, y recuérdale que descansar también cuenta."))

    def _cancion(self, obs: Observacion) -> Motivo | None:
        if not self.atenta or not obs.cancion or obs.cancion == self.ultima_cancion:
            return None
        self.ultima_cancion = obs.cancion
        if _minutos(self.ultimo_comentario_cancion, obs.ahora) < CANCION_PAUSA \
                or self.azar.random() > CANCION_PROBABILIDAD:
            return None
        self.ultimo_comentario_cancion = obs.ahora
        return Motivo("cancion", (
            f"Está sonando {obs.cancion} en el Spotify de {self.nombre}. Coméntala en una o dos frases, "
            "con tu opinión o un dato curioso, sin interrumpir demasiado."))

    # ------------------------------------------------------------ persistencia

    def guardar(self) -> None:
        """Guarda lo que debe sobrevivir a reiniciar Dahiana (para no saludar en cada arranque)."""
        estado = {
            "ultimo_saludo": _texto(self.ultimo_saludo),
            "ultima_iniciativa": _texto(self.ultima_iniciativa),
            "dia": _texto(self.dia),
            "iniciativas_hoy": self.iniciativas_hoy,
        }
        ARCHIVO_ESTADO.parent.mkdir(parents=True, exist_ok=True)
        ARCHIVO_ESTADO.write_text(json.dumps(estado), encoding="utf-8")

    def cargar(self) -> None:
        """Recupera el estado guardado; si no hay o está dañado, empieza de cero."""
        try:
            estado = json.loads(ARCHIVO_ESTADO.read_text(encoding="utf-8"))
            self.ultimo_saludo = _fecha(estado.get("ultimo_saludo"), datetime.datetime)
            self.ultima_iniciativa = _fecha(estado.get("ultima_iniciativa"), datetime.datetime)
            self.dia = _fecha(estado.get("dia"), datetime.date)
            self.iniciativas_hoy = int(estado.get("iniciativas_hoy") or 0)
        except (OSError, ValueError, TypeError):
            pass


def _texto(fecha: datetime.date | None) -> str | None:
    """Fecha u hora como texto ISO para guardarla en JSON."""
    return fecha.isoformat() if fecha else None


def _fecha(texto: str | None, tipo: type) -> datetime.datetime | datetime.date | None:
    """Lo contrario de _texto: de texto ISO a fecha u hora."""
    return tipo.fromisoformat(texto) if texto else None


# ---------------------------------------------------------------- observar Windows


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def minutos_sin_usar_el_pc() -> float:
    """Minutos desde la última vez que Nine tocó el teclado o el mouse."""
    info = _LASTINPUTINFO(ctypes.sizeof(_LASTINPUTINFO))
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):  # type: ignore[attr-defined]
        return 0
    milisegundos = ctypes.windll.kernel32.GetTickCount() - info.dwTime  # type: ignore[attr-defined]
    return max(milisegundos, 0) / 60_000


def clasificar(ruta: str, nombre: str) -> str:
    """"juego", "codigo" u "otro" según el ejecutable de la ventana activa."""
    if any(carpeta in ruta.lower() for carpeta in _CARPETAS_DE_JUEGOS):
        return "juego"
    return "codigo" if nombre.lower() in _PROGRAMAS_DE_CODIGO else "otro"


def ventana_activa() -> tuple[str, str]:
    """(actividad, título) de la ventana que Nine tiene al frente."""
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    hwnd = user32.GetForegroundWindow()
    largo = user32.GetWindowTextLengthW(hwnd)
    titulo = ctypes.create_unicode_buffer(largo + 1)
    user32.GetWindowTextW(hwnd, titulo, largo + 1)
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        proceso = psutil.Process(pid.value)
        actividad = clasificar(proceso.exe(), proceso.name())
    except psutil.Error:
        actividad = "otro"
    return actividad, titulo.value or "un programa"


def observar(cancion: str | None = None) -> Observacion:
    """Mira el PC ahora mismo."""
    actividad, programa = ventana_activa()
    return Observacion(datetime.datetime.now(), minutos_sin_usar_el_pc(), actividad, programa, cancion)
