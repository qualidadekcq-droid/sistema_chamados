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
chamados = load(ARQ_CHAMADOS)

if not isinstance(usuarios, list):
    usuarios = []

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
            try:
                return bcrypt.checkpw(
                    senha.encode(),
                    u.get("senha_hash", "").encode()
                ) and u
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

    chamados.append({
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
    })

    save(ARQ_CHAMADOS, chamados)

    return redirect("/chamados")


# ========================
# ADMIN PANEL
# ========================
@app.route("/admin")
def admin():
    if session.get("role") != "master":
        return "❌ Acesso negado"

    return render_template("painel_admin.html", usuarios=usuarios)


# ========================
# CRIAR USUÁRIO (FIXED FORM)
# ========================
@app.route("/criar_usuario", methods=["POST"])
def criar_usuario():
    if session.get("role") != "master":
        return "❌ Acesso negado"

    user = request.form.get("username")
    senha = request.form.get("senha")

    # FIX: seu HTML manda "tipo", não "role"
    role = request.form.get("tipo")
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
# START
# ========================
if __name__ == "__main__":
    app.run(debug=True)