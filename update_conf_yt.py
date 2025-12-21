
import os
import re

target = "config.py"
if not os.path.exists(target):
    print("config.py not found")
    exit(1)

with open(target, "r", encoding="utf-8") as f:
    content = f.read()

# Pattern: find the tiktok entry (which we added previously) or dropbox if tiktok failed, and insert youtube after
# Ideally looking for the end of the dict which is "}"
pattern = r'(    "tiktok": os\.path\.join\(COOKIES_DIR, "cookies_tiktok\.txt"\),\s*})'
replacement = r'    "tiktok": os.path.join(COOKIES_DIR, "cookies_tiktok.txt"),\n    "youtube": os.path.join(COOKIES_DIR, "cookies_youtube.txt"),\n    "youtu.be": os.path.join(COOKIES_DIR, "cookies_youtube.txt"),\n}'

# Try matching the new tiktok entry first
new_content, count = re.subn(pattern, replacement, content)

if count == 0:
    # If looking for tiktok failed (maybe previous step failed?), try matching the end brace broadly
    # But be careful not to match other dicts. COOKIE_MAP is usually near the top.
    # Let's try matching dropbox if tiktok isn't there
    pattern_backup = r'(    "dropbox\.com": os\.path\.join\(COOKIES_DIR, "dropbox_cookies\.txt"\),\s*})'
    replacement_backup = r'    "dropbox.com": os.path.join(COOKIES_DIR, "dropbox_cookies.txt"),\n    "youtube": os.path.join(COOKIES_DIR, "cookies_youtube.txt"),\n    "youtu.be": os.path.join(COOKIES_DIR, "cookies_youtube.txt"),\n}'
    new_content, count = re.subn(pattern_backup, replacement_backup, content)

if count > 0:
    with open(target, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Updated successfully")
else:
    print("Pattern not found due to previous state mismatch.")
