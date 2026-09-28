# Interfaz de Dahiana

App de escritorio en **Tauri 2** (Rust) + **React 19** (TypeScript, Vite, Tailwind 4, Motion, Zustand).
Es el "cuerpo" de Dahiana: el cerebro vive en Python (`../servicio.py`).

## Desarrollo

```
pnpm install
pnpm tauri dev      # abre la app con recarga en vivo (o usa ../iniciar_dahiana.bat)
pnpm exec tsc --noEmit            # revisa tipos de TypeScript
cd src-tauri && cargo clippy      # revisa buenas prácticas de Rust
```

## Estructura

| Archivo                     | Qué hace                                                            |
|-----------------------------|---------------------------------------------------------------------|
| `src-tauri/src/lib.rs`      | Lanza `servicio.py`, bandeja, atajos `Ctrl+Alt+D` / `Ctrl+Alt+H`, posición y cierre |
| `src-tauri/tauri.conf.json` | Ventana (380x580, sin bordes, transparente) y empaquetado           |
| `src/estado.ts`             | Estado global y conexión con Rust (eventos `dahiana`, comandos)     |
| `src/reproductor.ts`        | Reproduce la voz y mide su volumen para que el orbe "hable"         |
| `src/App.tsx`               | Panel: barra superior, orbe, chat y campo de texto                  |
| `src/componentes/Orbe.tsx`  | El orbe animado y sus estados                                       |
| `src/componentes/Chat.tsx`  | Las burbujas de la conversación                                     |
| `src/componentes/VistaOrbe.tsx` | Modo orbe: solo el orbe flotante (la ventana se achica a 170x200) |

## Comunicación

React ⇄ Rust: comandos (`enviar_mensaje`, `escuchar`, `cancelar_escucha`, `reiniciar_conversacion`,
`controlar_motor`, `ajustar_ventana`, `enviar_preferencias`, `cursor_relativo`, `mostrar_sin_foco`,
`estado_motor`) y los eventos `dahiana` (del servicio) y `atajo_escuchar` (Ctrl+Alt+H).
La voz llega como data URL (`data:audio/mpeg;base64,...`) y se reproduce en el navegador interno
(la ventana permite reproducir sin clic previo: `additionalBrowserArgs` en `tauri.conf.json`). Rust ⇄ Python: una línea JSON por mensaje; el protocolo está documentado
en `../servicio.py`. Si cambias el protocolo, actualiza los tres lados.
