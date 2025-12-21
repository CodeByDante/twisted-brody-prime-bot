import os
import json
import time
import asyncio
import subprocess
from pyrogram import enums
from pyrogram.errors import FloodWait
from config import HAS_FFMPEG

# --- FUNCIONES DE MEDIA (FFMPEG) ---

async def get_thumb(path, cid, ts):
    out = f"t_{cid}_{ts}.jpg"
    log_file = "media_debug.log"
    if HAS_FFMPEG:
        try:
            # Thumbnail con corrección de Aspect Ratio (Square Pixels)
            # Primero intenta en el segundo 2
            cmd = ["ffmpeg", "-i", path, "-ss", "00:00:02", "-vf", "scale=iw*sar:ih", "-vframes", "1", out, "-y"]
            with open(log_file, "a", encoding="utf-8") as f: f.write(f"Thumb Cmd 1: {cmd}\n")
            
            process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            await process.wait()
            
            # Si falla (video muy corto), intenta al principio
            if not os.path.exists(out):
                cmd = ["ffmpeg", "-i", path, "-ss", "00:00:00", "-vf", "scale=iw*sar:ih", "-vframes", "1", out, "-y"]
                with open(log_file, "a", encoding="utf-8") as f: f.write(f"Thumb Cmd 2: {cmd}\n")
                process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                await process.wait()

            if os.path.exists(out): 
                with open(log_file, "a", encoding="utf-8") as f: f.write(f"Thumb created: {out} ({os.path.getsize(out)} bytes)\n")
                return out
            else:
                with open(log_file, "a", encoding="utf-8") as f: f.write(f"Thumb FAILED for {path}\n")
        except Exception as e:
            print(f"Error thumb: {e}")
            with open(log_file, "a", encoding="utf-8") as f: f.write(f"Thumb Error: {e}\n")
    return None


async def get_meta(path):
    log_file = "media_debug.log"
    if not HAS_FFMPEG: return 0, 0, 0
    try:
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0", 
            "-show_entries", "stream=width,height,duration,sample_aspect_ratio:stream_tags=rotate", 
            "-of", "json", path
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd, 
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, _ = await process.communicate()
        
        d = json.loads(stdout)
        s = d['streams'][0]
        w = int(s.get('width', 0))
        h = int(s.get('height', 0))
        dur = int(float(s.get('duration', 0)))
        
        with open(log_file, "a", encoding="utf-8") as f: f.write(f"Raw Meta: w={w}, h={h}, sar={s.get('sample_aspect_ratio')}\n")

        # Aspect Ratio Correction
        sar = s.get('sample_aspect_ratio', '1:1')
        if sar != '1:1' and sar != '0:1' and ':' in sar:
            try:
                num, den = map(int, sar.split(':'))
                if den > 0:
                     # Calculate Display Width
                     w = int(w * (num / den))
                     with open(log_file, "a", encoding="utf-8") as f: f.write(f"Corrected w={w}\n")
            except: pass
        
        # Check rotation
        tags = s.get('tags', {})
        rot = tags.get('rotate')
        if rot:
            rot = int(rot)
            if abs(rot) in [90, 270]:
                w, h = h, w
        
        with open(log_file, "a", encoding="utf-8") as f: f.write(f"Final Meta: w={w}, h={h}\n")
        return w, h, dur
    except Exception as e:
        with open(log_file, "a", encoding="utf-8") as f: f.write(f"Meta Error: {e}\n")
        return 0, 0, 0

async def get_audio_dur(path):
    try:
        cmd = [
            "ffprobe", "-v", "error", 
            "-show_entries", "format=duration", 
            "-of", "json", path
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE
        )
        stdout, _ = await process.communicate()
        return int(float(json.loads(stdout)['format']['duration']))
    except:
        return 0

async def progreso(cur, tot, msg, times, act):
    now = time.time()
    
    # SAFEGUARD: tot/cur can be None or 0
    safe_cur = int(cur) if cur else 0
    safe_tot = int(tot) if tot else 0
    
    if safe_tot == 0: return

    per = safe_cur * 100 / safe_tot
    
    # THROTTLING INTELIGENTE:
    # Solo actualizar si:
    # 1. Pasaron > 8 segundos (Time-based prevent FloodWait)
    # 2. O si el progreso cambió > 5% (Step-based)
    # 3. O si terminó (100%)
    
    last_time = times[0]
    last_per = times[1]
    
    if (now - last_time) > 8 or (per - last_per) > 5 or safe_cur == safe_tot:
        times[0] = now
        times[1] = per
        
        try:
            from utils import render_bar
            
            mb_cur = safe_cur / (1024 * 1024)
            mb_tot = safe_tot / (1024 * 1024)
            bar = render_bar(safe_cur, safe_tot)
            
            txt = f"**{act} {per:.1f}%**\n📦 {mb_cur:.1f}/{mb_tot:.1f} MB"
            
            await msg.edit_text(txt)
            
        except FloodWait as e:
            # Si Telegram nos dice "espera X segundos", NO crasheamos, solo esperamos y saltamos este update visual.
            # print(f"⏳ FloodWait en barra: {e.value}s")
            await asyncio.sleep(e.value)
        except Exception as e:
            # Error visual ignorado para no romper subida
            pass