import urllib.request
import zipfile
import os
import shutil

url = "https://github.com/nilaoda/N_m3u8DL-RE/releases/download/v0.5.0-beta/N_m3u8DL-RE_v0.5.0-beta_win-x64_20251027.zip"
print(f"Downloading fro {url}...")
try:
    urllib.request.urlretrieve(url, "tool.zip")
    print("Extracting...")
    with zipfile.ZipFile("tool.zip", 'r') as zip_ref:
        zip_ref.extractall("temp_tool")

    # Find exe
    found = False
    for root, dirs, files in os.walk("temp_tool"):
        for file in files:
            if "N_m3u8DL-RE" in file and file.endswith(".exe"):
                shutil.move(os.path.join(root, file), "N_m3u8DL-RE.exe")
                print(f"Movido {file} a tools/")
                found = True

    if not found:
        print("No se encontró el .exe en el zip")

    # Clean
    if os.path.exists("tool.zip"): os.remove("tool.zip")
    if os.path.exists("temp_tool"): shutil.rmtree("temp_tool")
    print("Done")
except Exception as e:
    print(f"Error: {e}")
