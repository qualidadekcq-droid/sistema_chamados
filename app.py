from flask import Flask, request, redirect, render_template, session, send_from_directory
import json
import bcrypt
import os
import uuid
import time
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "super_secret_key_123"

# ========================
# ARQUIVOS
# ========================
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
# DEPARTAMENTOS
# ========================
def get_departamentos():
    data = load(ARQ_DEPARTAMENTOS)
    return data if isinstance(data, list) else []

# ========================
# DADOS
# ========================
users_data = load(ARQ_USUARIOS)
usuarios = users_data.get("usuarios", [])

chamados = load(ARQ_CHAMADOS)
if not isinstance(chamados, list):
    chamados = []

# ========================
# PRIORIDADE
# ========================
def priority(level):
    return {"Alta": 3, "Média": 2, "Baixa": 1}.get(level, 2)

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
    user = request.form.get("username")
    senha = request.form.get("senha")

    u = auth(user, senha)

    if u:
        session["user"] = u["usuario"]
        session["role"] = u.get("role", "usuario")
        session["setor"] = u.get("setor", "Usuário padrão")
        session["empresa"] = u.get("empresa", "Matriz")
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

    empresa = session.get("empresa")
    role = session.get("role")
    user = session.get("user")
    setor = session.get("setor")

    lista = [c for c in chamados if c.get("empresa") == empresa]

    if role == "admin":
        lista = [c for c in lista if c.get("setor") == setor]
    elif role != "master":
        lista = [c for c in lista if c.get("criador") == user]

    lista.sort(key=lambda c: (c["status"] == "Finalizado", -c.get("created_at", 0)))

    return render_template("chamados.html", chamados=lista, departamentos=get_departamentos(), role=role)

# ========================
# ABRIR CHAMADO
# ========================
@app.route("/abrir_chamado", methods=["POST"])
def abrir_chamado():
    if "user" not in session:
        return redirect("/")

    file = request.files.get("evidencia")
    filename = None

    if file and file.filename:
        filename = str(uuid.uuid4()) + "_" + secure_filename(file.filename)
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

    urgencia = request.form.get("urgencia") if session.get("role") == "admin" else "Média"

    chamado = {
        "id": str(uuid.uuid4()),
        "empresa": session.get("empresa"),
        "titulo": request.form.get("titulo"),
        "descricao": request.form.get("descricao"),
        "setor": request.form.get("setor"),
        "urgencia": urgencia,
        "prioridade": priority(urgencia),
        "status": "Aberto",
        "criador": session.get("user"),
        "evidencia": filename,
        "respostas": [],
        "created_at": time.time()
    }

    chamados.append(chamado)
    save(ARQ_CHAMADOS, chamados)

    return redirect("/chamados")

# ========================
# STATUS
# ========================
@app.route("/atender/<id>")
def atender(id):
    for c in chamados:
        if c["id"] == id:
            c["status"] = "Em andamento"
    save(ARQ_CHAMADOS, chamados)
    return redirect("/chamados")

@app.route("/finalizar/<id>")
def finalizar(id):
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
    texto = request.form.get("texto")

    for c in chamados:
        if c["id"] == id:
            c.setdefault("respostas", []).append({
                "autor": session.get("user"),
                "texto": texto,
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

    return render_template("painel_admin.html", usuarios=usuarios, departamentos=get_departamentos())

# ========================
# USUÁRIOS
# ========================
@app.route("/criar_usuario", methods=["POST"])
def criar_usuario():
    user = request.form.get("username")
    senha = request.form.get("senha")
    role = request.form.get("role")

    setor = "Usuário padrão" if role == "usuario" else request.form.get("setor")

    hash_pw = bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()

    usuarios.append({
        "usuario": user,
        "senha_hash": hash_pw,
        "role": role,
        "setor": setor
    })

    save(ARQ_USUARIOS, {"usuarios": usuarios})
    return redirect("/admin")

# 🔥 EXCLUSÃO CORRIGIDA
@app.route("/excluir_usuario/<path:usuario>")
def excluir_usuario(usuario):
    global usuarios
    usuarios = [u for u in usuarios if u["usuario"] != usuario]
    save(ARQ_USUARIOS, {"usuarios": usuarios})
    return redirect("/admin")

@app.route("/reset_senha/<usuario>")
def reset_senha(usuario):
    for u in usuarios:
        if u["usuario"] == usuario:
            u["senha_hash"] = bcrypt.hashpw("123456".encode(), bcrypt.gensalt()).decode()

    save(ARQ_USUARIOS, {"usuarios": usuarios})
    return redirect("/admin")

# ========================
# DEPARTAMENTOS
# ========================
@app.route("/add_departamento", methods=["POST"])
def add_departamento():
    nome = request.form.get("nome")
    deps = get_departamentos()

    if nome and nome not in deps:
        deps.append(nome)
        save(ARQ_DEPARTAMENTOS, deps)

    return redirect("/admin")

@app.route("/del_departamento/<path:nome>")
def del_departamento(nome):
    deps = get_departamentos()
    deps = [d for d in deps if d != nome]
    save(ARQ_DEPARTAMENTOS, deps)
    return redirect("/admin")

# ========================
# START
# ========================
if __name__ == "__main__":
    app.run(debug=True)