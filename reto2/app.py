"""
app.py — Mercado Libre · Best TV Shows Challenge
-------------------------------------------------
Sirve una web con login (JWT en cookie) y una UI para consultar el Top de series por género
usando la API pública de HackerRank.

Rutas principales:
 - GET  /health      -> chequeo de vida (devops)
 - GET  /login       -> página de login (si ya estás logueado, te manda a "/")
 - GET  /            -> APP protegida por JWT (require_auth)
 - GET  /logout      -> borra cookie JWT y redirige a login
 - POST /api/login   -> recibe {username, password} -> set cookie JWT HttpOnly
 - POST /api/logout  -> borra cookie
 - POST /api/register-> crea usuario (solo para pruebas)
 - GET  /api/top     -> consulta la API externa, filtra por género y devuelve Top (protegida)

Notas:
 - Python 3.10+
 - Almacena usuarios en SQLite (archivo users.db)
 - La clave de firma JWT viene en FLASK_SECRET (o un valor de dev)
"""

# -----------------------------
# 1) IMPORTS
# -----------------------------
import os
import sqlite3
import time
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, jsonify, request, make_response, g,
    render_template, send_from_directory
)
import jwt                # PyJWT: firma y verificación de tokens
import requests           # HTTP client para llamar a la API externa
from passlib.hash import pbkdf2_sha256 as hasher
# ↑ Elegimos PBKDF2 en vez de bcrypt: es portable y evita problemas de compilación en Windows.


# -----------------------------
# 2) RUTAS ABSOLUTAS (evita “pantalla en blanco” por cwd)
# -----------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))          # carpeta donde está app.py
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")            # /reto2/templates
STATIC_DIR = os.path.join(BASE_DIR, "static")                  # /reto2/static (opcional)

# -----------------------------
# 3) CONFIG APP / JWT / CACHE
# -----------------------------
DATABASE = os.path.join(BASE_DIR, "users.db")   # archivo SQLite local
JWT_COOKIE_NAME = "ml_token"                    # nombre de la cookie
SECRET_KEY = os.environ.get("FLASK_SECRET", "dev-secret-change-me")  # clave firma JWT
JWT_ALGORITHM = "HS256"
JWT_EXP_HOURS = 8                               # tiempo de vida del token

# Cache en memoria muy simple: {clave: (ts_expira, datos)}
CACHE: dict[str, tuple[float, object]] = {}
CACHE_TTL_SECONDS = 300  # 5 minutos

# Inicializa Flask con rutas de templates/static absolutas
app = Flask(__name__, static_folder=STATIC_DIR, template_folder=TEMPLATES_DIR)
app.config["JSON_SORT_KEYS"] = False  # no reordenar keys al hacer jsonify


# -----------------------------
# 4) CAPA DE DATOS (SQLite)
# -----------------------------
def ensure_schema():
    """
    Crea la tabla users si no existe. Idempotente: puedes llamarla al arrancar sin peligro.
    """
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
    """
    Crea un usuario admin desde variables de entorno (ADMIN_USER / ADMIN_PASSWORD).
    Útil en demos para no tener que registrar a mano. Si ya existe, no hace nada.
    """
    admin_user = os.environ.get("ADMIN_USER")
    admin_pass = os.environ.get("ADMIN_PASSWORD")
    if not admin_user or not admin_pass:
        return
    with sqlite3.connect(DATABASE) as db:
        db.row_factory = sqlite3.Row
        cur = db.execute("SELECT id FROM users WHERE username = ?", (admin_user,))
        row = cur.fetchone()
        if not row:
            db.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (admin_user, hasher.hash(admin_pass))
            )
            db.commit()


def get_db():
    """
    Devuelve una conexión SQLite por-request y la cachea en g._database.
    row_factory hace que los rows sean dict-like.
    """
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    """
    Cierra la conexión SQLite cuando termina el request.
    """
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def query_user(username: str):
    """
    Busca un usuario por username y devuelve (id, username, password_hash) o None.
    """
    db = get_db()
    cur = db.execute("SELECT id, username, password_hash FROM users WHERE username = ?", (username,))
    return cur.fetchone()


def create_user(username: str, password: str):
    """
    Inserta un usuario nuevo con password hasheado (PBKDF2-SHA256).
    """
    db = get_db()
    password_hash = hasher.hash(password)
    db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, password_hash))
    db.commit()


# -----------------------------
# 5) JWT y CACHE helpers
# -----------------------------
def generate_jwt(payload: dict) -> str:
    """
    Genera un JWT con expiración y lo firma con SECRET_KEY.
    """
    exp = datetime.utcnow() + timedelta(hours=JWT_EXP_HOURS)
    payload = dict(payload)
    payload["exp"] = exp
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str) -> dict | None:
    """
    Verifica y decodifica el JWT; si falla, devuelve None.
    """
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except Exception:
        return None


def cache_get(key: str):
    """
    Lee de la caché en memoria, invalidando si expiró.
    """
    item = CACHE.get(key)
    if not item:
        return None
    ts_expire, data = item
    if ts_expire < time.time():
        del CACHE[key]
        return None
    return data


def cache_set(key: str, data, ttl: int = CACHE_TTL_SECONDS):
    """
    Escribe en la caché en memoria con TTL (segundos).
    """
    CACHE[key] = (time.time() + ttl, data)


# -----------------------------
# 6) AUTH DECORATOR (protege rutas)
# -----------------------------
def require_auth(f):
    """
    Decorator que:
      - Lee cookie JWT
      - Verifica token
      - En caso de OK, deja pasar; si no, 401
    """
    @wraps(f)
    def wrapped(*args, **kwargs):
        token = request.cookies.get(JWT_COOKIE_NAME)
        if not token:
            return jsonify({"error": "authentication required"}), 401
        payload = decode_jwt(token)
        if not payload:
            return jsonify({"error": "invalid or expired token"}), 401
        # Podrías inyectar el usuario en el request para auditoría
        request.user = payload.get("username")
        return f(*args, **kwargs)
    return wrapped


# -----------------------------
# 7) RUTAS HTML (páginas)
# -----------------------------
@app.get("/health")
def health():
    """Endpoint de salud: útil para revisar despliegue."""
    return "ok", 200


@app.get("/login")
def login_page():
    """
    Página de login. Si ya estás autenticado, te manda a la app ('/').
    """
    token = request.cookies.get(JWT_COOKIE_NAME)
    if token and decode_jwt(token):
        return render_template("app.html")
    return render_template("login.html")


@app.get("/")
@require_auth
def home_app():
    """
    Página principal de la app. Protegida por JWT.
    """
    return render_template("app.html")


@app.get("/logout")
def logout_get():
    """
    Borra la cookie JWT y redirige a /login.
    """
    resp = make_response("", 302)
    resp.headers["Location"] = "/login"
    resp.set_cookie(JWT_COOKIE_NAME, "", expires=0)
    return resp


# -----------------------------
# 8) RUTAS API (JSON)
# -----------------------------
@app.route("/api/register", methods=["POST"])
def api_register():
    """
    Crea usuario (para pruebas). En producción se deshabilita o se protege.
    Body JSON: { "username": "...", "password": "..." }
    """
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
    """
    Login:
      - Verifica credenciales
      - Si OK, crea JWT y lo devuelve en cookie HttpOnly (mitiga XSS)
    """
    data = request.json or {}
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return jsonify({"error": "username and password required"}), 400

    row = query_user(username)
    if not row or not hasher.verify(password, row["password_hash"]):
        return jsonify({"error": "invalid credentials"}), 401

    token = generate_jwt({"username": username})
    resp = make_response(jsonify({"ok": True, "msg": "logged in"}))
    # Cookie HttpOnly y SameSite Lax (buena base, en prod agregar Secure bajo HTTPS)
    resp.set_cookie(JWT_COOKIE_NAME, token, httponly=True, samesite="Lax")
    return resp


@app.route("/api/logout", methods=["POST"])
def api_logout():
    """
    Logout por API: borra cookie.
    """
    resp = make_response(jsonify({"ok": True}))
    resp.set_cookie(JWT_COOKIE_NAME, "", expires=0)
    return resp


# -----------------------------
# 9) LÓGICA DE NEGOCIO: API EXTERNA + FILTRADO
# -----------------------------
HACKERRANK_API = "https://jsonmock.hackerrank.com/api/tvseries"

def fetch_all_shows_from_api():
    """
    Descarga la lista completa (paginada) de series desde la API externa.
    Usa caché para evitar múltiples requests en poco tiempo.
    """
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
            break  # en error devolvemos lo recopilado hasta ahora
        data = resp.json()
        shows.extend(data.get("data", []))
        if page >= data.get("total_pages", 1):
            break
        page += 1

    cache_set(cache_key, shows)  # TTL por defecto
    return shows


@app.route("/api/top", methods=["GET"])
@require_auth
def api_top():
    """
    Query params:
      - genre (required): /api/top?genre=Action
      - limit (optional): /api/top?genre=Action&limit=5  (default 10)
    Devuelve JSON con top ordenado por imdb_rating desc y name asc.
    """
    genre = request.args.get("genre")
    try:
        limit = int(request.args.get("limit", 10))
    except ValueError:
        limit = 10

    if not genre:
        return jsonify({"error": "genre query param required"}), 400

    # cache por combinación (género, límite)
    cache_key = f"top_{genre.lower()}_{limit}"
    cached = cache_get(cache_key)
    if cached is not None:
        return jsonify({"ok": True, "source": "cache", "results": cached})

    shows = fetch_all_shows_from_api()

    # filtrar y normalizar en memoria
    filtered = []
    for s in shows:
        genres = [g.strip() for g in s.get("genre", "").split(",")]
        if genre in genres:
            try:
                rating = float(s.get("imdb_rating") or 0)
            except Exception:
                rating = 0.0
            filtered.append({"name": s.get("name", ""), "rating": rating, "raw": s})

    # ordenar: rating desc, name asc
    filtered.sort(key=lambda x: (-x["rating"], x["name"]))

    top = filtered[:max(1, limit)]
    cache_set(cache_key, top, ttl=120)  # cache corto para respuestas top
    return jsonify({"ok": True, "source": "api", "results": top})


# -----------------------------
# 10) ARCHIVOS ESTÁTICOS (en dev)
# -----------------------------
@app.route("/static/<path:filename>")
def static_files(filename):
    """
    Sirve archivos estáticos desde /static (en desarrollo).
    En producción: mejor un CDN / Nginx.
    """
    return send_from_directory(STATIC_DIR, filename)


# -----------------------------
# 11) BOOTSTRAP AL ARRANCAR
# -----------------------------
ensure_schema()     # asegúrate de que exista la tabla
bootstrap_admin()   # crea admin desde env vars si se definieron


# -----------------------------
# 12) MAIN (DEV SERVER)
# -----------------------------
if __name__ == "__main__":
    print("Starting Flask dev server on http://127.0.0.1:5000")
    # debug=True recarga en caliente y muestra traceback bonito
    app.run(host="0.0.0.0", port=5000, debug=True)
