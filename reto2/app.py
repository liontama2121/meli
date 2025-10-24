import os
import sqlite3
import time
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, jsonify, request, make_response, g,
    render_template, send_from_directory
)
import jwt
import requests
from passlib.hash import bcrypt

# === RUTAS ABSOLUTAS ===
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

DATABASE = os.path.join(BASE_DIR, "users.db")
JWT_COOKIE_NAME = "ml_token"
SECRET_KEY = os.environ.get("FLASK_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXP_HOURS = 8

CACHE = {}
CACHE_TTL_SECONDS = 300

app = Flask(__name__, static_folder=STATIC_DIR, template_folder=TEMPLATES_DIR)
app.config["JSON_SORT_KEYS"] = False

# === DB ===
def ensure_schema():
    with sqlite3.connect(DATABASE) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        """)
        db.commit()

def bootstrap_admin():
    admin_user = os.environ.get("ADMIN_USER")
    admin_pass = os.environ.get("ADMIN_PASSWORD")
    if not admin_user or not admin_pass:
        return
    with sqlite3.connect(DATABASE) as db:
        db.row_factory = sqlite3.Row
        cur = db.execute("SELECT id FROM users WHERE username = ?", (admin_user,))
        if not cur.fetchone():
            db.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (admin_user, bcrypt.hash(admin_pass))
            )
            db.commit()

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()

def query_user(username: str):
    db = get_db()
    cur = db.execute("SELECT id, username, password_hash FROM users WHERE username = ?", (username,))
    return cur.fetchone()

def create_user(username: str, password: str):
    db = get_db()
    db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, bcrypt.hash(password)))
    db.commit()

def generate_jwt(payload: dict):
    exp = datetime.utcnow() + timedelta(hours=JWT_EXP_HOURS)
    payload = dict(payload)
    payload.update({"exp": exp})
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)

def decode_jwt(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except Exception:
        return None

def cache_get(key: str):
    item = CACHE.get(key)
    if not item:
        return None
    ts_expire, data = item
    if ts_expire < time.time():
        del CACHE[key]
        return None
    return data

def cache_set(key: str, data, ttl: int = CACHE_TTL_SECONDS):
    CACHE[key] = (time.time() + ttl, data)

def require_auth(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        token = request.cookies.get(JWT_COOKIE_NAME)
        if not token:
            return jsonify({"error": "authentication required"}), 401
        payload = decode_jwt(token)
        if not payload:
            return jsonify({"error": "invalid or expired token"}), 401
        request.user = payload.get("username")
        return f(*args, **kwargs)
    return wrapped

# === Rutas ===
@app.get("/health")
def health():
    return "ok", 200

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.json or {}
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return jsonify({"error": "username and password required"}), 400
    if query_user(username):
        return jsonify({"error": "user exists"}), 400
    create_user(username, password)
    return jsonify({"ok": True, "msg": "user created"}), 201

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.json or {}
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return jsonify({"error": "username and password required"}), 400
    row = query_user(username)
    if not row or not bcrypt.verify(password, row["password_hash"]):
        return jsonify({"error": "invalid credentials"}), 401
    token = generate_jwt({"username": username})
    resp = make_response(jsonify({"ok": True, "msg": "logged in"}))
    resp.set_cookie(JWT_COOKIE_NAME, token, httponly=True, samesite="Lax")
    return resp

@app.route("/api/logout", methods=["POST"])
def api_logout():
    resp = make_response(jsonify({"ok": True}))
    resp.set_cookie(JWT_COOKIE_NAME, "", expires=0)
    return resp

HACKERRANK_API = "https://jsonmock.hackerrank.com/api/tvseries"

def fetch_all_shows_from_api():
    cache_key = "all_shows"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    shows = []
    page = 1
    while True:
        url = f"{HACKERRANK_API}?page={page}"
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            break
        data = resp.json()
        shows.extend(data.get("data", []))
        if page >= data.get("total_pages", 1):
            break
        page += 1
    cache_set(cache_key, shows)
    return shows

@app.route("/api/top", methods=["GET"])
@require_auth
def api_top():
    genre = request.args.get("genre")
    try:
        limit = int(request.args.get("limit", 10))
    except ValueError:
        limit = 10
    if not genre:
        return jsonify({"error": "genre query param required"}), 400
    cache_key = f"top_{genre.lower()}_{limit}"
    cached = cache_get(cache_key)
    if cached is not None:
        return jsonify({"ok": True, "source": "cache", "results": cached})
    shows = fetch_all_shows_from_api()
    filtered = []
    for s in shows:
        genres = [g.strip() for g in s.get("genre", "").split(",")]
        if genre in genres:
            try:
                rating = float(s.get("imdb_rating") or 0)
            except Exception:
                rating = 0.0
            filtered.append({"name": s.get("name", ""), "rating": rating, "raw": s})
    filtered.sort(key=lambda x: (-x["rating"], x["name"]))
    top = filtered[:max(1, limit)]
    cache_set(cache_key, top, ttl=120)
    return jsonify({"ok": True, "source": "api", "results": top})

@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(STATIC_DIR, filename)

# === Bootstrap ===
ensure_schema()
bootstrap_admin()

if __name__ == "__main__":
    print("Starting Flask dev server on http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=True)
