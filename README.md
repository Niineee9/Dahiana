# Dahiana 💜

Mi asistente personal de escritorio, estilo Cortana. Corre 100% local, usando llama.cpp
(`llama-server`) como servidor de modelos compatible con OpenAI.

Vive en la bandeja del sistema como un orbe morado: le escribes y ella entiende y actúa. Abre y
cierra programas, abre sitios, busca en Google o YouTube, controla el volumen, te dice la hora y el
estado del PC, y sobre todo te acompaña y te cuida.

## Instalación (Windows)

1. Instala **Python 3.11 o superior** desde python.org (marca "Add Python to PATH").
2. Descarga llama.cpp para Vulkan (GPU AMD) desde
   https://github.com/ggml-org/llama.cpp/releases (archivo `llama-bXXXXX-bin-win-vulkan-x64.zip`)
   y descomprímelo en `C:\llama.cpp`.
3. Descarga un modelo GGUF con soporte de herramientas a `C:\Modelos`, en el SSD para que cargue rápido (el predeterminado es
   `Qwen3-14B-Q4_K_M.gguf`). Las rutas están en `MOTOR` dentro de `config.py`.
4. En la carpeta del proyecto: `pip install -r requirements.txt`
5. Para la interfaz: **Node.js**, **pnpm**, **Rust** y **Visual Studio Build Tools (C++)**. Luego:
   ```
   cd interfaz
   pnpm install
   ```

## Usarla

- **Con interfaz:** doble clic en **`iniciar_dahiana.bat`**. Ella enciende el modelo sola.
  - `Ctrl+Alt+D` la muestra u oculta; `Esc` la oculta.
  - Clic en el orbe de la bandeja: mostrar/ocultar. Clic derecho: modo juego o salir.
  - **Modo juego** (botón de la luna): apaga el modelo y libera ~9 GB de VRAM. Escríbele y se despierta.
  - Al salir, el modelo se apaga y la VRAM queda libre.
- **Por terminal:** `iniciar_modelo.bat` (deja esa ventana abierta) y luego `python main.py`.

## Cosas para probar

- `abre el bloc de notas` / `abre steam` / `cierra discord`
- `pon youtube` / `búscame recetas de arepas en youtube`
- `sube el volumen` / `silencia`
- `¿qué hora es?` / `¿cómo va el PC?`
- `hoy fue un día pesado` / `me fue bien en el examen`

## Arquitectura

```
Interfaz (Tauri: Rust + React)  ──JSON por stdin/stdout──►  servicio.py (Python)
  ventana, bandeja, atajo                                    brain.py + tools.py
                                                             motor.py ──► llama-server (modelo)
```

| Archivo              | Qué hace                                                        |
|----------------------|-----------------------------------------------------------------|
| `main.py`            | Conversación en la terminal                                     |
| `servicio.py`        | Dahiana como servicio para la interfaz (protocolo JSON)         |
| `brain.py`           | Habla con el modelo y ejecuta las herramientas que pida         |
| `tools.py`           | Las acciones que Dahiana sabe hacer                             |
| `motor.py`           | Enciende y apaga llama-server (modo juego)                      |
| `config.py`          | Motor, modelo, personalidad, `SOBRE_MI`, atajos de apps y sitios |
| `interfaz/`          | App de escritorio: `src/` (React) y `src-tauri/` (Rust)         |
| `iniciar_dahiana.bat`| Abre la interfaz                                                |
| `iniciar_modelo.bat` | Enciende solo el modelo, para usar `main.py`                    |

**¿Por qué llama.cpp directo?** Con Qwen3 14B usa ~9 GB de VRAM y ~1 GB de RAM (en Bionic eran
~13 GB y ~10 GB), y deja ~5 GB de VRAM libres para Windows, juegos y la voz de la Fase 2.

## Personalizar

- **Personalidad:** edita `PERSONALIDAD` en `config.py`.
- **Que te conozca:** llena `SOBRE_MI` en `config.py` (gustos, rutinas, metas); lo usa para cuidarte.
- **Apps que no encuentra:** agrégalas a `APPS` en `config.py` con su ruta.
- **Nueva habilidad:** escribe una función con docstring en `tools.py` y agrégala a `HERRAMIENTAS`.
- **Otro modelo:** cambia `MOTOR["modelo"]` (ruta del .gguf) y `MODELO` en `config.py`. Debe
  soportar herramientas. Busca GGUF en https://huggingface.co/models?library=gguf (prefiere
  lmstudio-community, unsloth o bartowski, Q4_K_M) y deja ~5 GB de VRAM libres.

## Hoja de ruta

- [x] Fase 1: texto + herramientas
- [x] Interfaz: Tauri + React, orbe en la bandeja, modo juego
- [ ] Fase 2: voz (whisper + Piper / Edge TTS / Kokoro)
- [ ] Fase 3: "Oye Dahiana" · avatar anime
- [ ] Fase 4: recordatorios, rutinas, memoria...
