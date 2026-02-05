from flask import Flask, jsonify, render_template, request
import sqlite3
from pathlib import Path
from flask import abort
import math
from flask import session, redirect, url_for, render_template, request, jsonify
import os
import hashlib
import hmac
import ipaddress


app = Flask(__name__)
app.secret_key = "CHANGE_THIS_TO_A_RANDOM_SECRET"
DB_PATH = Path("room.db")
# ================== CAMPUS NETWORK RESTRICTION ==================

# Allow only private (campus) networks
ALLOWED_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
]

def get_client_ip():
    # If behind proxy, first IP in X-Forwarded-For
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr

@app.before_request
def require_campus_wifi():
    ip_str = get_client_ip()
     if ip_str in ("127.0.0.1", "::1"):
        return  # allow localhost

    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return "Invalid IP", 400

    if not any(ip in net for net in ALLOWED_NETS):
        return (
            "❌ This system works only on Holberton - Students Wi-Fi.",
            403
        )

# ===============================================================

BUILDING_LAT = 40.40663934042372   # <- replace with your real location
BUILDING_LON = 49.848206791133954   # <- replace with your real location
RADIUS_METERS = 50
MAX_ACCURACY_METERS = 40  # reject bad GPS readings

# ====== CONFIG: define your room layout here ======
# Each "block" is a list of rows; each row is a list of pc IDs (or None for empty space).
ROOM_LAYOUT = {
    "left": [
        ["L1", "L2", "L3", "L4", "L5"],
      
        ["L6", "L7", "L8", "L9", None],
        ["L10", "L11", "L12", "L13", "L14"],
      
        ["L15", "L16", "L17", "L18", None],
        ["L19", "L20", "L21", "L22", "L23"],
      
        ["L24", "L25", "L26", "L27", "L28"],
        ["L29", "L30", "L31", "L32", None],
      
        ["L33", "L34", "L35", "L36", None],
        ["L37", "L38", "L39", "L40", None]
    ],
    "right": [
        ["R1", "R2", "R3", "R4", "R5"],
        ["R6", "R7", "R8", "R9", "R10"],
        ["R11", "R12", "R13", "R14", "R15"],
        ["R16", "R17", "R18", "R19", "R20"],
        ["R21", "R22", "R23", "R24", "R25"],
        ["R26", "R27", "R28", "R29", "R30"],
        ["R31", "R32", "R33", "R34", "R35"],
        ["R36", "R37", "R38", "R39", "R40"],
        ["R41", "R42", "R43", "R44", "R45"]
    ]
}
# ================================================


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dl/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    """Returns (salt_hex, hash_hex). Uses PBKDF2-HMAC-SHA256."""
    if salt is None:
        salt = os.urandom(16)
    pwd = password.encode("utf-8")
    dk = hashlib.pbkdf2_hmac("sha256", pwd, salt, 200_000)
    return salt.hex(), dk.hex()


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    salt = bytes.fromhex(salt_hex)
    _, computed = hash_password(password, salt=salt)
    return hmac.compare_digest(computed, hash_hex)


def init_db():
    conn = get_db()

    # Users table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            username TEXT NOT NULL UNIQUE,
            salt_hex TEXT NOT NULL,
            hash_hex TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Computers table (token required for QR security)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS computers (
            id TEXT PRIMARY KEY,
            token TEXT NOT NULL UNIQUE,
            is_busy INTEGER NOT NULL DEFAULT 0,
            user_name TEXT DEFAULT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            busy_user_id INTEGER DEFAULT NULL,
            last_seen TEXT DEFAULT NULL

        )
    """)
    conn.commit()

    # Ensure PCs exist with token
    all_pcs = []
    for side in ("left", "right"):
        for row in ROOM_LAYOUT.get(side, []):
            for pc in row:
                if pc:
                    all_pcs.append(pc)

    for pc_id in all_pcs:
        # create token if missing
        token = os.urandom(12).hex()
        conn.execute(
            "INSERT OR IGNORE INTO computers (id, token, is_busy, user_name) VALUES (?, ?, 0, NULL)",
            (pc_id, token)
        )
        # if exists but token empty (unlikely), keep it safe
        conn.execute(
            "UPDATE computers SET token=COALESCE(NULLIF(token,''), ?) WHERE id=?",
            (token, pc_id)
        )

    conn.commit()
    conn.close()


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    conn = get_db()
    user = conn.execute("SELECT id, full_name, username FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    return user


@app.route("/")
def index():
    return render_template("index.html", layout=ROOM_LAYOUT, user=current_user())


# ---------- AUTH ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        if len(full_name) < 2:
            return render_template("register.html", error="Full name is too short.")
        if len(username) < 3 or " " in username:
            return render_template("register.html", error="Username must be at least 3 chars, no spaces.")
        if len(password) < 6:
            return render_template("register.html", error="Password must be at least 6 chars.")
        if password != password2:
            return render_template("register.html", error="Passwords do not match.")

        salt_hex, hash_hex = hash_password(password)

        try:
            conn = get_db()
            conn.execute(
                "INSERT INTO users (full_name, username, salt_hex, hash_hex) VALUES (?, ?, ?, ?)",
                (full_name, username, salt_hex, hash_hex),
            )
            conn.commit()
            user = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            conn.close()

            session["user_id"] = user["id"]
            session["student_name"] = full_name  # used for marking PC
            return redirect(url_for("index"))
        except sqlite3.IntegrityError:
            return render_template("register.html", error="Username already exists.")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    next_url = request.args.get("next") or url_for("index")

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()
        user = conn.execute(
            "SELECT id, full_name, username, salt_hex, hash_hex FROM users WHERE username=?",
            (username,),
        ).fetchone()
        conn.close()

        if not user or not verify_password(password, user["salt_hex"], user["hash_hex"]):
            return render_template("login.html", error="Wrong username or password.", next_url=next_url)

        session["user_id"] = user["id"]
        session["student_name"] = user["full_name"]
        return redirect(next_url)

    return render_template("login.html", next_url=next_url)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ---------- API: STATUS ----------
@app.route("/api/status")
def api_status():
    conn = get_db()
    rows = conn.execute("SELECT id, is_busy, user_name FROM computers").fetchall()
    conn.close()
    return jsonify({r["id"]: {"is_busy": bool(r["is_busy"]), "user_name": r["user_name"]} for r in rows})


# ---------- QR SCAN (auto mark busy with GPS check) ----------
@app.route("/scan/<pc_id>")
def scan(pc_id):
    token = request.args.get("token")
    if not token:
        return "Forbidden", 403

    if not session.get("user_id"):
        return redirect(url_for("login", next=request.full_path))

    return render_template("scan.html", pc_id=pc_id, token=token)


@app.route("/api/verify_scan", methods=["POST"])
def verify_scan():
    if not session.get("user_id"):
        return jsonify({"ok": False, "error": "not_logged_in"}), 401

    data = request.get_json(force=True)
    pc_id = data.get("pc_id")
    token = data.get("token")
    lat = data.get("lat")
    lon = data.get("lon")
    accuracy = data.get("accuracy")

    if not pc_id or not token or lat is None or lon is None or accuracy is None:
        return jsonify({"ok": False, "error": "missing_fields"}), 400

    try:
        lat = float(lat); lon = float(lon); accuracy = float(accuracy)
    except ValueError:
        return jsonify({"ok": False, "error": "bad_location"}), 400

    if accuracy > MAX_ACCURACY_METERS:
        return jsonify({"ok": False, "error": "low_accuracy", "accuracy": accuracy}), 403

    dist = haversine_m(lat, lon, BUILDING_LAT, BUILDING_LON)
    if dist > RADIUS_METERS:
        return jsonify({"ok": False, "error": "too_far", "distance_m": round(dist, 1)}), 403

    student_name = session.get("student_name") or "Student"

    conn = get_db()
    row = conn.execute(
        "SELECT id, is_busy FROM computers WHERE id=? AND token=?",
        (pc_id, token)
    ).fetchone()

    if not row:
        conn.close()
        return jsonify({"ok": False, "error": "forbidden"}), 403

    if row["is_busy"] == 0:
        conn.execute(
            "UPDATE computers SET is_busy=1, user_name=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (student_name, pc_id)
        )
        conn.commit()

    conn.close()
    return jsonify({"ok": True, "pc_id": pc_id, "distance_m": round(dist, 1)})

@app.route("/api/pc_action", methods=["POST"])
def pc_action():
    cleanup_stale_sessions()

    if not session.get("user_id"):
        return jsonify({"ok": False, "error": "not_logged_in"}), 401

    data = request.get_json(force=True)
    pc_id = data.get("pc_id")
    token = data.get("token")
    action = data.get("action")  # "start" or "finish"
    lat = data.get("lat")
    lon = data.get("lon")
    accuracy = data.get("accuracy")

    if not pc_id or not token or action not in ("start", "finish") or lat is None or lon is None or accuracy is None:
        return jsonify({"ok": False, "error": "missing_fields"}), 400

    lat = float(lat); lon = float(lon); accuracy = float(accuracy)

    if accuracy > MAX_ACCURACY_METERS:
        return jsonify({"ok": False, "error": "low_accuracy", "accuracy": accuracy}), 403

    dist = haversine_m(lat, lon, BUILDING_LAT, BUILDING_LON)
    if dist > RADIUS_METERS:
        return jsonify({"ok": False, "error": "too_far", "distance_m": round(dist, 1)}), 403

    user_id = int(session["user_id"])
    student_name = session.get("student_name") or "Student"

    conn = get_db()
    row = conn.execute(
        "SELECT is_busy, busy_user_id FROM computers WHERE id=? AND token=?",
        (pc_id, token)
    ).fetchone()

    if not row:
        conn.close()
        return jsonify({"ok": False, "error": "forbidden"}), 403

    # START
    if action == "start":
        if row["is_busy"] == 1:
            conn.close()
            return jsonify({"ok": False, "error": "already_busy"}), 409

        conn.execute("""
            UPDATE computers
            SET is_busy=1, busy_user_id=?, user_name=?, last_seen=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        """, (user_id, student_name, pc_id))
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "action": "started", "distance_m": round(dist, 1)})

    # FINISH
    if action == "finish":
        if row["is_busy"] == 0:
            conn.close()
            return jsonify({"ok": False, "error": "already_free"}), 409

        if row["busy_user_id"] != user_id:
            conn.close()
            return jsonify({"ok": False, "error": "not_owner"}), 403

        conn.execute("""
            UPDATE computers
            SET is_busy=0, busy_user_id=NULL, user_name=NULL, last_seen=NULL, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        """, (pc_id,))
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "action": "stopped", "distance_m": round(dist, 1)})

@app.route("/api/heartbeat", methods=["POST"])
def heartbeat():
    if not session.get("user_id"):
        return jsonify({"ok": False, "error": "not_logged_in"}), 401

    data = request.get_json(force=True)
    pc_id = data.get("pc_id")
    token = data.get("token")
    if not pc_id or not token:
        return jsonify({"ok": False, "error": "missing_fields"}), 400

    user_id = int(session["user_id"])

    conn = get_db()
    row = conn.execute(
        "SELECT is_busy, busy_user_id FROM computers WHERE id=? AND token=?",
        (pc_id, token)
    ).fetchone()

    if row and row["is_busy"] == 1 and row["busy_user_id"] == user_id:
        conn.execute("UPDATE computers SET last_seen=CURRENT_TIMESTAMP WHERE id=?", (pc_id,))
        conn.commit()

    conn.close()
    return jsonify({"ok": True})


if __name__ == "__main__":
    init_db()
    # IMPORTANT for phones on same WiFi:
    app.run(host="0.0.0.0", port=5000, debug=True)
