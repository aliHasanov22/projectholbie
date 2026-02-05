from flask import Flask, jsonify, render_template, request
import sqlite3
from pathlib import Path
from flask import abort
import math
from flask import session, redirect, url_for, render_template, request, jsonify



app = Flask(__name__)
DB_PATH = Path("room.db")

BUILDING_LAT = 40.4093   # <- replace with your real location
BUILDING_LON = 49.8671   # <- replace with your real location
RADIUS_METERS = 40
MAX_ACCURACY_METERS = 30  # reject bad GPS readings

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


def init_db():
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS computers (
            id TEXT PRIMARY KEY,
            is_busy INTEGER NOT NULL DEFAULT 0,
            user_name TEXT DEFAULT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            token TEXT UNIQUE
        )
        """
    )
    conn.commit()

    # Ensure all PCs in layout exist in DB
    all_pcs = []
    for side in ("left", "right"):
        for row in ROOM_LAYOUT[side]:
            for pc in row:
                if pc:
                    all_pcs.append(pc)

    for pc_id in all_pcs:
        conn.execute(
            "INSERT OR IGNORE INTO computers (id, is_busy, user_name) VALUES (?, 0, NULL)",
            (pc_id,),
        )
    conn.commit()
    conn.close()

def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000  # meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

@app.route("/")
def index():
    return render_template("index.html", layout=ROOM_LAYOUT)


@app.route("/api/status", methods=["GET"])
def api_status():
    conn = get_db()
    rows = conn.execute("SELECT id, is_busy, user_name FROM computers").fetchall()
    conn.close()
    data = {r["id"]: {"is_busy": bool(r["is_busy"]), "user_name": r["user_name"]} for r in rows}
    return jsonify(data)


@app.route("/api/toggle", methods=["POST"])
def api_toggle():
    payload = request.get_json(force=True)
    pc_id = payload.get("pc_id")
    user_name = payload.get("user_name")  # optional

    if not pc_id:
        return jsonify({"error": "pc_id required"}), 400

    conn = get_db()
    row = conn.execute("SELECT is_busy FROM computers WHERE id=?", (pc_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "unknown pc_id"}), 404

    new_busy = 0 if row["is_busy"] else 1

    # If busy, store user_name; if freeing, clear it
    if new_busy == 1:
        conn.execute(
            "UPDATE computers SET is_busy=1, user_name=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (user_name or None, pc_id),
        )
    else:
        conn.execute(
            "UPDATE computers SET is_busy=0, user_name=NULL, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (pc_id,),
        )

    conn.commit()
    conn.close()
    return jsonify({"ok": True, "pc_id": pc_id, "is_busy": bool(new_busy)})
#new updates
@app.route("/pc/<pc_id>")
def pc_page(pc_id):
    token = request.args.get("token")
    if not token:
        abort(403)

    conn = get_db()
    row = conn.execute(
        "SELECT id, is_busy, user_name FROM computers WHERE id=? AND token=?",
        (pc_id, token)
    ).fetchone()
    conn.close()

    if not row:
        abort(403)

    return render_template("pc.html", pc_id=pc_id, is_busy=bool(row["is_busy"]), user_name=row["user_name"])

@app.route("/api/pc_action", methods=["POST"])
def pc_action():
    data = request.get_json(force=True)
    pc_id = data["pc_id"]
    token = data["token"]
    action = data["action"]  # "start" or "finish"
    user_name = data.get("user_name")

    conn = get_db()
    row = conn.execute("SELECT id FROM computers WHERE id=? AND token=?", (pc_id, token)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "forbidden"}), 403

    if action == "start":
        conn.execute("UPDATE computers SET is_busy=1, user_name=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (user_name or None, pc_id))
    elif action == "finish":
        conn.execute("UPDATE computers SET is_busy=0, user_name=NULL, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (pc_id,))
    else:
        conn.close()
        return jsonify({"error": "bad action"}), 400

    conn.commit()
    conn.close()
    return jsonify({"ok": True})



@app.route("/api/set", methods=["POST"])
def api_set():
    payload = request.get_json(force=True)
    pc_id = payload.get("pc_id")
    is_busy = payload.get("is_busy")
    user_name = payload.get("user_name")

    if pc_id is None or is_busy is None:
        return jsonify({"error": "pc_id and is_busy required"}), 400

    conn = get_db()
    if int(is_busy) == 1:
        conn.execute(
            "UPDATE computers SET is_busy=1, user_name=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (user_name or None, pc_id),
        )
    else:
        conn.execute(
            "UPDATE computers SET is_busy=0, user_name=NULL, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (pc_id,),
        )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/scan/<pc_id>")
def scan(pc_id):
    token = request.args.get("token")
    if not token:
        return "Forbidden", 403

    # Require student identity (simple session name; replace with real login later)
    if not session.get("student_name"):
        return redirect(url_for("login", next=request.full_path))

    return render_template("scan.html", pc_id=pc_id, token=token)


@app.route("/api/verify_scan", methods=["POST"])
def verify_scan():
    data = request.get_json(force=True)
    pc_id = data.get("pc_id")
    token = data.get("token")
    lat = data.get("lat")
    lon = data.get("lon")
    accuracy = data.get("accuracy")

    student_name = session.get("student_name")
    if not student_name:
        return jsonify({"ok": False, "error": "not_logged_in"}), 401

    # basic validations
    if not pc_id or not token or lat is None or lon is None or accuracy is None:
        return jsonify({"ok": False, "error": "missing_fields"}), 400

    try:
        lat = float(lat); lon = float(lon); accuracy = float(accuracy)
    except ValueError:
        return jsonify({"ok": False, "error": "bad_location"}), 400

    # accuracy gate (prevents “I’m somewhere far but accuracy says 1000m”)
    if accuracy > MAX_ACCURACY_METERS:
        return jsonify({"ok": False, "error": "low_accuracy", "accuracy": accuracy}), 403

    # distance check
    dist = haversine_m(lat, lon, BUILDING_LAT, BUILDING_LON)
    if dist > RADIUS_METERS:
        return jsonify({"ok": False, "error": "too_far", "distance_m": round(dist, 1)}), 403

    # token check + mark busy
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


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
