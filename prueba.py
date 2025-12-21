from pyrogram import Client, filters

# DATOS REALES DEL BOT (Extraídos de tu config)
api_id = 33226415          
api_hash = "01999dae3e5348c7ab0dbcc6f7f4edc5"   
bot_token = "7898954550:AAFpND1LdlHUVF2_fjz3rbaOvbFgpGrS6C0" 

app = Client("prueba_bot_user", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

@app.on_message(filters.command("start"))
async def responder(client, message):
    print(">>> ¡COMANDO RECIBIDO! <<<")
    await message.reply("¡Estoy vivo! El problema era el código complejo.")

print("Iniciando bot de prueba...")
app.run()
