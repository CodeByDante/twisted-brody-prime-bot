import firebase_admin
from firebase_admin import credentials, firestore
import os
import json
import asyncio

# Variable global para el cliente de Firestore
db = None

def init_firebase():
    global db
    if db is not None:
        return db

    try:
        # 1. Intentar cargar desde variable de entorno (JSON RAW)
        firebase_json = os.environ.get("FIREBASE_JSON")
        
        # 2. Si no es JSON raw, intentar ruta de archivo
        if not firebase_json:
            cred_path = os.environ.get("FIREBASE_CREDENTIALS", "firebase_credentials.json")
            if os.path.exists(cred_path):
                cred = credentials.Certificate(cred_path)
            else:
                print("⚠️ [Firebase] No se encontraron credenciales (FIREBASE_JSON ni archivo).")
                return None
        else:
            # Parsear el JSON del string
            try:
                cred_dict = json.loads(firebase_json)
                cred = credentials.Certificate(cred_dict)
            except Exception as e:
                print(f"❌ [Firebase] Error parseando FIREBASE_JSON: {e}")
                return None

        # Inicializar App
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        
        db = firestore.client()
        print("🔥 [Firebase] Conectado exitosamente a Firestore.")
        return db

    except Exception as e:
        print(f"❌ [Firebase] Error inicializando: {e}")
        return None

# Inicializar al importar (o llamar explícitamente en main)
init_firebase()

from config import BOT_TOKEN

# Segregar cache por Bot ID para evitar conflictos al cambiar de bot
BOT_ID = BOT_TOKEN.split(":")[0] if ":" in BOT_TOKEN else "global"
CACHE_COLLECTION = f"media_cache_{BOT_ID}"

async def get_cached_file(video_id, quality):
    """
    Busca en la colección del bot actual si existe el file_id.
    Retorna el file_id o None.
    """
    if not db: return None

    try:
        # Usamos el video_id como ID del documento para búsqueda rápida O(1)
        doc_ref = db.collection(CACHE_COLLECTION).document(str(video_id))
        
        loop = asyncio.get_running_loop()
        # FIX: Añadir timeout de 5s para evitar hanging si Firebase falla
        try:
            doc = await asyncio.wait_for(loop.run_in_executor(None, doc_ref.get), timeout=5.0)
        except asyncio.TimeoutError:
            print(f"⚠️ [Firebase] Cache Read Timeout ({video_id}) - Saltando cache.")
            return None
        
        if doc.exists:
            data = doc.to_dict()
            # data estructura: {'mp3': 'file_id_1', '720': 'file_id_2', ...}
            return data.get(quality)
        return None
    except Exception as e:
        print(f"⚠️ [Firebase] Error leyendo cache: {e}")
        return None

async def get_cached_data(video_id):
    """
    Retorna el documento completo del cache (incluyendo meta y todos los formatos).
    """
    if not db: return None
    try:
        doc_ref = db.collection(CACHE_COLLECTION).document(str(video_id))
        loop = asyncio.get_running_loop()
        doc = await loop.run_in_executor(None, doc_ref.get)
        
        if doc.exists: return doc.to_dict()
    except Exception as e:
        print(f"⚠️ [Firebase] Error leyendo data cache: {e}")
    return None

async def save_cached_file(video_id, quality, file_id, meta=None):
    """
    Guarda o actualiza el file_id para una calidad dada.
    """
    if not db: return
    
    try:
        doc_ref = db.collection(CACHE_COLLECTION).document(str(video_id))
        
        # Usamos set con merge=True para no borrar otras calidades
        update_data = {
            quality: file_id,
            'last_updated': firestore.SERVER_TIMESTAMP
        }
        
        if meta:
            update_data['meta'] = meta # Título, duración, etc si queremos guardar info extra
            
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: doc_ref.set(update_data, merge=True))
        
        print(f"🔥 [Firebase] Cache guardado: {video_id} [{quality}]")
    except Exception as e:
        print(f"❌ [Firebase] Error guardando cache: {e}")

async def delete_cached_file(video_id):
    """
    Elimina un archivo del cache (útil si el link expira o es inválido).
    """
    if not db: return
    try:
        doc_ref = db.collection(CACHE_COLLECTION).document(str(video_id))
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, doc_ref.delete)
        print(f"🗑 [Firebase] Cache eliminado: {video_id}")
    except Exception as e:
        print(f"⚠️ [Firebase] Error eliminando cache: {e}")

async def get_bot_config():
    """
    Obtiene la configuración global del bot (ej: canal de backup).
    Retorna un dict con las keys.
    """
    if not db: return {}
    try:
        doc_ref = db.collection('bot_settings').document('global_config')
        loop = asyncio.get_running_loop()
        doc = await loop.run_in_executor(None, doc_ref.get)
        
        if doc.exists:
            return doc.to_dict()
        return {}
    except Exception as e:
        print(f"⚠️ [Firebase] Error leyendo config global: {e}")
        return {}

async def save_bot_config(key, value):
    """
    Guarda una key especifica en la configuración global.
    """
    if not db: return False
    try:
        doc_ref = db.collection('bot_settings').document('global_config')
        
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: doc_ref.set({key: value}, merge=True))
        
        print(f"🔥 [Firebase] Config guardada: {key} = {value}")
        return True
    except Exception as e:
        print(f"❌ [Firebase] Error guardando config global: {e}")
        return False

async def load_all_user_configs():
    """Carga todas las configs de usuarios desde Firestore."""
    if not db: return {}
    try:
        # Ejecutar en thread pool para no bloquear
        loop = asyncio.get_running_loop()
        docs = await loop.run_in_executor(None, lambda: db.collection('user_configs').stream())
        
        # Stream devuelve un generador, iterarlo puede bloquear si son muchos,
        # pero es necesario para poblar la RAM inicial.
        data = {}
        for doc in docs:
            try:
                data[int(doc.id)] = doc.to_dict()
            except: pass
        print(f"🔥 [Firebase] Configs cargadas: {len(data)} usuarios.")
        return data
    except Exception as e:
        print(f"⚠️ [Firebase] Config Load Error: {e}")
        return {}

async def save_user_config_fb(chat_id, config_data):
    """Guarda/Actualiza la config de un usuario."""
    if not db: return
    try:
        # Fire-and-forget sync wrapper
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: db.collection('user_configs').document(str(chat_id)).set(config_data, merge=True))
    except Exception as e:
         print(f"❌ [Firebase] Save Config Error: {e}")

async def load_all_hashtags():
    """Carga todos los hashtags."""
    if not db: return {}
    try:
        loop = asyncio.get_running_loop()
        docs = await loop.run_in_executor(None, lambda: db.collection('hashtags').stream())
        
        data = {}
        for doc in docs:
            data[doc.id] = doc.to_dict().get('msgs', [])
        print(f"🔥 [Firebase] Hashtags cargados: {len(data)} tags.")
        return data
    except Exception as e:
        print(f"⚠️ [Firebase] Tags Load Error: {e}")
        return {}

async def save_hashtag_fb(tag, msgs_list):
    if not db: return
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: db.collection('hashtags').document(tag).set({'msgs': msgs_list}, merge=True))
    except Exception as e:
        print(f"❌ [Firebase] Save Tag Error: {e}")

async def register_user(user_id, first_name, username):
    """
    Registra al usuario, cuenta el total y detecta cambio de nombre.
    Retorna: (is_new, count, name_changed)
    """
    if not db: return (False, 0, False) # Fallback

    try:
        # Referencias
        user_ref = db.collection('user_configs').document(str(user_id))
        stats_ref = db.collection('bot_settings').document('stats')
        
        # Ejecutar transacción (pseudo-transacción para simplificar en async wrapper)
        # Nota: Firestore async de python no soporta transactions con await facil dentro de lambda
        # Haremos una logica optimista/separada por simplicidad y velocidad
        
        # 1. Obtener User
        loop = asyncio.get_running_loop()
        doc = await loop.run_in_executor(None, user_ref.get)
        
        if not doc.exists:
            # --- NUEVO USUARIO ---
            # 1. Incrementar contador global
            try:
                # Lectura + Escritura (Riesgo bajo de colision en low traffic)
                st_doc = await loop.run_in_executor(None, stats_ref.get)
                current_count = st_doc.to_dict().get('user_count', 0) if st_doc.exists else 0
                new_count = current_count + 1
                await loop.run_in_executor(None, lambda: stats_ref.set({'user_count': new_count}, merge=True))
            except:
                new_count = 1 # Fallback
            
            # 2. Guardar Usuario
            user_data = {
                'first_name': first_name,
                'username': username,
                'joined_at': firestore.SERVER_TIMESTAMP,
                'user_id': user_id
            }
            await loop.run_in_executor(None, lambda: user_ref.set(user_data, merge=True))
            return (True, new_count, False)
            
        else:
            # --- USUARIO EXISTENTE ---
            data = doc.to_dict()
            old_name = data.get('first_name', '')
            
            # Detectar cambio de nombre
            if old_name != first_name:
                await loop.run_in_executor(None, lambda: user_ref.set({'first_name': first_name, 'username': username}, merge=True))
                return (False, 0, True)
            
            return (False, 0, False)

    except Exception as e:
        print(f"⚠️ [Firebase] Register Error: {e}")
        return (False, 0, False)

async def get_global_stats():
    """Retorna el diccionario de stats (ej: user_count)."""
    if not db: return {}
    try:
        doc_ref = db.collection('bot_settings').document('stats')
        loop = asyncio.get_running_loop()
        doc = await loop.run_in_executor(None, doc_ref.get)
        
        if doc.exists: return doc.to_dict()
        return {}
    except: return {}
