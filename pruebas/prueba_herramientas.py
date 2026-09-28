"""Pruebas de tools.py: búsqueda de programas, decisiones de abrir_programa y esquemas.

No abren programas ni tocan el volumen: lo que actúa sobre Windows se reemplaza por simulaciones.
"""

import datetime
import inspect
import unittest
from unittest.mock import MagicMock, patch

import tools

# Índice falso de programas instalados: nombre normalizado -> (nombre visible, objetivo).
INDICE = {
    "discord": ("Discord", "shell:AppsFolder\\discord"),
    "microsoft teams": ("Microsoft Teams", "shell:AppsFolder\\teams"),
    "microsoft teams classic": ("Microsoft Teams classic", "shell:AppsFolder\\teams-classic"),
    "steam": ("Steam", "shell:AppsFolder\\steam"),
    "word": ("Word", "shell:AppsFolder\\word"),
    "wordpad": ("WordPad", "shell:AppsFolder\\wordpad"),
    "configuracion del sistema": ("Configuración del sistema", "shell:AppsFolder\\msconfig"),
}


class PruebaNormalizarYPuntaje(unittest.TestCase):
    def test_normalizar_quita_tildes_y_mayusculas(self):
        self.assertEqual(tools._normalizar("  Configuración "), "configuracion")

    def test_puntaje_por_tipo_de_coincidencia(self):
        self.assertEqual(tools._puntaje("steam", "steam"), 100)
        self.assertEqual(tools._puntaje("word", "wordpad"), 80)
        self.assertEqual(tools._puntaje("teams", "microsoft teams"), 60)
        self.assertEqual(tools._puntaje("soft", "microsoft teams"), 50)
        self.assertEqual(tools._puntaje("zzz", "discord"), 0)

    def test_puntaje_parecido_es_solo_sugerencia(self):
        puntos = tools._puntaje("discrod", "discord")
        self.assertTrue(0 < puntos < 50, puntos)


@patch.object(tools, "_ya_abierto", return_value=False)
@patch.object(tools, "_lanzar")
@patch.object(tools, "_indice_programas", MagicMock(return_value=INDICE))
class PruebaAbrirPrograma(unittest.TestCase):
    def test_coincidencia_exacta_abre(self, lanzar, _):
        self.assertEqual(tools.abrir_programa("word"), "Abrí Word.")
        lanzar.assert_called_once_with("shell:AppsFolder\\word")

    def test_varias_opciones_no_abre_y_las_devuelve(self, lanzar, _):
        resultado = tools.abrir_programa("teams")
        lanzar.assert_not_called()
        self.assertIn("Microsoft Teams, Microsoft Teams classic", resultado)
        self.assertNotIn("Steam", resultado)  # parecido por letras: no se mezcla con coincidencias reales

    def test_error_de_escritura_sugiere_sin_abrir(self, lanzar, _):
        resultado = tools.abrir_programa("discrod")
        lanzar.assert_not_called()
        self.assertIn("Lo más parecido: Discord", resultado)

    def test_no_encontrado(self, lanzar, _):
        self.assertIn("No encontré", tools.abrir_programa("juego inventado"))
        lanzar.assert_not_called()

    def test_herramienta_sensible_solo_con_nombre_exacto(self, lanzar, _):
        self.assertIn("No encontré", tools.abrir_programa("configuracion del"))
        tools.abrir_programa("Configuración del sistema")
        lanzar.assert_called_once_with("shell:AppsFolder\\msconfig")

    def test_atajo_de_config_sin_tilde(self, lanzar, _):
        with patch.dict(tools.APPS, {"configuración": "ms-settings:"}):
            tools.abrir_programa("configuracion")
        lanzar.assert_called_once_with("ms-settings:")

    def test_avisa_si_ya_estaba_abierto(self, lanzar, ya_abierto):
        ya_abierto.return_value = True
        self.assertIn("ya estaba abierto", tools.abrir_programa("discord"))
        lanzar.assert_called_once()


@patch.object(tools, "_indice_programas", MagicMock(return_value=INDICE))
class PruebaBuscarProgramas(unittest.TestCase):
    def test_lista_coincidencias(self):
        self.assertIn("Word, WordPad", tools.buscar_programas("word"))

    def test_sin_coincidencias(self):
        self.assertIn("No hay ningún programa", tools.buscar_programas("zzz"))


class PruebaHora(unittest.TestCase):
    def test_momento_del_dia(self):
        casos = {3: "madrugada", 5: "mañana", 12: "tarde", 19: "noche", 23: "noche"}
        for hora, esperado in casos.items():
            self.assertEqual(tools.momento_del_dia(hora), esperado, hora)

    def _hora(self, *momento: int) -> str:
        """hora_y_fecha() como si el reloj marcara `momento` (año, mes, día, hora, minuto)."""
        fecha = datetime.datetime(*momento)  # antes de simular: el reemplazo afecta a todo el módulo
        with patch.object(tools.datetime, "datetime") as reloj:
            reloj.now.return_value = fecha
            return tools.hora_y_fecha()

    def test_hora_hablada_sin_am_pm(self):
        self.assertEqual(self._hora(2026, 9, 27, 18, 39), "Son las 6:39 de la tarde del domingo 27 de septiembre.")

    def test_la_una_en_singular(self):
        self.assertTrue(self._hora(2026, 9, 28, 1, 5).startswith("Es la 1:05 de la madrugada"))


class PruebaOtrasHerramientas(unittest.TestCase):
    def test_nivel(self):
        self.assertEqual([tools._nivel(p) for p in (10, 70, 95)], ["normal", "algo alto", "muy alto"])

    @patch.object(tools, "_tecla")
    def test_volumen(self, tecla):
        self.assertEqual(tools.controlar_volumen("subir", 3), "Volumen: subir unos 6%.")
        self.assertEqual(tecla.call_count, 3)
        self.assertIn("No entiendo", tools.controlar_volumen("gritar"))


class PruebaMusica(unittest.TestCase):
    @patch.object(tools, "_tecla")
    def test_teclas_multimedia(self, tecla):
        tools.controlar_musica("pausar")
        tools.controlar_musica("siguiente")
        self.assertEqual([llamada.args[0] for llamada in tecla.call_args_list],
                         [tools._VK_REPRODUCIR_PAUSAR, tools._VK_SIGUIENTE])

    @patch.object(tools, "_lanzar")
    @patch.object(tools.spotify, "reproducir")
    @patch.object(tools.spotify, "buscar", return_value={"uri": "spotify:track:1", "name": "Tití me preguntó",
                                                           "artists": [{"name": "Bad Bunny"}]})
    def test_reproducir_en_spotify(self, buscar, reproducir, lanzar):
        resultado = tools.reproducir_en_spotify("Tití me preguntó", artista="Bad Bunny")
        self.assertEqual(resultado, "Está sonando en Spotify: Tití me preguntó de Bad Bunny.")
        buscar.assert_called_once_with("Tití me preguntó", "cancion", "Bad Bunny")
        lanzar.assert_not_called()

    @patch.object(tools.spotify, "reproducir")
    @patch.object(tools.spotify, "buscar", return_value={"uri": "spotify:track:2", "name": "Dos Mil 16",
                                                           "artists": [{"name": "Bad Bunny"}]})
    def test_avisa_si_suena_otra_cancion(self, *_):
        resultado = tools.reproducir_en_spotify("Tití me preguntó", artista="Bad Bunny")
        self.assertTrue(resultado.startswith("Ojo"))  # así Dahiana no finge que sonó lo pedido
        self.assertIn("Dos Mil 16", resultado)

    @patch.object(tools.spotify, "reproducir")
    @patch.object(tools.spotify, "buscar", return_value={"uri": "spotify:track:3", "name": "PROVENZA",
                                                           "artists": [{"name": "KAROL G"}]})
    def test_avisa_si_es_de_otro_artista(self, *_):
        resultado = tools.reproducir_en_spotify("Provenza", artista="Bad Bunny")
        self.assertIn("Ojo: es de otro artista, no de Bad Bunny", resultado)

    @patch.object(tools.spotify, "reproducir")
    @patch.object(tools.spotify, "buscar", return_value={"uri": "spotify:track:4", "name": "T.N.T.",
                                                           "artists": [{"name": "AC/DC"}]})
    def test_acdc_escrito_distinto_no_es_otro_artista(self, *_):
        self.assertEqual(tools.reproducir_en_spotify("TNT", artista="ACDC"), "Está sonando en Spotify: T.N.T. de AC/DC.")

    @patch.object(tools, "_lanzar")
    @patch.object(tools.spotify, "buscar", side_effect=tools.spotify.ErrorSpotify("Sin internet."))
    def test_si_falla_spotify_abre_la_busqueda(self, _, lanzar):
        resultado = tools.reproducir_en_spotify("Tití me preguntó")
        lanzar.assert_called_once_with("spotify:search:Tit%C3%AD%20me%20pregunt%C3%B3")
        self.assertIn("Sin internet.", resultado)
        self.assertIn("le dé play", resultado)  # el modelo sabe que no sonó sola


class PruebaVista(unittest.TestCase):
    def test_avisa_a_la_interfaz(self):
        avisos = []
        with patch.object(tools, "avisar_a_la_interfaz", avisos.append):
            self.assertIn("solo se ve el orbe", tools.cambiar_vista("orbe"))
            tools.cambiar_vista("chat")
        self.assertEqual(avisos, [{"tipo": "vista", "vista": "orbe"}, {"tipo": "vista", "vista": "chat"}])

    def test_en_la_terminal_explica_que_no_aplica(self):
        with patch.object(tools, "avisar_a_la_interfaz", None):
            self.assertIn("solo funciona en la interfaz", tools.cambiar_vista("orbe"))


class PruebaEsquemas(unittest.TestCase):
    def test_literal_se_convierte_en_enum(self):
        esquema = tools._esquema(tools.controlar_volumen)["function"]["parameters"]
        self.assertEqual(esquema["properties"]["accion"]["enum"], ["subir", "bajar", "silenciar"])
        self.assertEqual(esquema["required"], ["accion"])

    def test_toda_herramienta_esta_documentada(self):
        """Convención del proyecto: descripción y cada argumento en la sección Args del docstring."""
        for funcion, esquema in zip(tools.HERRAMIENTAS, tools.ESQUEMAS):
            with self.subTest(herramienta=funcion.__name__):
                self.assertTrue(esquema["function"]["description"])
                for nombre in inspect.signature(funcion).parameters:
                    descripcion = esquema["function"]["parameters"]["properties"][nombre]["description"]
                    self.assertTrue(descripcion, f"Falta documentar '{nombre}' en Args")


if __name__ == "__main__":
    unittest.main()
