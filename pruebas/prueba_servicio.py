"""Pruebas de servicio.py: el protocolo JSON que usa la interfaz.

El motor, el cerebro, el oído y la voz se simulan: no se enciende ningún modelo ni el micrófono.
"""

import io
import json
import unittest
from unittest.mock import MagicMock, patch

import servicio
from iniciativa import Motivo

RESPUESTA = {"tipo": "respuesta", "texto": "¡Hola, Nine!", "animo": "alegre"}


def _sesion(lo_que_oye: str = "abre discord", al_escuchar=None) -> servicio.Sesion:
    """Sesión con el cerebro, el motor, el oído y el vigía simulados."""
    dahiana, motor, oido = MagicMock(), MagicMock(), MagicMock()
    dahiana.responder.return_value = "¡Hola, Nine!"
    dahiana.iniciar.return_value = "¡Buenos días, Nine!"
    dahiana.animo = "alegre"
    motor.encender.return_value = True
    oido.escuchar.return_value = lo_que_oye
    oido.escuchar.side_effect = al_escuchar
    sesion = servicio.Sesion(dahiana, motor, oido, MagicMock())
    sesion.atuendo_enviado = "normal"  # la interfaz ya sabe qué ropa lleva (ver _capturar)
    return sesion


def _capturar(funcion, *argumentos, activo: bool = True, entrada: str = "", ropa: str = "normal") -> list[dict]:
    """Ejecuta una función del servicio y devuelve los eventos que envió a la interfaz.

    `ropa` es lo que lleva puesto Dahiana (fijo: si no, dependería del día y de atuendo.json).
    """
    salida = io.StringIO()
    with patch("sys.stdin", io.StringIO(entrada)), patch("sys.stdout", salida), \
         patch.object(servicio, "esta_activo", return_value=activo), \
         patch.object(servicio.atuendo, "actual", return_value=ropa), \
         patch.object(servicio, "sintetizar", return_value=(b"mp3", "audio/mpeg")):
        funcion(*argumentos)
    return [json.loads(linea) for linea in salida.getvalue().splitlines()]


def _atender(*lineas: str, activo: bool = True, lo_que_oye: str = "abre discord",
             al_escuchar=None) -> tuple[list[dict], MagicMock]:
    """Pasa líneas por _atender como si vinieran de la interfaz.

    Args:
        al_escuchar: Reemplaza a oido.escuchar(cancelar) si se quiere simular algo más que un texto.

    Returns:
        Los eventos emitidos y el cerebro simulado (para revisar qué recibió).
    """
    sesion = _sesion(lo_que_oye, al_escuchar)
    entrada = "".join(f"{linea}\n" for linea in lineas)
    eventos = _capturar(servicio._atender, sesion, False, activo=activo, entrada=entrada)
    return eventos, sesion.dahiana


class PruebaProtocolo(unittest.TestCase):
    def test_mensaje_sin_voz(self):
        eventos, _ = _atender('{"tipo": "mensaje", "texto": "hola"}')
        self.assertEqual(eventos, [{"tipo": "pensando"}, RESPUESTA])

    def test_si_se_cambio_de_ropa_se_ve_antes_de_la_respuesta(self):
        sesion = _sesion()
        eventos = _capturar(servicio._atender, sesion, False, entrada='{"tipo": "mensaje", "texto": "voy a estudiar"}\n',
                            ropa="animadora")
        self.assertEqual(eventos, [{"tipo": "pensando"}, {"tipo": "atuendo", "atuendo": "animadora"}, RESPUESTA])

    def test_las_preferencias_reciben_la_ropa_puesta(self):
        # La interfaz las manda al arrancar: el aviso de la ropa enviado antes pudo perderse.
        eventos, _ = _atender('{"tipo": "preferencias", "voz": true}')
        self.assertEqual(eventos, [{"tipo": "atuendo", "atuendo": "normal"}])

    def test_mensaje_con_voz_agrega_el_audio(self):
        eventos, _ = _atender('{"tipo": "mensaje", "texto": "hola", "hablar": true}')
        self.assertEqual(eventos[-1], {"tipo": "voz", "audio": "data:audio/mpeg;base64,bXAz"})

    def test_mensaje_en_modo_juego_despierta_el_modelo(self):
        eventos, _ = _atender('{"tipo": "mensaje", "texto": "hola"}', activo=False)
        self.assertEqual([e.get("estado") for e in eventos[:2]], ["cargando", "encendido"])
        self.assertEqual(eventos[-1]["tipo"], "respuesta")

    def test_apagar_motor(self):
        eventos, _ = _atender('{"tipo": "motor", "accion": "apagar"}')
        self.assertEqual(eventos, [{"tipo": "motor", "estado": "apagado"}])

    def test_tolera_bom_y_lineas_vacias(self):
        eventos, _ = _atender("", '\uFEFF{"tipo": "reiniciar"}')
        self.assertEqual(eventos, [])

    def test_errores_de_formato(self):
        eventos, _ = _atender("esto no es json", '{"tipo": "bailar"}')
        self.assertEqual([e["tipo"] for e in eventos], ["error", "error"])
        self.assertIn("bailar", eventos[1]["texto"])


class PruebaIniciativa(unittest.TestCase):
    MOTIVO = Motivo("juego_largo", "Lleva 3 horas jugando.", "Nine, llevas 3 horas jugando. ¿Una pausita?")

    def test_con_el_modelo_encendido_lo_escribe_el_modelo(self):
        sesion = _sesion()
        eventos = _capturar(servicio._tomar_iniciativa, sesion, self.MOTIVO)
        self.assertEqual(eventos[0], {"tipo": "iniciativa", "texto": "¡Buenos días, Nine!", "animo": "alegre"})
        self.assertEqual(eventos[1]["tipo"], "voz")

    def test_en_modo_juego_usa_la_frase_lista_sin_despertar_el_modelo(self):
        sesion = _sesion()
        eventos = _capturar(servicio._tomar_iniciativa, sesion, self.MOTIVO, activo=False)
        self.assertEqual(eventos[0]["texto"], self.MOTIVO.plantilla)
        sesion.dahiana.iniciar.assert_not_called()
        sesion.motor.encender.assert_not_called()

    def test_en_modo_juego_sin_frase_lista_no_dice_nada(self):
        saludo = Motivo("saludo", "Salúdalo.")
        self.assertEqual(_capturar(servicio._tomar_iniciativa, _sesion(), saludo, activo=False), [])

    def test_con_la_voz_apagada_solo_escribe(self):
        sesion = _sesion()
        sesion.preferencias["voz"] = False
        eventos = _capturar(servicio._tomar_iniciativa, sesion, self.MOTIVO)
        self.assertEqual([e["tipo"] for e in eventos], ["iniciativa"])

    def test_preferencias_de_la_interfaz(self):
        sesion = _sesion()
        _capturar(servicio._atender, sesion, False, entrada='{"tipo": "preferencias", "atenta": false, "orbe": true}\n')
        self.assertEqual(sesion.preferencias, {"voz": True, "orbe": True, "atenta": False})


class PruebaEscuchar(unittest.TestCase):
    def test_escucha_transcribe_responde_y_habla(self):
        eventos, dahiana = _atender('{"tipo": "escuchar"}')
        self.assertEqual([e["tipo"] for e in eventos], ["escuchando", "transcripcion", "pensando", "respuesta", "voz"])
        self.assertEqual(eventos[1]["texto"], "abre discord")
        dahiana.responder.assert_called_once_with("abre discord")

    def test_si_no_escucha_nada_no_responde(self):
        eventos, dahiana = _atender('{"tipo": "escuchar"}', lo_que_oye="")
        self.assertEqual([e["tipo"] for e in eventos], ["escuchando", "no_escuche"])
        dahiana.responder.assert_not_called()

    def test_si_lo_cancelan_no_dice_que_no_escucho(self):
        def pulsan_esc_mientras_graba(cancelar):
            cancelar.set()
            return ""

        eventos, dahiana = _atender('{"tipo": "escuchar"}', al_escuchar=pulsan_esc_mientras_graba)
        self.assertEqual([e["tipo"] for e in eventos], ["escuchando", "escucha_cancelada"])
        dahiana.responder.assert_not_called()

    def test_cancelar_no_llega_a_la_cola(self):
        eventos, _ = _atender('{"tipo": "cancelar"}')
        self.assertEqual(eventos, [])  # se atiende en el hilo lector, sin respuesta


if __name__ == "__main__":
    unittest.main()
