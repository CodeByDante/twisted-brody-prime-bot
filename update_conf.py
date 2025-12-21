
import os
import re

target = "config.py"
if not os.path.exists(target):
    print("config.py not found")
    exit(1)

with open(target, "r", encoding="utf-8") as f:
    content = f.read()

# Pattern: find the dropbox entry and the closing brace of the dictionary
# We look for the line with dropbox, any following whitespace/newlines, and the closing brace.
# We want to insert the new keys before the closing brace.
pattern = r'("dropbox\.com":\s*os\.path\.join\(COOKIES_DIR,\s*"dropbox_cookies\.txt"\),)(\s*})'

# Replacement: specific formatting to match existing style
replacement = r'\1\n    "facebook": os.path.join(COOKIES_DIR, "cookies_facebook.txt"),\n    "fb.watch": os.path.join(COOKIES_DIR, "cookies_facebook.txt"),\n    "instagram": os.path.join(COOKIES_DIR, "cookies_instagram.txt"),\n    "tiktok": os.path.join(COOKIES_DIR, "cookies_tiktok.txt"),\2'

new_content, count = re.subn(pattern, replacement, content)

if count > 0:
    with open(target, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Updated successfully")
else:
    print("Pattern not found. Content dump near expected area:")
    start_idx = content.find("dropbox")
    if start_idx != -1:
        print(content[start_idx:start_idx+200])
    else:
        print("Dropbox entry not found.")
