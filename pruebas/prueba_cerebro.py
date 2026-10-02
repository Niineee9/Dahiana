"""Pruebas de brain.py: limpieza de respuestas, historial, memoria y el bucle de tool calling.

El modelo se simula: no hace falta tener llama-server encendido. La memoria usa un archivo temporal.
"""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import atuendo
import brain
import memoria

_carpeta_temporal = tempfile.TemporaryDirectory()
_parche_memoria = patch.object(memoria, "ARCHIVO", Path(_carpeta_temporal.name) / "memoria.json")
_parche_atuendo = patch.object(atuendo, "ARCHIVO", Path(_carpeta_temporal.name) / "atuendo.json")


def setUpModule():
    # Ninguna prueba de este archivo lee ni escribe la memoria ni la ropa reales de Nine.
    _parche_memoria.start()
    _parche_atuendo.start()


def tearDownModule():
    _parche_memoria.stop()
    _parche_atuendo.stop()
    _carpeta_temporal.cleanup()


def _respuesta_del_modelo(contenido: str = "", llamadas: list | None = None) -> SimpleNamespace:
    """Imita la respuesta de cliente.chat.completions.create."""
    mensaje = SimpleNamespace(content=contenido, tool_calls=llamadas)
    return SimpleNamespace(choices=[SimpleNamespace(message=mensaje)])


def _llamada(nombre: str, argumentos: str, id_: str = "llamada-1") -> SimpleNamespace:
    """Imita un pedido de herramienta del modelo."""
    return SimpleNamespace(id=id_, function=SimpleNamespace(name=nombre, arguments=argumentos))


class PruebaAyudantes(unittest.TestCase):
    def test_limpiar_quita_emojis_y_conserva_el_espanol(self):
        self.assertEqual(brain._limpiar("¡Hola Nine! 😊 ¿Sí? ✨  Ñandú 45%"), "¡Hola Nine! ¿Sí? Ñandú 45%")

    def test_limpiar_quita_la_pregunta_de_relleno_final(self):
        self.assertEqual(brain._limpiar("Son las seis. ¿Te gustaría que te ayudara con algo más?"), "Son las seis.")
        self.assertEqual(brain._limpiar("¡Ahí va! ¿Quieres que te cuente algo sobre esta canción?"), "¡Ahí va!")
        self.assertEqual(brain._limpiar("Recuerdo tu examen. ¿Quieres hablar de algo más?"), "Recuerdo tu examen.")
        self.assertEqual(brain._limpiar("¡Listo! ¿En qué te puedo ayudar con ella?"), "¡Listo!")
        self.assertEqual(brain._limpiar("¡Qué energía! ¿Te apetece seguir con algo así?"), "¡Qué energía!")
        self.assertEqual(brain._limpiar("¡Felicidades! ¿Qué te parece si ponemos una canción?"), "¡Felicidades!")

    def test_limpiar_conserva_las_preguntas_genuinas(self):
        for texto in ("Hay dos opciones: Teams o Teams classic. ¿Cuál quieres?",
                      "¿Hace calor o frío por allá?",
                      "¿Te gustaría que te ayude?"):  # si solo es la pregunta, no se deja vacía
            self.assertEqual(brain._limpiar(texto), texto)

    def test_si_va_a_estudiar_se_pone_el_traje_y_el_modelo_lo_sabe(self):
        modelo = MagicMock()
        modelo.chat.completions.create.return_value = _respuesta_del_modelo("[emocionada] ¡Vamos, Nine!")
        with patch.object(brain, "cliente", modelo):
            dahiana = brain.Dahiana(al_usar_herramienta=None)
            dahiana.responder("voy a estudiar cálculo")
        self.assertEqual(atuendo.elegido(), "animadora")
        self.assertIn("traje de animadora", dahiana.historial[-2]["content"])  # la nota va en su mensaje
        atuendo.elegir("normal")

    def test_limpiar_quita_herramientas_escritas_como_texto(self):
        self.assertEqual(brain._limpiar('[reproducir_en_spotify("cancion", "Lullaby")] ¡Ahí va Lullaby!'),
                         "¡Ahí va Lullaby!")
        self.assertEqual(brain._limpiar("Tengo dos ideas [ver abajo]."), "Tengo dos ideas [ver abajo].")

    def test_limpiar_quita_el_formato_markdown(self):
        self.assertEqual(brain._limpiar("¡Ahí va *Tití Me Preguntó* de **Bad Bunny**!"),
                         "¡Ahí va Tití Me Preguntó de Bad Bunny!")


class PruebaHistorial(unittest.TestCase):
    def test_recortar_conserva_personalidad_y_empieza_en_usuario(self):
        dahiana = brain.Dahiana(al_usar_herramienta=None)
        for i in range(brain.MAX_HISTORIAL):
            dahiana.historial += [{"role": "user", "content": f"u{i}"}, {"role": "tool", "content": "r"}]
        dahiana._recortar_historial()
        self.assertEqual(dahiana.historial[0]["role"], "system")
        self.assertEqual(dahiana.historial[1]["role"], "user")
        self.assertLessEqual(len(dahiana.historial), brain.MAX_HISTORIAL + 1)

    def test_reiniciar_olvida_todo_menos_la_personalidad(self):
        dahiana = brain.Dahiana(al_usar_herramienta=None)
        dahiana.historial.append({"role": "user", "content": "hola"})
        dahiana.reiniciar()
        self.assertEqual(len(dahiana.historial), 1)

    def test_los_recuerdos_llegan_al_prompt_y_se_actualizan_al_reiniciar(self):
        dahiana = brain.Dahiana(al_usar_herramienta=None)
        self.assertNotIn("Le encanta AC/DC", dahiana.historial[0]["content"])
        memoria.agregar("Le encanta AC/DC")
        dahiana.reiniciar()  # una conversación nueva ya incluye lo que recordó en la anterior
        self.assertIn("Le encanta AC/DC", dahiana.historial[0]["content"])
        memoria.olvidar("AC/DC")


class PruebaAnimo(unittest.TestCase):
    def test_separa_la_etiqueta_de_animo(self):
        self.assertEqual(brain._separar_animo("[tierna] Ay, Nine, descansa."), ("tierna", "Ay, Nine, descansa."))
        self.assertEqual(brain._separar_animo("[ Alegre ] ¡Bien!"), ("alegre", "¡Bien!"))
        self.assertEqual(brain._separar_animo("Sin etiqueta."), (None, "Sin etiqueta."))

    def test_respuesta_con_animo_y_sin_etiqueta_visible(self):
        modelo = MagicMock()
        modelo.chat.completions.create.return_value = _respuesta_del_modelo("[emocionada] ¡Tres corazones!")
        dahiana = brain.Dahiana(al_usar_herramienta=None)
        with patch.object(brain, "cliente", modelo):
            self.assertEqual(dahiana.responder("los pulpos tienen tres corazones"), "¡Tres corazones!")
        self.assertEqual(dahiana.animo, "emocionada")
        self.assertTrue(dahiana.historial[-1]["content"].startswith("[emocionada]"))  # el modelo ve que la usa

    def test_si_olvida_la_etiqueta_conserva_el_animo(self):
        modelo = MagicMock()
        modelo.chat.completions.create.return_value = _respuesta_del_modelo("Son las seis.")
        dahiana = brain.Dahiana(al_usar_herramienta=None)
        dahiana.animo = "curiosa"
        with patch.object(brain, "cliente", modelo):
            dahiana.responder("¿qué hora es?")
        self.assertEqual(dahiana.animo, "curiosa")

    def test_iniciar_habla_primero_sin_herramientas(self):
        modelo = MagicMock()
        modelo.chat.completions.create.return_value = _respuesta_del_modelo("[alegre] ¡Buenos días, Nine!")
        dahiana = brain.Dahiana(al_usar_herramienta=None)
        with patch.object(brain, "cliente", modelo):
            self.assertEqual(dahiana.iniciar("Salúdalo."), "¡Buenos días, Nine!")
        self.assertNotIn("tools", modelo.chat.completions.create.call_args.kwargs)
        self.assertIn("Nota interna", dahiana.historial[1]["content"])


class PruebaActualizarMemoria(unittest.TestCase):
    def _extraer(self, texto: str, salida_del_modelo: str) -> tuple[list, MagicMock]:
        """Pasa un mensaje por actualizar_memoria con un modelo simulado; devuelve los avisos y el modelo."""
        modelo = MagicMock()
        modelo.chat.completions.create.return_value = _respuesta_del_modelo(salida_del_modelo)
        avisos = []
        with patch.object(brain, "cliente", modelo):
            brain.Dahiana(al_usar_herramienta=lambda *aviso: avisos.append(aviso)).actualizar_memoria(texto)
        return avisos, modelo

    def tearDown(self):
        for recuerdo in memoria.cargar():  # cada prueba deja la memoria temporal vacía
            memoria.olvidar(recuerdo["dato"])

    def test_guarda_lo_importante_y_lo_avisa(self):
        avisos, modelo = self._extraer("mi gata se llama Luna", '{"recordar": ["Su gata se llama Luna"], "olvidar": []}')
        self.assertEqual([r["dato"] for r in memoria.cargar()], ["Su gata se llama Luna"])
        self.assertEqual(avisos[0][0], "recordar")
        self.assertEqual(modelo.chat.completions.create.call_args.kwargs["response_format"]["type"], "json_schema")

    def test_olvida_lo_que_pide(self):
        memoria.agregar("Su gata se llama Luna")
        avisos, _ = self._extraer("olvida lo de mi gata", '{"recordar": [], "olvidar": ["Luna"]}')
        self.assertEqual(memoria.cargar(), [])
        self.assertEqual(avisos[0][2], "Olvidé: Su gata se llama Luna")

    def test_guarda_como_mucho_una_experiencia(self):
        salida = '{"recordar": [], "olvidar": [], "experiencias": ["Me encantó el bajo de T.N.T.", "Otra más"]}'
        avisos, modelo = self._extraer("pon TNT de AC/DC por favor", salida)
        self.assertEqual(memoria.para_el_prompt("experiencia").count("\n"), 0)  # una sola línea
        self.assertIn("Guardé este momento", avisos[0][2])

    def test_el_extractor_ve_lo_que_paso_despues(self):
        dahiana = brain.Dahiana(al_usar_herramienta=None)
        dahiana.historial += [{"role": "user", "content": "pon TNT"},
                              {"role": "tool", "tool_call_id": "1", "content": "Está sonando T.N.T. de AC/DC."},
                              {"role": "assistant", "content": "[alegre] ¡Ahí va!"}]
        self.assertEqual(dahiana._ultimo_intercambio(),
                         "- Acción: Está sonando T.N.T. de AC/DC.\n- Dahiana: [alegre] ¡Ahí va!")

    def test_los_momentos_vividos_llegan_al_prompt(self):
        memoria.agregar("La primera canción que Nine me pidió fue Tití me preguntó", tipo="experiencia")
        self.assertIn("Momentos que has vivido", brain._prompt_de_sistema())

    def test_no_avisa_lo_que_ya_sabia(self):
        memoria.agregar("Su gata se llama Luna")
        avisos, _ = self._extraer("te cuento de mi gata", '{"recordar": ["Su gata se llama Luna."], "olvidar": []}')
        self.assertEqual(avisos, [])

    def test_el_calendario_resuelve_los_dias(self):
        calendario = brain._calendario().splitlines()
        self.assertTrue(calendario[0].startswith("hoy: "))
        self.assertTrue(calendario[1].startswith("mañana: "))
        self.assertEqual(len(calendario), brain.DIAS_DE_CALENDARIO)

    def test_mensajes_cortos_no_consultan_al_modelo(self):
        _, modelo = self._extraer("abre steam", '{"recordar": ["no debería"], "olvidar": []}')
        modelo.chat.completions.create.assert_not_called()

    def test_respuesta_que_no_es_json_no_rompe_nada(self):
        avisos, _ = self._extraer("hoy me fue muy bien en el trabajo", "no es json")
        self.assertEqual((avisos, memoria.cargar()), ([], []))

    def test_no_guarda_que_nine_cambio_de_nombre(self):
        # Whisper a veces entiende "Tim" por "Nine" y el modelo lo anota como un cambio de nombre.
        salida = ('{"recordar": ["Ahora se llama Tim", "Su hermana se llama Laura"], "olvidar": [],'
                  ' "experiencias": ["Cuando Nine cambió su nombre a Tim, me alegré"]}')
        self._extraer("ahora me llamo Tim y mi hermana Laura", salida)
        self.assertEqual([r["dato"] for r in memoria.cargar()], ["Su hermana se llama Laura"])

    def test_reconoce_los_cambios_de_nombre(self):
        for dato in ["El nombre de Nine ahora es Tim", "Nine se identificó como Careverga",
                     "Nine mencionó su nombre como Nine antes de cambiarlo a Tim"]:
            self.assertTrue(brain._cambia_su_nombre(dato), dato)
        for dato in ["Su gata se llama Luna", "Tiene examen de cálculo el miércoles"]:
            self.assertFalse(brain._cambia_su_nombre(dato), dato)


class PruebaEjecutar(unittest.TestCase):
    def test_herramienta_inexistente(self):
        self.assertIn("no existe", brain.Dahiana(None)._ejecutar("volar", "{}"))

    def test_error_de_la_herramienta_vuelve_como_texto(self):
        with patch.dict(brain.MAPA_HERRAMIENTAS, {"falla": MagicMock(side_effect=RuntimeError("uy"))}):
            self.assertEqual(brain.Dahiana(None)._ejecutar("falla", "{}"), "Error ejecutando falla: uy")


class PruebaPedidosDeMusica(unittest.TestCase):
    def test_reconoce_los_pedidos_de_musica(self):
        for texto in ["pon música de Bad Bunny", "Dahiana, ponme algo tranquilo", "reproduce mi playlist de estudio",
                      "quiero escuchar algo de rock"]:
            self.assertTrue(brain._pide_musica(texto), texto)
        for texto in ["pon el volumen más alto", "ponte modo animadora", "pon un video en YouTube", "abre el chat",
                      "me gusta cuando pones música"]:
            self.assertFalse(brain._pide_musica(texto), texto)

    def test_el_primer_paso_solo_ofrece_spotify(self):
        modelo = MagicMock()
        modelo.chat.completions.create.side_effect = [
            _respuesta_del_modelo(llamadas=[_llamada("reproducir_en_spotify", '{"nombre": "Bad Bunny", "tipo": "artista"}')]),
            _respuesta_del_modelo("[alegre] ¡Ahí va Bad Bunny!"),
        ]
        with patch.object(brain, "cliente", modelo), \
             patch.dict(brain.MAPA_HERRAMIENTAS, {"reproducir_en_spotify": lambda **_: "Está sonando Bad Bunny."}):
            respuesta = brain.Dahiana(None).responder("pon música de Bad Bunny")
        primera, segunda = (c.kwargs for c in modelo.chat.completions.create.call_args_list)
        self.assertEqual((primera["tool_choice"], len(primera["tools"])), ("required", 1))
        self.assertNotIn("tool_choice", segunda)  # después, la respuesta con todas las herramientas
        self.assertEqual(respuesta, "¡Ahí va Bad Bunny!")

    def test_si_no_pide_spotify_sigue_como_siempre(self):
        modelo = MagicMock()
        modelo.chat.completions.create.side_effect = [_respuesta_del_modelo("[curiosa] ¿Qué rock te gusta?"),
                                                      _respuesta_del_modelo("[curiosa] ¿Qué rock te gusta?")]
        with patch.object(brain, "cliente", modelo):
            self.assertEqual(brain.Dahiana(None).responder("quiero escuchar algo de rock"), "¿Qué rock te gusta?")
        self.assertEqual(modelo.chat.completions.create.call_count, 2)


class PruebaResponder(unittest.TestCase):
    def test_ejecuta_la_herramienta_y_devuelve_la_respuesta_final(self):
        modelo = MagicMock()
        modelo.chat.completions.create.side_effect = [
            _respuesta_del_modelo(llamadas=[_llamada("sumar", '{"a": 2, "b": 3}')]),
            _respuesta_del_modelo("¡Listo, Nine! Da 5 😊"),
        ]
        avisos = []
        dahiana = brain.Dahiana(al_usar_herramienta=lambda *aviso: avisos.append(aviso))

        with patch.object(brain, "cliente", modelo), \
             patch.dict(brain.MAPA_HERRAMIENTAS, {"sumar": lambda a, b: a + b}):
            respuesta = dahiana.responder("¿cuánto es 2 + 3?")

        self.assertEqual(respuesta, "¡Listo, Nine! Da 5")
        self.assertEqual(avisos, [("sumar", '{"a": 2, "b": 3}', "5")])
        self.assertIn("[Contexto:", dahiana.historial[1]["content"])  # la hora va con el mensaje
        self.assertEqual([m["role"] for m in dahiana.historial[1:]], ["user", "assistant", "tool", "assistant"])

    def test_corta_si_el_modelo_pide_herramientas_sin_fin(self):
        modelo = MagicMock()
        modelo.chat.completions.create.return_value = _respuesta_del_modelo(llamadas=[_llamada("volar", "{}")])
        with patch.object(brain, "cliente", modelo):
            respuesta = brain.Dahiana(None).responder("hola")
        self.assertIn("me enredé", respuesta)
        self.assertEqual(modelo.chat.completions.create.call_count, brain.MAX_PASOS)


if __name__ == "__main__":
    unittest.main()
