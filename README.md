# Dahiana 💜

Asistente personal de escritorio para Windows, al estilo de Cortana, con una personalidad tierna que
te acompaña, te cuida y conversa contigo. Vive en la bandeja del sistema como un orbe morado: le
escribes o le hablas, y ella entiende y actúa. Su cerebro es un modelo de lenguaje que corre en tu
propio PC.

## Inspiración

Dahiana nació tomando como base e inspiración a **[Yui](https://github.com/EDAKZIN/yui-asistente)**,
el asistente de [EDAKZIN](https://github.com/EDAKZIN). Todavía no es tan robusta como Yui, pero la
idea es que siga evolucionando, versión a versión.

## Lo más importante: su personalidad

Dahiana no quiere ser solo un asistente que ejecuta órdenes. Lo que la define es cómo te trata:

- **Tierna, alegre y cercana.** Habla en español latino, te tutea y habla de sí misma en femenino.
- **Te cuida.** Sabe qué hora es: si es de madrugada te sugiere descansar, si llevas horas jugando te
  propone una pausa, y te acompaña con cariño cuando estás cansado o triste. Su cariño es sano: no te
  culpa ni te pide que dependas de ella.
- **Conversa de verdad.** Tiene curiosidad, gustos propios (el espacio, la música, los datos curiosos)
  y opiniones; si le cuentas algo, aporta algo suyo en vez de un "qué interesante".
- **Te recuerda.** Guarda lo importante que le cuentas (planes, gustos, personas) y los momentos que
  vivió contigo, y los retoma otro día: "¿cómo te fue en el examen?".
- **Te habla primero.** Te saluda al llegar, te escribe tras un silencio largo y comenta de vez en
  cuando lo que haces, sin molestar.
- **Tiene ánimo propio.** El orbe cambia de color según cómo se siente y su voz cambia de tono.
- **Es honesta.** Si no puede hacer algo o una acción falla, lo dice.

## Qué sabe hacer

- Abrir y cerrar programas (también apps de la Microsoft Store), buscar qué tienes instalado.
- Decirte qué ventanas tienes abiertas (por ejemplo, con quién hablas en Discord).
- Abrir sitios, buscar en Google o YouTube.
- Controlar el volumen y la música (pausar, siguiente, anterior).
- Poner canciones, artistas, álbumes o playlists en Spotify (con la API oficial; requiere Premium).
- Decirte la hora y el estado del PC (CPU, RAM, disco).
- Escucharte por micrófono y responderte en voz alta.
- **Modo orbe:** oculta el chat y queda solo el orbe flotando ("Dahiana, oculta el chat").
- **Modo juego:** apaga el modelo para liberar la VRAM; escribirle la despierta.

## Cómo funciona

```
Interfaz (Tauri: Rust + React)  ──JSON por stdin/stdout──►  servicio.py (Python)
  ventana, bandeja, atajos,                                  brain.py + tools.py
  reproduce la voz                                           motor.py ──► llama-server (modelo)
                                                             voz.py: micrófono → Whisper · Edge TTS → audio
```

| Archivo                 | Qué hace                                                            |
|-------------------------|---------------------------------------------------------------------|
| `brain.py`              | Conversa con el modelo y ejecuta las herramientas que pida (tool calling) |
| `tools.py`              | Las acciones que Dahiana sabe hacer                                 |
| `config.py`             | Modelo, voz, **personalidad**, gustos, atajos de apps y sitios      |
| `memoria.py`            | Memoria a largo plazo: lo que sabe de ti y los momentos vividos     |
| `iniciativa.py`         | Cuándo hablarte primero (saludo, silencio, horas jugando, música)   |
| `voz.py`                | Escuchar (micrófono → Whisper) y hablar (Edge TTS o voz de Windows) |
| `spotify.py`            | Poner música con la API de Spotify                                  |
| `motor.py`              | Enciende y apaga llama-server (modo juego)                          |
| `servicio.py`           | Dahiana como servicio para la interfaz (protocolo JSON)             |
| `main.py`               | Conversación en la terminal, sin interfaz                           |
| `interfaz/`             | App de escritorio: `src/` (React) y `src-tauri/` (Rust)             |
| `pruebas/`              | Pruebas automáticas (sin modelo ni ventanas)                        |

## Requisitos

Es un proyecto personal pensado para Windows 11; seguramente tendrás que adaptar rutas y ajustes.
Se desarrolla con una GPU AMD de 16 GB (Radeon RX 7800 XT) y 32 GB de RAM.

- **Python 3.11 o superior.**
- **[llama.cpp](https://github.com/ggml-org/llama.cpp/releases)** con Vulkan (sirve para GPUs AMD,
  NVIDIA e Intel).
- **Un modelo GGUF con soporte de herramientas.** El predeterminado es Qwen3 14B en Q4_K_M (~9 GB de
  VRAM); busca GGUF en [Hugging Face](https://huggingface.co/models?library=gguf).
- **Para la interfaz:** Node.js, pnpm, Rust y Visual Studio Build Tools (C++).

## Instalación

1. Descomprime llama.cpp en `C:\llama.cpp` y guarda el modelo GGUF en `C:\Modelos` (idealmente en un
   SSD). Las rutas se cambian en `MOTOR` dentro de `config.py`.
2. Instala las dependencias de Python: `pip install -r requirements.txt`. El modelo de Whisper
   (~0,5 GB) se descarga solo la primera vez.
3. Instala las de la interfaz:
   ```
   cd interfaz
   pnpm install
   ```
4. Copia `config_local.ejemplo.py` como `config_local.py` para tus datos personales. Ese archivo no
   se sube al repositorio.
5. **Spotify (opcional, requiere Premium):** crea una app en el
   [panel de desarrolladores](https://developer.spotify.com/dashboard) con el Redirect URI
   `http://127.0.0.1:8888/callback`, pon su Client ID en `config_local.py` y ejecuta
   `python spotify.py` una vez para autorizar en el navegador.

## Uso

- **Con interfaz:** doble clic en `iniciar_dahiana.bat`. Enciende el modelo sola y lo apaga al salir.
  - `Ctrl+Alt+D`: mostrar u ocultar. `Ctrl+Alt+H`: hablarle. `Esc`: ocultar o dejar de escuchar.
  - Botones de la barra: voz, "atenta" (si comenta lo que haces), modo juego, nueva conversación y
    modo orbe.
- **Por terminal:** `iniciar_modelo.bat` (deja esa ventana abierta) y luego `python main.py`.

Algunas cosas para decirle:
- `abre steam` / `cierra discord` / `¿tengo Spotify instalado?`
- `pon Tití me preguntó de Bad Bunny` / `¿qué está sonando?` / `pausa la música`
- `¿qué hora es?` / `¿cómo va el PC?` / `¿con quién estoy hablando en Discord?`
- `hoy fue un día pesado` / `me fue bien en el examen` / `¿por qué soñamos?`
- `oculta el chat` / `olvida lo de mi gata`

## Personalizar

- **Personalidad:** `PERSONALIDAD` en `config.py`. Es el corazón de Dahiana.
- **Sus gustos:** `GUSTOS_DE_DAHIANA` en `config.py`.
- **Lo que sabe de ti y cómo te llama:** `SOBRE_MI` y `NOMBRE_USUARIO` en `config_local.py`.
- **Su voz:** `VOZ` en `config.py` (voz de Edge, velocidad, tono y pronunciación). Lista de voces:
  `edge-tts --list-voices`.
- **Nueva habilidad:** una función en `tools.py`, agregada a `HERRAMIENTAS` (ver convenciones abajo).
- **Cuándo te habla primero:** las reglas y pausas están al inicio de `iniciativa.py`.

## Privacidad

- **Queda en tu PC:** el modelo, lo que dices por micrófono (Whisper), la memoria
  (`%APPDATA%\Dahiana\memoria.json`, puedes abrirla, editarla o borrarla) y lo que ve de tus ventanas.
- **Sale de tu PC:** el texto de sus respuestas cuando habla (Edge TTS, servidores de Microsoft) y las
  búsquedas y la reproducción de Spotify. Sin internet, usa la voz de Windows.

## Hoja de ruta

- [x] Texto y herramientas con un modelo local
- [x] Interfaz: orbe en la bandeja, modo orbe y modo juego
- [x] Voz: pulsar para hablar y respuestas habladas
- [x] Memoria a largo plazo
- [x] Iniciativa propia, estados de ánimo y orbe con vida propia
- [ ] Modo manos libres (conversar sin pulsar nada)
- [ ] "Oye Dahiana" (palabra de activación)
- [ ] Avatar anime
- [ ] Recordatorios y rutinas

## Contribuir

Cualquier sugerencia o colaboración que ayude a Dahiana a evolucionar es bienvenida: ideas para su
personalidad, nuevas habilidades, correcciones o mejoras de rendimiento. Abre un *issue* para
conversarlo o un *pull request* con tu propuesta. Las ideas sobre su personalidad son las más
valiosas, porque es lo que la hace ser quien es.

Para que el código siga siendo coherente:

- Todo en español: nombres de funciones, variables, archivos, comentarios y mensajes.
- Docstrings en cada módulo, clase y función (estilo Google en Python), JSDoc en TypeScript y `///`
  en Rust. Las herramientas de `tools.py` documentan cada argumento en `Args`: es lo que lee el modelo.
- Sin dependencias nuevas sin conversarlo antes.
- Las respuestas de Dahiana son cortas y sin emojis ni formato, porque se leen en voz alta.
- Antes de proponer un cambio:
  ```
  python -m unittest discover -s pruebas -p "prueba_*.py" -t .
  cd interfaz && pnpm exec tsc --noEmit
  cd interfaz/src-tauri && cargo clippy
  ```

## Licencia

[MIT](LICENSE). Inspirada en [Yui](https://github.com/EDAKZIN/yui-asistente) de EDAKZIN, también
bajo licencia MIT.
