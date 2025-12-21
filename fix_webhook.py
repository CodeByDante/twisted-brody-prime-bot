import requests
from config import BOT_TOKEN

def clear_webhook():
    print(f"🔓 Intentando borrar Webhook para el token...")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook?drop_pending_updates=True"
    try:
        r = requests.get(url)
        print(f"📡 Respuesta Telegram: {r.status_code}")
        print(f"📄 Cuerpo: {r.text}")
        if r.status_code == 200 and r.json().get('ok'):
            print("✅ Webhook eliminado correctamente. Ahora el bot debería recibir mensajes.")
        else:
            print("⚠️ Hubo un problema eliminando el webhook.")
    except Exception as e:
        print(f"❌ Error de conexión: {e}")

if __name__ == "__main__":
    clear_webhook()
