"""Dahiana - Fase 1: asistente por texto en la terminal."""

import sys

import openai

from brain import Dahiana
from config import MODELO, NOMBRE_USUARIO, URL_SERVIDOR

SALIR = {"salir", "adiós", "adios", "chao", "exit", "quit"}


def main() -> None:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")  # emojis y tildes en la consola

    dahiana = Dahiana()
    print(f"✨ Dahiana lista (modelo: {MODELO}). Escribe 'salir' para terminar.\n")

    while True:
        try:
            texto = input(f"{NOMBRE_USUARIO}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nDahiana: ¡Nos vemos!")
            break

        if not texto:
            continue
        if texto.lower() in SALIR:
            print("Dahiana: ¡Nos vemos!")
            break

        try:
            print(f"Dahiana: {dahiana.responder(texto)}\n")
        except openai.APIConnectionError:
            print(f"⚠ No pude conectarme a {URL_SERVIDOR}. "
                  "¿Ejecutaste iniciar_modelo.bat (o el 'Local Model API' de Bionic)?\n")
        except (openai.NotFoundError, openai.BadRequestError) as error:
            print(f"⚠ Problema con el modelo '{MODELO}': {error}\n"
                  "  Revisa que el nombre en config.py coincida con el de la app.\n")
        except openai.APIError as error:
            print(f"⚠ Error del servidor de modelos: {error}\n")


if __name__ == "__main__":
    main()
