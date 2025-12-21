import json
import os
from config import DB_FILE, DATA_DIR

DB_CACHE = os.path.join(DATA_DIR, "manga_cache.json")
DB_TAGS = os.path.join(DATA_DIR, "hashtags.json")

# --- VARIABLES GLOBALES (NO BORRAR) ---
url_storage = {}    # <-- Esta es la variable que te faltaba
user_config = {}    
downloads_db = {}   
hashtag_db = {}     # <-- Base de datos de hashtags
active_downloads = {} # {chat_id: {msg_id: future/task}}
user_cooldowns = {}   # {chat_id: timestamp}

# --- FUNCIONES ---

def cargar_db():
    global downloads_db
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                downloads_db.update(json.load(f))
        except:
            downloads_db = {}

def guardar_db():
    try:
        with open(DB_FILE, 'w') as f:
            json.dump(downloads_db, f, indent=4)
    except:
        pass

def load_tags():
    global hashtag_db
    if os.path.exists(DB_TAGS):
        try:
            with open(DB_TAGS, 'r', encoding='utf-8') as f:
                hashtag_db.update(json.load(f))
        except:
            hashtag_db = {}

def save_tags():
    try:
        with open(DB_TAGS, 'w', encoding='utf-8') as f:
            json.dump(hashtag_db, f, indent=4, ensure_ascii=False)
    except:
        pass

def get_config(chat_id):
    if chat_id not in user_config:
        user_config[chat_id] = {
            'lang': 'es', 
            'fmt': 'mp4',
            'q_fixed': None, 
            'q_auto': None, 
            'meta': True,
            'fast_enabled': True,
            'html_mode': False,
            'doc_mode': False,
            'replay_enabled': False, # <--- Nuevo modo replay
            'party_mode': False,
            'ai_mode': False, # Modo Party
        }
    return user_config[chat_id]

def can_download(chat_id, max_concurrent=3, cooldown_sec=2):
    # Restricciones deshabilitadas a petición del usuario (Modo Ilimitado)
    return True, None

def add_active(chat_id, msg_id, task=None, pid=None):
    if chat_id not in active_downloads:
        active_downloads[chat_id] = {}
    # Guardamos diccionario con task y pid opcional
    active_downloads[chat_id][msg_id] = {'task': task, 'pid': pid}

def remove_active(chat_id, msg_id):
    if chat_id in active_downloads and msg_id in active_downloads[chat_id]:
        del active_downloads[chat_id][msg_id]
        if not active_downloads[chat_id]:
            del active_downloads[chat_id]

async def cancel_all(chat_id):
    count = 0
    if chat_id in active_downloads:
        tasks_map = active_downloads[chat_id]
        count = len(tasks_map)
        
        for mid, info in tasks_map.items():
            # Soportar formato antiguo (solo task) o nuevo (dict)
            if isinstance(info, dict):
                task = info.get('task')
                pid = info.get('pid')
            else:
                task = info
                pid = None
            
            # 1. Cancelar Task de Python
            if task and not task.done():
                task.cancel()
            
            # 2. Matar proceso del sistema (FFmpeg / Aria2 / 7z)
            if pid:
                try:
                    import signal
                    # En Windows, os.kill con SIGTERM suele funcionar, o taskkill forzado
                    os.kill(pid, signal.SIGTERM)
                    print(f"🔪 Process Killed: PID {pid}")
                except Exception as e:
                    print(f"⚠️ Kill Error {pid}: {e}")
                    # Intento Force Windows
                    try:
                        import subprocess
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    except: pass

        active_downloads.pop(chat_id, None)
    return count

# Cargar base de datos al iniciar
cargar_db()
load_tags()