from flask import Flask, request, redirect, render_template, session, send_from_directory, jsonify
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
# LOAD SEGURO (ANTI QUEBRA)
# ========================
def load(file):
    try:
        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)

            if isinstance(data, dict):
                return data
            if isinstance(data, list):
                return data
            return {}

    except:
        return {} if "usuarios" in file else []


def save(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# ========================
# USUÁRIOS / CHAMADOS
# ========================
users_data = load(ARQ_USUARIOS)
usuarios = users_data.get("usuarios", []) if isinstance(users_data, dict) else []

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
            senha_hash = u.get("senha_hash")
            if not senha_hash:
                return None

            try:
                if bcrypt.checkpw(senha.encode(), senha_hash.encode()):
                    return u
            except:
                return None

    return None


# ========================
# HOME
# ========================
@app.route("/")
def home():
    return render_template("login.html")


# ========================
# LOGIN
# ========================
@app.route("/login", methods=["POST"])
def login():
    user = request.form.get("username")
    senha = request.form.get("senha")

    u = auth(user, senha)

    if u:
        session["user"] = u.get("usuario")
        session["role"] = u.get("role", "usuario")
        session["setor"] = u.get("setor", "geral")

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

    base = chamados if isinstance(chamados, list) else []

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
# CHAMADOS (SEM FILTRO QUEBRADO)
# ========================
@app.route("/chamados")
def view_chamados():
    if "user" not in session:
        return redirect("/")

    role = session.get("role")
    setor = session.get("setor")
    user = session.get("user")

    lista = chamados if isinstance(chamados, list) else []

    # filtros seguros
    if role == "admin":
        lista = [c for c in lista if c.get("setor") == setor]

    elif role != "master":
        lista = [c for c in lista if c.get("criador") == user]

    return render_template("chamados.html", chamados=lista)


# ========================
# CRIAR CHAMADO
# ========================
@app.route("/abrir_chamado", methods=["POST"])
def abrir_chamado():
    if "user" not in session:
        return redirect("/")

    file = request.files.get("evidencia")

    filename = None
    if file and file.filename:
        filename = secure_filename(file.filename)
        filename = str(uuid.uuid4()) + "_" + filename
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

    novo = {
        "id": str(uuid.uuid4()),
        "titulo": request.form.get("titulo"),
        "descricao": request.form.get("descricao"),
        "setor": request.form.get("setor"),
        "urgencia": request.form.get("urgencia"),
        "prioridade": priority(request.form.get("urgencia")),
        "status": "Aberto",
        "criador": session.get("user"),
        "evidencia": filename,
        "respostas": [],
        "created_at": time.time()
    }

    chamados.append(novo)
    save(ARQ_CHAMADOS, chamados)

    return redirect("/chamados")


# ========================
# CHAT
# ========================
@app.route("/responder/<id>", methods=["POST"])
def responder(id):
    if "user" not in session:
        return redirect("/")

    texto = request.form.get("texto")
    file = request.files.get("anexo")

    filename = None
    if file and file.filename:
        filename = secure_filename(file.filename)
        filename = str(uuid.uuid4()) + "_" + filename
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

    for c in chamados:
        if c.get("id") == id:
            if "respostas" not in c:
                c["respostas"] = []

            c["respostas"].append({
                "autor": session.get("user"),
                "texto": texto,
                "anexo": filename,
                "time": time.time()
            })

    save(ARQ_CHAMADOS, chamados)
    return redirect("/chamados")


# ========================
# STATUS
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

    usuarios.append({
        "usuario": request.form.get("username"),
        "senha_hash": bcrypt.hashpw(request.form.get("senha").encode(), bcrypt.gensalt()).decode(),
        "role": request.form.get("role"),
        "setor": request.form.get("setor")
    })

    save(ARQ_USUARIOS, {"usuarios": usuarios})
    return redirect("/admin")


# ========================
# EXCLUIR USUÁRIO
# ========================
@app.route("/excluir_usuario/<usuario>")
def excluir_usuario(usuario):
    global usuarios

    if session.get("role") not in ["master", "admin"]:
        return "❌ Acesso negado"

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

    for u in usuarios:
        if u.get("usuario") == usuario:
            u["senha_hash"] = bcrypt.hashpw("123456".encode(), bcrypt.gensalt()).decode()

    save(ARQ_USUARIOS, {"usuarios": usuarios})
    return redirect("/admin")


# ========================
# DOWNLOAD
# ========================
@app.route("/download/<filename>")
def download(filename):
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)


# ========================
# DEBUG (REMOVE DEPOIS SE QUISER)
# ========================
@app.route("/debug")
def debug():
    return jsonify(chamados)


if __name__ == "__main__":
    app.run(debug=True)