"""Pruebas de memoria.py (guardar, actualizar, olvidar y mostrar recuerdos).

Usan un archivo temporal: nunca tocan la memoria real de Nine.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import memoria


class ConMemoriaTemporal(unittest.TestCase):
    """Base: cada prueba empieza con una memoria vacía en una carpeta temporal."""

    def setUp(self):
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        parche = patch.object(memoria, "ARCHIVO", Path(carpeta.name) / "memoria.json")
        parche.start()
        self.addCleanup(parche.stop)


class PruebaMemoria(ConMemoriaTemporal):
    def test_sin_archivo_no_hay_recuerdos(self):
        self.assertEqual(memoria.cargar(), [])
        self.assertEqual(memoria.para_el_prompt(), "")

    def test_agregar_guarda_con_fecha(self):
        self.assertTrue(memoria.agregar("Le encanta AC/DC"))
        guardado = json.loads(memoria.ARCHIVO.read_text(encoding="utf-8"))
        self.assertEqual(guardado[0]["dato"], "Le encanta AC/DC")
        self.assertRegex(guardado[0]["fecha"], r"^\d{4}-\d{2}-\d{2}$")

    def test_un_recuerdo_casi_igual_se_actualiza(self):
        memoria.agregar("Tiene un examen de física el viernes")
        self.assertFalse(memoria.agregar("Tiene un examen de física el viernes."))
        self.assertEqual(len(memoria.cargar()), 1)

    def test_olvidar_por_una_palabra_en_comun(self):
        memoria.agregar("Le encanta AC/DC")
        memoria.agregar("Tiene una gata llamada Luna que es muy traviesa")
        self.assertEqual(memoria.olvidar("lo de mi gata"), "Tiene una gata llamada Luna que es muy traviesa")
        self.assertEqual([r["dato"] for r in memoria.cargar()], ["Le encanta AC/DC"])

    def test_olvidar_no_borra_al_azar(self):
        memoria.agregar("Le encanta AC/DC")
        self.assertIsNone(memoria.olvidar("lo de mi trabajo"))
        self.assertEqual(len(memoria.cargar()), 1)

    def test_para_el_prompt_con_fecha_hablada(self):
        memoria.ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
        memoria.ARCHIVO.write_text(json.dumps([{"dato": "Le encanta AC/DC", "fecha": "2026-09-27"}]), encoding="utf-8")
        self.assertEqual(memoria.para_el_prompt(), "- (27 de septiembre) Le encanta AC/DC")

    def test_experiencias_aparte_de_los_recuerdos_de_nine(self):
        memoria.agregar("Le encanta AC/DC")
        memoria.agregar("La primera canción que Nine me pidió fue Tití me preguntó", tipo="experiencia")
        self.assertIn("AC/DC", memoria.para_el_prompt("nine"))
        self.assertNotIn("Tití", memoria.para_el_prompt("nine"))
        self.assertIn("Tití", memoria.para_el_prompt("experiencia"))

    def test_los_recuerdos_antiguos_sin_tipo_son_de_nine(self):
        memoria.ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
        memoria.ARCHIVO.write_text(json.dumps([{"dato": "Su gata se llama Luna", "fecha": "2026-09-27"}]),
                                   encoding="utf-8")
        self.assertIn("Luna", memoria.para_el_prompt("nine"))
        self.assertEqual(memoria.para_el_prompt("experiencia"), "")

    def test_archivo_danado_no_rompe_nada(self):
        memoria.ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
        memoria.ARCHIVO.write_text("esto no es json", encoding="utf-8")
        self.assertEqual(memoria.cargar(), [])


if __name__ == "__main__":
    unittest.main()
