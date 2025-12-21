import asyncio
import os
import sys
import yt_dlp
import time
import re
import shutil
import logging
from pyrogram import Client, filters, idle
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, 
    InputMediaPhoto, InputMediaDocument, Message,
    BotCommand, WebAppInfo
)
from pyrogram.errors import FloodWait
from io import BytesIO
import aiohttp
import threading
# import uvicorn # Removed but kept for safety if referenced elsewhere, actually removing it is better.
# import uvicorn
# from fastapi import FastAPI
from http.server import HTTPServer, BaseHTTPRequestHandler

# --- WEB SERVER SETUP (SIMPLE THREADED) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b'OK')
    def log_message(self, format, *args): return # Silenciar logs

def run_health_check():
    server = HTTPServer(('0.0.0.0', 7860), HealthCheckHandler)
    server.serve_forever()

# --- IMPORTACIONES DEL PROYECTO ---
from config import API_ID, API_HASH, BOT_TOKEN, DATA_DIR, COOKIE_MAP, DATABASE_CHANNEL, BASE_DIR, OWNER_ID
from database import get_config, url_storage, hashtag_db, can_download, cancel_all, add_active, remove_active
from utils import format_bytes, limpiar_url, sel_cookie, resolver_url_facebook, descargar_galeria, scan_channel_history
from jav_extractor import extraer_jav_directo
from downloader import procesar_descarga
from manga_service import (
    get_all_mangas_paginated, get_manga_metadata, 
    process_manga_download, get_or_cache_cover,
    get_manga_chapters
)
from firebase_service import save_bot_config, get_cached_file, save_cached_file, get_cached_data, register_user

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 1. FIX WINDOWS LOOP ---
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# --- 2. CONFIGURACIÓN CLIENTE ---
WORKDIR = "sessions"
if not os.path.exists(WORKDIR):
    os.makedirs(WORKDIR)

app = Client(
    "brody_final_v1", 
    api_id=int(API_ID),
    api_hash=API_HASH, 
    bot_token=BOT_TOKEN, 
    workers=100,
    workdir=WORKDIR,
    ipv6=False,
    sleep_threshold=60
)

BOT_USERNAME = None

# --- HELPER: LOGICA PARTY ---
async def run_party_logic(client, chat_id, file_path, mode, val, msg_to_edit=None):
    from utils import split_video_generic, cut_video_range
    from tools_media import get_meta, get_thumb
    
    if msg_to_edit:
        await msg_to_edit.edit(f"⏳ Procesando Party ({mode}={val})...")
    else:
         sm = await client.send_message(chat_id, f"⏳ Procesando Party ({mode}={val})...")
         msg_to_edit = sm

    try:
        if mode == 'parts':
            parts = await asyncio.get_running_loop().run_in_executor(None, lambda: split_video_generic(file_path, mode, float(val)))
        elif mode in ['sec', 'min']:
            parts = await asyncio.get_running_loop().run_in_executor(None, lambda: split_video_generic(file_path, mode, float(val)))
        elif mode == 'range':
            pts = str(val).split()
            if len(pts) != 2:
                await msg_to_edit.edit("❌ Formato de rango inválido.")
                return False
            p_path = await asyncio.get_running_loop().run_in_executor(None, lambda: cut_video_range(file_path, pts[0], pts[1]))
            parts = [p_path] if p_path else []
        else:
            parts = []

        if not parts:
            await msg_to_edit.edit("❌ Error al procesar el video.")
            return False

        await msg_to_edit.edit(f"📤 Enviando {len(parts)} partes...")
        ts = int(time.time())
        for i, p in enumerate(parts):
            try:
                # Extraer meta para cada parte
                w, h, dur = await get_meta(p)
                thumb = await get_thumb(p, chat_id, f"{ts}_{i}")
                
                await client.send_video(
                    chat_id, p,
                    width=w if w else None,
                    height=h if h else None,
                    duration=dur if dur else None,
                    thumb=thumb,
                    caption=f"🎉 Party: Parte {i+1}" if len(parts) > 1 else "🎉 Party Video"
                )
                if thumb and os.path.exists(thumb): os.remove(thumb)
            except Exception as e:
                print(f"Error enviando parte {i}: {e}")
                try: await client.send_document(chat_id, p)
                except: pass
        
        # Cleanup
        try: 
            if os.path.exists(file_path): os.remove(file_path)
            for p in parts: 
                if os.path.exists(p): os.remove(p)
        except: pass
        
        await msg_to_edit.delete()
        return True
    except Exception as e:
        await msg_to_edit.edit(f"❌ Error en Party: {e}")
        return False



# --- 3. DISEÑO DE MENÚ (DISEÑO REFINADO) ---
def gen_kb(conf, user_id=None):
    c_on, c_off = "🟢", "🔴"
    
    # 1. Metadatos (Full width)
    s_meta = c_on if conf.get('meta', True) else c_off
    btn_meta = InlineKeyboardButton(f"📝 Metadatos: {s_meta}", callback_data="toggle|meta")
    
    # 2. Turbo & Doc (Split)
    s_turbo = c_on if conf.get('fast_enabled', True) else c_off
    btn_turbo = InlineKeyboardButton(f"🚀 Turbo: {s_turbo}", callback_data="toggle|fast")
    s_doc = c_on if conf.get('doc_mode', False) else c_off
    btn_doc = InlineKeyboardButton(f"📄 Doc: {s_doc}", callback_data="toggle|doc")
    
    # 3. Agrup (Full width)
    s_group = c_on if conf.get('group_mode', True) else c_off
    btn_group = InlineKeyboardButton(f"📚 Agrup: {s_group}", callback_data="toggle|group")
    
    # 4. Auto (Full width)
    q_auto_val = conf.get('q_auto')
    txt_auto = "Desact."
    if q_auto_val == 'max': txt_auto = "Máx"
    elif q_auto_val == 'min': txt_auto = "Mín"
    btn_auto = InlineKeyboardButton(f"⚙️ Auto: {txt_auto}", callback_data="menu|auto")
    
    # 5. Idioma (Full width)
    lang = conf.get('lang', 'es')
    flag = "🇪🇸" if lang == 'es' else "🇺🇸"
    btn_lang = InlineKeyboardButton(f"🌐 Idioma: {flag}", callback_data="toggle|lang")
    
    # 6. Formato (Full width)
    fmt = conf.get('fmt', 'mp4')
    btn_fmt = InlineKeyboardButton(f"📦 Formato: 📹 {fmt.upper()}", callback_data="toggle|fmt")
    
    # 7. Modo Party & Manga Flow (Split)
    btn_party = InlineKeyboardButton("🎉 Modo Party", callback_data="menu|party_on")
    # btn_manga = InlineKeyboardButton("🌀 Manga Flow", callback_data="menu|mflow") # REMOVED
    
    # NUEVO: Mini App Web Button
    btn_webapp = InlineKeyboardButton(
        text="Twisted Brody Manga Flow",
        web_app=WebAppInfo(url="https://twisted-brody-manga-flow.vercel.app/")
    )
    
    kb = [
        [btn_webapp], # 0. Mini App (Top Priority)
        [btn_meta],
        [btn_turbo, btn_doc],
        [btn_group],
        [btn_auto],
        [btn_lang],
        [btn_fmt],
        [btn_party]
    ]

    # Admin Panel (Sigue existiendo para el owner como botón extra)
    if user_id == OWNER_ID:
        kb.append([InlineKeyboardButton("👮‍♂️ Panel Admin (Stats)", callback_data="menu|admin")])

    return InlineKeyboardMarkup(kb)

# --- 4. HANDLERS DE MENSAJES ---

@app.on_message(group=-1)
async def log_message(c, m):
    try:
        uid = m.from_user.id if m.from_user else "Unknown"
        text = m.text if m.text else "[Media/Emoji]"
        print(f"📩 [MSG] From: {uid} | Text: {text[:50]}")
    except: pass
    m.continue_propagation()

@app.on_message(filters.command("ping"))
async def ping_cmd(c, m):
    import socket
    import sys
    msg = [f"🏓 **Pong!**", f"🐍 Py: {sys.version.split()[0]}"]
    
    targets = [("google.com", "Google"), ("www.youtube.com", "YouTube")]
    
    for host, label in targets:
        try:
            ip = socket.gethostbyname(host)
            msg.append(f"✅ {label}: `{ip}`")
        except Exception as e:
            msg.append(f"❌ {label}: `{e}`")
            
    await m.reply("\n".join(msg))

@app.on_message(filters.command("start"))
async def start_handler(c, m):
    uid = m.from_user.id
    try:
        from firebase_service import register_user
        await register_user(uid, m.from_user.first_name, m.from_user.username)
    except: pass
    
    caption = (
        f"👋 **¡Hola {m.from_user.mention}!**\n\n"
        f"🚀 **Twisted Brody Bot Pro** está listo.\n"
        f"Configura tus preferencias abajo o envíame un link."
    )
    
    menu_caption = caption
    if uid == OWNER_ID: menu_caption = "⚙️ **Panel de Control (Modo Dios)**"

    try:
        # FIX: Use path relative to this script, more robust than BASE_DIR
        base = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(base, "icons", "@twistedbrody.png")
        
        if os.path.exists(icon_path):
            # DIAGNOSTICS: Check for Git LFS pointer
            try:
                f_size = os.path.getsize(icon_path)
                with open(icon_path, 'rb') as f:
                    header = f.read(50) # Read enough to see "version https"
                
                # DEBUG MSG (Remove in production)
                # await m.reply(f"🔍 DEBUG: Encontrado {icon_path} ({f_size} bytes). Header: {header[:10]}")

                if b"version https" in header:
                    await m.reply(f"⚠️ Error: La imagen es un puntero LFS ({f_size} bytes).", reply_markup=gen_kb(get_config(m.chat.id), uid))
                    return

                # ATTEMPT 1: Send as Photo
                try:
                    await m.reply_photo(photo=icon_path, caption=menu_caption, reply_markup=gen_kb(get_config(m.chat.id), uid))
                except Exception as e_photo:
                    await m.reply(f"⚠️ Falla FOTO: {e_photo}. Intentando DOC...", reply_markup=gen_kb(get_config(m.chat.id), uid))
                    # ATTEMPT 2: Send as Document (Force upload)
                    await m.reply_document(document=icon_path, caption=menu_caption, reply_markup=gen_kb(get_config(m.chat.id), uid))

            except Exception as e_inner:
                await m.reply(f"⚠️ Error Interno: {e_inner}", reply_markup=gen_kb(get_config(m.chat.id), uid))

        else:
            # DEBUG: Why is it missing?
            icons_dir = os.path.join(base, "icons")
            if os.path.exists(icons_dir):
                files = os.listdir(icons_dir)
                file_list = "\n".join(files)
                err_msg = f"⚠️ Icono NO encontrado en: `{icon_path}`\n📂 Archivos en 'icons':\n`{file_list}`"
            else:
                err_msg = f"⚠️ Carpeta 'icons' NO encontrada en: `{base}`"
            
            await m.reply(err_msg, reply_markup=gen_kb(get_config(m.chat.id), uid))
    except Exception as e:
        await m.reply(f"❌ Error CRITICO: {e}", reply_markup=gen_kb(get_config(m.chat.id), uid))

@app.on_message(filters.command("menu") | filters.command("settings") | filters.regex("⚙️ Configuración") | filters.regex("Menu"))
async def cmd_menu(c, m):
    uid = m.from_user.id
    
    # Texto Explicativo Solicitado
    txt = (
        "🛠 **Guía de Botones:**\n\n"
        "🤖 **Mini App Manga:** Abre el catálogo visual de Twisted Brody.\n"
        "📝 **Metadatos:** (ON/OFF) Obtiene título, artista y portada real del archivo.\n"
        "🚀 **Turbo:** (ON/OFF) Descarga acelerada multi-hilo (x16).\n"
        "📄 **Doc:** (ON/OFF) Envía todo como archivo (sin compresión).\n"
        "📚 **Agrup:** (ON/OFF) Envía imágenes juntas en álbum (máx 10).\n"
        "⚙️ **Auto:** Elige la mejor o peor calidad automáticamente.\n"
        "🌐 **Idioma:** Cambia textos del bot (ES/EN).\n"
        "📦 **Formato:** Preferir video (MP4) o extraer audio (MP3).\n"
        "🎉 **Modo Party:** Cortar videos largos o extraer clips."
    )
    
    await m.reply(txt, reply_markup=gen_kb(get_config(m.chat.id), uid))

@app.on_callback_query()
async def cb(c, q):
    cid = q.message.chat.id
    uid = q.from_user.id
    data = q.data
    conf = get_config(cid)
    msg = q.message

    # 1. Anti-Spam (Mejorado para evitar bugs de edición rápida)
    now = time.time()
    if not hasattr(app, 'click_locks'): app.click_locks = {}
    if now - app.click_locks.get(uid, 0) < 0.5: return await q.answer("⏳", show_alert=False)
    app.click_locks[uid] = now

    try:
        if data == "cancel": 
            url_storage.pop(cid, None)
            await msg.delete()
            return

        # --- SECCION: PARTY MODE ---
        if data == "party_main" or data == "menu|party_on":
            conf['party_mode'] = True
            # Guardar configuración si fue activado
            if data == "menu|party_on":
                 from firebase_service import save_user_config_fb
                 asyncio.create_task(save_user_config_fb(cid, conf))
            
            # FLUJO SOLICITADO: Activar -> Pedir Video -> (Al recibir video) Mostrar Menu
            await msg.edit_text("✂️ **Modo Party Activo**\n\n🎬 **¡Envíame el video ahora!**\n(Te preguntaré cómo cortarlo después de recibirlo)", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancelar", callback_data="menu|party_off")]]))
            return

        if data.startswith("party_sel|"):
            mode = data.split("|")[1]
            if mode == "parts":
                bts = [
                    [InlineKeyboardButton("2", callback_data="party_exec|parts|2"), InlineKeyboardButton("3", callback_data="party_exec|parts|3"), InlineKeyboardButton("4", callback_data="party_exec|parts|4")],
                    [InlineKeyboardButton("5", callback_data="party_exec|parts|5"), InlineKeyboardButton("10", callback_data="party_exec|parts|10")],
                    [InlineKeyboardButton("✏️ Manual", callback_data="party_input|parts")],
                    [InlineKeyboardButton("🔙 Volver", callback_data="party_main")]
                ]
                await msg.edit("🧩 **Dividir en Partes**\n¿En cuántas partes cortarlo?", reply_markup=InlineKeyboardMarkup(bts))
            elif mode == "time":
                bts = [
                    [InlineKeyboardButton("10s", callback_data="party_exec|sec|10"), InlineKeyboardButton("30s", callback_data="party_exec|sec|30"), InlineKeyboardButton("1m", callback_data="party_exec|min|1")],
                    [InlineKeyboardButton("5m", callback_data="party_exec|min|5"), InlineKeyboardButton("10m", callback_data="party_exec|min|10")],
                    [InlineKeyboardButton("✏️ Manual (seg)", callback_data="party_input|sec"), InlineKeyboardButton("✏️ Manual (min)", callback_data="party_input|min")],
                    [InlineKeyboardButton("🔙 Volver", callback_data="party_main")]
                ]
                await msg.edit("⏱ **Dividir por Duración**\n¿De cuánto cada parte?", reply_markup=InlineKeyboardMarkup(bts))
            elif mode == "range":
                 url_storage[cid] = url_storage.get(cid, {})
                 url_storage[cid]['party_input_mode'] = 'range'
                 await msg.edit("✂️ **Cortar Rango**\n\nEnvía el tiempo de inicio y fin.\nEjemplo: `00:10 01:30` (Min 0:10 a 1:30)\nEjemplo 2: `10 90` (Seg 10 a 90)", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Volver", callback_data="party_main")]]))
            return

        if data.startswith("party_input|"):
             mode = data.split("|")[1]
             url_storage[cid] = url_storage.get(cid, {})
             url_storage[cid]['party_input_mode'] = mode
             await msg.edit(f"✍️ **Ingresa el valor** para dividir ({mode}):", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Volver", callback_data="party_main")]]))
             return

        if data.startswith("party_exec|"):
            pts = data.split("|")
            mode, val = pts[1], pts[2]
            st = url_storage.get(cid, {})
            if 'file' not in st:
                url_storage[cid] = st
                url_storage[cid]['party_pending'] = (mode, val)
                await msg.edit(f"✅ **Configurado:** `{mode}={val}`\n\n🎬 **Ahora envíame el video** para procesarlo automáticamente.")
                return
            await msg.delete()
            await run_party_logic(c, cid, st['file'], mode, val)
            url_storage.pop(cid, None)
            return

        # --- SECCION: DESCARGAS ---
        if data.startswith("dl|"):
            d_st = url_storage.get(cid)
            if not d_st: return await q.answer("⚠️ Link expiró. Reenvía el link.", show_alert=True)
            await msg.delete()
            url_storage.pop(cid, None)
            d_st['fast_enabled'] = conf.get('fast_enabled', True)
            asyncio.create_task(procesar_descarga(c, cid, d_st['url'], data.split("|")[1], d_st, msg))
            return

        # --- SECCION: CONFIGURACION ---
        if data.startswith("toggle|"):
            k = data.split("|")[1]
            if k == "meta": conf['meta'] = not conf.get('meta', True)
            elif k == "fast": conf['fast_enabled'] = not conf.get('fast_enabled', True)
            elif k == "doc": conf['doc_mode'] = not conf.get('doc_mode', False)
            elif k == "group": conf['group_mode'] = not conf.get('group_mode', True)
            elif k == "lang": conf['lang'] = 'es' if conf.get('lang', 'es') == 'orig' else 'orig'
            elif k == "fmt": conf['fmt'] = 'mp3' if conf.get('fmt', 'mp4') == 'mp4' else 'mp4'
            from firebase_service import save_user_config_fb
            asyncio.create_task(save_user_config_fb(cid, conf))
            await msg.edit_reply_markup(gen_kb(conf, uid))
            return

        if data == "menu|auto":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🌟 Máxima Calidad", callback_data="set_auto|max")],
                [InlineKeyboardButton("📉 Mínimo Peso", callback_data="set_auto|min")],
                [InlineKeyboardButton("🔴 Desactivar", callback_data="set_auto|off")],
                [InlineKeyboardButton("🔙 Volver", callback_data="menu|main")]
            ])
            await msg.edit_text("⚙️ **Auto-Descarga**", reply_markup=kb)
            return

        if data.startswith("set_auto|"):
            v = data.split("|")[1]
            conf['q_auto'] = None if v == "off" else v
            from firebase_service import save_user_config_fb
            asyncio.create_task(save_user_config_fb(cid, conf))
            await msg.edit_text("⚙️ **Configuración Actualizada**", reply_markup=gen_kb(conf, uid))
            return

        if data == "menu|party_off":
            conf['party_mode'] = False
            url_storage.pop(cid, None)
            from firebase_service import save_user_config_fb
            asyncio.create_task(save_user_config_fb(cid, conf))
            await msg.edit_text("⚙️ **Panel de Configuración**", reply_markup=gen_kb(conf, uid))
            return

        if data == "menu|main":
            await msg.edit_text("⚙️ **Panel de Configuración**", reply_markup=gen_kb(conf, uid))
            return

        if data == "menu|admin":
            if uid != OWNER_ID: return await q.answer("🔒", show_alert=True)
            active_c = len(url_storage)
            from firebase_service import db
            st_doc = db.collection('bot_settings').document('stats').get()
            u_count = st_doc.to_dict().get('user_count', 0) if st_doc.exists else 0
            txt = (f"👮‍♂️ **Panel de Control**\n\n"
                   f"👥 **Usuarios Totales:** `{u_count}`\n"
                   f"⬇️ **Descargas Activas:** `{active_c}`\n\n"
                   f"🆔 **Tu ID:** `{uid}`")
            await msg.edit(text=txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Volver", callback_data="menu|main")]]))
            return

        # --- SECCION: MANGA FLOW ---
        if data == "menu|mflow":
            await q.answer("🔄 Cargando catálogo...")
            mgs = await get_all_mangas_paginated()
            if not mgs: return await q.answer("⚠️ Catálogo vacío.", show_alert=True)
            url_storage[cid] = {'catalog_list': mgs}
            curr = mgs[0]
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️", callback_data=f"catalog|nav|{len(mgs)-1}"), InlineKeyboardButton(f"1/{len(mgs)}", callback_data="ignore"), InlineKeyboardButton("➡️", callback_data=f"catalog|nav|1")],
                [InlineKeyboardButton("📥 VER MANGA", callback_data=f"catalog|sel|{curr['id']}")],
                [InlineKeyboardButton("🔙 Salir", callback_data="menu|main")]
            ])
            txt = f"📚 **Manga Flow**\n\n📌 **{curr['title']}**\n👤 {curr['author']}"
            if curr.get('cover'):
                await msg.delete()
                await c.send_photo(cid, curr['cover'], caption=txt, reply_markup=kb)
            else:
                await msg.edit(txt, reply_markup=kb)
            return

        if data.startswith("catalog|"):
            m_m = data.split("|")[1]
            if m_m == "nav":
                px = int(data.split("|")[2])
                lst = url_storage.get(cid, {}).get('catalog_list', [])
                if not lst: return
                if px < 0: px = len(lst)-1
                if px >= len(lst): px = 0
                cur = lst[px]
                kb_n = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️", callback_data=f"catalog|nav|{px-1}"), InlineKeyboardButton(f"{px+1}/{len(lst)}", callback_data="ignore"), InlineKeyboardButton("➡️", callback_data=f"catalog|nav|{px+1}")], [InlineKeyboardButton("📥 VER", callback_data=f"catalog|sel|{cur['id']}")], [InlineKeyboardButton("🔙 Salir", callback_data="menu|main")]])
                await msg.edit_media(InputMediaPhoto(cur['cover'], caption=f"📚 **Manga Flow**\n📌 **{cur['title']}**"), reply_markup=kb_n)
            elif m_m == "sel":
                mi = data.split("|")[2]
                t = next((m for m in url_storage[cid]['catalog_list'] if m['id'] == mi), None)
                url_storage[cid]['manga_data'] = t
                # AÑADIDO BOTÓN IMAGENES
                kb_d = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📦 ZIP", callback_data="manga_sel|zip"), InlineKeyboardButton("📄 PDF", callback_data="manga_sel|pdf")],
                    [InlineKeyboardButton("🖼 Ver Imágenes", callback_data="manga_sel|images")],
                    [InlineKeyboardButton("🔙 Volver", callback_data="catalog|nav|0")]
                ])
                await msg.edit_caption(f"📚 **{t['title']}**\nDescargar:", reply_markup=kb_d)
            return

        if data.startswith("manga_sel|"):
            pts = data.split("|")
            mg = url_storage.get(cid, {}).get('manga_data')
            
            # Si eligió formato, preguntar calidad (si es ZIP/PDF) o enviar directo (Imagenes)
            if len(pts) == 2:
                fmt = pts[1]
                if fmt == "images":
                     await msg.delete()
                     sm = await c.send_message(cid, f"⏳ Obteniendo imágenes...")
                     
                     # FIX: Respetar configuración de Doc y Grupo
                     conf = get_config(cid)
                     doc_m = conf.get('doc_mode', False)
                     grp_m = conf.get('group_mode', True)
                     
                     asyncio.create_task(process_manga_download(c, cid, mg, "images", "original", sm, doc_mode=doc_m, group_mode=grp_m))
                else:
                    kb_q = InlineKeyboardMarkup([[InlineKeyboardButton("💎 Original", callback_data=f"manga_sel|{fmt}|original")], [InlineKeyboardButton("⚡ WebP", callback_data=f"manga_sel|{fmt}|webp")], [InlineKeyboardButton("🔙 Atrás", callback_data=f"menu|main")]])
                    await msg.edit_text(f"Calidad:", reply_markup=kb_q)
            elif len(pts) == 3:
                await msg.delete()
                sm = await c.send_message(cid, f"⏳ Descargando {pts[1].upper()}...")
                asyncio.create_task(process_manga_download(c, cid, mg, pts[1], pts[2], sm))
            return


    except Exception as e:
        print(f"Callback Error: {e}")
        try: await q.answer("❌ Error en el botón.", show_alert=True)
        except: pass



@app.on_message(filters.video | filters.document)
async def party_video_handler(c, m):
    cid = m.chat.id
    if not get_config(cid).get('party_mode'): return m.continue_propagation()
    
    st = url_storage.get(cid, {})
    wait = await m.reply("⬇️ Bajando video para Party...")
    f_p = await c.download_media(m, file_name=os.path.join(DATA_DIR, f"party_{cid}.mp4"))
    
    # ¿Hay una acción pendiente?
    if 'party_pending' in st:
        mode, val = st['party_pending']
        await run_party_logic(c, cid, f_p, mode, val, wait)
        url_storage.pop(cid, None)
    else:
        # Modo clásico: El usuario envió el video y AHORA elige
        url_storage[cid] = {'party_step': 'wait_mode', 'file': f_p}
        kb_p = InlineKeyboardMarkup([
            [InlineKeyboardButton("🧩 Partes", callback_data="party_sel|parts"), InlineKeyboardButton("⏱ Tiempo", callback_data="party_sel|time")],
            [InlineKeyboardButton("✂️ Rango", callback_data="party_sel|range")],
            [InlineKeyboardButton("🔙 Cancelar", callback_data="menu|party_off")]
        ])
        await wait.edit("✂️ **Modo Party**\nSelecciona una opción:", reply_markup=kb_p)


@app.on_message(filters.text & ~filters.command(["start", "help", "id", "menu", "cancel", "user", "setsudo"]), group=1)
async def input_handler(c, m):
    # Fix: Combined logic for ID detection and party mode input
    cid = m.chat.id
    text = m.text.strip()
    
    # 0. Check Party Input Mode first (Existing Logic)
    st = url_storage.get(cid)
    if st and 'party_input_mode' in st:
        mode = st['party_input_mode']
        url_storage[cid].pop('party_input_mode', None)

        if 'file' not in st:
            url_storage[cid]['party_pending'] = (mode, text)
            await m.reply(f"✅ **Configurado:** `{mode}={text}`\n\n🎬 **Envía el video** ahora.")
            return
        
        await run_party_logic(c, cid, st['file'], mode, text)
        url_storage.pop(cid, None)
        return

    # 1. RAW MANGA ID CHECK (AlphaNumeric ~20 chars)
    # Ejemplo: sX2wxwVUjoJzWmN0W2cG
    if re.match(r'^[a-zA-Z0-9]{20}$', text):
        wm = await m.reply("⬇️ **Analizando ID de Manga...**")
        await show_manga_menu(c, m, text, wait_msg=wm)
        return

    m.continue_propagation()


@app.on_message(filters.text & (filters.regex("http") | filters.regex("www") | filters.regex("twisted-brody-manga-flow")))
async def analyze(c, m):
    cid = m.chat.id
    if not can_download(cid)[0]: return await m.reply("⚠️ Espera a que terminen tus descargas.")
    url_storage.pop(cid, None)
    match = re.search(r"(https?://\S+)", m.text)
    if not match: return
    l_u = limpiar_url(match.group(1))
    
    # --- AUTO-MP3 CHECK ---
    conf = get_config(cid)
    if conf.get('fmt') == 'mp3':
        wm = await m.reply("🎵 **Descargando Audio MP3...**")
        # Preparamos un d_storage mínimo necesario para procesar_descarga
        # procesar_descarga necesita 'url' en d_storage si descarga 'direct' o 'mp3' de yt-dlp
        url_storage[cid] = {'url': l_u, 'titulo': "Audio Auto-MP3", 'fast_enabled': conf.get('fast_enabled', True)}
        
        # Lanzamos descarga directa como MP3
        asyncio.create_task(procesar_descarga(c, cid, l_u, "mp3", url_storage[cid], m))
        await wm.delete()
        return

    # 1. MANGA FLOW CHECK
    if "twisted-brody-manga-flow" in l_u:
        wm = await m.reply("⬇️ **Analizando Manga...**")
        try:
            # Extract ID from #manga/ID
            if "#manga/" in l_u:
                raw_id = l_u.split("#manga/")[1]
            elif "/manga/" in l_u:
                raw_id = l_u.split("/manga/")[1]
            else:
                 await wm.edit("❌ Error: ID no encontrado en el link.\nUsa formato: `.../#manga/ID`")
                 return
            
            # Clean ID (Alphanumeric only, stops at special chars or extra URLs)
            match_id = re.match(r'^([a-zA-Z0-9]+)', raw_id)
            if match_id:
                mi_l = match_id.group(1)
            else:
                mi_l = raw_id.split("?")[0].strip() # Fallback


            await show_manga_menu(c, m, mi_l, wait_msg=wm)
        except Exception as e:
            await wm.edit(f"❌ Error al procesar link de manga: {e}")
        return

    # 2. GALLERY CHECK (X, Pinterest, Instagram)
    # MOD: Intentar primero imágenes "silenciosamente" como pidió el usuario.
    # Si encuentra imágenes, las envía. Si no, o después de hacerlo, SIGUE para buscar video.
    gallery_sent = False
    if any(x in l_u for x in ['twitter.com', 'x.com', 'pinterest.com', 'instagram.com']):
        # MOD: Silencio absoluto hasta encontrar algo.
        wm_gal = None
        try:
            # Usar cookie si existe
            c_file = sel_cookie(l_u)
            paths, tmp = await asyncio.get_running_loop().run_in_executor(None, lambda: descargar_galeria(l_u, c_file))
            
            if paths:
                # Solo AHORA avisamos, cuando YA tenemos las imagenes listas
                conf = get_config(cid)
                is_doc = conf.get('doc_mode')
                
                wm_gal = await m.reply(f"📤 **Enviando {len(paths)} imágenes...**")
                
                if is_doc:
                    for p in paths:
                        try: await c.send_document(cid, p)
                        except: pass
                else:
                    # Group mode check
                    if len(paths) > 1 and len(paths) <= 10:
                        from pyrogram.types import InputMediaPhoto
                        media = [InputMediaPhoto(p) for p in paths]
                        try: await c.send_media_group(cid, media)
                        except: 
                             # Fallback si falla grupo
                             for p in paths: await c.send_photo(cid, p)
                    else:
                        for p in paths:
                            try: await c.send_photo(cid, p)
                            except: pass
                
                gallery_sent = True # Flag de éxito
                
                # Limpiar
                import shutil
                try: shutil.rmtree(tmp)
                except: pass
                
                if wm_gal: await wm_gal.delete()

        except Exception as e:
            # Si falla galeria, NO DECIMOS NADA y seguimos probando video
            # print(f"Silent Gallery Fail: {e}")
            if wm_gal: 
                try: await wm_gal.delete()
                except: pass
        
        # SI ENCONTRAMOS IMAGENES EN INSTAGRAM/PINTEREST, QUIZAS NO QUEREMOS SEGUIR?
        # PERO EN TWITTER/X PUEDE HABER VIDEO.
        # El usuario dijo: "primero procesa las imaganes... de ahi los videos"
        # Así que dejamos caer al bloque de abajo (yt-dlp).


    # 3. NORMALIZAR FACEBOOK
    if "facebook.com" in l_u or "fb.watch" in l_u:
        l_u = await resolver_url_facebook(l_u)

    wm = await m.reply("⬇️ **Analizando enlace...**")

    # 4. JAV TURBO SNIFFER
    if any(x in l_u for x in ['jav', 'hpjav', 'missav', 'javtrailers', '7mmtv']):
        try:
            links = extraer_jav_directo(l_u)
            if links:
                btns = []
                for i, l in enumerate(links[:8]):
                    btns.append([InlineKeyboardButton(f"🚀 {l['res']}", callback_data=f"dl|html_{i}")])
                btns.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancel")])
                
                url_storage[cid] = {'url': l_u, 'id': f"jav_{int(time.time())}", 'titulo': "JAV Video", 'html_links_data': links}
                await wm.delete()
                return await m.reply(f"🎬 **JAV Detectado**\nTurbocargado 🔥", reply_markup=InlineKeyboardMarkup(btns))
        except: pass

    # 4. DIRECT SITES / DIRECT LINKS (Mediafire, YourUpload, MP4Upload, Rule34Video GetFile)
    is_direct = any(x in l_u for x in ['mediafire.com', 'yourupload.com', 'mp4upload.com', 'rule34video.com/get_file/'])
    if not is_direct:
        # Check for video extensions in URL (ignoring params/slashes)
        if re.search(r'\.(mp4|mkv|webm|avi|mov)(/|\?|$)', l_u, re.I):
            is_direct = True

    if is_direct:
        url_storage[cid] = {'url': l_u, 'id': f"direct_{int(time.time())}", 'titulo': "Enlace Directo"}
        btns = [
            [InlineKeyboardButton("⬇️ Descargar Ahora", callback_data="dl|direct")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")]
        ]
        await wm.delete()
        return await m.reply(f"📦 **Archivo Detectado**\nMotor de descarga directa listo.", reply_markup=InlineKeyboardMarkup(btns))

    # 5. YT-DLP STANDARD
    try:
        y_o = {
            'quiet': True, 
            'force_ipv4': False, # Allow System Default
            'nocheckcertificate': True, # Ignore SSL errors
            # 'socket_timeout': 30, # Remove timeout to let OS decide
            'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'}
        }
        
        c_file = sel_cookie(l_u)
        if c_file:
            y_o['cookiefile'] = c_file

        # RETRY LOGIC FOR ANALYSIS
        y_i = None
        try:
            # Attempt 1: With Cookies (if available)
            y_i = await asyncio.get_running_loop().run_in_executor(None, lambda: yt_dlp.YoutubeDL(y_o).extract_info(l_u, download=False))
        except Exception as e_analysis:
            print(f"⚠️ Analysis Attempt 1 Failed: {e_analysis}")
            # Attempt 2: Without Cookies (often fixes HTTPSConnection/403 on Servers)
            if 'cookiefile' in y_o:
                print("🔄 Retrying analysis WITHOUT cookies...")
                del y_o['cookiefile']
                try:
                    y_i = await asyncio.get_running_loop().run_in_executor(None, lambda: yt_dlp.YoutubeDL(y_o).extract_info(l_u, download=False))
                except Exception as e_analysis_2:
                    raise e_analysis_2 # Raise the second error if both fail
            else:
                raise e_analysis # No cookies to remove, raise original error

        if y_i and 'entries' in y_i: y_i = y_i['entries'][0]
        
        y_b, y_f = [], []
        # Calidades de video
        formats = y_i.get('formats', [])
        for fl in formats:
            hv = fl.get('height')
            if hv:
                if hv not in y_f:
                    y_f.append(hv)
                    # Usar width si existe, sino solo height
                    label = f"{fl.get('width', '???')}x{hv}" if fl.get('width') else f"{hv}p"
                    
                    # Añadir PESO si existe (Estimado)
                    f_size = fl.get('filesize') or fl.get('filesize_approx')
                    if not f_size:
                        tbr = fl.get('tbr') or ((fl.get('vbr') or 0) + (fl.get('abr') or 0))
                        dur = y_i.get('duration') or fl.get('duration')
                        if tbr and dur:
                            f_size = (tbr * 1024 * dur) / 8
                    
                    if f_size:
                        from utils import format_bytes
                        label += f" ({format_bytes(f_size)})"
                    
                    y_b.append([InlineKeyboardButton(f"🎬 {label}", callback_data=f"dl|{hv}")])
        
        # SI NO SE ENCONTRARON CALIDADES CON 'HEIGHT', PERO HAY FORMATOS
        if not y_b and formats:
            # Intentar buscar el mejor formato de video
            best_v = next((f for f in reversed(formats) if f.get('vcodec') != 'none'), None)
            if best_v:
                y_b.append([InlineKeyboardButton("🎬 Calidad Única / Best", callback_data="dl|best")])

        # Audio
        y_b.append([InlineKeyboardButton("🎵 Audio MP3", callback_data="dl|mp3")])
        y_b.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancel")])
        
        url_storage[cid] = {'url': l_u, 'id': y_i.get('id'), 'titulo': y_i.get('title')}
        
        # FIX SURRIT ID: Si ID es 'playlist', intentar sacar UUID del URL
        if 'surrit.com' in l_u and str(y_i.get('id')) in ['playlist', 'video']:
            match_uuid = re.search(r'surrit\.com/([a-zA-Z0-9-]+)', l_u)
            if match_uuid:
                url_storage[cid]['id'] = match_uuid.group(1)
                print(f"🔧 ID corregido para Surrit: {url_storage[cid]['id']}")

        # --- AUTO QUALITY LOGIC ---
        q_auto = conf.get('q_auto')
        if q_auto in ['max', 'min']:
            target_q = None
            if y_f:
                # y_f tiene ints ordenados? No necesariamente, ordenemos
                start_l = sorted([int(x) for x in y_f])
                if q_auto == 'max': target_q = str(start_l[-1])
                else: target_q = str(start_l[0])
            else:
                # Si no hay resoluciones claras, 'best' para max, no tenemos 'worst' claro en dl|...
                # Asumiremos 'best' para max siempre que sea posible.
                if q_auto == 'max': target_q = "best"
                # Para min sin resoluciones es dificil, dejaremos que el usuario decida o 'best'
            
            if target_q:
                await wm.edit(f"⚙️ **Auto-Calidad ({q_auto.upper()}):** {target_q}p")
                # Necesitamos guardar el st antes de llamar, igual que en el callback
                d_st = url_storage[cid]
                d_st['fast_enabled'] = conf.get('fast_enabled', True)
                
                # Lanzar download
                asyncio.create_task(procesar_descarga(c, cid, d_st['url'], target_q, d_st, m))
                await wm.delete()
                return

        await wm.delete()
        await m.reply(f"🎬 **{y_i.get('title', 'Video Detectado')}**", reply_markup=InlineKeyboardMarkup(y_b))
    except Exception as e:
        if gallery_sent:
            # Si ya enviamos imágenes, el error de 'no video' es esperado y debemos ignorarlo.
            await wm.delete()
            return
        await wm.edit(f"❌ Error de análisis.\n\n`{str(e)[:100]}`")

async def show_manga_menu(c, m, manga_id, wait_msg=None):
    cid = m.chat.id
    meta_m = await get_manga_metadata(manga_id)
    
    if not meta_m: 
        if wait_msg: await wait_msg.edit("❌ **Error:** Manga no encontrado (ID inválido o DB vacía).")
        return

    url_storage[cid] = {'manga_data': meta_m}
    
    if wait_msg: await wait_msg.delete()
    
    # BOTONES SOLICITADOS:
    # [ ZIP ] [ PDF ]
    # [ Enviar Imágenes ]
    kb_m_f = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 ZIP", callback_data="manga_sel|zip"), InlineKeyboardButton("📄 PDF", callback_data="manga_sel|pdf")],
        [InlineKeyboardButton("🖼 Ver Imágenes", callback_data="manga_sel|images")],
        [InlineKeyboardButton("🔙 Cancelar", callback_data="cancel")]
    ])
    
    txt = f"📚 **{meta_m['title']}**\n👤 {meta_m.get('author', 'Desconocido')}\n\n⬇️ **Selecciona formato:**"
    
    # OLD: if meta_m.get('cover'): await c.send_photo(cid, meta_m['cover'], ...
    
    # NEW: Cache Logic
    cover_ref = meta_m.get('cover')
    if cover_ref:
        # Intentar obtener ID cacheado o generar uno nuevo
        if wait_msg: 
            try: await wait_msg.edit("🖼 **Procesando portada...**")
            except: pass
            
        final_cover = await get_or_cache_cover(c, cid, manga_id, cover_ref)
        
        try: await wait_msg.delete()
        except: pass
        
        try:
            await c.send_photo(cid, final_cover, caption=txt, reply_markup=kb_m_f)
        except Exception as e:
            print(f"❌ Error enviando Cover: {e}")
            # Fallback: Enviar texto con botones si la foto falla
            await c.send_message(cid, txt, reply_markup=kb_m_f)
    else:
        if wait_msg: await wait_msg.delete()
        await c.send_message(cid, txt, reply_markup=kb_m_f)

# --- COMANDOS ADICIONALES ---

@app.on_message(filters.command("id"))
async def id_command(c, m):
    await m.reply_text(f"🆔 **ID del Chat:** `{m.chat.id}`")

@app.on_message(filters.command("cancel"))
async def cancel_cmd(c, m):
    n = cancel_all(m.chat.id)
    url_storage.pop(m.chat.id, None)
    await m.reply(f"🛑 **Se cancelaron {n} descargas activas.**")

@app.on_message(filters.command("menu"))
async def menu_help(c, m):
    help_text = "📖 **Guía de Bot Pro**\n\nUsa `/start` para ver el panel de configuración."
    await m.reply_text(help_text)

@app.on_message(filters.command("user"))
async def user_profile_cmd(c, m):
    uid = m.from_user.id
    txt = f"🆔 **Perfil de Usuario**\n👤 **Nombre:** {m.from_user.first_name}\n🔢 **ID:** `{uid}`"
    await m.reply(txt)

@app.on_message(filters.command("setsudo"))
async def setsudo_cmd(c, m):
    if m.from_user.id != OWNER_ID: return
    if len(m.command) < 2: return
    new_id = int(m.command[1])
    # Lógica de guardado en Firebase...
    await m.reply(f"👮‍♂️ Admin añadido: `{new_id}`")

# --- ARRANQUE ---

# --- ARRANQUE ---

async def boot_services():
    print("🚀 Bot Iniciando (Versión Final)...")
    
    # --- CLEANUP STARTUP ---
    try:
        import shutil
        cwd = os.getcwd()
        print("🧹 Ejecutando limpieza inicial...")
        for item in os.listdir(cwd):
            if item.startswith("tmp_gallery_") and os.path.isdir(item):
                try: 
                    shutil.rmtree(item)
                    print(f"🗑 Eliminado: {item}")
                except Exception as e:
                    print(f"⚠️ Error borrando {item}: {e}")
    except: pass
    
    
    # --- CLEANUP SESSION & START ---
    # --- CLEANUP SESSION & START ---
    max_retries = 10
    connected = False
    
    for i in range(max_retries):
        try:
            if i > 0: print(f"🔄 Intento de conexión {i+1}/{max_retries}...")
            await app.start()
            connected = True
            break
        except Exception as e:
            err_str = str(e)
            # 1. Error de Sesión (Corrupción) -> Borrar y reintentar inmediatamente
            if "406" in err_str or "AUTH_KEY" in err_str or "Unauthorized" in err_str:
                print(f"⚠️ Error de Sesión detectado ({e}). Eliminando archivo de sesión corrupto y reintentando...")
                s_path = os.path.join(WORKDIR, "brody_final_v1.session")
                if os.path.exists(s_path):
                    try: os.remove(s_path)
                    except: pass
                continue

            # 2. Error de Red (Timeout, Connection, etc) -> Esperar y reintentar
            is_net = any(x in err_str for x in ["Connection", "Timeout", "Network", "OSError", "Unreachable"])
            if is_net:
                wait_sec = (i + 1) * 3  # 3s, 6s, 9s...
                print(f"⚠️ Error de Red ({e}). Reintentando en {wait_sec} segundos...")
                await asyncio.sleep(wait_sec)
                continue
            
            # 3. Otros errores -> Crash
            raise e

    if not connected:
        print("❌ Error Crítico: No se pudo conectar a Telegram tras múltiples intentos.")
        sys.exit(1)
    
    # Comandos
    await app.set_bot_commands([
        BotCommand("start", "⚙️ Menú Principal"),
        BotCommand("menu", "📖 Guía de Ayuda"),
        BotCommand("id", "🆔 Ver ID"),
        BotCommand("user", "👤 Mi Perfil"),
        BotCommand("cancel", "🛑 Cancelar")
    ])
    
    # Firebase sync
    try:
        from firebase_service import load_all_user_configs, load_all_hashtags
        import database
        cfs = await load_all_user_configs()
        if cfs: database.user_config.update(cfs)
        tgs = await load_all_hashtags()
        if tgs: database.hashtag_db.update(tgs)
    except: pass
    
    print("✅ Bot Conectado y Listo.")
    await idle()
    await app.stop()

if __name__ == "__main__":
    try:
        # 1. Hilo Web (Independiente)
        threading.Thread(target=run_health_check, daemon=True).start()
        print("🌍 Servidor Web 'Fantasma' activo en puerto 7860")

        # 2. Hilo Bot (Asyncio Principal)
        print('🚀 Iniciando Loop Principal del Bot...')
        loop = asyncio.get_event_loop()
        loop.run_until_complete(boot_services())

    except Exception as e:
        print(f"❌ CRITICAL BOT CRASH: {e}")
    except KeyboardInterrupt:
        print("🛑 Bot detenido manualmente.")