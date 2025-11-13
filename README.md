## ⚙️ Instalación

1. **Clona el proyecto** o copia el archivo principal:}

git clone  https://github.com/liontama2121/meli


# Reto 1 💣 Buscaminas Mercado Libre · Versión Pygame

Juego del **Buscaminas** inspirado en el estilo visual de **Mercado Libre**, desarrollado en **Python + Pygame**.  
Incluye interfaz gráfica, selección de niveles, detección de minas, banderas, contador de tiempo y diseño adaptado al branding de Meli.

---



## 🎮 Descripción general

El proyecto recrea el clásico **Minesweeper (Buscaminas)** con colores y estética de **Mercado Libre**, utilizando el motor gráfico **Pygame**.

Cuenta con:
- 🎨 Interfaz moderna (azul y amarillo Meli)
- 💥 Detección de minas
- 🚩 Colocación de banderas
- 🧠 Tres niveles de dificultad
- ⏱️ Temporizador en tiempo real
- 🧱 Redimensionamiento automático según la ventana
- 🖱️ Controles de ratón y teclado

---

## 🛠️ Requisitos del sistema

- Python **3.8** o superior  
- pip (gestor de paquetes de Python)


# 📺 Reto 2 - Mercado Libre · Best TV Shows Challenge

Este proyecto es parte del reto técnico de Mercado Libre. Consiste en una aplicación web desarrollada con Python + Flask, que permite consultar las mejores series de TV por género, integrando autenticación, consumo de API externa, y una interfaz web moderna inspirada en el estilo de Mercado Libre.

## 🚀 Funcionalidades principales

- Inicio de sesión con usuario y contraseña  
- Autenticación con JWT en cookies  
- Consulta de las mejores series según género (usando API de HackerRank)  
- Ordenadas por rating IMDB  
- Loader animado mientras se carga la información  
- Interfaz responsiva y moderna con branding Meli  

## 🛠️ Requisitos del sistema

- Python 3.8 o superior  
- pip (gestor de paquetes de Python)  
- Git (opcional, si clonas desde repo)  

## 🧪 Instalación paso a paso

1. Clona el proyecto o descarga los archivos:

git clone https://github.com/liontama2121/meli.git  
cd meli/reto2

2. Crea un entorno virtual e instala las dependencias:

python -m venv venv  
venv\Scripts\activate        # En Windows  
# source venv/bin/activate   # En macOS/Linux  

pip install flask passlib requests pyjwt

3. Crear usuario administrador (solo la primera vez):

En PowerShell (Windows):

$env:ADMIN_USER = "admin"  
$env:ADMIN_PASSWORD = "superseguro"  

En CMD:

set ADMIN_USER=admin  
set ADMIN_PASSWORD=superseguro

4. Ejecutá la aplicación:

python app.py

La aplicación correrá en: http://127.0.0.1:5000/

## 🔑 Usuario de prueba

Usuario: admin  
Contraseña: superseguro

## 🌐 Rutas principales

GET / — Página principal  
POST /api/login — Login del usuario  
POST /api/logout — Logout del usuario  
GET /api/top — Consulta de series (requiere login)

## ⚙️ Seguridad, logs y control de integridad



### 1️⃣ Control de errores con logs

**Ubicación:**
- Bloque `@app.errorhandler(Exception)`
- Función `log_json()`
- Configuración de `RotatingFileHandler` (carpeta `/logs/app.log`)

**Descripción:**  
Todos los errores y eventos importantes se registran en formato **JSON estructurado** con información como:
- Timestamp  
- Usuario  
- IP  
- Método  
- Ruta  
- Latencia  
- Error  

Cada request tiene un **X-Request-ID único** para rastreo completo.

---

### 2️⃣ “Certificado” — Bloqueo de tokens/cookies en peticiones externas

**Ubicación:**
- Función `safe_session()`
- Función `safe_get()`

**Descripción:**  
Las peticiones externas a la API de HackerRank usan una **sesión aislada sin credenciales ni tokens** (`trust_env=False`).  
Esto garantiza que **no se envíen cookies, proxies o tokens JWT** fuera del dominio interno.

---

### 3️⃣ Sanitización de datos (entrada y salida)

**Ubicación:**
- Función `sanitize_str()`
- Función `expect_json()`
- Uso en `/api/register`, `/api/login`, `/api/top`

**Descripción:**  
Cada dato que entra al sistema se valida para asegurar su integridad:
- Tipo (`str`, `int`, etc.)
- Longitud máxima
- Patrón de caracteres seguros (sin símbolos peligrosos)  

Además, las salidas JSON eliminan **campos sensibles** (como hashes o tokens).

---

### 4️⃣ Logs de usuario (auditoría y control)

**Ubicación:**
- Middlewares `@app.before_request` y `@app.after_request`
- Variables `g.user`, `g.request_id`
- Eventos `login_success`, `login_failed`, `logout`, `top_query`

**Descripción:**  
Cada acción del usuario se registra con:
- Usuario autenticado  
- Ruta y método HTTP  
- IP y User-Agent  
- Tiempo de ejecución (ms)  
- Resultado (OK / error)  

Esto genera un **historial detallado de auditoría** de todas las acciones de los usuarios en el sistema.

---

### 5️⃣ Integridad de datos JSON

**Ubicación:**
- Función `expect_json()`
- Validación de `Content-Type: application/json`

**Descripción:**  
Solo se aceptan solicitudes con formato **JSON válido** y estructura esperada.  
Si falta un campo o el tipo es incorrecto, el sistema devuelve un **error 400 (`bad_request`)** para prevenir inconsistencias.

---

### 6️⃣ Límite de tiempo (time limit) y protección contra inyección

**Ubicación:**
- Variable `MAX_REQ_MS = 6000`
- Middleware `@app.after_request`
- Uso de `timeout` en `requests.get()`

**Descripción:**  
- Si una solicitud demora más de **6 segundos**, responde con **408 Request Timeout**.  
- Las consultas SQL usan **parámetros seguros (`?`)** para evitar inyecciones.  
- Las peticiones externas tienen límite de **10 segundos (`timeout=10`)**, evitando abusos o ataques por sobrecarga.

---

### 7️⃣ Control de intentos fallidos de login

**Ubicación:**
- Funciones `register_auth_fail()`, `auth_is_blocked()`, `reset_auth_fail()`
- Endpoint `/api/login`

**Descripción:**  
- Máximo **5 intentos de login** por usuario/IP en una ventana de **15 minutos**.  
- Si se excede, el usuario queda bloqueado por **10 minutos** (`429 Too Many Attempts`).  
- Todos los intentos (fallidos o exitosos) quedan registrados en los logs con timestamp, IP y usuario.

---

# 🔐 Reto 3 – Base de datos segura con Supabase (PostgreSQL + RLS)

Base de datos **gratuita y segura** en **Supabase** (PostgreSQL administrado) para el Reto 3.  
Incluye: esquema, datos de ejemplo del enunciado, consulta del reto, **Row Level Security (RLS)** y **políticas** que restringen el acceso por `customer_id`.

## ✅ ¿Por qué Supabase?
- **Gratis** (free tier).
- **PostgreSQL real** con **RLS** nativo.
- **Auth + API REST** integrados (fácil de consumir desde tu app).
- Editor SQL en el dashboard.

---

## 🧭 Estructura del reto
- Tabla **customers**
- Tabla **campaigns** (FK a customers)
- Tabla **events** (FK a campaigns) con `status` = `success` / `failure`
- Reporte: **clientes con más de 3 fallas** (formato `customer | failures`)

---

## 🚀 Pasos para montar la BD

### 1️⃣ Crear proyecto en Supabase
1. Ve a **https://supabase.com** → **New Project**.  
2. Elige la **contraseña** del DB, nombre y región.  
3. Entra al dashboard → **SQL Editor**.

---

### 2️⃣ Crear tablas e índices
Copia y ejecuta este bloque en **SQL Editor**:

```sql
create table if not exists customers (
  id smallint primary key,
  first_name varchar(64) not null,
  last_name  varchar(64) not null
);

create table if not exists campaigns (
  id smallint primary key,
  customer_id smallint not null references customers(id) on delete cascade,
  name varchar(64) not null
);

create table if not exists events (
  dt timestamp not null,
  campaign_id smallint not null references campaigns(id) on delete cascade,
  status varchar(64) not null check (status in ('failure','success'))
);

create index if not exists idx_events_campaign on events(campaign_id);
create index if not exists idx_events_status   on events(status);
create index if not exists idx_campaigns_customer on campaigns(customer_id);
```

---

### 3️⃣ Insertar datos de ejemplo (del enunciado)
Ejecuta:

```sql
truncate events, campaigns, customers restart identity;

insert into customers (id, first_name, last_name) values
(1,'Whitney','Ferrero'),
(2,'Dickie','Romera');

insert into campaigns (id, customer_id, name) values
(1,1,'Upton Group'),
(2,1,'Roob, Hudson and Rippin'),
(3,1,'McCullough, Rempel and Larson'),
(4,1,'Lang and Sons'),
(5,2,'Ruecker, Hand and Haley');

insert into events (dt, campaign_id, status) values
('2021-12-02 13:52:00',1,'failure'),
('2021-12-02 08:17:48',2,'failure'),
('2021-12-02 08:18:17',2,'failure'),
('2021-12-01 11:55:32',3,'failure'),
('2021-12-01 06:53:16',4,'failure'),
('2021-12-02 04:51:09',4,'failure'),
('2021-12-01 06:34:04',5,'failure'),
('2021-12-02 03:21:18',5,'failure'),
('2021-12-01 03:18:24',5,'failure'),
('2021-12-02 15:32:37',1,'success'),
('2021-12-01 04:23:20',1,'success'),
('2021-12-02 06:53:24',1,'success'),
('2021-12-02 08:01:02',2,'success'),
('2021-12-01 15:57:19',2,'success'),
('2021-12-02 16:14:34',3,'success'),
('2021-12-02 21:56:38',3,'success'),
('2021-12-01 05:54:43',4,'success'),
('2021-12-02 17:56:45',4,'success'),
('2021-12-02 11:56:50',4,'success'),
('2021-12-02 06:08:20',5,'success');
```

---

### 4️⃣ Consulta del reto (clientes con > 3 fallas)

```sql
select
  (cu.first_name || ' ' || cu.last_name) as customer,
  count(*) as failures
from events e
join campaigns ca on ca.id = e.campaign_id
join customers cu on cu.id = ca.customer_id
where e.status = 'failure'
group by cu.id, cu.first_name, cu.last_name
having count(*) > 3
order by failures desc, customer;
```

**Resultado esperado:**
```
customer         | failures
-----------------+----------
Whitney Ferrero  | 6
```

---

## 🔒 Seguridad: RLS + Políticas

### 5) Activar RLS
```sql
alter table customers enable row level security;
alter table campaigns enable row level security;
alter table events    enable row level security;
```

### 6) Políticas por customer_id

#### a) `read_own_customer`
```sql
create policy "read_own_customer"
on customers for select
to authenticated
using ( id::text = auth.jwt() ->> 'customer_id' );
```
> Permite que un usuario autenticado vea **solo su propio registro** en `customers`.

#### b) `read_campaigns_by_customer`
```sql
create policy "read_campaigns_by_customer"
on campaigns for select
to authenticated
using ( customer_id::text = auth.jwt() ->> 'customer_id' );
```
> Permite que el usuario vea solo las **campañas asociadas a su customer_id**.

#### c) `read_events_by_customer`
```sql
create policy "read_events_by_customer"
on events for select
to authenticated
using (
  exists (
    select 1 from campaigns c
    where c.id = events.campaign_id
      and c.customer_id::text = auth.jwt() ->> 'customer_id'
  )
);
```
> Permite que el usuario vea solo los **eventos** pertenecientes a **sus campañas**.

#### (Opcional) d) `insert_events_from_service`
```sql
create policy "insert_events_from_service"
on events for insert
to service_role
with check (true);
```
> Permite que el **backend** (rol `service_role`) inserte datos sin restricciones.

---

## 🧪 Pruebas
- Si usas un **JWT** con `{ "customer_id": "1" }`, verás solo los datos del cliente 1.
- Si usas `{ "customer_id": "2" }`, verás solo los del cliente 2.
- Sin JWT válido → acceso denegado (RLS activo).

---

## 📌 Resultado final
**Cliente con más de 3 fallas:**  
`Whitney Ferrero | 6`

 🤖 Reto 4 – Mercado Libre · CLI de Resumen con GenAI

Este reto consiste en una **aplicación de línea de comandos (CLI)** desarrollada en **Go**, que utiliza un modelo público de **IA generativa** (Hugging Face Inference API) para **resumir archivos de texto** de forma automática.  
El programa soporta varios tipos de resumen (`short`, `medium`, `bullet`) y maneja errores, fragmentación de texto y fallback de modelos de manera robusta.

---

## 🚀 Funcionalidades principales

- 📄 Lee archivos de texto y genera resúmenes automáticos usando IA.  
- ⚙️ Parámetros configurables:
  - `--input`: ruta del archivo a resumir.  
  - `--type`: tipo de resumen (`short`, `medium`, `bullet`).  
- 🧠 Usa modelos públicos de Hugging Face (por defecto `facebook/bart-large-cnn`).  
- 🔁 Fallback automático si un modelo falla (usa otros modelos estables).  
- ✂️ Fragmenta textos largos (map-reduce) para evitar errores del modelo.  
- 🛡️ Soporte de autenticación segura con `HF_API_TOKEN`.  
- 🪶 Interfaz amigable, salida directa por consola (`stdout`).

---

## 🧰 Requisitos del sistema

- **Go 1.22+**  
- Conexión a Internet  
- Cuenta gratuita en [Hugging Face](https://huggingface.co/)  
- Token con permiso ✅ **“Make calls to Inference Providers”**

---

## ⚙️ Instalación y ejecución

### 1. Clona el repositorio o crea el archivo
```bash
git clone https://github.com/liontama2121/meli.git
cd meli/reto4
```
O copia el archivo `solution_summarizer.go` en una carpeta local.

### 2. Crea tu token de Hugging Face
Ingresa a 👉 [https://huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)

Crea un nuevo token con solo este permiso:  
✅ **Make calls to Inference Providers**  

Copia el token (comienza con `hf_...`).

### 3. Configura las variables de entorno

#### En PowerShell (Windows)
```powershell
$env:HF_API_TOKEN = "hf_tu_token_aqui"
$env:HF_MODEL = "facebook/bart-large-cnn"
```

#### En macOS / Linux
```bash
export HF_API_TOKEN="hf_tu_token_aqui"
export HF_MODEL="facebook/bart-large-cnn"
```

### 4. Crea un archivo de prueba
```bash
echo "Mercado Libre está desarrollando nuevas herramientas de IA para mejorar la experiencia de compra y proteger la seguridad de los datos." > ejemplo.txt
```

### 5. Ejecuta el programa
```bash
go run solution_summarizer.go --input ejemplo.txt --type bullet
``
```
## 🧑‍💻 Autor
Juan C. Molina  
Desarrollador Java / Python  

