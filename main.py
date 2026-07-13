from fastapi import FastAPI, Form, WebSocket, WebSocketDisconnect, UploadFile, File, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import random
import string
import json
import time
import os
import uuid
import uuid
import sqlite3

from passlib.context import CryptContext
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.responses import RedirectResponse

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(
    SessionMiddleware,
    secret_key="pycom_desarrollo_2026"
)

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

salas = {}
conexiones = {}

UPLOAD_DIR = "static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

DB = "pycom.db"

conexion = sqlite3.connect(DB)
cursor = conexion.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS usuarios(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    correo TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    foto TEXT DEFAULT ''
)
""")

conexion.commit()
conexion.close()

conexion = sqlite3.connect(DB)
cursor = conexion.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS historial_salas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT NOT NULL,
    codigo_sala TEXT NOT NULL,
    accion TEXT NOT NULL,
    fecha TEXT DEFAULT CURRENT_TIMESTAMP
)
""")

conexion.commit()
conexion.close()

conexion = sqlite3.connect(DB)
cursor = conexion.cursor()

try:
    cursor.execute("ALTER TABLE usuarios ADD COLUMN foto TEXT DEFAULT ''")
    conexion.commit()
except sqlite3.OperationalError:
    pass

conexion.close()

def abrir_html(ruta):
    with open(ruta, "r", encoding="utf-8") as archivo:
        return archivo.read()

def render_error(titulo, mensaje, volver="/login"):
    return HTMLResponse(f"""
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>{titulo} - Pycom</title>
        <link rel="stylesheet" href="/static/style.css">
    </head>
    <body>
        <div class="navbar">
            <div class="logo">PYCOM</div>
            <div>
                <a href="/">Inicio</a>
                <a href="/crear-sala">Crear sala</a>
                <a href="/unirse-sala">Unirse a sala</a>
                <a href="/registro">Registro</a>
                <a href="/login">Login</a>
            </div>
        </div>

        <main class="home-hero">
            <div class="card home-form-card">
                <h1>{titulo}</h1>
                <p>{mensaje}</p>
                <br>
                <a href="{volver}">
                    <button>Volver</button>
                </a>
            </div>
        </main>

        <footer>
            <p>© 2024 <strong>Pycom</strong></p>
        </footer>
    </body>
    </html>
    """)

def render_mensaje_html(mensaje, nombre_usuario):
    if isinstance(mensaje, str):
        return f'<div class="mensaje mensaje-sistema"><div class="burbuja">{mensaje}</div></div>'

    if mensaje.get("tipo") == "SISTEMA":
        return f'<div class="mensaje mensaje-sistema"><div class="burbuja">{mensaje.get("texto", "")}</div></div>'

    nombre = mensaje.get("nombre", "Usuario")
    texto = mensaje.get("texto", "")
    lado = "propio" if nombre == nombre_usuario else "otro"

    return f"""
    <div class="mensaje {lado}">
        <div class="burbuja">
            <div class="mensaje-nombre">{nombre}</div>
            <div>{texto}</div>
        </div>
    </div>
    """


def render_sala(codigo_sala, titulo_sala, nombre_usuario, rol):
    sala = salas[codigo_sala]

    html = abrir_html("templates/sala.html")

    mensajes_chat = ""
    for mensaje in sala["mensajes"]:
        mensajes_chat += render_mensaje_html(mensaje, nombre_usuario)

    if rol == "creador":
        bloque_codigo = f"""
        <div class="room-mobile-layout">
            <div class="room-left">
                <div class="codigo" id="codigoSala">{codigo_sala}</div>

                <button type="button" onclick="copiarCodigoSala()">
                    Copiar código
                </button>
            </div>
        """

    else:
        bloque_codigo = """
        <div class="room-mobile-layout">
            <div class="room-left">
                <p><b>Te uniste a la sala</b></p>
                <div class="codigo">Invitado</div>
            </div>
        """

    participantes_html = f"""
    <div class="room-right">
        <p id="contador-participantes">Participantes: {len(sala["usuarios"])}</p>
        <div id="lista-participantes">
            {"".join([f"<p>🟢 {u}</p>" for u in sala["usuarios"]])}
        </div>
    </div>
    </div>
    """

    html = html.replace("{titulo_sala}", titulo_sala)
    html = html.replace("{nombre_sala}", sala["nombre"])
    html = html.replace("{titulo_card}", "Código de la sala" if rol == "creador" else "Participantes")
    html = html.replace("{bloque_codigo}", bloque_codigo)
    html = html.replace("{bloque_particioantes}", participantes_html)
    html = html.replace("{codigo_sala}", codigo_sala)
    html = html.replace("{mensajes_chat}", mensajes_chat)
    html = html.replace("{nombre_usuario}", nombre_usuario)
    html = html.replace("{rol_usuario}", rol)

    return html


@app.get("/", response_class=HTMLResponse)
def inicio():
    return RedirectResponse("/login", status_code=303)


@app.get("/crear-sala", response_class=HTMLResponse)
def crear_sala():
    return abrir_html("templates/crear_sala.html")


@app.post("/crear-sala", response_class=HTMLResponse)
def guardar_sala(request: Request, nombre_sala: str = Form(...), nombre_usuario: str = Form("Creador")):
    codigo_sala = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

    if "usuario" in request.session:
        nombre_usuario = request.session["usuario"]

    if not nombre_usuario.strip():
        nombre_usuario = "Creador"

    salas[codigo_sala] = {
        "nombre": nombre_sala,
        "usuarios": [nombre_usuario],
        "mensajes": [
            {"tipo": "SISTEMA", "texto": "Sistema: Bienvenido a la sala."}
        ],
        "estado": {
            "videoId": "",
            "tiempo": 0,
            "reproduciendo": False,
            "ultimaActualizacion": time.time()
        }
    }

    conexiones[codigo_sala] = []

    conexion = sqlite3.connect(DB)
    cursor = conexion.cursor()

    cursor.execute("""
    INSERT INTO historial_salas (usuario, codigo_sala, accion)
    VALUES (?, ?, ?)
    """, (nombre_usuario, codigo_sala, "Creó una sala"))

    conexion.commit()
    conexion.close()

    request.session["sala_actual"] = {
        "codigo": codigo_sala,
        "nombre": nombre_usuario,
        "rol": "creador"
    }

    return RedirectResponse(
        url=f"/sala/{codigo_sala}",
        status_code=303
    )


@app.get("/unirse-sala", response_class=HTMLResponse)
def unirse_sala():
    return abrir_html("templates/unirse_sala.html")


@app.post("/unirse-sala", response_class=HTMLResponse)
def entrar_sala(request: Request, codigo_sala: str = Form(...), nombre_usuario: str = Form("")):
    codigo_sala = codigo_sala.upper()

    if "usuario" in request.session:
        nombre_usuario = request.session["usuario"]

    if codigo_sala not in salas:
        return """
        <html>
        <head>
            <title>Sala no encontrada</title>
            <link rel="stylesheet" href="/static/style.css">
        </head>
        <body>
            <h1>Sala no encontrada</h1>
            <p>Verifica el código e intenta otra vez.</p>
            <a href="/unirse-sala"><button>Volver</button></a>
        </body>
        </html>
        """

    if not nombre_usuario.strip():
        numero = len(salas[codigo_sala]["usuarios"]) + 1
        nombre_usuario = f"Invitado {numero}"

    salas[codigo_sala]["usuarios"].append(nombre_usuario)
    salas[codigo_sala]["mensajes"].append({
        "tipo": "SISTEMA",
        "texto": f"Sistema: {nombre_usuario} entró a la sala."
    })

    conexion = sqlite3.connect(DB)
    cursor = conexion.cursor()

    cursor.execute("""
    INSERT INTO historial_salas (usuario, codigo_sala, accion)
    VALUES (?, ?, ?)
    """, (nombre_usuario, codigo_sala, "Entró a una sala"))

    conexion.commit()
    conexion.close()

    request.session["sala_actual"] = {
        "codigo": codigo_sala,
        "nombre": nombre_usuario,
        "rol": "invitado"
    }

    return RedirectResponse(
        url=f"/sala/{codigo_sala}",
        status_code=303
    )

@app.get("/sala/{codigo_sala}", response_class=HTMLResponse)
def ver_sala(request: Request, codigo_sala: str):
    codigo_sala = codigo_sala.upper()

    if codigo_sala not in salas:
        return RedirectResponse(
            url="/unirse-sala",
            status_code=303
        )

    acceso = request.session.get("sala_actual")

    if not acceso or acceso.get("codigo") != codigo_sala:
        return RedirectResponse(
            url="/unirse-sala",
            status_code=303
        )

    nombre_usuario = acceso.get("nombre", "Usuario")
    rol = acceso.get("rol", "invitado")

    titulo = "Sala creada" if rol == "creador" else "Te uniste a la sala"

    return HTMLResponse(
        render_sala(
            codigo_sala,
            titulo,
            nombre_usuario,
            rol
        )
    )

@app.get("/registro")
def ver_registro():
    html = abrir_html("templates/registro.html")
    return HTMLResponse(html)

@app.post("/registro")
def registrar(
    nombre: str = Form(...),
    correo: str = Form(...),
    password: str = Form(...)
):
    password_hash = pwd_context.hash(password)

    conexion = sqlite3.connect(DB)
    cursor = conexion.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO usuarios(nombre, correo, password)
            VALUES (?, ?, ?)
            """,
            (nombre, correo, password_hash)
        )

        conexion.commit()

    except sqlite3.IntegrityError:
        conexion.close()
        return render_error("Correo registrado", "Ese correo ya esta registrado.", "/registro")

    conexion.close()

    return RedirectResponse("/login", status_code=303)

@app.get("/perfil")
def perfil(request: Request):
    if "usuario" not in request.session:
        return RedirectResponse("/login", status_code=303)

    usuario_actual = request.session["usuario"]

    conexion = sqlite3.connect(DB)
    cursor = conexion.cursor()

    cursor.execute(
        "SELECT nombre, foto FROM usuarios WHERE nombre = ?",
        (usuario_actual,)
    )

    usuario = cursor.fetchone()

    nombre = usuario[0]
    foto = usuario[1] if usuario[1] else ""

    cursor.execute("""
    SELECT codigo_sala, accion, fecha
    FROM historial_salas
    WHERE usuario = ?
    ORDER BY id DESC
    LIMIT 10
    """, (nombre,))

    historial = cursor.fetchall()

    historial_html = ""

    for codigo_sala, accion, fecha in historial:
        historial_html += f"""
        <div class="historial-item">
            <strong>{accion}</strong>
            <span>Código: {codigo_sala}</span>
            <small>{fecha}</small>
        </div>
        """

    if not historial_html:
        historial_html = "<p class='historial-vacio'>Aún no tienes actividad.</p>"

    conexion.close()

    html = abrir_html("templates/perfil.html")
    html = html.replace("{{nombre}}", nombre)
    html = html.replace("{{foto}}", foto)
    html = html.replace("{{historial}}", historial_html)

    return HTMLResponse(html)

@app.get("/editar-perfil")
def editar_perfil(request: Request):
    if "usuario" not in request.session:
        return RedirectResponse("/login", status_code=303)

    html = abrir_html("templates/editar_perfil.html")
    return HTMLResponse(html)

@app.post("/publicar-video")
async def publicar_video(
    request: Request,
    titulo: str = Form(...),
    video: UploadFile = File(...)
):
    if "usuario" not in request.session:
        return RedirectResponse("/login", status_code=303)

    usuario = request.session["usuario"]

    carpeta_uploads = "static/uploads"
    os.makedirs(carpeta_uploads, exist_ok=True)

    nombre_archivo = f"{int(time.time())}_{video.filename}"
    ruta_archivo = os.path.join(carpeta_uploads, nombre_archivo)

    with open(ruta_archivo, "wb") as archivo:
        archivo.write(await video.read())

    conexion = sqlite3.connect(DB)
    cursor = conexion.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS videos_pycom (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT,
            titulo TEXT,
            archivo TEXT,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        INSERT INTO videos_pycom (usuario, titulo, archivo)
        VALUES (?, ?, ?)
    """, (usuario, titulo, "/" + ruta_archivo.replace("\\", "/")))

    conexion.commit()
    conexion.close()

    return RedirectResponse("/editar-perfil", status_code=303)

@app.get("/historial")
def historial(request: Request):
    if "usuario" not in request.session:
        return RedirectResponse("/login", status_code=303)

    usuario = request.session["usuario"]

    conexion = sqlite3.connect(DB)
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT codigo_sala, accion, fecha
        FROM historial_salas
        WHERE usuario = ?
        ORDER BY id DESC
        LIMIT 30
    """, (usuario,))

    registros = cursor.fetchall()
    conexion.close()

    historial_html = ""

    if registros:
        for codigo, accion, fecha in registros:
            historial_html += f"""
            <div class="card" style="margin-bottom:15px;">
                <strong>{accion}</strong><br>
                Sala: {codigo}<br>
                <small>{fecha}</small>
            </div>
            """
    else:
        historial_html = "<p>Aún no tienes historial.</p>"

    html = abrir_html("templates/historial.html")
    html = html.replace("{{historial}}", historial_html)

    return HTMLResponse(html)

@app.get("/videos")
def videos():
    conexion = sqlite3.connect(DB)
    cursor = conexion.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS videos_pycom (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT,
            titulo TEXT,
            archivo TEXT,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        SELECT usuario, titulo, archivo
        FROM videos_pycom
        ORDER BY id DESC
    """)

    videos = cursor.fetchall()
    conexion.close()

    tarjetas = ""

    if not videos:
        tarjetas = "<p>Aún no hay videos publicados.</p>"

    for usuario, titulo, archivo in videos:
        tarjetas += f"""
        <div class="video-card">
            <video controls width="100%">
                <source src="{archivo}" type="video/mp4">
            </video>

            <h3>{titulo}</h3>
            <p>👤 {usuario}</p>
        </div>
        """

    html = abrir_html("templates/videos.html")
    html = html.replace("{videos}", tarjetas)

    return HTMLResponse(html)

@app.get("/api-videos")
def api_videos():
    conexion = sqlite3.connect(DB)
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT usuario, titulo, archivo
        FROM videos_pycom
        ORDER BY id DESC
    """)

    videos = cursor.fetchall()
    conexion.close()

    return [
        {
            "usuario": usuario,
            "titulo": titulo,
            "archivo": archivo
        }
        for usuario, titulo, archivo in videos
    ]

@app.post("/borrar-historial")
def borrar_historial(request: Request):
    if "usuario" not in request.session:
        return RedirectResponse("/login", status_code=303)

    usuario = request.session["usuario"]

    conexion = sqlite3.connect(DB)
    cursor = conexion.cursor()

    cursor.execute(
        "DELETE FROM historial_salas WHERE usuario = ?",
        (usuario,)
    )

    conexion.commit()
    conexion.close()

    return RedirectResponse("/historial", status_code=303)

@app.post("/editar-perfil")
def guardar_editar_perfil(
    request: Request,
    nuevo_nombre: str = Form(""),
    nuevo_correo: str = Form(""),
    nueva_password: str = Form(""),
    confirmar_password: str = Form("")
):
    if "usuario" not in request.session:
        return RedirectResponse("/login", status_code=303)

    usuario_actual = request.session["usuario"]

    conexion = sqlite3.connect(DB)
    cursor = conexion.cursor()

    if nuevo_nombre.strip():
        cursor.execute(
            "UPDATE usuarios SET nombre = ? WHERE nombre = ?",
            (nuevo_nombre.strip(), usuario_actual)
        )
        request.session["usuario"] = nuevo_nombre.strip()
        usuario_actual = nuevo_nombre.strip()

    if nuevo_correo.strip():
        try:
            cursor.execute(
                "UPDATE usuarios SET correo = ? WHERE nombre = ?",
                (nuevo_correo.strip(), usuario_actual)
            )
        except sqlite3.IntegrityError:
            conexion.close()
            return render_error("Correo registrado", "Ese correo ya está registrado.", "/editar-perfil")

    if nueva_password.strip():
        if nueva_password != confirmar_password:
            conexion.close()
            return render_error("Contraseñas distintas", "Las contraseñas no coinciden.", "/editar-perfil")

        password_hash = pwd_context.hash(nueva_password)
        cursor.execute(
            "UPDATE usuarios SET password = ? WHERE nombre = ?",
            (password_hash, usuario_actual)
        )

    conexion.commit()
    conexion.close()

    return RedirectResponse("/perfil", status_code=303)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)

@app.post("/cambiar-foto")
async def cambiar_foto(request: Request, foto: UploadFile = File(...)):
    if "usuario" not in request.session:
        return RedirectResponse("/login", status_code=303)

    extension = os.path.splitext(foto.filename)[1].lower()
    nombre_guardado = f"{uuid.uuid4().hex}{extension}"
    ruta = os.path.join(UPLOAD_DIR, nombre_guardado)

    contenido = await foto.read()

    with open(ruta, "wb") as f:
        f.write(contenido)

    conexion = sqlite3.connect(DB)
    cursor = conexion.cursor()

    cursor.execute(
        "UPDATE usuarios SET foto = ? WHERE nombre = ?",
        (nombre_guardado, request.session["usuario"])
    )

    conexion.commit()
    conexion.close()

    return RedirectResponse("/editar-perfil", status_code=303)

@app.get("/login")
def ver_login():
    html = abrir_html("templates/login.html")
    return HTMLResponse(html)


@app.post("/login")
def login(
    request: Request,
    correo: str = Form(...),
    password: str = Form(...)
):
    conexion = sqlite3.connect(DB)
    cursor = conexion.cursor()

    cursor.execute(
        "SELECT id, nombre, correo, password FROM usuarios WHERE correo = ?",
        (correo,)
    )

    usuario = cursor.fetchone()
    conexion.close()

    if usuario is None:
        return render_error(
            "Datos incorrectos",
            "Correo o contraseña incorrectos.",
            "/login"
        )

    if not pwd_context.verify(password, usuario[3]):
        return render_error(
            "Datos incorrectos",
            "Correo o contraseña incorrectos.",
            "/login"
        )
    
    request.session["usuario"] = usuario[1]
    return RedirectResponse("/perfil", status_code=303)

@app.post("/subir-archivo")
async def subir_archivo(archivo: UploadFile = File(...)):
    extension = os.path.splitext(archivo.filename)[1].lower()
    nombre_guardado = f"{uuid.uuid4().hex}{extension}"
    ruta = os.path.join(UPLOAD_DIR, nombre_guardado)

    contenido = await archivo.read()

    with open(ruta, "wb") as f:
        f.write(contenido)

    return JSONResponse({
        "ok": True,
        "nombre": archivo.filename,
        "url": f"/static/uploads/{nombre_guardado}",
        "tipo": archivo.content_type
    })


async def enviar_a_sala(codigo_sala, mensaje):
    if codigo_sala not in conexiones:
        return

    for conexion in conexiones[codigo_sala]:
        await conexion.send_text(mensaje)


def estado_actual_sala(codigo_sala):
    estado = salas[codigo_sala]["estado"].copy()

    if estado["reproduciendo"]:
        ahora = time.time()
        estado["tiempo"] = estado["tiempo"] + (ahora - estado["ultimaActualizacion"])

    estado["tiempo"] = int(estado["tiempo"])
    return estado


@app.websocket("/ws/{codigo_sala}")
async def websocket_endpoint(codigo_sala: str, websocket: WebSocket):
    codigo_sala = codigo_sala.upper()

    nombre = websocket.query_params.get("nombre", "Usuario")
    rol = websocket.query_params.get("rol", "invitado")

    await websocket.accept()

    if codigo_sala not in conexiones:
        conexiones[codigo_sala] = []

    conexiones[codigo_sala].append(websocket)

    await websocket.send_text(json.dumps({
        "tipo": "STATE",
        "estado": estado_actual_sala(codigo_sala)
    }))

    await enviar_a_sala(codigo_sala, json.dumps({
        "tipo": "PARTICIPANTES",
        "usuarios": salas[codigo_sala]["usuarios"]
    }))

    try:
        while True:
            mensaje = await websocket.receive_text()

            try:
                data = json.loads(mensaje)
            except:
                data = {"tipo": "CHAT", "nombre": nombre, "texto": mensaje}

            tipo = data.get("tipo")

            if tipo == "CHAT":
                texto = data.get("texto", "")
                nombre_chat = data.get("nombre", nombre)

                salas[codigo_sala]["mensajes"].append({
                    "tipo": "CHAT",
                    "nombre": nombre_chat,
                    "texto": texto
                })

            if tipo == "ARCHIVO":
                salas[codigo_sala]["mensajes"].append({
                    "tipo": "ARCHIVO",
                    "nombre": data.get("nombre", nombre),
                    "texto": data.get("nombreArchivo", "Archivo enviado")
                })

            if tipo == "VIDEO":
                salas[codigo_sala]["estado"]["videoId"] = data.get("videoId", "")
                salas[codigo_sala]["estado"]["tiempo"] = 0
                salas[codigo_sala]["estado"]["reproduciendo"] = False
                salas[codigo_sala]["estado"]["ultimaActualizacion"] = time.time()

            if tipo == "PLAY":
                salas[codigo_sala]["estado"]["tiempo"] = float(data.get("tiempo", 0))
                salas[codigo_sala]["estado"]["reproduciendo"] = True
                salas[codigo_sala]["estado"]["ultimaActualizacion"] = time.time()

            if tipo == "PAUSE":
                salas[codigo_sala]["estado"]["tiempo"] = float(data.get("tiempo", 0))
                salas[codigo_sala]["estado"]["reproduciendo"] = False
                salas[codigo_sala]["estado"]["ultimaActualizacion"] = time.time()

            if tipo == "SEEK":
                salas[codigo_sala]["estado"]["tiempo"] = float(data.get("tiempo", 0))
                salas[codigo_sala]["estado"]["ultimaActualizacion"] = time.time()

            if tipo == "STATE_UPDATE":
                salas[codigo_sala]["estado"]["tiempo"] = float(data.get("tiempo", 0))
                salas[codigo_sala]["estado"]["reproduciendo"] = bool(data.get("reproduciendo", False))
                salas[codigo_sala]["estado"]["ultimaActualizacion"] = time.time()
                continue

            await enviar_a_sala(codigo_sala, json.dumps(data))

    except WebSocketDisconnect:
        if websocket in conexiones[codigo_sala]:
            conexiones[codigo_sala].remove(websocket)

        await enviar_a_sala(codigo_sala, json.dumps({
            "tipo": "PARTICIPANTES",
            "usuarios": salas[codigo_sala]["usuarios"]
        }))


@app.get("/prueba")
def prueba():
    return {"ok": True}


@app.get("/rutas")
def ver_rutas():
    return [route.path for route in app.routes]