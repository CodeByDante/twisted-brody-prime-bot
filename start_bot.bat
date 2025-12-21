@echo off
title Twisted Brody Bot Pro
cls
echo 📦 Verificando dependencias...
pip install -r requirements.txt
cls
echo Iniciando Twisted Brody Bot...
:loop
python main.py
echo.
echo ⚠️ El bot se ha detenido o ha ocurrido un error.
echo 🔄 Reiniciando en 5 segundos...
timeout /t 5
goto loop
