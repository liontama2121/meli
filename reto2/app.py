# -*- coding: utf-8 -*-
"""
Reto 2 – Best TV Shows Challenge (Flask)
Seguridad y observabilidad integradas:
- Logging estructurado (JSON) con RotatingFileHandler
- Manejo centralizado de errores y trazas
- No envío de tokens/cookies en requests salientes (requests.Session trust_env=False)
- Sanitización de datos de entrada/salida
- Auditoría de usuario (before/after request) con X-Request-ID
- Validación de JSON e integridad de tipos
- Límite de tiempo por request (time limit) y timeouts en requests externas
- Autenticación con JWT en cookie HttpOnly
- Control de intentos de login fallidos con ventana/bloqueo
"""

import os, re, json, sqlite3, time, uuid, traceback
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, jsonify, request, make_response, g,
    render_template, send_from_directory
)
import jwt
import requests
from logging.handlers import RotatingFileHandler
import logging

# Hash seguro en Windows: PBKDF2-SHA256 (evita fricciones con bcrypt)
from passlib.hash import pbkdf2_sha256 as hasher

# === RUTAS ABSOLUTAS ===
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

# === CONFIG APP / SEGURIDAD ===
DATABASE = os.path.join(BASE_DIR, "users.db")
JWT_COOKIE_NAME = "ml_token"
SECRET_KEY = os.environ.get("FLASK_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXP_HOURS = 8

CACHE = {}
CACHE_TTL_SECONDS = 300
MAX_REQ_MS = 6000  # 6s límite por request de app (protege de abusos)
PROD = os.environ.get("ENV", "").lower() in {"prod", "production"}
COOKIE_SAMESITE = "Lax"
COOKIE_SECURE = True if PROD else False

HACKERRANK_API = "https://jsonmock.hackerrank.com/api/tvseries"

# === ANTI-ABUSO / LOGIN FAILS ===
AUTH_FAIL_WINDOW_SEC = 15 * 60   # ventana de conteo (15 min)
AUTH_FAIL_MAX = 5                # máx. intentos fallidos en esa ventana
AUTH_BLOCK_MIN = 10              # bloquear 10 min al exceder
FAILED_LOGINS = {}               # clave: f"{username}|{ip}" -> dict

# === APP ===
app = Flask(__name__, static_folder=STATIC_DIR, template_folder=TEMPLATES_DIR)
app.config["JSON_SORT_KEYS"] = False

# === LOGGING ESTRUCTURADO ===
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
log_handler = RotatingFileHandler(os.path.join(LOG_DIR, "app.log"),
                                  maxBytes=2_000_000, backupCount=5, encoding="utf-8")
log_formatter = logging.Formatter("%(message)s")
log_handler.setFormatter(log_formatter)
app.logger.setLevel(logging.INFO)
app.logger.addHandler(log_handler)

def log_json(level: str, **fields):
    """Escribe una línea JSON en el log rotativo."""
    try:
        fields.setdefault("ts", datetime.utcnow().isoformat() + "Z")
        line = json.dumps(fields, ensure_ascii=False)
    except Exception:
        line = json.dumps({
            "ts": datetime.utcnow().isoformat()+"Z",
            "level": level,
            "msg": "log_serialize_error"
        })
    getattr(app.logger, level.lower(), app.logger.info)(line)

# === UTILES: SANITIZACION / JSON / CACHE ===
SAFE_TEXT_RE = re.compile(r"[A-Za-z0-9_.\- @]+$", re.UNICODE)

def sanitize_str(value: str, *, max_len: int = 64, allow_empty=False) -> str:
    """
    Normaliza string:
      - trim y colapsa espacios
      - límite de longitud
      - whitelist de caracteres seguros
    """
    if value is None:
        raise ValueError("string required")
    s = str(value).strip()
    s = re.sub(r"\s+", " ", s)
    if not s and not allow_empty:
        raise ValueError("empty")
    if len(s) > max_len:
        raise ValueError("too_long")
    if not SAFE_TEXT_RE.match(s):
        raise ValueError("invalid_chars")
    return s

def expect_json(required_fields: dict):
    """
    required_fields: {"username": str, "password": str}
    - Verifica Content-Type application/json
    - Valida tipos básicos
    - Retorna dict JSON
    """
    if request.content_type is None or "application/json" not in request.content_type:
        raise ValueError("content_type_must_be_application_json")
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("invalid_or_missing_json_body")
    for k, typ in required_fields.items():
        if k not in data:
            raise ValueError(f"missing_field:{k}")
        if typ is int and not isinstance(data[k], int):
            raise ValueError(f"type_error:{k}:int_required")
        if typ is str and not isinstance(data[k], str):
            raise ValueError(f"type_error:{k}:str_required")
    return data

def cache_get(key: str):
    item = CACHE.get(key)
    if not item:
        return None
    ts_expire, data = item
    if ts_expire < time.time():
        try:
            del CACHE[key]
        except Exception:
            pass
        return None
    return data

def cache_set(key: str, data, ttl: int = CACHE_TTL_SECONDS):
    CACHE[key] = (time.time() + ttl, data)

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
    """
    Crea un admin desde ENV si no existe:
      ADMIN_USER / ADMIN_PASSWORD
    """
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
                (admin_user, hasher.hash(admin_pass))
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
    db.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, hasher.hash(password))
    )
    db.commit()

# === JWT ===
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

# === SALIDAS HTTP (sin tokens/cookies) ===
_SESSION = None
def safe_session():
    """
    Session sin heredar variables de entorno (trust_env=False) para evitar
    filtrado involuntario de proxies/cookies de sistema.
    """
    global _SESSION
    if _SESSION is None:
        s = requests.Session()
        s.trust_env = False
        _SESSION = s
    return _SESSION

def safe_get(url: str, *, timeout: int = 10):
    """
    GET externo sin Authorization/cookies.
    """
    headers = {"User-Agent": "MELI-Challenge/1.0"}
    return safe_session().get(url, headers=headers, timeout=timeout, allow_redirects=True, verify=True)

# === ANTI-ABUSO HELPERS (login fails) ===
def _fail_key(username: str, ip: str) -> str:
    return f"{username}|{ip}"

def _now() -> float:
    return time.time()

def _cleanup_and_get(bucket: dict, key: str):
    rec = bucket.get(key)
    if not rec:
        return None
    now = _now()
    # Si está bloqueado y ya pasó el bloqueo, levántalo
    if rec.get("blocked_until") and now >= rec["blocked_until"]:
        rec["blocked_until"] = None
        rec["attempts"] = 0
        rec["first_ts"] = None
    # Ventana expirada
    if not rec.get("blocked_until") and rec.get("first_ts") and now - rec["first_ts"] > AUTH_FAIL_WINDOW_SEC:
        rec["attempts"] = 0
        rec["first_ts"] = None
    return rec

def auth_is_blocked(username: str, ip: str):
    key = _fail_key(username, ip)
    rec = _cleanup_and_get(FAILED_LOGINS, key)
    if not rec:
        return False, None
    if rec.get("blocked_until") and _now() < rec["blocked_until"]:
        return True, rec["blocked_until"]
    return False, None

def register_auth_fail(username: str, ip: str):
    key = _fail_key(username, ip)
    rec = _cleanup_and_get(FAILED_LOGINS, key) or {"attempts": 0, "first_ts": None, "blocked_until": None}
    now = _now()
    if rec["first_ts"] is None:
        rec["first_ts"] = now
        rec["attempts"] = 0
    if now - rec["first_ts"] > AUTH_FAIL_WINDOW_SEC:
        rec["first_ts"] = now
        rec["attempts"] = 0
    rec["attempts"] += 1

    blocked_until = None
    if rec["attempts"] >= AUTH_FAIL_MAX:
        blocked_until = now + AUTH_BLOCK_MIN * 60
        rec["blocked_until"] = blocked_until
        # Reinicia ventana tras bloqueo
        rec["first_ts"] = None
        rec["attempts"] = 0

    FAILED_LOGINS[key] = rec
    return rec, blocked_until

def reset_auth_fail(username: str, ip: str):
    key = _fail_key(username, ip)
    if key in FAILED_LOGINS:
        del FAILED_LOGINS[key]

# === MIDDLEWARE AUDITORIA + TIME LIMIT ===
@app.before_request
def _audit_begin():
    g._start_ts = time.time()
    g.request_id = uuid.uuid4().hex[:12]
    g.user = None
    try:
        tok = request.cookies.get(JWT_COOKIE_NAME)
        payload = decode_jwt(tok) if tok else None
        if payload and isinstance(payload, dict):
            g.user = payload.get("username")
    except Exception:
        g.user = None

@app.after_request
def _audit_end(response):
    elapsed_ms = int((time.time() - getattr(g, "_start_ts", time.time())) * 1000)
    # Time limit: si excede y la respuesta es <400, devolvemos 408
    if elapsed_ms > MAX_REQ_MS and (response[1] if isinstance(response, tuple) else response.status_code) < 400:
        response = jsonify({"error": "request_time_limit_exceeded"}), 408

    log_json("info",
        event="http_access",
        request_id=getattr(g, "request_id", "-"),
        user=getattr(g, "user", None),
        ip=request.headers.get("X-Forwarded-For", request.remote_addr),
        ua=request.headers.get("User-Agent"),
        method=request.method,
        path=request.path,
        status=response[1] if isinstance(response, tuple) else response.status_code,
        latency_ms=elapsed_ms
    )

    # Añadir cabecera de correlación
    if isinstance(response, tuple):
        resp = make_response(response[0], response[1], response[2] if len(response) > 2 else {})
    else:
        resp = response
    resp.headers["X-Request-ID"] = getattr(g, "request_id", "-")
    return resp

@app.errorhandler(Exception)
def _on_error(e):
    elapsed_ms = int((time.time() - getattr(g, "_start_ts", time.time())) * 1000)
    log_json("error",
        event="error",
        request_id=getattr(g, "request_id", "-"),
        user=getattr(g, "user", None),
        method=request.method,
        path=request.path,
        latency_ms=elapsed_ms,
        error=str(e),
        traceback=traceback.format_exc()
    )
    return jsonify({"error": "internal_error"}), 500

# === RUTAS ===
@app.get("/health")
def health():
    return "ok", 200

@app.route("/")
def index():
    # Asegúrate de tener templates/index.html
    return render_template("index.html")

@app.route("/api/register", methods=["POST"])
def api_register():
    try:
        data = expect_json({"username": str, "password": str})
        username = sanitize_str(data["username"], max_len=32)
        password = str(data["password"]).strip()
        if len(password) < 6 or len(password) > 128:
            return jsonify({"error": "password_length"}), 400
        if query_user(username):
            return jsonify({"error": "user_exists"}), 400
        create_user(username, password)
        log_json("info", event="user_register", username=username)
        return jsonify({"ok": True, "msg": "user_created"}), 201
    except ValueError as ve:
        return jsonify({"error": f"bad_request:{ve}"}), 400

@app.route("/api/login", methods=["POST"])
def api_login():
    try:
        data = expect_json({"username": str, "password": str})
        username = sanitize_str(data["username"], max_len=32)
        password = str(data["password"])
        client_ip = request.headers.get("X-Forwarded-For", request.remote_addr) or "-"

        # 1) Verifica si está bloqueado por demasiados intentos
        blocked, until_ts = auth_is_blocked(username, client_ip)
        if blocked:
            log_json("info",
                event="login_blocked",
                username=username,
                ip=client_ip,
                blocked_until=datetime.utcfromtimestamp(until_ts).isoformat() + "Z"
            )
            return jsonify({
                "error": "too_many_attempts",
                "retry_after_sec": max(1, int(until_ts - time.time()))
            }), 429

        # 2) Verificación de credenciales
        row = query_user(username)
        if not row or not hasher.verify(password, row["password_hash"]):
            rec, blocked_until = register_auth_fail(username, client_ip)
            remaining = 0 if blocked_until else max(0, AUTH_FAIL_MAX - rec.get("attempts", 0))
            log_json("info",
                event="login_failed",
                username=username,
                ip=client_ip,
                attempt=(AUTH_FAIL_MAX - remaining) if remaining >= 0 else AUTH_FAIL_MAX,
                remaining_attempts=remaining,
                blocked_until=(datetime.utcfromtimestamp(blocked_until).isoformat() + "Z") if blocked_until else None
            )
            status = 429 if blocked_until else 401
            return jsonify({"error": "invalid_credentials", "remaining_attempts": remaining}), status

        # 3) Éxito: resetea contador y emite token
        reset_auth_fail(username, client_ip)
        token = generate_jwt({"username": username})
        resp = make_response(jsonify({"ok": True, "msg": "logged_in"}))
        resp.set_cookie(JWT_COOKIE_NAME, token, httponly=True, samesite=COOKIE_SAMESITE, secure=COOKIE_SECURE)
        log_json("info", event="login_success", username=username, ip=client_ip)
        return resp

    except ValueError as ve:
        return jsonify({"error": f"bad_request:{ve}"}), 400

@app.route("/api/logout", methods=["POST"])
@require_auth
def api_logout():
    username = getattr(request, "user", None)
    resp = make_response(jsonify({"ok": True}))
    resp.set_cookie(JWT_COOKIE_NAME, "", expires=0)
    log_json("info", event="logout", username=username)
    return resp

def fetch_all_shows_from_api():
    cache_key = "all_shows"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    shows = []
    page = 1
    while True:
        url = f"{HACKERRANK_API}?page={page}"
        resp = safe_get(url, timeout=10)
        if resp.status_code != 200:
            log_json("error", event="external_api_error", url=url, status=resp.status_code)
            break
        try:
            data = resp.json()
        except Exception:
            log_json("error", event="external_api_json_error", url=url)
            break
        shows.extend(data.get("data", []))
        if page >= data.get("total_pages", 1):
            break
        page += 1
    cache_set(cache_key, shows, ttl=300)
    return shows

@app.route("/api/top", methods=["GET"])
@require_auth
def api_top():
    # Sanitización y validación de query params
    try:
        genre_raw = request.args.get("genre")
        genre = sanitize_str(genre_raw, max_len=32)
    except Exception:
        return jsonify({"error": "genre_invalid"}), 400

    try:
        limit = int(request.args.get("limit", 10))
    except ValueError:
        limit = 10
    if limit < 1 or limit > 50:
        return jsonify({"error": "limit_out_of_range"}), 400

    cache_key = f"top_{genre.lower()}_{limit}"
    cached = cache_get(cache_key)
    if cached is not None:
        log_json("info", event="top_cache_hit", user=getattr(request, "user", None), genre=genre, limit=limit)
        return jsonify({"ok": True, "source": "cache", "results": cached})

    shows = fetch_all_shows_from_api()
    filtered = []
    for s in shows:
        genres = [g.strip() for g in (s.get("genre") or "").split(",")]
        if genre in genres:
            try:
                rating = float(s.get("imdb_rating") or 0)
            except Exception:
                rating = 0.0
            filtered.append({"name": s.get("name", ""), "rating": rating})

    filtered.sort(key=lambda x: (-x["rating"], x["name"]))
    top = filtered[:max(1, limit)]
    cache_set(cache_key, top, ttl=120)
    log_json("info", event="top_query", user=getattr(request, "user", None), genre=genre, limit=limit, results=len(top))
    return jsonify({"ok": True, "source": "api", "results": top})

@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(STATIC_DIR, filename)

# === Bootstrap ===
ensure_schema()
bootstrap_admin()

if __name__ == "__main__":
    print("Starting Flask dev server on http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=not PROD)
