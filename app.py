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

chamados_data = load(ARQ_CHAMADOS)
chamados = chamados_data if isinstance(chamados_data, list) else []


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
        if u.get("usuario") == user:
            try:
                if bcrypt.checkpw(
                    senha.encode(),
                    u.get("senha_hash", "").encode()
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
        session["user"] = u["usuario"]
        session["role"] = u.get("role", "usuario").lower()
        session["setor"] = u.get("setor", "geral")

        return redirect("/dashboard")

    return "Login inválido"


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

    user = session["user"]

    base = [c for c in chamados if c.get("criador") == user or session.get("role") in ["admin", "master"]]

    return render_template(
        "dashboard.html",
        user=user,
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
def chamados_view():
    if "user" not in session:
        return redirect("/")

    user = session["user"]
    role = session["role"]
    setor = session["setor"]

    if role == "master":
        lista = chamados
    elif role == "admin":
        lista = [c for c in chamados if c.get("setor") == setor]
    else:
        lista = [c for c in chamados if c.get("criador") == user]

    return render_template("chamados.html", chamados=lista)


# ========================
# ABRIR CHAMADO (COM CHAT INICIAL)
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
        "titulo": request.form.get("titulo"),
        "descricao": request.form.get("descricao"),
        "setor": request.form.get("setor"),
        "status": "Aberto",
        "criador": session["user"],
        "anexo": filename,
        "respostas": [],
        "created_at": time.time()
    }

    chamados.append(chamado)
    save(ARQ_CHAMADOS, chamados)

    return redirect("/chamados")


# ========================
# CHAT NO CHAMADO
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
        if c["id"] == id:
            c["respostas"].append({
                "autor": session["user"],
                "texto": texto,
                "anexo": filename,
                "data": time.time()
            })

    save(ARQ_CHAMADOS, chamados)
    return redirect("/chamados")


# ========================
# ADMIN - USUÁRIOS
# ========================
@app.route("/admin")
def admin():
    if session.get("role") not in ["master", "admin"]:
        return redirect("/dashboard")

    return render_template("painel_admin.html", usuarios=usuarios)


@app.route("/criar_usuario", methods=["POST"])
def criar_usuario():
    if session.get("role") not in ["master", "admin"]:
        return redirect("/dashboard")

    role = request.form.get("role")

    if session.get("role") == "admin" and role == "master":
        return "Sem permissão"

    senha = request.form.get("senha")

    usuarios.append({
        "usuario": request.form.get("username"),
        "senha_hash": bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode(),
        "role": role,
        "setor": request.form.get("setor")
    })

    save(ARQ_USUARIOS, {"usuarios": usuarios})

    return redirect("/admin")


# ========================
# EXCLUIR USUÁRIO
# ========================
@app.route("/excluir_usuario/<user>")
def excluir_usuario(user):
    if session.get("role") == "master":
        pass
    elif session.get("role") == "admin":
        usuarios[:] = [u for u in usuarios if u["usuario"] != user and u.get("setor") != session.get("setor")]
    else:
        return redirect("/dashboard")

    save(ARQ_USUARIOS, {"usuarios": usuarios})
    return redirect("/admin")


# ========================
# START
# ========================
if __name__ == "__main__":
    app.run(debug=True)