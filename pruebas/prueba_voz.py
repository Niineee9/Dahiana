"""Pruebas de voz.py: detección de silencio, remuestreo, pronunciación y voz de respaldo.

No usan el micrófono ni internet: la energía del audio y las voces se simulan.
"""

import unittest
from unittest.mock import patch

import numpy as np

import voz

SILENCIO, VOZ = 0.001, 0.05  # energías típicas de ruido de fondo y de alguien hablando


def _procesar(detector: voz.DetectorDeSilencio, energias: list[float]) -> list[str]:
    """Pasa una secuencia de energías por el detector y devuelve cada estado."""
    return [detector.agregar(e) for e in energias]


def _bloques(segundos: float) -> int:
    return round(segundos / voz.DURACION_BLOQUE)


class PruebaDetectorDeSilencio(unittest.TestCase):
    def test_detecta_inicio_y_fin_de_la_voz(self):
        detector = voz.DetectorDeSilencio()
        silencio = detector.silencio_final + 0.1
        estados = _procesar(detector, [SILENCIO] * _bloques(0.5) + [VOZ] * _bloques(1) + [SILENCIO] * _bloques(silencio))
        self.assertIn("hablando", estados)
        self.assertEqual(estados[-1], "terminado")

    def test_sin_voz_se_rinde(self):
        detector = voz.DetectorDeSilencio(espera_maxima=2)
        estados = _procesar(detector, [SILENCIO] * _bloques(3))
        self.assertEqual(estados[-1], "sin_voz")

    def test_un_golpe_suelto_no_cuenta_como_voz(self):
        detector = voz.DetectorDeSilencio(espera_maxima=2)
        estados = _procesar(detector, [SILENCIO] * _bloques(0.5) + [VOZ] + [SILENCIO] * _bloques(2))
        self.assertNotIn("hablando", estados)

    def test_una_pausa_corta_no_corta_la_frase(self):
        detector = voz.DetectorDeSilencio(silencio_final=0.9)
        energias = [SILENCIO] * _bloques(0.5) + [VOZ] * _bloques(1) + [SILENCIO] * _bloques(0.4) + [VOZ] * _bloques(1)
        self.assertNotIn("terminado", _procesar(detector, energias))

    def test_el_umbral_se_adapta_al_ruido(self):
        detector = voz.DetectorDeSilencio()
        _procesar(detector, [0.01] * _bloques(0.5))  # habitación ruidosa
        self.assertAlmostEqual(detector._umbral, 0.03)


class PruebaAudio(unittest.TestCase):
    def test_remuestrear_a_16_khz(self):
        un_segundo = np.zeros(44_100, dtype=np.float32)
        self.assertEqual(len(voz._remuestrear(un_segundo, 44_100)), voz.FRECUENCIA)

    def test_remuestrear_filtra_los_agudos(self):
        # A 16 kHz no cabe nada sobre 8 kHz: sin filtro, un tono de 12 kHz se "dobla" a 4 kHz, sobre la voz.
        tiempo = np.arange(48_000) / 48_000
        energia = lambda tono: float(np.sqrt(np.mean(voz._remuestrear(np.sin(2 * np.pi * tono * tiempo), 48_000)[500:-500] ** 2)))
        self.assertGreater(energia(1_000), 0.65)  # la voz pasa casi intacta (un seno puro da 0,71)
        self.assertLess(energia(12_000), 0.02)

    def test_pronunciacion(self):
        with patch.dict(voz.VOZ, {"pronunciacion": {"Nine": "Nain"}}):
            self.assertEqual(voz._preparar_texto("¡Hola, Nine!"), "¡Hola, Nain!")


class PruebaAnimoEnLaVoz(unittest.TestCase):
    def test_ajustar_suma_al_valor_base(self):
        self.assertEqual(voz._ajustar("+0%", "%", 10), "+10%")
        self.assertEqual(voz._ajustar("+8Hz", "Hz", -3), "+5Hz")
        self.assertEqual(voz._ajustar("-5%", "%", -6), "-11%")

    def test_cada_animo_tiene_su_ajuste(self):
        import brain
        self.assertEqual(set(voz.AJUSTES_POR_ANIMO), set(brain.ANIMOS))


class PruebaSintetizar(unittest.TestCase):
    def test_usa_edge_si_responde(self):
        async def edge(*_):
            return b"mp3"

        with patch.object(voz, "_edge", edge):
            self.assertEqual(voz.sintetizar("hola"), (b"mp3", "audio/mpeg"))

    def test_sin_internet_usa_la_voz_de_windows(self):
        async def sin_internet(*_):
            raise OSError("sin conexión")

        with patch.object(voz, "_edge", sin_internet), patch.object(voz, "_voz_de_windows", return_value=b"wav"):
            self.assertEqual(voz.sintetizar("hola"), (b"wav", "audio/wav"))


if __name__ == "__main__":
    unittest.main()
