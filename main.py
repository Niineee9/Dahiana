"""Dahiana en la terminal: conversación por texto, sin interfaz gráfica.

Necesita el modelo encendido antes: ejecuta iniciar_modelo.bat y deja esa ventana abierta.
"""

import sys

import openai

from brain import Dahiana
from config import MODELO, NOMBRE_USUARIO, URL_SERVIDOR

# Palabras que cierran la conversación.
SALIR = {"salir", "adiós", "adios", "chao", "exit", "quit"}


def main() -> None:
    """Bucle de conversación: lee lo que escribe Nine y muestra la respuesta de Dahiana."""
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
            dahiana.actualizar_memoria(texto)  # guarda lo importante para otras conversaciones
        except openai.APIConnectionError:
            print(f"⚠ No pude conectarme a {URL_SERVIDOR}. ¿Ejecutaste iniciar_modelo.bat?\n")
        except (openai.NotFoundError, openai.BadRequestError) as error:
            print(f"⚠ Problema con el modelo '{MODELO}': {error}\n"
                  "  Revisa que MODELO en config.py coincida con el --alias del motor.\n")
        except openai.APIError as error:
            print(f"⚠ Error del servidor de modelos: {error}\n")


if __name__ == "__main__":
    main()
