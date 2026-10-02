"""Pruebas de atuendo.py: qué ropa lleva Dahiana y cuándo se cambia (con un atuendo.json temporal)."""

import datetime
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import atuendo

VIERNES, SABADO, DOMINGO, LUNES = (datetime.date(2026, 10, d) for d in (2, 3, 4, 5))


class PruebaAtuendo(unittest.TestCase):
    def setUp(self):
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        parche = patch.object(atuendo, "ARCHIVO", Path(carpeta.name) / "atuendo.json")
        parche.start()
        self.addCleanup(parche.stop)

    def test_los_fines_de_semana_se_pone_su_ropa_de_fin_de_semana(self):
        self.assertEqual([atuendo.actual(d) for d in (VIERNES, SABADO, DOMINGO, LUNES)],
                         ["normal", "fin_de_semana", "fin_de_semana", "normal"])

    def test_el_traje_de_animadora_se_queda_hasta_que_se_lo_pidan(self):
        atuendo.elegir("animadora")
        self.assertEqual([atuendo.actual(d) for d in (VIERNES, SABADO, LUNES)], ["animadora"] * 3)
        atuendo.elegir("normal")
        self.assertEqual(atuendo.actual(SABADO), "fin_de_semana")  # "normal" = la ropa del día

    def test_sin_archivo_lleva_la_ropa_del_dia(self):
        self.assertIsNone(atuendo.elegido())
        self.assertEqual(atuendo.actual(LUNES), "normal")

    def test_un_archivo_danado_no_rompe_nada(self):
        atuendo.ARCHIVO.write_text("no es json", encoding="utf-8")
        self.assertEqual(atuendo.actual(LUNES), "normal")

    def test_solo_comenta_su_ropa_si_es_especial(self):
        with patch.object(atuendo, "actual", return_value="normal"):
            self.assertEqual(atuendo.como_te_sientes(), "")
        with patch.object(atuendo, "actual", return_value="fin_de_semana"):
            self.assertIn("bonita y especial", atuendo.como_te_sientes())

    def test_reconoce_cuando_necesita_animos(self):
        for texto in ["voy a estudiar para el examen", "me toca estudiar", "estoy muy cansada", "Estoy agotado hoy",
                      "ya, me pongo a estudiar", "Dahiana, ponte modo animadora.", "ponte tu traje de animadora",
                      "vístete de porrista", "modo animadora"]:
            self.assertEqual(atuendo.pedido_en(texto), "animadora", texto)

    def test_reconoce_cuando_pide_su_ropa_normal(self):
        for texto in ["vuelve a tu atuendo normal", "Dahiana, regresa a tu ropa de siempre", "quítate el traje porfa",
                      "ponte tu ropa normal", "quítate el traje de animadora"]:
            self.assertEqual(atuendo.pedido_en(texto), "normal", texto)

    def test_lo_demas_no_cambia_su_ropa(self):
        for texto in ["hola, ¿cómo estás?", "ponme música", "estudiar es aburrido", "mi hermano está cansado"]:
            self.assertIsNone(atuendo.pedido_en(texto), texto)

    def test_si_se_lo_pide_la_nota_lo_dice(self):
        self.assertIn("te lo pidió", atuendo.atender_pedido("ponte modo animadora"))

    def test_se_cambia_una_sola_vez(self):
        self.assertIn("traje de animadora", atuendo.atender_pedido("voy a estudiar"))
        self.assertEqual(atuendo.atender_pedido("estoy cansado"), "")  # ya lo lleva: sin nota ni gesto nuevo
        self.assertIn("quitar", atuendo.atender_pedido("vuelve a tu ropa normal"))
        self.assertEqual(atuendo.atender_pedido("quítate el traje"), "")


if __name__ == "__main__":
    unittest.main()
