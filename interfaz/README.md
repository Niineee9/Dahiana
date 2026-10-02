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
| `src/componentes/Avatar.tsx` | Avatar 3D (three.js + @pixiv/three-vrm); si no hay modelo, el orbe |
| `src/cuerpo.ts`             | Lenguaje corporal del avatar: posturas, respiración, peso, gestos    |
| `src/componentes/Orbe.tsx`  | El orbe animado y sus estados                                       |
| `src/componentes/Chat.tsx`  | Las burbujas de la conversación                                     |
| `src/componentes/VistaOrbe.tsx` | Vista inicial, sin chat: Dahiana de cuerpo entero (ventana de 300x560) |

## Avatar 3D

El modelo de Dahiana es un diseño propio hecho en VRoid Studio y **no está en el repositorio**. Para
usar el tuyo, expórtalo desde VRoid Studio como VRM (1.0 o 0.x) y guárdalo en
`public/avatar/dahiana.vrm`. Sin ese archivo, Dahiana aparece como el orbe.

Su ropa es un modelo por atuendo, con el mismo esqueleto: `dahiana_fin_de_semana.vrm` (sábados y
domingos) y `dahiana_animadora.vrm` (cuando Nine estudia o está cansado). El servicio avisa cuál lleva
con el evento `atuendo`; el avatar se funde, carga el modelo y hace un gesto (vuelta, porra o saltito).
Si falta el archivo de una ropa, usa `dahiana.vrm`.

El avatar usa las expresiones estándar de VRM: `happy`, `relaxed`, `surprised` y `sad` para el ánimo,
`blink` para parpadear y `aa`/`oh` para mover la boca con la voz. Los modelos de VRoid ya las traen.

## Comunicación

React ⇄ Rust: comandos (`enviar_mensaje`, `escuchar`, `cancelar_escucha`, `reiniciar_conversacion`,
`controlar_motor`, `ajustar_ventana`, `enviar_preferencias`, `cursor_relativo`, `mostrar_sin_foco`,
`estado_motor`) y los eventos `dahiana` (del servicio) y `atajo_escuchar` (Ctrl+Alt+H).
La voz llega como data URL (`data:audio/mpeg;base64,...`) y se reproduce en el navegador interno
(la ventana permite reproducir sin clic previo: `additionalBrowserArgs` en `tauri.conf.json`). Rust ⇄ Python: una línea JSON por mensaje; el protocolo está documentado
en `../servicio.py`. Si cambias el protocolo, actualiza los tres lados.
