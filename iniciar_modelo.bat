@echo off
rem Inicia el cerebro de Dahiana (llama.cpp) para usarla desde la terminal con main.py.
rem La configuración del modelo está en config.py (MOTOR). La interfaz no necesita este archivo.
rem Deja esta ventana abierta mientras usas Dahiana; ciérrala para liberar la VRAM.
python "%~dp0motor.py"
pause
