"""Pruebas de iniciativa.py: cuándo Dahiana le habla primero a Nine (y cuándo no, para no molestar).

Las situaciones se simulan con horas inventadas: no se observa Windows ni se espera tiempo real.
"""

import datetime
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import iniciativa as ini

LUNES_10AM = datetime.datetime(2026, 9, 28, 10, 0)


def _obs(minutos_desde_las_10: float, actividad: str = "otro", inactivo: float = 0, cancion: str | None = None,
         base: datetime.datetime = LUNES_10AM) -> ini.Observacion:
    """Observación simulada a cierta distancia (en minutos) de la hora base."""
    return ini.Observacion(base + datetime.timedelta(minutes=minutos_desde_las_10), inactivo, actividad,
                           "Hollow Knight" if actividad == "juego" else "Visual Studio Code", cancion)


class AzarFijo:
    """Reemplazo de random.Random: siempre el mismo resultado, para pruebas deterministas."""

    def __init__(self, valor: float):
        self.valor = valor

    def random(self) -> float:
        return self.valor

    def choice(self, opciones):
        return opciones[0]


def _vigia(**datos) -> ini.Vigia:
    """Vigía que ya saludó (para probar los otros motivos sin que el saludo se adelante)."""
    return ini.Vigia(ultimo_saludo=LUNES_10AM, ultima_interaccion=LUNES_10AM, **datos)


class PruebaSaludo(unittest.TestCase):
    def test_saluda_al_llegar_y_no_de_nuevo(self):
        vigia = ini.Vigia()
        self.assertEqual(vigia.revisar(_obs(0)).tipo, "saludo")
        self.assertIsNone(vigia.revisar(_obs(1)))

    def test_si_no_esta_frente_al_pc_no_saluda(self):
        self.assertIsNone(ini.Vigia().revisar(_obs(0, inactivo=30)))

    def test_vuelve_a_saludar_tras_horas_sin_verse(self):
        vigia = ini.Vigia()
        vigia.revisar(_obs(0))
        self.assertEqual(vigia.revisar(_obs(ini.SALUDO_TRAS_AUSENCIA + 1)).tipo, "saludo")


class PruebaJuego(unittest.TestCase):
    def _jugar(self, vigia: ini.Vigia, desde: int, hasta: int) -> list[ini.Motivo]:
        """Simula revisiones cada minuto jugando y devuelve los motivos que salieron."""
        motivos = [vigia.revisar(_obs(m, "juego")) for m in range(desde, hasta)]
        return [m for m in motivos if m]

    def test_avisa_a_las_tres_horas_con_plantilla(self):
        motivos = self._jugar(_vigia(azar=AzarFijo(0.5)), 0, ini.JUEGO_LARGO + 1)
        self.assertEqual([m.tipo for m in motivos], ["juego_largo"])
        self.assertIn("3 horas", motivos[0].plantilla)  # para el modo juego, sin el modelo

    def test_repite_cada_hora_no_antes(self):
        motivos = self._jugar(_vigia(azar=AzarFijo(0.5)), 0, ini.JUEGO_LARGO + ini.JUEGO_REPETIR_CADA + 1)
        self.assertEqual(len(motivos), 2)

    def test_salir_un_momento_no_reinicia_la_cuenta(self):
        vigia = _vigia(azar=AzarFijo(0.5))
        self._jugar(vigia, 0, 100)  # último minuto en el juego: el 99
        vigia.revisar(_obs(102, "otro"))  # sale un momento...
        self.assertEqual([m.tipo for m in self._jugar(vigia, 104, ini.JUEGO_LARGO + 1)], ["juego_largo"])  # ...y vuelve 5 min después

    def test_salir_largo_si_reinicia_la_cuenta(self):
        vigia = _vigia(azar=AzarFijo(0.5))
        self._jugar(vigia, 0, 100)
        self.assertEqual(self._jugar(vigia, 130, ini.JUEGO_LARGO + 1), [])  # 30 min fuera: empezó de nuevo

    def test_sin_permiso_no_comenta_el_juego(self):
        self.assertEqual(self._jugar(_vigia(atenta=False), 0, ini.JUEGO_LARGO + 1), [])


class PruebaOtrosMotivos(unittest.TestCase):
    def test_madrugada_programando_una_vez_por_noche(self):
        vigia = _vigia(ultima_iniciativa=None)
        madrugada = datetime.datetime(2026, 9, 29, 2, 30)
        vigia.ultimo_saludo = vigia.ultima_interaccion = madrugada
        self.assertEqual(vigia.revisar(_obs(0, "codigo", base=madrugada)).tipo, "madrugada_codigo")
        self.assertIsNone(vigia.revisar(_obs(ini.PAUSA_ENTRE_INICIATIVAS + 5, "codigo", base=madrugada)))

    def test_comenta_algunas_canciones_nuevas(self):
        vigia = _vigia(azar=AzarFijo(0.0))  # 0.0: siempre "le toca" comentar
        self.assertEqual(vigia.revisar(_obs(0, cancion="T.N.T. de AC/DC")).tipo, "cancion")
        self.assertIsNone(vigia.revisar(_obs(ini.PAUSA_ENTRE_INICIATIVAS + 1, cancion="T.N.T. de AC/DC")))

    def test_no_comenta_si_no_le_toca(self):
        self.assertIsNone(_vigia(azar=AzarFijo(0.99)).revisar(_obs(0, cancion="Provenza de KAROL G")))

    def test_silencio_largo(self):
        motivo = _vigia().revisar(_obs(ini.SILENCIO_LARGO + 1))
        self.assertEqual(motivo.tipo, "silencio")
        self.assertIn("2 horas", motivo.indicacion)

    def test_hablarle_reinicia_el_silencio(self):
        vigia = _vigia()
        vigia.registrar_interaccion(LUNES_10AM + datetime.timedelta(minutes=100))
        self.assertIsNone(vigia.revisar(_obs(ini.SILENCIO_LARGO + 1)))


class PruebaLimites(unittest.TestCase):
    def test_pausa_entre_iniciativas(self):
        vigia = _vigia(azar=AzarFijo(0.0))
        vigia.revisar(_obs(0, cancion="Canción A"))
        self.assertIsNone(vigia.revisar(_obs(10, cancion="Canción B")))  # muy pronto

    def test_maximo_por_dia(self):
        vigia = _vigia(azar=AzarFijo(0.0), iniciativas_hoy=ini.MAXIMO_POR_DIA, dia=LUNES_10AM.date())
        self.assertIsNone(vigia.revisar(_obs(0, cancion="Canción A")))


class PruebaPersistenciaYClasificacion(unittest.TestCase):
    def test_guardar_y_cargar(self):
        with tempfile.TemporaryDirectory() as carpeta, \
             patch.object(ini, "ARCHIVO_ESTADO", Path(carpeta) / "estado.json"):
            original = ini.Vigia(ultimo_saludo=LUNES_10AM, iniciativas_hoy=3, dia=LUNES_10AM.date())
            original.guardar()
            recuperado = ini.Vigia()
            recuperado.cargar()
        self.assertEqual((recuperado.ultimo_saludo, recuperado.iniciativas_hoy, recuperado.dia),
                         (LUNES_10AM, 3, LUNES_10AM.date()))

    def test_clasificar(self):
        self.assertEqual(ini.clasificar(r"D:\Steam\steamapps\common\Hollow Knight\hk.exe", "hk.exe"), "juego")
        self.assertEqual(ini.clasificar(r"C:\Program Files\Code\Code.exe", "Code.exe"), "codigo")
        self.assertEqual(ini.clasificar(r"C:\Program Files\Google\Chrome\chrome.exe", "chrome.exe"), "otro")


if __name__ == "__main__":
    unittest.main()
