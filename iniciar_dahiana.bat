@echo off
rem Abre Dahiana con su interfaz (modo desarrollo). Enciende el modelo sola y lo apaga al salir.
rem Atajo para mostrar/ocultar: Ctrl+Alt+D. Menú: clic derecho en el orbe de la bandeja.
cd /d "%~dp0interfaz"
pnpm tauri dev
