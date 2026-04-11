from flask import Flask, request, redirect, render_template, session
import json
import bcrypt
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "super_secret_key_123"

# ========================
# ARQUIVOS
# ========================
ARQ_USUARIOS = "usuarios.json"
ARQ_CHAMADOS = "chamados.json"

# ========================
# UPLOAD
# ========================
UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ========================
# FUNÇÕES BASE
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

users_data = load(ARQ_USUARIOS)
usuarios = users_data.get("usuarios", [])

chamados = load(ARQ_CHAMADOS)
if not isinstance(chamados, list):
    chamados = []

# ========================
# LOGIN
# ========================
def auth(user, senha):
    for u in usuarios:
        if u["usuario"] == user:
            try:
                if bcrypt.checkpw(senha.encode(), u["senha_hash"].encode()):
                    return u
            except:
                return None
    return None

# ========================
# PRIORIDADE
# ========================
def priority(level):
    return {"Alta": 3, "Média": 2, "Baixa": 1}.get(level, 1)

# ========================
# ROTAS
# ========================
@app.route("/")
def home():
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login():
    user = request.form["username"]
    senha = request.form["senha"]

    u = auth(user, senha)

    if u:
        session["user"] = u["usuario"]
        session["role"] = u.get("tipo", "usuario")
        session["setor"] = u.get("setor", "geral")
        return redirect("/dashboard")

    return "❌ Login inválido"


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")

    return render_template("dashboard.html",
        user=session["user"],
        role=session["role"],
        setor=session["setor"]
    )

# ========================
# CHAMADOS
# ========================
@app.route("/chamados")
def view_chamados():
    if "user" not in session:
        return redirect("/")

    user = session["user"]
    role = session["role"]
    setor = session["setor"]

    # garante status
    for c in chamados:
        if "status" not in c:
            c["status"] = "Aberto"

    # regras de acesso
    if user == "willian":
        lista = chamados
    elif role == "admin":
        lista = [c for c in chamados if c.get("setor") == setor]
    else:
        lista = [c for c in chamados if c.get("criador") == user]

    lista.sort(key=lambda x: x.get("prioridade", 1), reverse=True)

    return render_template("chamados.html", chamados=lista)


@app.route("/abrir_chamado", methods=["POST"])
def abrir_chamado():
    if "user" not in session:
        return redirect("/")

    file = request.files.get("evidencia")

    filename = None
    if file and file.filename != "":
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

    chamado = {
        "id": len(chamados) + 1,
        "titulo": request.form["titulo"],
        "descricao": request.form["descricao"],
        "setor": request.form["setor"],
        "urgencia": request.form["urgencia"],
        "prioridade": priority(request.form["urgencia"]),
        "status": "Aberto",
        "criador": session["user"],
        "evidencia": filename
    }

    chamados.append(chamado)
    save(ARQ_CHAMADOS, chamados)

    return redirect("/chamados")

# ========================
# ADMIN MASTER
# ========================
@app.route("/admin")
def admin():
    if session.get("user") != "willian":
        return "❌ Acesso negado"

    return render_template("admin.html", usuarios=usuarios)


@app.route("/criar_usuario", methods=["POST"])
def criar_usuario():
    if session.get("user") != "willian":
        return "❌ Acesso negado"

    user = request.form["username"]
    senha = request.form["senha"]
    role = request.form["tipo"]
    setor = request.form["setor"]

    hash_pw = bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()

    usuarios.append({
        "usuario": user,
        "senha_hash": hash_pw,
        "tipo": role,
        "setor": setor
    })

    save(ARQ_USUARIOS, {"usuarios": usuarios})

    return redirect("/admin")

# ========================
# AÇÕES
# ========================
@app.route("/atender/<int:id>")
def atender(id):
    if "user" not in session:
        return redirect("/")

    for c in chamados:
        if c["id"] == id:
            c["status"] = "Em andamento"

    save(ARQ_CHAMADOS, chamados)
    return redirect("/chamados")


@app.route("/finalizar/<int:id>")
def finalizar(id):
    if "user" not in session:
        return redirect("/")

    user = session["user"]
    role = session["role"]

    for c in chamados:
        if c["id"] == id:
            if user == "willian" or role == "admin":
                c["status"] = "Finalizado"

    save(ARQ_CHAMADOS, chamados)
    return redirect("/chamados")


if __name__ == "__main__":
    app.run(debug=True)