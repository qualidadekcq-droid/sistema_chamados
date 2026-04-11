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
            hash_pw = u.get("senha_hash", "")
            if not hash_pw:
                return None

            try:
                if bcrypt.checkpw(
                    senha.encode("utf-8"),
                    hash_pw.encode("utf-8")
                ):
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
        session["user"] = u["usuario"]
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
# ABRIR CHAMADO
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

    chamado = {
        "id": str(uuid.uuid4()),
        "empresa": session.get("empresa"),
        "titulo": request.form.get("titulo"),
        "descricao": request.form.get("descricao"),
        "setor": request.form.get("setor"),
        "urgencia": request.form.get("urgencia"),
        "prioridade": priority(request.form.get("urgencia")),
        "status": "Aberto",
        "criador": session.get("user"),
        "evidencia": filename,
        "created_at": time.time()
    }

    chamados.append(chamado)
    save(ARQ_CHAMADOS, chamados)

    return redirect("/chamados")


# ========================
# DOWNLOAD
# ========================
@app.route("/download/<filename>")
def download(filename):
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)


# ========================
# ATENDER / FINALIZAR
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
# ADMIN PANEL
# ========================
@app.route("/admin")
def admin():
    if session.get("role") != "master":
        return redirect("/dashboard")

    return render_template("painel_admin.html", usuarios=usuarios)


# ========================
# CRIAR USUÁRIO
# ========================
@app.route("/criar_usuario", methods=["POST"])
def criar_usuario():
    if session.get("role") != "master":
        return redirect("/dashboard")

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
# EXCLUIR USUÁRIO (MASTER OU ADMIN SETOR)
# ========================
@app.route("/excluir_usuario/<usuario>")
def excluir_usuario(usuario):
    if session.get("role") not in ["master", "admin"]:
        return redirect("/dashboard")

    global usuarios

    novo = []
    for u in usuarios:
        if u["usuario"] == usuario:
            # admin só pode excluir do próprio setor
            if session.get("role") == "admin" and u.get("setor") != session.get("setor"):
                novo.append(u)
                continue
            continue
        novo.append(u)

    usuarios = novo
    save(ARQ_USUARIOS, {"usuarios": usuarios})

    return redirect("/admin")


# ========================
# START
# ========================
if __name__ == "__main__":
    app.run(debug=True)