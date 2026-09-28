"""Pruebas de spotify.py: seguridad del inicio de sesión, renovación del token y uso de la API.

No se conectan a Spotify: la API y el archivo del token se simulan.
"""

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import spotify

CANCION = {"uri": "spotify:track:abc", "name": "Tití me preguntó", "artists": [{"name": "Bad Bunny"}]}
TNT_JACOBO = {"uri": "spotify:track:jacobo", "name": "TNT", "artists": [{"name": "Jacobo Palacio"}]}
TNT_ACDC = {"uri": "spotify:track:acdc", "name": "T.N.T.", "artists": [{"name": "AC/DC"}]}
PROVENZA = {"uri": "spotify:track:provenza", "name": "PROVENZA", "artists": [{"name": "KAROL G"}]}


def _spotify_simulado(respuestas: dict[str, list[dict]]):
    """_api falso: responde según la consulta (clave = texto de q; sin clave, ningún resultado)."""
    def api(_metodo, _ruta, parametros=None, _cuerpo=None):
        tipo = parametros["type"]
        return {f"{tipo}s": {"items": respuestas.get(parametros["q"], [])}}
    return api


class PruebaAutorizacion(unittest.TestCase):
    def test_desafio_pkce_del_estandar(self):
        # Ejemplo oficial del RFC 7636, apéndice B.
        self.assertEqual(spotify._desafio_pkce("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"),
                         "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")

    def test_sin_client_id_explica_que_falta_configurar(self):
        with patch.dict(spotify.SPOTIFY, {"client_id": ""}):
            with self.assertRaises(spotify.ErrorSpotify) as error:
                spotify.autorizar()
            self.assertFalse(spotify.conectado())
        self.assertIn("config_local.py", str(error.exception))

    def test_token_vencido_se_renueva(self):
        with tempfile.TemporaryDirectory() as carpeta:
            archivo = Path(carpeta) / "spotify.json"
            archivo.write_text(json.dumps({"access_token": "viejo", "refresh_token": "r", "vence": time.time() - 5}))
            with patch.object(spotify, "_ARCHIVO_TOKEN", archivo), \
                 patch.object(spotify, "_pedir_token", return_value={"access_token": "nuevo"}) as pedir:
                self.assertEqual(spotify._token_vigente(), "nuevo")
            self.assertEqual(pedir.call_args.args[0]["grant_type"], "refresh_token")

    def test_token_vigente_no_se_renueva(self):
        with tempfile.TemporaryDirectory() as carpeta:
            archivo = Path(carpeta) / "spotify.json"
            archivo.write_text(json.dumps({"access_token": "bueno", "refresh_token": "r", "vence": time.time() + 900}))
            with patch.object(spotify, "_ARCHIVO_TOKEN", archivo), patch.object(spotify, "_pedir_token") as pedir:
                self.assertEqual(spotify._token_vigente(), "bueno")
            pedir.assert_not_called()


class PruebaConsulta(unittest.TestCase):
    def test_usa_filtros_de_spotify(self):
        self.assertEqual(spotify._consulta("Tití me preguntó", "cancion", "Bad Bunny"),
                         'track:"Tití me preguntó" artist:"Bad Bunny"')
        self.assertEqual(spotify._consulta("Karol G", "artista", ""), "Karol G")

    def test_coincide_ignora_signos_tildes_y_errores_leves(self):
        self.assertTrue(spotify.coincide("ACDC", "AC/DC"))
        self.assertTrue(spotify.coincide("AC DC", "AC/DC"))
        self.assertTrue(spotify.coincide("TNT", "T.N.T."))
        self.assertTrue(spotify.coincide("Titi me pregunto", "Tití Me Preguntó"))
        self.assertTrue(spotify.coincide("Provensa", "PROVENZA"))
        self.assertFalse(spotify.coincide("ACDC", "Jacobo Palacio"))

    def test_acdc_usa_el_nombre_oficial_y_no_se_queda_con_el_primero(self):
        api = _spotify_simulado({
            "ACDC": [{"name": "AC/DC"}],  # búsqueda del artista: nombre oficial con barra
            'track:"TNT" artist:"AC/DC"': [TNT_JACOBO, TNT_ACDC],  # el primero no es el bueno
        })
        with patch.object(spotify, "_api", api):
            self.assertEqual(spotify.buscar("TNT", artista="ACDC"), TNT_ACDC)

    def test_si_el_artista_no_cuadra_prueba_sin_el(self):
        api = _spotify_simulado({"Bad Bunny": [{"name": "Bad Bunny"}], 'track:"Provenza"': [PROVENZA]})
        with patch.object(spotify, "_api", api):
            self.assertEqual(spotify.buscar("Provenza", artista="Bad Bunny"), PROVENZA)

    def test_texto_libre_si_los_filtros_no_encuentran(self):
        api = _spotify_simulado({"Titi me pregunto Bad Bunny": [CANCION]})
        with patch.object(spotify, "_api", api):
            self.assertEqual(spotify.buscar("Titi me pregunto", artista="Bad Bunny"), CANCION)

    def test_describir_limita_los_artistas(self):
        diles = {"name": "Diles", "artists": [{"name": n} for n in ("Bad Bunny", "Ozuna", "Farruko", "Arcángel")]}
        self.assertEqual(spotify.describir(diles), "Diles de Bad Bunny y Ozuna y otros")


class PruebaApi(unittest.TestCase):
    @patch.object(spotify, "_api", return_value={"tracks": {"items": [CANCION]}})
    def test_buscar_cancion(self, api):
        self.assertEqual(spotify.buscar("Tití me preguntó"), CANCION)
        self.assertEqual(api.call_args.args[2]["type"], "track")

    @patch.object(spotify, "_api", return_value={"tracks": {"items": []}})
    def test_buscar_sin_resultados(self, _):
        with self.assertRaises(spotify.ErrorSpotify):
            spotify.buscar("zzzz")

    @patch.object(spotify, "_mis_playlists", return_value={"uri": "spotify:playlist:mia", "name": "Para dormir"})
    @patch.object(spotify, "_api")
    def test_primero_busca_en_las_playlists_de_nine(self, api, _):
        self.assertEqual(spotify.buscar("dormir", "playlist")["uri"], "spotify:playlist:mia")
        api.assert_not_called()

    @patch.object(spotify, "_dispositivo", return_value="pc")
    @patch.object(spotify, "_api")
    def test_reproducir_cancion_o_coleccion(self, api, _):
        spotify.reproducir(CANCION)
        self.assertEqual(api.call_args.args[3], {"uris": ["spotify:track:abc"]})
        spotify.reproducir({"uri": "spotify:artist:xyz", "name": "Bad Bunny"})
        self.assertEqual(api.call_args.args[3], {"context_uri": "spotify:artist:xyz"})
        self.assertEqual(api.call_args.args[2], {"device_id": "pc"})

    @patch.object(spotify, "_api", return_value={"devices": [{"id": "tv", "type": "TV"},
                                                             {"id": "pc", "type": "Computer"}]})
    def test_prefiere_esta_pc_si_no_hay_dispositivo_activo(self, _):
        self.assertEqual(spotify._dispositivo(), "pc")

    @patch.object(spotify, "_api", return_value={"devices": [{"id": "tv", "type": "TV", "is_active": True}]})
    def test_sigue_donde_ya_esta_sonando(self, _):
        self.assertEqual(spotify._dispositivo(), "tv")

    @patch.object(spotify.time, "sleep")
    @patch.object(spotify.os, "startfile", create=True)
    @patch.object(spotify, "_api", return_value={"devices": [{"id": "tv", "type": "TV", "is_active": False}]})
    def test_nunca_elige_la_tv_al_azar(self, _, abrir, __):
        with self.assertRaises(spotify.ErrorSpotify):
            spotify._dispositivo()
        abrir.assert_called_once_with("spotify:")  # intentó abrir Spotify en esta PC

    @patch.object(spotify, "_api", return_value={"is_playing": True, "item": CANCION})
    def test_que_suena(self, _):
        self.assertEqual(spotify.sonando(), "Tití me preguntó de Bad Bunny")


if __name__ == "__main__":
    unittest.main()
