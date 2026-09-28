"""Motor de Dahiana: enciende y apaga llama.cpp (llama-server) con el modelo local.

Ejecutado directamente (python motor.py) lo inicia en primer plano mostrando su registro.
"""

import subprocess
import time
import urllib.request

import psutil

from config import MODELO, MOTOR

_SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # solo existe en Windows


def _argumentos() -> list[str]:
    """Línea de comandos de llama-server con la configuración de MOTOR."""
    # -ngl 99: todo en la GPU · -np 1: una conversación · --load-mode none: sin copia en RAM
    # --reasoning off: sin modo "pensar" · muestreo recomendado por Qwen3 sin razonamiento
    return [
        MOTOR["ejecutable"], "-m", MOTOR["modelo"], "--alias", MODELO,
        "--host", "127.0.0.1", "--port", str(MOTOR["puerto"]),
        "-ngl", "99", "-c", str(MOTOR["contexto"]), "-np", "1",
        "--load-mode", "none", "--jinja", "--reasoning", "off",
        "--temp", "0.7", "--top-p", "0.8", "--top-k", "20", "--min-p", "0",
    ]


def esta_activo() -> bool:
    """True si el servidor responde y el modelo ya terminó de cargar."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{MOTOR['puerto']}/health", timeout=1) as r:
            return r.status == 200
    except OSError:  # apagado, o 503 mientras carga
        return False


class Motor:
    """Controla el proceso de llama-server: lo enciende cuando hace falta y lo apaga (modo juego)."""

    def __init__(self):
        self._proceso: subprocess.Popen | None = None

    def encender(self, espera: float = 120) -> bool:
        """Enciende el servidor si hace falta y espera a que el modelo cargue.

        Args:
            espera: Segundos máximos de espera (la primera carga desde disco puede tardar).

        Returns:
            True si el modelo quedó listo; False si el proceso falló o se agotó la espera.
        """
        if esta_activo():
            return True
        if self._proceso is None or self._proceso.poll() is not None:
            self._proceso = subprocess.Popen(
                _argumentos(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, creationflags=_SIN_VENTANA,
            )
        limite = time.monotonic() + espera
        while time.monotonic() < limite:
            if esta_activo():
                return True
            if self._proceso.poll() is not None:  # se cerró: ruta mala, sin VRAM, etc.
                return False
            time.sleep(0.5)
        return False

    def apagar(self) -> None:
        """Apaga el servidor y libera la VRAM, aunque lo haya encendido otro (p. ej. el .bat)."""
        if self._proceso and self._proceso.poll() is None:
            self._proceso.terminate()
            try:
                self._proceso.wait(10)
            except subprocess.TimeoutExpired:
                self._proceso.kill()
        self._proceso = None
        for proceso in psutil.process_iter(["name"]):
            if (proceso.info["name"] or "").lower() == "llama-server.exe":
                try:
                    proceso.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass


if __name__ == "__main__":
    subprocess.run(_argumentos())
