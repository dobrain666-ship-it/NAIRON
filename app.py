import os, json, urllib.request, urllib.parse, urllib.error
from flask import Flask, request, jsonify, send_from_directory, session

app = Flask(__name__, static_folder=".", static_url_path="")
app.secret_key = os.environ.get("SECRET_KEY", "nairon-mavia-secret-key-2026-change-me")

# ============ CONFIG PATH (Zeabur Volume) ============
# Agar /data folder exist karta hai (Zeabur pe Volume mount hua hai) toh wahan save karo
# Warna local pe config.json use karo
if os.path.isdir("/data"):
    CONFIG_FILE = "/data/config.json"
else:
    CONFIG_FILE = "config.json"

# ============ DEFAULT CONFIG ============
DEFAULT_CONFIG = {
    "token": "hsmdz_2026_secure_9xAk!kL",
    "api_base": "https://db-service-pk.vercel.app/api/search",
    "maintenance": False,
    "passwords": {
        "NAIRON": "NAIRON",
        "MAVIA":  "MAVIA",
        "ADMIN":  "2580"
    }
}

ADMIN_NAME = "ADMIN"

def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        with open(CONFIG_FILE, "r") as f:
            cfg = json.load(f)
        # ensure all keys exist (purane config ke liye)
        for k, v in DEFAULT_CONFIG.items():
            if k not in cfg:
                cfg[k] = v
        return cfg
    except Exception as e:
        print("config.json corrupt, resetting:", e)
        save_config(DEFAULT_CONFIG)
        return json.loads(json.dumps(DEFAULT_CONFIG))

def save_config(cfg):
    try:
        # folder exist karta hai?
        folder = os.path.dirname(CONFIG_FILE)
        if folder and not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print("save_config error:", e)

# ============ FRONTEND ============
@app.route("/")
def home():
    return send_from_directory(".", "index.html")

@app.route("/admin")
def admin_page():
    return send_from_directory(".", "admin.html")

# ============ AUTH ============
@app.route("/api/auth", methods=["POST"])
def auth():
    cfg = load_config()
    data = request.get_json(silent=True) or {}
    pw = str(data.get("password", "")).strip()

    matched = None
    for name, value in cfg["passwords"].items():
        if value == pw:
            matched = name
            break

    is_admin = (matched == ADMIN_NAME)
    maint = bool(cfg.get("maintenance", False))

    # ---------- MAINTENANCE ON ----------
    if maint:
        if is_admin:
            session["role"] = "admin"
            session["pw_name"] = matched
            return jsonify({"success": True, "role": "admin", "name": matched})
        else:
            return jsonify({"success": False, "maintenance": True, "error": "maintenance"}), 503

    # ---------- MAINTENANCE OFF ----------
    if not matched:
        return jsonify({"success": False, "error": "wrong key"}), 401

    role = "admin" if is_admin else "user"
    session["role"] = role
    session["pw_name"] = matched
    return jsonify({"success": True, "role": role, "name": matched})

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})

# ============ SEARCH (proxy) ============
@app.route("/api/search")
def search():
    cfg = load_config()
    role = session.get("role")
    maint = bool(cfg.get("maintenance", False))

    if maint and role != "admin":
        return jsonify({"success": False, "maintenance": True, "error": "maintenance"}), 503

    query = request.args.get("query", "")
    if not query:
        return jsonify({"success": False, "error": "query missing"}), 400

    url = f"{cfg['api_base']}?query={urllib.parse.quote(query)}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {cfg['token']}",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0"
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return jsonify(json.loads(r.read()))
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read())
        except Exception:
            body = {"success": False, "error": "upstream error"}
        return jsonify(body), e.code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ============ ADMIN ============
def admin_required():
    return session.get("role") == "admin"

@app.route("/api/admin/status")
def admin_status():
    if not admin_required():
        return jsonify({"success": False, "error": "unauthorized"}), 401
    cfg = load_config()
    return jsonify({
        "success": True,
        "token": cfg["token"],
        "api_base": cfg["api_base"],
        "maintenance": cfg["maintenance"],
        "passwords": list(cfg["passwords"].keys())
    })

@app.route("/api/admin/token", methods=["POST"])
def admin_token():
    if not admin_required():
        return jsonify({"success": False, "error": "unauthorized"}), 401
    cfg = load_config()
    data = request.get_json(silent=True) or {}
    new_token = data.get("token", "").strip()
    if not new_token:
        return jsonify({"success": False, "error": "empty token"}), 400
    cfg["token"] = new_token
    save_config(cfg)
    return jsonify({"success": True})

@app.route("/api/admin/api_base", methods=["POST"])
def admin_api_base():
    if not admin_required():
        return jsonify({"success": False, "error": "unauthorized"}), 401
    cfg = load_config()
    data = request.get_json(silent=True) or {}
    new_base = data.get("api_base", "").strip()
    if not new_base:
        return jsonify({"success": False, "error": "empty"}), 400
    cfg["api_base"] = new_base
    save_config(cfg)
    return jsonify({"success": True})

@app.route("/api/admin/maintenance", methods=["POST"])
def admin_maintenance():
    if not admin_required():
        return jsonify({"success": False, "error": "unauthorized"}), 401
    cfg = load_config()
    data = request.get_json(silent=True) or {}
    cfg["maintenance"] = bool(data.get("on", False))
    save_config(cfg)
    return jsonify({"success": True, "maintenance": cfg["maintenance"]})

@app.route("/api/admin/password", methods=["POST"])
def admin_add_password():
    if not admin_required():
        return jsonify({"success": False, "error": "unauthorized"}), 401
    cfg = load_config()
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    value = data.get("value", "").strip()
    if not name or not value:
        return jsonify({"success": False, "error": "name/value missing"}), 400
    if name == ADMIN_NAME:
        return jsonify({"success": False, "error": "cannot modify admin"}), 400
    cfg["passwords"][name] = value
    save_config(cfg)
    return jsonify({"success": True})

@app.route("/api/admin/password/delete", methods=["POST"])
def admin_del_password():
    if not admin_required():
        return jsonify({"success": False, "error": "unauthorized"}), 401
    cfg = load_config()
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if name == ADMIN_NAME:
        return jsonify({"success": False, "error": "cannot delete admin"}), 400
    cfg["passwords"].pop(name, None)
    save_config(cfg)
    return jsonify({"success": True})

# ============ DEBUG ============
@app.route("/api/debug")
def debug():
    cfg = load_config()
    return jsonify({
        "config_file": CONFIG_FILE,
        "config_exists": os.path.exists(CONFIG_FILE),
        "data_dir_exists": os.path.isdir("/data"),
        "maintenance": cfg.get("maintenance"),
        "passwords_count": len(cfg.get("passwords", {})),
        "password_names": list(cfg.get("passwords", {}).keys()),
        "session": dict(session)
    })

# ============ RUN ============
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"→ http://localhost:{port}")
    print(f"→ config file: {CONFIG_FILE}")
    app.run(host="0.0.0.0", port=port, debug=False)