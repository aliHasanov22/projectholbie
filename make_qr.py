import sqlite3
import qrcode
from pathlib import Path

# CHANGE THIS to your real address (ngrok or local IP)
BASE_URL = "https://spectrochemical-noncognizantly-harlow.ngrok-free.dev "  # e.g. https://abcd.ngrok.io

DB_PATH = Path("room.db")
OUTPUT_DIR = Path("qr_codes")
OUTPUT_DIR.mkdir(exist_ok=True)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

rows = conn.execute("SELECT id, token FROM computers").fetchall()
conn.close()

print(f"Generating {len(rows)} QR codes...")

for row in rows:
    pc_id = row["id"]
    token = row["token"]

    url = f"{BASE_URL}/scan/{pc_id}?token={token}"

    img = qrcode.make(url)
    img.save(OUTPUT_DIR / f"qr_{pc_id}.png")

print("✅ Done. QR codes saved in /qr_codes/")

https://spectrochemical-noncognizantly-harlow.ngrok-free.dev 
