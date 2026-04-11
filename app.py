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

UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# ========================
# LOAD / SAVE
# ========================
def load(file):
    try:
        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except:
        return {}


def save(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# ========================
# DADOS
# ========================
users_data = load(ARQ_USUARIOS)
usuarios = users_data.get("usuarios", [])
if not isinstance(usuarios, list):
    usuarios = []

chamados = load(ARQ_CHAMADOS)
if not isinstance(chamados, list):
    chamados = []


# ========================
# PRIORIDADE
# ========================
def priority(level):
    return {"Alta": 3, "Média": 2, "Baixa": 1}.get(level, 1)


# ========================
# AUTH
# ========================
def auth(user, senha):
    for u in usuarios:
        if not isinstance(u, dict):
            continue

        if u.get("usuario") == user:
            senha_hash = u.get("senha_hash", "")
            if not senha_hash:
                return None

            try:
                if bcrypt.checkpw(
                    senha.encode("utf-8"),
                    senha_hash.encode("utf-8")
                ):
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
        session["user"] = u.get("usuario")
        session["role"] = u.get("role", "usuario")
        session["setor"] = u.get("setor", "geral")
        session["empresa"] = u.get("empresa", "Matriz")
        return redirect("/dashboard")

    return "❌ Login inválido"


# ========================
# LOGOUT
# ========================
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
        abertos=len([c for c in base if c.get("status") == "Aberto"]),
        andamento=len([c for c in base if c.get("status") == "Em andamento"]),
        finalizados=len([c for c in base if c.get("status") == "Finalizado"]),
    )


# ========================
# CHAMADOS
# ========================
@app.route("/chamados")
def view_chamados():
    if "user" not in session:
        return redirect("/")

    empresa = session.get("empresa")
    role = session.get("role")
    setor = session.get("setor")
    user = session.get("user")

    lista = [c for c in chamados if c.get("empresa") == empresa]

    if role == "admin":
        lista = [c for c in lista if c.get("setor") == setor]

    elif role != "master":
        lista = [c for c in lista if c.get("criador") == user]

    return render_template("chamados.html", chamados=lista)


# ========================
# ADMIN
# ========================
@app.route("/admin")
def admin():
    if session.get("role") not in ["master", "admin"]:
        return "❌ Acesso negado"

    return render_template("painel_admin.html", usuarios=usuarios)


# ========================
# CRIAR USUÁRIO
# ========================
@app.route("/criar_usuario", methods=["POST"])
def criar_usuario():
    if session.get("role") not in ["master", "admin"]:
        return "❌ Acesso negado"

    user = request.form.get("username")
    senha = request.form.get("senha")
    role = request.form.get("role")
    setor = request.form.get("setor")

    hash_pw = bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()

    usuarios.append({
        "usuario": user,
        "senha_hash": hash_pw,
        "role": role,
        "setor": setor
    })

    save(ARQ_USUARIOS, {"usuarios": usuarios})

    return redirect("/admin")


# ========================
# EXCLUIR USUÁRIO
# ========================
@app.route("/excluir_usuario/<usuario>")
def excluir_usuario(usuario):
    if session.get("role") not in ["master", "admin"]:
        return "❌ Acesso negado"

    global usuarios

    if session.get("role") == "admin":
        usuarios = [u for u in usuarios if not (u.get("usuario") == usuario and u.get("setor") == session.get("setor"))]
    else:
        usuarios = [u for u in usuarios if u.get("usuario") != usuario]

    save(ARQ_USUARIOS, {"usuarios": usuarios})

    return redirect("/admin")


# ========================
# RESET SENHA
# ========================
@app.route("/reset_senha/<usuario>")
def reset_senha(usuario):
    if session.get("role") not in ["master", "admin"]:
        return "❌ Acesso negado"

    nova = "123456"

    for u in usuarios:
        if u.get("usuario") == usuario:
            u["senha_hash"] = bcrypt.hashpw(nova.encode(), bcrypt.gensalt()).decode()

    save(ARQ_USUARIOS, {"usuarios": usuarios})

    return redirect("/admin")


# ========================
# CHAMADOS AÇÕES
# ========================
@app.route("/atender/<id>")
def atender(id):
    for c in chamados:
        if c.get("id") == id:
            c["status"] = "Em andamento"

    save(ARQ_CHAMADOS, chamados)
    return redirect("/chamados")


@app.route("/finalizar/<id>")
def finalizar(id):
    for c in chamados:
        if c.get("id") == id:
            c["status"] = "Finalizado"

    save(ARQ_CHAMADOS, chamados)
    return redirect("/chamados")


# ========================
# START
# ========================
if __name__ == "__main__":
    app.run(debug=True)