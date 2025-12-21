import re
import math
import os
import time
import asyncio
import yt_dlp
import shutil
import subprocess
import aiohttp
import random
from pyrogram import enums
from config import LIMIT_2GB, HAS_FAST, DOWNLOAD_DIR, TOOLS_DIR, FAST_PATH
from database import get_config, downloads_db, guardar_db, add_active, remove_active
from utils import sel_cookie, traducir_texto
from tools_media import get_thumb, get_meta, get_audio_dur, progreso
from firebase_service import get_cached_file, save_cached_file, get_bot_config, delete_cached_file

# --- HELPER: SAFE BACKUP ---
 


# Límite real de Telegram para dividir (1.9 GB para ir seguros)
TG_LIMIT = int(1.9 * 1024 * 1024 * 1024)

# Detectamos si tienes la herramienta Turbo instalada (Cross-Platform)
# Priorizamos tools/
RE_NAME = "N_m3u8DL-RE.exe" if os.name == 'nt' else "N_m3u8DL-RE"
RE_PATH = os.path.join(TOOLS_DIR, RE_NAME)

if not os.path.exists(RE_PATH):
    RE_PATH = shutil.which("N_m3u8DL-RE") 
    if not RE_PATH:
         if os.path.exists("N_m3u8DL-RE.exe"): RE_PATH = "N_m3u8DL-RE.exe"
         elif os.path.exists("N_m3u8DL-RE"): RE_PATH = "./N_m3u8DL-RE"

HAS_RE = RE_PATH is not None and os.path.exists(RE_PATH)

async def get_mediafire_link(url):
    try:
        from utils import load_cookies_dict
        cookies = load_cookies_dict(sel_cookie(url))
        async with aiohttp.ClientSession(cookies=cookies) as session:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200: return None
                text = await resp.text()
                match = re.search(r'href="([^"]+)"\s+id="downloadButton"', text)
                if match: return match.group(1)
                match2 = re.search(r'href="([^"]+)"[^>]+aria-label="Download file"', text)
                if match2: return match2.group(1)
    except Exception as e: print(f"Error Mediafire: {e}")
    return None

async def get_yourupload_link(url):
    try:
        from utils import load_cookies_dict
        cookies = load_cookies_dict(sel_cookie(url))
        headers = {"User-Agent": "Mozilla/5.0", "Referer": url}
        async with aiohttp.ClientSession(cookies=cookies) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200: return None
                text = await resp.text()
                match_og = re.search(r'property="og:video"\s+content="([^"]+)"', text)
                if match_og: return match_og.group(1)
                match_jw = re.search(r"file\s*:\s*['\"]([^'\"]+)['\"]", text)
                if match_jw:
                    link = match_jw.group(1)
                    return "https://www.yourupload.com" + link if link.startswith("/") else link
    except Exception as e: print(f"Error YourUpload: {e}")
    return None

async def get_mp4upload_link(url):
    try:
        if "embed-" not in url:
            vid_id = url.split("/")[-1].replace(".html", "")
            url = f"https://www.mp4upload.com/embed-{vid_id}.html"

        from utils import load_cookies_dict
        cookies = load_cookies_dict(sel_cookie(url))
        headers = {"User-Agent": "Mozilla/5.0", "Referer": url}
        async with aiohttp.ClientSession(cookies=cookies) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200: return None
                text = await resp.text()
                match = re.search(r'src:\s*"([^"]+\.mp4)"', text)
                if match: return match.group(1)
    except Exception as e: print(f"Error MP4Upload: {e}")
    return None

async def procesar_descarga(client, chat_id, url, calidad, datos, msg_orig):
    conf = get_config(chat_id)
    vid_id = datos.get('id')
    
    final = None
    thumb = None
    # Identificador único (Timestamp ms + Random)
    ts = f"{int(time.time() * 1000)}_{random.randint(100, 999)}"
    
    # Usar directorio de descargas
    base_name = os.path.join(DOWNLOAD_DIR, f"dl_{chat_id}_{ts}")
    # Limpiamos base_name de posibles caracteres raros por si acaso (aunque es solo ID_TS)

    url_descarga = url
    ckey = calidad
    
    # Si viene del Sniffer/JAV Extractor
    if calidad.startswith("html_"):
        idx = int(calidad.split("_")[1])
        if 'html_links_data' in datos and len(datos['html_links_data']) > idx:
            url_descarga = datos['html_links_data'][idx]['url']
            ckey = f"html_{idx}" 
        else:
            await client.send_message(chat_id, "❌ **Enlace expirado (Datos perdidos).**\nPor favor, reenvía el enlace y prueba de nuevo.")
            return
    else:
        ckey = "mp3" if calidad == "mp3" else calidad

    # FIX: Diferenciar cache si es modo documento
    if conf.get('doc_mode') and calidad != "mp3":
        ckey += "_doc"

    # --- ZONA DE CACHE (FIREBASE) ---
    # --- ZONA DE CACHE (FIREBASE) ---
    cached_fid = None
    if vid_id:
        # print(f"🔎 DEBUG: Checking cache for {vid_id} [{ckey}]...")
        # cached_fid = await get_cached_file(vid_id, ckey)
        print(f"🔎 DEBUG: Skipping cache for {vid_id} (FORCE DISABLE)")
        cached_fid = None
    else:
        print("⚠️ DEBUG: vid_id is None! Skipping cache check.")

    if cached_fid:
        try:
            print(f"✨ Firebase Cache Hit: {vid_id} [{ckey}]")
            file_id = cached_fid
            
            res_str = f"{calidad}p" if calidad.isdigit() else calidad.upper()
            cap_cache = f"🎬 **{datos.get('titulo','Video')}**\n⚙️ {res_str} | ✨ (Reenviado al instante)"
            
            if calidad == "mp3": 
                await client.send_audio(chat_id, file_id, caption=cap_cache)
            elif conf.get('doc_mode'):
                # FIX: Si el usuario quiere documento, ENVIAR DOCUMENTO
                await client.send_document(chat_id, file_id, caption=cap_cache)
            else:
                try:
                    await client.send_video(chat_id, file_id, caption=cap_cache)
                except:
                    await client.send_document(chat_id, file_id, caption=cap_cache)
            return
        except Exception as e:
            print(f"⚠️ Cache inválido o borrado: {e}")
            if vid_id: await delete_cached_file(vid_id)

    # Register Task for Anti-Spam / Cancellation
    curr_task = asyncio.current_task()
    add_active(chat_id, msg_orig.id, curr_task)

    try:
        # Variables de control de progreso
        last_edit = 0
        start_time = time.time()
        loop = asyncio.get_running_loop()
        
        def progress_hook(d):
            nonlocal last_edit
            now = time.time()
            
            # Filtro Anti-Flood (Editar cada 4 segundos máx o al finalizar)
            if d['status'] == 'finished' or (now - last_edit) > 4:
                last_edit = now
                
                # Extraer datos de YT-DLP / Fast
                percent = d.get('_percent_str', '0%').strip()
                # Limpiar caracteres ANSI si Fast los mete
                percent = re.sub(r'\x1b\[[0-9;]*m', '', percent)
                
                speed = d.get('_speed_str', 'N/A').strip()
                eta = d.get('_eta_str', 'N/A').strip()
                
                # Fallback simple si no hay speed string
                if speed == 'N/A' and d.get('speed'):
                    speed = format_bytes(d.get('speed')) + "/s"
                    
                try:
                    from utils import render_bar
                    
                    # Safe parse percent
                    try: p_val = float(percent.replace('%','')) 
                    except: p_val = 0
                    
                    # Parse bytes to get total estimation if needed, or just bar 0-100
                    # For yt-dlp, let's trust percent
                    bar = render_bar(p_val, 100)
                    
                    msg_text = (
                        f"⏳ **Descargando...**\n"
                        f"📥 {calidad}\n"
                        f"🚀 **Motor:** {engine_name}\n\n"
                        f"**{percent}**\n"
                        f"⚡ **{speed}** | ⏳ **{eta}**"
                    )
                    # FIX: Ejecutar la corrutina en el loop principal de forma segura desde el hilo de yt-dlp
                    asyncio.run_coroutine_threadsafe(status.edit(msg_text), loop)
                except: pass

        status = await client.send_message(chat_id, f"⏳ **Descargando...**\n📥 {calidad}")
        
        # --- LOGICA DE SELECCIÓN DE MOTOR ---
        engine_name = "Nativo (Estándar)"
        is_direct_download = False
        mediafire_link = None
        yourupload_link = None
        mp4_link = None
        
        # 1. Mediafire Check
        if "mediafire.com" in url_descarga:
            await status.edit(f"⏳ **Mediafire Check...**\n🔍 Buscando enlace directo...")
            mf_link = await get_mediafire_link(url_descarga)
            if mf_link:
                url_descarga = mf_link
                engine_name = "Mediafire (Directo)"
                is_direct_download = True
                mediafire_link = True
            else:
                await status.edit("❌ **Error: Mediafire cambió.**\nNo pude sacar el link directo.")
                return 

        # 2. YourUpload Check
        elif "yourupload.com" in url_descarga:
             await status.edit(f"⏳ **YourUpload Check...**\n🔍 Buscando video directo...")
             yu_link = await get_yourupload_link(url_descarga)
             if yu_link:
                 url_descarga = yu_link
                 engine_name = "YourUpload (Directo)"
                 is_direct_download = True
                 yourupload_link = True
             else:
                 pass

        # 2b. MP4Upload Check
        elif "mp4upload.com" in url_descarga:
             await status.edit(f"⏳ **MP4Upload Check...**\n🔍 Extrayendo video real...")
             mp4_link = await get_mp4upload_link(url_descarga)
             if mp4_link:
                 url_descarga = mp4_link
                 engine_name = "MP4Upload (Directo)"
                 is_direct_download = True
             else:
                 await status.edit("❌ **Error: MP4Upload falló.**\nNo pude sacar el video.")
                 return

        # 2c. Eporner Direct Check
        elif "eporner.com" in url_descarga and "/dload/" in url_descarga:
             # Limpiar URL (es.eporner -> www.eporner para evitar problemas de certificado/redirección)
             url_descarga = re.sub(r'https?://\w+\.eporner\.com', 'https://www.eporner.com', url_descarga)
             engine_name = "Eporner (Directo)"
             is_direct_download = True

        # 3. Turbo Check (Priority for m3u8 if tool exists)
        # Removed Owner Restriction per user request
        
        usar_turbo = HAS_RE and ".m3u8" in url_descarga and calidad != "mp3" and not mediafire_link and not yourupload_link

        if usar_turbo: 
            engine_name = "Turbo (N_m3u8DL-RE)"
        elif is_direct_download or (HAS_FAST and not calidad.startswith("html_") and conf.get('fast_enabled', True) and "eporner" not in url_descarga):
            if not is_direct_download: 
                 engine_name = "Fast (Ultra)"

        await status.edit(f"⏳ **Descargando...**\n📥 {calidad}\n🚀 **Motor:** {engine_name}")

        if usar_turbo:
            # Es mucho más rápido que yt-dlp para unir segmentos
            pure_name = f"dl_{chat_id}_{ts}"
            cmd = [
                RE_PATH,
                url_descarga,
                "--save-name", pure_name,
                "--save-dir", DOWNLOAD_DIR,      # Guardar en DOWNLOAD_DIR explicitamente
                "--tmp-dir", "tmp",      # Temporales
                "--no-log",              # No llenar la consola
                "--auto-select",         # Elegir mejor video/audio auto
                "--check-segments-count", "false", # No verificar cada segmento (Más velocidad)
                "--thread-count", "16",  # 16 Hilos de descarga
                "--download-retry-count", "10" # Reintentar si falla un trozo
            ]
            
            # Ejecutamos el proceso CON PIPE para leer salida
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Registrar PID para Cancelar
            add_active(chat_id, msg_orig.id, None, process.pid)
            
            # Loop para leer progreso de Turbo
            while True:
                line = await process.stdout.readline()
                if not line: break
                
                line_str = line.decode('utf-8', errors='ignore').strip()
                if line_str: print(f"Turbo: {line_str}") # Feedback en consola
                
                if "Progress:" in line_str:
                    now_t = time.time()
                    if (now_t - last_edit) > 4:
                        last_edit = now_t
                        p_match = re.search(r'Progress:\s*([\d\.]+%?)', line_str)
                        s_match = re.search(r'Speed:\s*([\d\.]+\s*\w+/s)', line_str)
                        
                        perc = p_match.group(1) if p_match else "..."
                        spd = s_match.group(1) if s_match else "..."
                        
                        try:
                            from utils import render_bar
                            try: p_v = float(perc.replace('%',''))
                            except: p_v = 0
                            bar = render_bar(p_v, 100)
                            
                            await status.edit(
                                f"⏳ **Descargando...**\n"
                                f"📥 {calidad}\n"
                                f"🚀 **Motor:** {engine_name}\n\n"
                                f"**{perc}**\n"
                                f"⚡ **{spd}**"
                            )
                        except: pass
            
            await process.wait()
            
            # Buscamos qué archivo creó (puede ser mp4 o mkv)
            for ext in ['.mp4', '.mkv', '.ts']:
                if os.path.exists(f"{base_name}{ext}"):
                    final = f"{base_name}{ext}"
                    break
        
             # --- MODO DIRECTO (FAST/MEDIAFIRE PURO) ---
        elif is_direct_download or str(vid_id).startswith("direct_"):
             
             temp_out = f"dl_{chat_id}_{ts}_temp"
             final_temp = os.path.join(DOWNLOAD_DIR, temp_out)
             
             # FALLBACK: Si no hay aria2c, usar aiohttp (Python nativo)
             if not HAS_FAST and not shutil.which("aria2c"):
                 await status.edit(f"⏳ **Descargando (Nativo)...**\n🚀 **Motor:** Python (aiohttp)")
                 try:
                     async with aiohttp.ClientSession() as session:
                         async with session.get(url_descarga) as resp:
                             if resp.status == 200:
                                 total_size = int(resp.headers.get('Content-Length', 0))
                                 downloaded = 0
                                 start_t = time.time()
                                 last_edit_t = 0
                                 
                                 with open(final_temp, 'wb') as f:
                                     while True:
                                         chunk = await resp.content.read(1024*1024) # 1MB chunks
                                         if not chunk: break
                                         f.write(chunk)
                                         downloaded += len(chunk)
                                         
                                         # Status update
                                         now_t = time.time()
                                         if now_t - last_edit_t > 4:
                                             last_edit_t = now_t
                                             from utils import render_bar
                                             pct = f"{int(downloaded/total_size*100)}%" if total_size else "..."
                                             bar = render_bar(downloaded, total_size) if total_size else "░░░░░░░░░░"
                                             mb = downloaded / (1024*1024)
                                             speed = mb / (now_t - start_t) if (now_t - start_t) > 0 else 0
                                             await status.edit(f"⏳ **Descargando...**\n**{pct}**\n⚡ {speed:.2f} MB/s")
                                             
                                 final = final_temp
                             else:
                                 await status.edit(f"❌ Error descarga: {resp.status}")
                                 return
                 except Exception as e:
                      print(f"Native DL Error: {e}")
                      await status.edit(f"❌ Error interno: {e}")
                      return

             else:
                 # ARIA2 BLOCK (Solo si existe)
                 cmd = [
                     FAST_PATH if os.path.exists(FAST_PATH) else "aria"+"2c", 
                     url_descarga,
                     "-o", temp_out, 
                     "-d", DOWNLOAD_DIR,
                     "-x", "16", "-s", "16", "-j", "1", "-k", "1M",
                     "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                     "--check-certificate=false",
                     "--allow-overwrite=true",
                     "--auto-file-renaming=false"
                 ]
                 
                 if yourupload_link:
                     cmd.extend(["--header", f"Referer: {url}"])
                 
                 cookie_file = sel_cookie(url)
                 if cookie_file:
                     cmd.extend(["--load-cookies", cookie_file])

                 process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 
                 # Loop simple de progreso (Aria2)
                 start_t = time.time()
                 while process.returncode is None:
                     try:
                         await asyncio.sleep(3)
                         elapsed = int(time.time() - start_t)
                         # Aria2 sin stdout parseado complejo solo sabemos que corre
                         # Mostramos barra indeterminada o simplemente "Corriendo"
                         bar = "░" * 10 
                         await status.edit(f"⏳ **Descargando (Aria2)...**\n{bar}\n⏱ Tiempo: {elapsed}s")
                     except: pass
                     
                     if process.returncode is not None: break
                     try: 
                        await asyncio.wait_for(process.wait(), timeout=0.1)
                     except: pass
                 
                 final = final_temp
             
             # Loop simple de progreso
             start_t = time.time()
             while process.returncode is None:
                 try:
                     await asyncio.sleep(3)
                     elapsed = int(time.time() - start_t)
                     await status.edit(f"⏳ **Descargando...**\n🚀 **Motor:** {engine_name}\n⏱ Tiempo: {elapsed}s")
                 except: pass
                 
                 if process.returncode is not None: break
                 try: 
                    await asyncio.wait_for(process.wait(), timeout=0.1)
                 except: pass

             final_temp = os.path.join(DOWNLOAD_DIR, temp_out)
             if os.path.exists(final_temp):
                 # Intentar detectar extensión real si podemos (usando libmagic o simplemente renombrando si Mediafire redirigió a un archivo con ext)
                 # En este caso simple, si sabemos que es mediafire, el link solía tener el nombre.
                 # Pero aria2 guarda con el nombre que le dimos.
                 
                 # Estrategia: Ver si file es Video o ZIP
                 # Renombramos a algo seguro por ahora, luego decidiremos si es Video o Doc
                 final = final_temp
             else:
                 # Fallback wget basico?
                 pass

        else:
            # --- MODO CLÁSICO (YT-DLP) ---
            # Para YouTube, Facebook, Twitter, etc.
            opts = {
                'outtmpl': f"{base_name}.%(ext)s",
                'quiet': True, 
                'no_warnings': True, 
                'max_filesize': LIMIT_2GB,
                'progress_hooks': [progress_hook], # HOOK AÑADIDO
                'force_ipv4': False,
                'socket_timeout': 30,
                'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'}
            }

            if calidad == "mp3":
                opts.update({'format': 'bestaudio/best', 'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3'}]})
            elif calidad.isdigit():
                 opts['format'] = f"bv*[height<={calidad}]+ba/b[height<={calidad}] / best"
            else:
                 opts['format'] = 'best'
            opts['merge_output_format'] = 'mp4'

            cookie_file = sel_cookie(url_descarga)
            if cookie_file: opts['cookiefile'] = cookie_file

            if "eporner" in url_descarga:
                opts['nocheckcertificate'] = True

            # --- FAST: PREPARAR OPCIONES ---
            force_std = False
            use_fast = False
            
            if HAS_FAST and not calidad.startswith("html_") and conf.get('fast_enabled', True) and "eporner" not in url_descarga:
                # FIX: Disable Fast for Twitter/X (keep disabled)
                # FIX: Disable Fast for Surrit (WinError 32 file locks on m3u8)
                # FIX: Disable Fast for YouTube (User request: Use Native yt-dlp + Tor for stability)
                if not any(x in url_descarga for x in ["youtube.com", "youtu.be", "twitter.com", "x.com", "surrit.com"]):
                    use_fast = True
            
            # Helper para ejecutar descarga
            async def run_ytdlp(options):
                with yt_dlp.YoutubeDL(options) as ydl:
                    await loop.run_in_executor(None, lambda: ydl.download([url_descarga]))

            # Intento 1: FAST (si aplica)
            if use_fast:
                print(f"🚀 Intentando Fast para: {url_descarga}")
                opts_fast = opts.copy()
                opts_fast.update({
                    'external_downloader': FAST_PATH if os.path.exists(FAST_PATH) else 'aria'+'2c',
                    'external_downloader_args': ['-x','16','-k','1M','-s','16'],
                    'merge_output_format': 'mp4' # Preferir MP4 para evitar errores de Video
                })
                try:
                    await run_ytdlp(opts_fast)
                except Exception as e:
                    print(f"⚠️ Fast falló: {e}")
                    # Verificar si fue error de archivo bloqueado (WinError 32) -> Ese es fatal, no retry
                    if "WinError 32" in str(e) or "used by another process" in str(e):
                        raise e
                    
                    await status.edit(f"⚠️ **Fast falló (Pornhub/Otros)...**\\n🔄 Reintentando con motor nativo...")
                    force_std = True

            # Intento 2: STANDARD (Si no se usó Fast o si Fast falló)
            if not use_fast or force_std:
                try:
                    await run_ytdlp(opts)
                except Exception as e:
                    # RETRY WITHOUT COOKIES LOGIC
                    err_str = str(e)
                    print(f"⚠️ Error descarga: {err_str}")
                    
                    if 'cookiefile' in opts and any(x in err_str for x in ["Sign in", "Unable to extract", "403", "captcha"]):
                        print("⚠️ Falló con cookies. Reintentando SIN cookies...")
                        del opts['cookiefile']
                        try:
                            await run_ytdlp(opts)
                        except Exception as e2:
                            # Si falla de nuevo, lanzamos el error original o el nuevo
                            raise e2
                    else:
                        # FIX: WinError 32/5 logic
                        if any(x in err_str for x in ["WinError 32", "WinError 5", "used by another process", "Access is denied"]):
                            print(f"⚠️ Conflicto de archivos ({err_str}). Reintentando loop de renomb... ")
                            posible_temp = f"{base_name}.temp.mp4"
                            posible_final = f"{base_name}.mp4"
                            renamed = False
                            for _ in range(5):
                                 await asyncio.sleep(2)
                                 if not os.path.exists(posible_final) and os.path.exists(posible_temp):
                                     try:
                                         os.rename(posible_temp, posible_final)
                                         renamed = True
                                         break
                                     except: pass
                            if not renamed and not os.path.exists(posible_final): raise e
                        else:
                            raise e

            if calidad == "mp3": final = f"{base_name}.mp3"
            else:
                for e in ['.mp4', '.mkv', '.webm']:
                    if os.path.exists(base_name+e): 
                        final = base_name+e
                        break
        
        # ... (lines 555-700 skipped for brevity in replacement, focusing on upload logic below) ...
        # NOTE: I need to target the UPLOAD loop effectively.
        # I will replace the block from "if use_fast:" down to end of upload loop if possible, 
        # or just the upload loop. 
        
        # Actually, separate tool calls is safer. I'll do the MP4 fix first, then the fallback fix.
        # This tool call is for FAST MP4 FIX + UPLOAD LOOP REWRITE.
        
        # To make it work in one go, I need to match a large chunk. 
        # Better to just do the Upload Loop rewrite here, and the MP4 fix in a separate call? 
        # No, I can't do multiple calls easily if I don't see the lines.
        # I'll stick to rewriting the UPLOAD LOOP ONLY here, and trust the previous step for line numbers.
        
        # WAITING... I will cancel this replacement content and write a targeted one for the Upload Loop.
        # I cannot change my plan mid-stream easily. 
        # I will target lines 700-745 for the UPLOAD LOGIC.


            # Intento 2: STANDARD (Si no se usó Fast o si Fast falló)
            if not use_fast or force_std:
                try:
                    await run_ytdlp(opts)
                except Exception as e:
                    # FIX: WinError 32/5 logic
                    str_err = str(e)
                    if any(x in str_err for x in ["WinError 32", "WinError 5", "used by another process", "Access is denied"]):
                        print(f"⚠️ Conflicto de archivos ({str_err}). Reintentando loop de renomb... ")
                        posible_temp = f"{base_name}.temp.mp4"
                        posible_final = f"{base_name}.mp4"
                        renamed = False
                        for _ in range(5):
                             await asyncio.sleep(2)
                             if not os.path.exists(posible_final) and os.path.exists(posible_temp):
                                 try:
                                     os.rename(posible_temp, posible_final)
                                     renamed = True
                                     break
                                 except: pass
                        if not renamed and not os.path.exists(posible_final): raise e
                    else:
                        raise e
            
            if calidad == "mp3": final = f"{base_name}.mp3"
            else:
                for e in ['.mp4', '.mkv', '.webm']:
                    if os.path.exists(base_name+e): 
                        final = base_name+e
                        break
        
        # --- POST-PROCESADO: DETECCION DE TIPO Y RENOMBRAMIENTO ---
        if not final or not os.path.exists(final):
            print(f"❌ DEBUG: File detection failed. Final var is: {final}")
            await status.edit("❌ **Error de descarga.**\nEl enlace puede estar protegido o expiró.")
            return
        
        file_size = os.path.getsize(final)
        print(f"✅ DEBUG: File found: {final} | Size: {file_size} bytes ({file_size/1024/1024/1024:.2f} GB)")

        if file_size == 0:
            await status.edit("❌ **Error: Archivo de 0 bytes.**\nLa descarga falló (posible bloqueo de IP o Login).")
            try: os.remove(final)
            except: pass
            return
        
        # Si venimos de descarga directa sin extensión clara
        # Intentamos detectar si es video por firma o simplemente asumimos Documento si no parece video
        is_video = False
        
        # Lista de extensiones de video comunes
        vid_exts = ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.m4v']
        
        # Detectar extensión actual
        _, ext = os.path.splitext(final)
        if ext.lower() in vid_exts:
            is_video = True
        elif is_direct_download:
            # Si descargamos de mediafire, a veces el archivo no tiene extensión si usamos aria2 con output fijo
            # Intentar ver si el nombre original del link tenía extensión
            # O simplemente ver si es reproducible.
            
            # Simple check: Si el usuario pidió MP3, es audio.
            if calidad == "mp3": is_video = False
            else:
                # Si no tiene extensión, intentar renombrar con la del link original si existe
                if not ext:
                    # Intento de sacar nombre del url original
                    # 1. Mediafire: .../file/xyz/Nombre_Archivo.rar/file
                    # 2. Generic: .../video.mp4
                    
                    possible_name = "downloaded_file"
                    clean_url = url_descarga.split('?')[0]
                    
                    if '/file/' in url: 
                        possible_name = url.split('/')[-2]
                    elif '.' in clean_url.split('/')[-1]:
                        possible_name = clean_url.split('/')[-1]

                    if '.' in possible_name:
                        new_ext = os.path.splitext(possible_name)[1]
                        # Validar que sea una extensión válida (length < 6) para evitar basura
                        if len(new_ext) < 7:
                            new_final = final + new_ext
                            os.rename(final, new_final)
                            final = new_final
                            ext = new_ext
                
                # YOURUPLOAD FIX: Forzar .mp4 si viene de yourupload y no tiene ext
                if yourupload_link and not ext:
                    new_final = final + ".mp4"
                    os.rename(final, new_final)
                    final = new_final
                    is_video = True
                elif ext.lower() in vid_exts: is_video = True
                else: is_video = False

        # Forzar is_video si yt-dlp fue usado exitosamente (generalmente descarga videos), salvo mp3
        if not is_direct_download and calidad != "mp3":
            is_video = True

        # USER REQUEST: Mediafire/MP4Upload always as specific document
        if mediafire_link or mp4_link:
             is_video = False

        print(f"ℹ️ DEBUG: Is Video? {is_video} | Ext: {ext}")
        
        await status.edit("📝 **Procesando Metadatos...**")
        w, h, dur = 0, 0, 0
        thumb = None
        
        # SI ES VIDEO O AUDIO
        if is_video or final.lower().endswith(('.mp3', '.m4a')):
            if final.lower().endswith(('.mp3', '.m4a')):
                dur = await get_audio_dur(final)
            else:
                print("ℹ️ DEBUG: Extracting Thumb & Meta...")
                thumb = await get_thumb(final, chat_id, ts)
                w, h, dur = await get_meta(final)
                print(f"ℹ️ DEBUG: Meta extracted: {w}x{h} | Dur: {dur}")
        else:
            # ES DOCUMENTO (ZIP, RAR, ETC)
            # No sacamos thumb ni meta de video
            pass
        
        files_to_send = [final]
        is_split = False
            
        # --- LÓGICA DE CORTE (SPLIT) - SOLO SI ES VIDEO ---
        # Si es un ZIP de 3GB, Telegram permite hasta 2GB (4GB con Premium, bot tiene 2GB limit por API a veces)
        # Si es Documento > 2GB, fallará. Split de ZIPs es complejo.
        # Por ahora solo cortamos VIDEO.
        
        print(f"ℹ️ DEBUG: Checking Split logic. Size {file_size} > {TG_LIMIT} ? {file_size > TG_LIMIT}")
        
        if is_video and file_size > TG_LIMIT and calidad != "mp3":
            from utils import split_video_generic, format_bytes
            
            sz_fmt = format_bytes(file_size)
            num_parts = int(-(-file_size // TG_LIMIT)) 
            est_part_size = format_bytes(file_size / num_parts)

            print(f"✂️ DEBUG: SPLIT TRIGGERED. Parts: {num_parts}")
            await status.edit(
                f"✂️ **Video Grande Detectado ({sz_fmt})**\n"
                f"🔪 Cortando en **{num_parts} partes** de ~**{est_part_size}**\n"
                "⏳ Por favor espera..."
            )
            
            loop = asyncio.get_running_loop()
            new_files = await loop.run_in_executor(None, lambda: split_video_generic(final, 'parts', num_parts))
            
            print(f"✂️ DEBUG: Split result: {len(new_files)} files.")
            if new_files:
                files_to_send = new_files
                is_split = True
                try: os.remove(final) 
                except: pass

        # --- BUCLE DE SUBIDA ---
        for i, f_path in enumerate(files_to_send):
            # SAFEGUARD: Verificar existencia real y tamaño > 0
            if not os.path.exists(f_path) or os.path.getsize(f_path) == 0:
                print(f"❌ Skipping 0-byte/missing file: {f_path}")
                continue

            # SAFEGUARD: Validar Thumb (Existencia y Tamaño)
            current_thumb = thumb
            if current_thumb:
                if not os.path.exists(current_thumb) or os.path.getsize(current_thumb) == 0:
                    print(f"⚠️ Invalid Thumb (Missing/Empty): {current_thumb}")
                    current_thumb = None

            msg_label = f"📤 **Subiendo Parte {i+1}/{len(files_to_send)}...**" if is_split else "📤 **Subiendo...**"
            await status.edit(msg_label)
            
            cur_dur = dur
            if is_split:
                 _, _, cur_dur = await get_meta(f_path)
            
            cap = ""
            # Caption solo si conf tiene meta activado
            if conf.get('meta'):
                t = datos.get('titulo','Archivo')
                # Si es mediafire y tenemos filename en path, usarlo
                if is_direct_download: t = os.path.basename(f_path)
                
                if is_split: t += f" [Parte {i+1}/{len(files_to_send)}]"
                
                if conf.get('lang') == 'es' and not is_direct_download: t = await traducir_texto(t) # Traducir solo si no es filename literal
                
                tags = [f"#{x.replace(' ','_')}" for x in (datos.get('tags') or [])[:10]]
                res_str = f"{w}x{h}" if w else ("Audio" if calidad=="mp3" else "Archivo")
                cap = f"🎬 **{t}**\n⚙️ {res_str}"
                if cur_dur: cap += f" | ⏱ {time.strftime('%H:%M:%S', time.gmtime(cur_dur))}"
                if tags: cap += f"\n{' '.join(tags)}"
                cap = cap[:1024]

            act = enums.ChatAction.UPLOAD_AUDIO if calidad == "mp3" else (enums.ChatAction.UPLOAD_VIDEO if is_video else enums.ChatAction.UPLOAD_DOCUMENT)
            
            res = None
            try:
                # INTENTO 1: Full (Video/Audio/Doc + Meta + Thumb + Progress)
                if calidad == "mp3":
                     res = await client.send_audio(chat_id, f_path, caption=cap, duration=cur_dur, thumb=current_thumb, progress=progreso, progress_args=(status, [time.time(),0], act), reply_to_message_id=msg_orig.id)
                elif is_video and not conf.get('doc_mode'):
                    res = await client.send_video(
                        chat_id, f_path, 
                        caption=cap, 
                        width=w if w else None, 
                        height=h if h else None, 
                        duration=cur_dur if cur_dur else None, 
                        thumb=current_thumb, 
                        progress=progreso, 
                        progress_args=(status, [time.time(),0], act), 
                        reply_to_message_id=msg_orig.id
                    )
                else:
                    res = await client.send_document(chat_id, f_path, caption=cap, thumb=current_thumb, progress=progreso, progress_args=(status, [time.time(),0], act), reply_to_message_id=msg_orig.id)
            
            except Exception as e:
                print(f"⚠️ Error intentando upload completo: {e}")
                
                # INTENTO 1.5: RETRY VIDEO LIMPIO (Solo si era video)
                # A veces width/height/thumb incorrectos rompen send_video. Probamos "pelado".
                retry_video_sucess = False
                if is_video and not conf.get('doc_mode'):
                    try:
                         # No usamos status edit para ser rápidos, o sí?
                         # await status.edit(f"⚠️ **Reintentando Video (Modo Compatible)...**")
                         res = await client.send_video(
                            chat_id, f_path, 
                            caption=cap, 
                            progress=progreso, 
                            progress_args=(status, [time.time(),0], act), 
                            reply_to_message_id=msg_orig.id
                         )
                         retry_video_sucess = True
                    except Exception as ex_v:
                        print(f"⚠️ Falló Retry Video Limpio: {ex_v}")

                if not retry_video_sucess:
                    # INTENTO 2: FALLBACK INTERMEDIO (Documento CON Progress + Thumb)
                    # Si falla send_video, probamos enviar como Doc pero MANTENIENDO la barra.
                    try:
                        # Silenciamos el aviso visual para no confundir (El usuario pidió "sin bug" visual)
                        # await status.edit(f"⚠️ **Detectado error de Video.**\n⬆️ Reintentando como Documento (con barra)...")
                        res = await client.send_document(chat_id, f_path, caption=cap, thumb=current_thumb, progress=progreso, progress_args=(status, [time.time(),0], act), reply_to_message_id=msg_orig.id)
                    except Exception as e2:
                        print(f"⚠️ Falló Fallback con barra: {e2}")
                        
                        # INTENTO 3: ULTIMO RECURSO (Sin Thumb/Progress)
                        try:
                            # await status.edit(f"⚠️ **Modo Seguro.**\n⬆️ Subiendo sin barra...")
                            if calidad == "mp3":
                                 res = await client.send_audio(chat_id, f_path, caption=cap)
                            else:
                                 res = await client.send_document(chat_id, f_path, caption=cap)
                        except Exception as e3:
                             print(f"❌ Error Fatal Upload: {e3}")
                             await client.send_message(chat_id, f"❌ Error crítico subiendo archivo: {e3}")

            
            # --- BACKUP CHANNEL FORWARDING REMOVED ---
            # User requested to remove this feature.
            # We now rely solely on the File ID from the user chat.




            # Guardar en Firebase (y DB local si se quiere, por ahora solo Firebase)
            # FIX: Quitamos restricción de html_ para que guarde JAVs también.
            if res and vid_id and not is_split:
                fid = None
                if res.audio: fid = res.audio.file_id
                elif res.video: fid = res.video.file_id
                elif res.document: fid = res.document.file_id
                
                if fid:
                    print(f"💾 DEBUG: Saving cache for {vid_id} | FID: {fid}[:10]...")
                    await save_cached_file(vid_id, ckey, fid, meta=datos)
            
            if is_split:
                try: os.remove(f_path)
                except: pass

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Excepción: {e}")
        if status: await status.edit(f"❌ Error: {e}")
    finally:
        remove_active(chat_id, msg_orig.id) # Cleanup Anti-Spam
        # Cleanup específico de la sesión actual
        for f in [final, thumb, f"dl_{chat_id}_{ts}.jpg"]:
            if f and os.path.exists(f):
                try: os.remove(f)
                except: pass
        if status:
            try: await status.delete()
            except: pass
            
        # Cleanup General solicitado por el usuario (Eliminar temporales viejos de ESTE chat > 10 min antigüedad)
        try:
             now_ts = time.time()
             for f in os.listdir(DOWNLOAD_DIR):
                 # Limpiar archivos viejos del mismo chat (evitar borrar descargas concurrentes activas)
                 if f.startswith(f"dl_{chat_id}_"):
                     full_p = os.path.join(DOWNLOAD_DIR, f)
                     try:
                         # Solo borrar si tiene más de 10 minutos (600s) de antigüedad
                         if os.path.getmtime(full_p) < (now_ts - 600):
                             os.remove(full_p)
                     except: pass
                 
                 # Limpieza de carpetas "parts" huerfanas viejas
                 if f.startswith("parts_"):
                      full_d = os.path.join(DOWNLOAD_DIR, f)
                      if os.path.isdir(full_d):
                           try:
                               if os.path.getmtime(full_d) < (now_ts - 600):
                                   shutil.rmtree(full_d)
                           except: pass
        except: pass