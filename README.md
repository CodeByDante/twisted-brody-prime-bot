---
title: Twisted Brody Bot
emoji: 🤖
colorFrom: purple
colorTo: pink
sdk: docker
pinned: false
app_port: 7860
---

# Twisted Brody Bot Pro

Este es un bot de Telegram desplegado en Hugging Face Spaces usando Docker.

## Configuración

Para que el bot funcione, debes configurar las siguientes **Secret Variables** en la pestaña `Settings` del Space:

1.  `API_ID`: Tu API ID de Telegram.
2.  `API_HASH`: Tu API Hash de Telegram.
3.  `BOT_TOKEN`: El token de tu bot.
4.  `FIREBASE_KEY`: El contenido COMPLETO de tu archivo `firebase_credentials.json` (copia y pega todo el JSON).
5.  `OWNER_ID`: Tu ID de usuario de Telegram.

## Despliegue

El `Dockerfile` ya está configurado para instalar las dependencias (`ffmpeg`, `aria2`, `python`) y ejecutar `main.py`.
