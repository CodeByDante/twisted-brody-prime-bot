from pyrogram import Client, filters
from config import API_ID, API_HASH, BOT_TOKEN
import os

# Borrar sesión anterior si existe para evitar conflictos
if os.path.exists("test_bot_session.session"):
    try:
        os.remove("test_bot_session.session")
        print("🗑️ Sesión anterior eliminada.")
    except: pass

print(f"⚙️ Usando Token: {BOT_TOKEN[:10]}...")

app = Client(
    "test_bot_session", 
    api_id=API_ID, 
    api_hash=API_HASH, 
    bot_token=BOT_TOKEN
)

@app.on_message(filters.command("start"))
async def start(client, message):
    print(f"📩 Comando /start recibido de {message.from_user.first_name}")
    await message.reply("✅ **¡Funciona!**\n\nSoy el bot de prueba. Si lees esto, tus credenciales y conexión están perfectas.\n\nEl problema está en `main.py`.")

@app.on_message(filters.text)
async def echo(client, message):
    print(f"📩 Mensaje recibido: {message.text}")
    await message.reply(f"Echo: {message.text}")

if __name__ == "__main__":
    print("🚀 Iniciando Bot de Prueba (Ctrl+C para salir)...")
    try:
        app.run()
    except Exception as e:
        print(f"❌ Error al iniciar: {e}")
