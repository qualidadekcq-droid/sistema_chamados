from flask import Flask, request, redirect, render_template, session, send_from_directory
import json
import bcrypt
import os
import uuid
import time
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "super_secret_key_123"

ARQ_USUARIOS = "usuarios.json"
ARQ_CHAMADOS = "chamados.json"
ARQ_DEPARTAMENTOS = "departamentos.json"

UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ========================
# LOAD / SAVE
# ========================
def load(file):
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# ========================
# DADOS
# ========================
usuarios = load(ARQ_USUARIOS).get("usuarios", [])

chamados = load(ARQ_CHAMADOS)
if not isinstance(chamados, list):
    chamados = []

def get_departamentos():
    data = load(ARQ_DEPARTAMENTOS)
    return data if isinstance(data, list) else []

# ========================
# PRIORIDADE
# ========================
def priority(level):
    return {"Alta": 3, "Média": 2, "Baixa": 1}.get(level, 0)

# ========================
# AUTH
# ========================
def auth(user, senha):
    for u in usuarios:
        if u.get("usuario", "").lower() == user.lower():
            try:
                if bcrypt.checkpw(senha.encode(), u["senha_hash"].encode()):
                    return u
            except:
                return None
    return None

# ========================
# LOGIN
# ========================
@app.route("/")
def home():
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def login():
    u = auth(request.form.get("username"), request.form.get("senha"))

    if u:
        session["user"] = u["usuario"]
        session["role"] = u.get("role", "usuario")
        session["setor"] = u.get("setor", "Usuário padrão")
        session["empresa"] = "Matriz"
        return redirect("/dashboard")

    return "❌ Login inválido"

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ========================
# DASHBOARD
# ========================
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")

    empresa = session.get("empresa")
    base = [c for c in chamados if c.get("empresa") == empresa]

    return render_template(
        "dashboard.html",
        user=session.get("user"),
        role=session.get("role"),
        setor=session.get("setor"),
        total=len(base),
        abertos=len([c for c in base if c["status"] == "Aberto"]),
        andamento=len([c for c in base if c["status"] == "Em andamento"]),
        finalizados=len([c for c in base if c["status"] == "Finalizado"]),
    )

# ========================
# CHAMADOS
# ========================
@app.route("/chamados")
def chamados_view():
    if "user" not in session:
        return redirect("/")

    role = session.get("role")
    user = session.get("user")
    setor = session.get("setor")

    lista = chamados.copy()

    if role == "admin":
        lista = [c for c in lista if c.get("setor") == setor]

    elif role == "usuario":
        lista = [c for c in lista if c.get("criador") == user]

    filtro_setor = request.args.get("setor")

    if role == "master" and filtro_setor:
        lista = [c for c in lista if c.get("setor") == filtro_setor]

    lista.sort(key=lambda c: (c["status"] == "Finalizado", -c.get("created_at", 0)))

    return render_template(
        "chamados.html",
        chamados=lista,
        departamentos=get_departamentos(),
        role=role,
        filtro_setor=filtro_setor
    )

# ========================
# ABRIR CHAMADO
# ========================
@app.route("/abrir_chamado", methods=["POST"])
def abrir_chamado():
    file = request.files.get("evidencia")
    filename = None

    if file and file.filename:
        filename = str(uuid.uuid4()) + "_" + secure_filename(file.filename)
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

    chamados.append({
        "id": str(uuid.uuid4()),
        "titulo": request.form.get("titulo"),
        "descricao": request.form.get("descricao"),
        "setor": request.form.get("setor"),
        "urgencia": "Pendente",
        "prioridade": 0,
        "status": "Aberto",
        "criador": session.get("user"),
        "evidencia": filename,
        "respostas": [],
        "created_at": time.time()
    })

    save(ARQ_CHAMADOS, chamados)
    return redirect("/chamados")

# ========================
# DEFINIR URGÊNCIA
# ========================
@app.route("/definir_urgencia/<id>", methods=["POST"])
def definir_urgencia(id):
    if session.get("role") != "admin":
        return redirect("/chamados")

    nivel = request.form.get("urgencia")

    for c in chamados:
        if c["id"] == id:
            c["urgencia"] = nivel
            c["prioridade"] = priority(nivel)

    save(ARQ_CHAMADOS, chamados)
    return redirect("/chamados")

# ========================
# STATUS
# ========================
@app.route("/atender/<id>")
def atender(id):
    if session.get("role") not in ["admin", "master"]:
        return redirect("/chamados")

    for c in chamados:
        if c["id"] == id:
            c["status"] = "Em andamento"

    save(ARQ_CHAMADOS, chamados)
    return redirect("/chamados")

@app.route("/finalizar/<id>")
def finalizar(id):
    if session.get("role") not in ["admin", "master"]:
        return redirect("/chamados")

    for c in chamados:
        if c["id"] == id:
            c["status"] = "Finalizado"

    save(ARQ_CHAMADOS, chamados)
    return redirect("/chamados")

# ========================
# CHAT
# ========================
@app.route("/responder/<id>", methods=["POST"])
def responder(id):
    if session.get("role") not in ["admin", "master"]:
        return redirect("/chamados")

    for c in chamados:
        if c["id"] == id:
            c["respostas"].append({
                "autor": session.get("user"),
                "texto": request.form.get("texto"),
                "time": time.time()
            })

    save(ARQ_CHAMADOS, chamados)
    return redirect("/chamados")

# ========================
# ADMIN
# ========================
@app.route("/admin")
def admin():
    if session.get("role") not in ["master", "admin"]:
        return redirect("/dashboard")

    return render_template("painel_admin.html", usuarios=usuarios, departamentos=get_departamentos(), role=session.get("role"))

# ========================
# USUÁRIOS
# ========================
@app.route("/criar_usuario", methods=["POST"])
def criar_usuario():
    if session.get("role") not in ["master", "admin"]:
        return redirect("/dashboard")

    role = request.form.get("role")

    if session.get("role") == "admin":
        role = "usuario"

    setor = "Usuário padrão" if role == "usuario" else request.form.get("setor")

    usuarios.append({
        "usuario": request.form.get("username"),
        "senha_hash": bcrypt.hashpw(request.form.get("senha").encode(), bcrypt.gensalt()).decode(),
        "role": role,
        "setor": setor
    })

    save(ARQ_USUARIOS, {"usuarios": usuarios})
    return redirect("/admin")

@app.route("/excluir_usuario/<path:usuario>")
def excluir_usuario(usuario):
    if session.get("role") not in ["master", "admin"]:
        return redirect("/dashboard")

    global usuarios
    novo = []

    for u in usuarios:
        if session.get("role") == "admin" and u["role"] != "usuario":
            novo.append(u)
            continue

        if u["usuario"] != usuario:
            novo.append(u)

    usuarios = novo
    save(ARQ_USUARIOS, {"usuarios": usuarios})

    return redirect("/admin")

# ========================
# DEPARTAMENTOS (MASTER)
# ========================
@app.route("/add_departamento", methods=["POST"])
def add_departamento():
    if session.get("role") != "master":
        return redirect("/admin")

    deps = get_departamentos()
    nome = request.form.get("nome")

    if nome and nome not in deps:
        deps.append(nome)
        save(ARQ_DEPARTAMENTOS, deps)

    return redirect("/admin")

@app.route("/del_departamento/<path:nome>")
def del_departamento(nome):
    if session.get("role") != "master":
        return redirect("/admin")

    deps = get_departamentos()
    deps = [d for d in deps if d != nome]
    save(ARQ_DEPARTAMENTOS, deps)

    return redirect("/admin")

# ========================
# DOWNLOAD
# ========================
@app.route("/download/<filename>")
def download(filename):
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)

# ========================
# START
# ========================
if __name__ == "__main__":
    app.run(debug=True)