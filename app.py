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

UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

<<<<<<< HEAD
# 🔥 NOVO: DEPARTAMENTOS CENTRALIZADOS
DEPARTAMENTOS = [
    "TI",
    "RH",
    "Departamento Pessoal",
    "Fiscal",
    "Financeiro",
    "Compras",
    "Gerência Comercial",
    "Gerência Administrativa",
    "Marketing",
    "Qualidade",
]
=======
>>>>>>> bfb93420f2cdc7449051580ce13458bae6ae345e

# ========================
# LOAD / SAVE
# ========================
def load(file):
    try:
        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, (dict, list)) else {}
    except:
        return {}

<<<<<<< HEAD
=======

>>>>>>> bfb93420f2cdc7449051580ce13458bae6ae345e
def save(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

<<<<<<< HEAD
=======

>>>>>>> bfb93420f2cdc7449051580ce13458bae6ae345e
# ========================
# DADOS
# ========================
users_data = load(ARQ_USUARIOS)
usuarios = users_data.get("usuarios", []) if isinstance(users_data, dict) else []

chamados = load(ARQ_CHAMADOS)
if not isinstance(chamados, list):
    chamados = []

<<<<<<< HEAD
=======

>>>>>>> bfb93420f2cdc7449051580ce13458bae6ae345e
# ========================
# PRIORIDADE
# ========================
def priority(level):
<<<<<<< HEAD
    return {"Alta": 3, "Média": 2, "Baixa": 1}.get(level, 2)

# ========================
# AUTH
=======
    return {"Alta": 3, "Média": 2, "Baixa": 1}.get(level, 1)


# ========================
# AUTH (case insensitive)
>>>>>>> bfb93420f2cdc7449051580ce13458bae6ae345e
# ========================
def auth(user, senha):
    for u in usuarios:
        if u.get("usuario", "").lower() == user.lower():
            try:
                if bcrypt.checkpw(
                    senha.encode(),
                    u.get("senha_hash", "").encode()
                ):
                    return u
            except:
                return None
    return None

<<<<<<< HEAD
=======

>>>>>>> bfb93420f2cdc7449051580ce13458bae6ae345e
# ========================
# LOGIN
# ========================
@app.route("/")
def home():
    return render_template("login.html")

<<<<<<< HEAD
=======

>>>>>>> bfb93420f2cdc7449051580ce13458bae6ae345e
@app.route("/login", methods=["POST"])
def login():
    user = request.form.get("username")
    senha = request.form.get("senha")

    u = auth(user, senha)

    if u:
        session["user"] = u["usuario"]
        session["role"] = u.get("role", "usuario")
<<<<<<< HEAD
        session["setor"] = u.get("setor", "Usuário padrão")
=======
        session["setor"] = u.get("setor", "geral")
>>>>>>> bfb93420f2cdc7449051580ce13458bae6ae345e
        session["empresa"] = u.get("empresa", "Matriz")
        return redirect("/dashboard")

    return "❌ Login inválido"

<<<<<<< HEAD
=======

>>>>>>> bfb93420f2cdc7449051580ce13458bae6ae345e
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

<<<<<<< HEAD
=======

>>>>>>> bfb93420f2cdc7449051580ce13458bae6ae345e
# ========================
# DASHBOARD
# ========================
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")

    empresa = session.get("empresa")
<<<<<<< HEAD
=======

>>>>>>> bfb93420f2cdc7449051580ce13458bae6ae345e
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

<<<<<<< HEAD
# ========================
# CHAMADOS
=======

# ========================
# CHAMADOS (ORDENADO)
>>>>>>> bfb93420f2cdc7449051580ce13458bae6ae345e
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
<<<<<<< HEAD
    elif role != "master":
        lista = [c for c in lista if c.get("criador") == user]

    lista.sort(key=lambda c: (c["status"] == "Finalizado", -c.get("created_at", 0)))

    return render_template("chamados.html", chamados=lista, departamentos=DEPARTAMENTOS)
=======

    elif role != "master":
        lista = [c for c in lista if c.get("criador") == user]

    def ordem(c):
        status = c.get("status")
        prioridade = 0 if status != "Finalizado" else 1
        return (prioridade, -c.get("created_at", 0))

    lista.sort(key=ordem)

    return render_template("chamados.html", chamados=lista)

>>>>>>> bfb93420f2cdc7449051580ce13458bae6ae345e

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

<<<<<<< HEAD
    # 🔥 URGÊNCIA CONTROLADA
    if session.get("role") == "admin":
        urgencia = request.form.get("urgencia")
    else:
        urgencia = "Média"

=======
>>>>>>> bfb93420f2cdc7449051580ce13458bae6ae345e
    chamado = {
        "id": str(uuid.uuid4()),
        "empresa": session.get("empresa"),
        "titulo": request.form.get("titulo"),
        "descricao": request.form.get("descricao"),
        "setor": request.form.get("setor"),
<<<<<<< HEAD
        "urgencia": urgencia,
        "prioridade": priority(urgencia),
=======
        "urgencia": request.form.get("urgencia"),
        "prioridade": priority(request.form.get("urgencia")),
>>>>>>> bfb93420f2cdc7449051580ce13458bae6ae345e
        "status": "Aberto",
        "criador": session.get("user"),
        "evidencia": filename,
        "respostas": [],
        "created_at": time.time()
    }

    chamados.append(chamado)
    save(ARQ_CHAMADOS, chamados)

    return redirect("/chamados")

<<<<<<< HEAD
=======

>>>>>>> bfb93420f2cdc7449051580ce13458bae6ae345e
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

<<<<<<< HEAD
=======

>>>>>>> bfb93420f2cdc7449051580ce13458bae6ae345e
@app.route("/finalizar/<id>")
def finalizar(id):
    for c in chamados:
        if c["id"] == id:
            c["status"] = "Finalizado"
    save(ARQ_CHAMADOS, chamados)
    return redirect("/chamados")

<<<<<<< HEAD
=======

>>>>>>> bfb93420f2cdc7449051580ce13458bae6ae345e
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
        filename = str(uuid.uuid4()) + "_" + secure_filename(file.filename)
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

    for c in chamados:
        if c["id"] == id:
            c.setdefault("respostas", []).append({
                "autor": session.get("user"),
                "texto": texto,
                "anexo": filename,
                "time": time.time()
            })

    save(ARQ_CHAMADOS, chamados)
    return redirect("/chamados")

<<<<<<< HEAD
# ========================
# ADMIN
=======

# ========================
# ADMIN (ADICIONADO)
>>>>>>> bfb93420f2cdc7449051580ce13458bae6ae345e
# ========================
@app.route("/admin")
def admin():
    if "user" not in session:
        return redirect("/")

    if session.get("role") not in ["master", "admin"]:
        return redirect("/dashboard")

<<<<<<< HEAD
    return render_template("painel_admin.html", usuarios=usuarios, departamentos=DEPARTAMENTOS)
=======
    return render_template("painel_admin.html", usuarios=usuarios)

>>>>>>> bfb93420f2cdc7449051580ce13458bae6ae345e

@app.route("/criar_usuario", methods=["POST"])
def criar_usuario():
    if session.get("role") not in ["master", "admin"]:
        return redirect("/dashboard")

    user = request.form.get("username")
    senha = request.form.get("senha")
    role = request.form.get("role")
<<<<<<< HEAD

    # 🔥 USUÁRIO PADRÃO AUTOMÁTICO
    if role == "usuario":
        setor = "Usuário padrão"
    else:
        setor = request.form.get("setor")
=======
    setor = request.form.get("setor")
>>>>>>> bfb93420f2cdc7449051580ce13458bae6ae345e

    hash_pw = bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()

    usuarios.append({
        "usuario": user,
        "senha_hash": hash_pw,
        "role": role,
        "setor": setor
    })

    save(ARQ_USUARIOS, {"usuarios": usuarios})
<<<<<<< HEAD
    return redirect("/admin")

=======

    return redirect("/admin")


>>>>>>> bfb93420f2cdc7449051580ce13458bae6ae345e
@app.route("/excluir_usuario/<usuario>")
def excluir_usuario(usuario):
    if session.get("role") not in ["master", "admin"]:
        return redirect("/dashboard")

    global usuarios
<<<<<<< HEAD
    usuarios = [u for u in usuarios if u["usuario"] != usuario]

    save(ARQ_USUARIOS, {"usuarios": usuarios})
    return redirect("/admin")

@app.route("/reset_senha/<usuario>")
def reset_senha(usuario):
=======

    if session.get("role") == "admin":
        usuarios = [u for u in usuarios if not (u["usuario"] == usuario and u["setor"] == session.get("setor"))]
    else:
        usuarios = [u for u in usuarios if u["usuario"] != usuario]

    save(ARQ_USUARIOS, {"usuarios": usuarios})

    return redirect("/admin")


@app.route("/reset_senha/<usuario>")
def reset_senha(usuario):
    if session.get("role") not in ["master", "admin"]:
        return redirect("/dashboard")

>>>>>>> bfb93420f2cdc7449051580ce13458bae6ae345e
    for u in usuarios:
        if u["usuario"] == usuario:
            u["senha_hash"] = bcrypt.hashpw("123456".encode(), bcrypt.gensalt()).decode()

    save(ARQ_USUARIOS, {"usuarios": usuarios})
<<<<<<< HEAD
    return redirect("/admin")

=======

    return redirect("/admin")


>>>>>>> bfb93420f2cdc7449051580ce13458bae6ae345e
# ========================
# DOWNLOAD
# ========================
@app.route("/download/<filename>")
def download(filename):
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)

<<<<<<< HEAD
=======

>>>>>>> bfb93420f2cdc7449051580ce13458bae6ae345e
# ========================
# START
# ========================
if __name__ == "__main__":
    app.run(debug=True)