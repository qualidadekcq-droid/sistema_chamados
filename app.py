from flask import Flask, request, redirect, render_template, session, send_from_directory
import json
import bcrypt
import os
from werkzeug.utils import secure_filename
import time
import uuid

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
            return json.load(f)
    except:
        return []

def save(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

usuarios = load(ARQ_USUARIOS)
chamados = load(ARQ_CHAMADOS)

# ========================
# AUTH
# ========================
def auth(user, senha):
    for u in usuarios:
        if u["usuario"] == user:
            if bcrypt.checkpw(senha.encode(), u["senha_hash"].encode()):
                return u
    return None

# ========================
# PRIORIDADE
# ========================
def priority(level):
    return {"Alta": 3, "Média": 2, "Baixa": 1}.get(level, 1)

# ========================
# NOTIFICAÇÕES
# ========================
def get_notificacoes(user, role, setor):
    notif = []

    for c in chamados:
        if c.get("status") == "Aberto":
            if user == "willian" or (role == "admin" and c.get("setor") == setor):
                notif.append(f"🆕 Novo chamado: {c['titulo']}")

        if c.get("status") == "Em andamento" and c.get("criador") == user:
            notif.append(f"🔵 Em andamento: {c['titulo']}")

        if c.get("status") == "Finalizado" and c.get("criador") == user:
            notif.append(f"🟢 Finalizado: {c['titulo']}")

    return notif[:10]

# ========================
# LOGIN
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
        session["empresa"] = u.get("empresa", "default")
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

    empresa = session["empresa"]
    user = session["user"]
    role = session["role"]
    setor = session["setor"]

    base = [c for c in chamados if c.get("empresa") == empresa]

    notificacoes = get_notificacoes(user, role, setor)

    return render_template(
        "dashboard.html",
        user=user,
        role=role,
        setor=setor,
        total=len(base),
        abertos=len([c for c in base if c["status"] == "Aberto"]),
        andamento=len([c for c in base if c["status"] == "Em andamento"]),
        finalizados=len([c for c in base if c["status"] == "Finalizado"]),
        notificacoes=notificacoes
    )

# ========================
# CHAMADOS (KANBAN)
# ========================
@app.route("/chamados")
def chamados_view():
    if "user" not in session:
        return redirect("/")

    empresa = session["empresa"]
    user = session["user"]
    role = session["role"]
    setor = session["setor"]

    lista = [c for c in chamados if c.get("empresa") == empresa]

    if role == "admin" and user != "willian":
        lista = [c for c in lista if c.get("setor") == setor]
    elif role != "admin":
        lista = [c for c in lista if c.get("criador") == user]

    lista.sort(key=lambda x: x.get("prioridade", 1), reverse=True)

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
        "empresa": session["empresa"],
        "filial": request.form["filial"],
        "titulo": request.form["titulo"],
        "descricao": request.form["descricao"],
        "setor": request.form["setor"],
        "urgencia": request.form["urgencia"],
        "prioridade": priority(request.form["urgencia"]),
        "status": "Aberto",
        "criador": session["user"],
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
# AÇÕES
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
# ADMIN
# ========================
@app.route("/admin")
def admin():
    if session.get("user") != "willian":
        return "❌ Acesso negado"

    return render_template("admin.html", usuarios=usuarios)

# ========================
# START
# ========================
if __name__ == "__main__":
    app.run(debug=True)