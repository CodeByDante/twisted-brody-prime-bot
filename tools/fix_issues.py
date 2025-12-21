import os
import shutil

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SESSION_FILE = os.path.join(DATA_DIR, "twisted_brody_session.session")
JOURNAL_FILE = os.path.join(DATA_DIR, "twisted_brody_session.session-journal")
FIREBASE_FILE = os.path.join(BASE_DIR, "firebase_credentials.json")

def fix_session():
    print("--- Fixing Session Files ---")
    if os.path.exists(SESSION_FILE):
        try:
            os.remove(SESSION_FILE)
            print(f"✅ Deleted: {SESSION_FILE}")
        except Exception as e:
            print(f"❌ Error deleting session: {e}")
    else:
        print(f"ℹ️ Session file not found: {SESSION_FILE}")

    if os.path.exists(JOURNAL_FILE):
        try:
            os.remove(JOURNAL_FILE)
            print(f"✅ Deleted: {JOURNAL_FILE}")
        except Exception as e:
            print(f"❌ Error deleting journal: {e}")
    else:
        print(f"ℹ️ Journal file not found: {JOURNAL_FILE}")

def fix_firebase_encoding():
    print("\n--- Fixing Firebase Credentials Encoding ---")
    if not os.path.exists(FIREBASE_FILE):
        print(f"❌ File not found: {FIREBASE_FILE}")
        return

    content = None
    # Try reading with different encodings
    encodings = ['utf-16', 'utf-16-le', 'utf-16-be', 'utf-8-sig', 'cp1252']
    
    for enc in encodings:
        try:
            with open(FIREBASE_FILE, 'r', encoding=enc) as f:
                content = f.read()
            print(f"✅ Successfully read file using encoding: {enc}")
            break
        except Exception:
            continue
    
    if content:
        # Check if it looks like JSON
        if content.strip().startswith('{'):
            try:
                # Save back as UTF-8
                with open(FIREBASE_FILE, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"✅ Converted {FIREBASE_FILE} to UTF-8")
            except Exception as e:
                print(f"❌ Error saving file: {e}")
        else:
             print("⚠️ File content does not look like JSON. Skipping save.")
    else:
        print("❌ Could not read file with standard encodings. It might be binary or corrupted.")

if __name__ == "__main__":
    fix_session()
    fix_firebase_encoding()
