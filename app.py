from flask import Flask, request, redirect, render_template, session, send_from_directory
import json, bcrypt, os, uuid, time
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "super_secret_key_123"

ARQ_USUARIOS = "usuarios.json"
ARQ_CHAMADOS = "chamados.json"
ARQ_DEPARTAMENTOS = "departamentos.json"

UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

def load(file):
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

usuarios = load(ARQ_USUARIOS).get("usuarios", [])
chamados = load(ARQ_CHAMADOS)
if not isinstance(chamados, list):
    chamados = []

def get_departamentos():
    data = load(ARQ_DEPARTAMENTOS)
    return data if isinstance(data, list) else []

def priority(level):
    return {"Alta": 3, "Média": 2, "Baixa": 1}.get(level, 0)

def auth(user, senha):
    for u in usuarios:
        if u["usuario"].lower() == user.lower():
            if bcrypt.checkpw(senha.encode(), u["senha_hash"].encode()):
                return u
    return None

@app.route("/")
def home():
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def login():
    u = auth(request.form.get("username"), request.form.get("senha"))
    if u:
        session["user"] = u["usuario"]
        session["role"] = u["role"]
        session["setor"] = u["setor"]
        return redirect("/dashboard")
    return "Login inválido"

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# DASHBOARD
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")

    role = session["role"]
    setor = session["setor"]
    user = session["user"]

    base = chamados.copy()

    if role == "admin":
        base = [c for c in base if c["setor"] == setor]
    elif role == "usuario":
        base = [c for c in base if c["criador"] == user]

    return render_template(
        "dashboard.html",
        user=user,
        role=role,
        setor=setor,
        total=len(base),
        abertos=len([c for c in base if c["status"] == "Aberto"]),
        andamento=len([c for c in base if c["status"] == "Em andamento"]),
        finalizados=len([c for c in base if c["status"] == "Finalizado"]),
    )

# ABRIR CHAMADO (TELA)
@app.route("/abrir")
def abrir():
    if "user" not in session:
        return redirect("/")
    return render_template("abrir_chamado.html", departamentos=get_departamentos(), role=session["role"])

# LISTA DE CHAMADOS
@app.route("/chamados")
def chamados_view():
    if "user" not in session:
        return redirect("/")

    role = session["role"]
    setor = session["setor"]

    if role == "usuario":
        return redirect("/dashboard")

    lista = chamados.copy()

    if role == "admin":
        lista = [c for c in lista if c["setor"] == setor]

    filtro = request.args.get("setor")
    if role == "master" and filtro:
        lista = [c for c in lista if c["setor"] == filtro]

    return render_template("chamados.html", chamados=lista, departamentos=get_departamentos(), role=role, filtro_setor=filtro)

# CRIAR CHAMADO
@app.route("/abrir_chamado", methods=["POST"])
def abrir_chamado():
    chamados.append({
        "id": str(uuid.uuid4()),
        "titulo": request.form.get("titulo"),
        "descricao": request.form.get("descricao"),
        "setor": request.form.get("setor"),
        "urgencia": "Pendente",
        "prioridade": 0,
        "status": "Aberto",
        "criador": session["user"],
        "respostas": [],
        "created_at": time.time()
    })
    save(ARQ_CHAMADOS, chamados)
    return redirect("/dashboard")

@app.route("/definir_urgencia/<id>", methods=["POST"])
def definir_urgencia(id):
    if session["role"] != "admin":
        return redirect("/chamados")
    for c in chamados:
        if c["id"] == id:
            nivel = request.form.get("urgencia")
            c["urgencia"] = nivel
            c["prioridade"] = priority(nivel)
    save(ARQ_CHAMADOS, chamados)
    return redirect("/chamados")

@app.route("/atender/<id>")
def atender(id):
    if session["role"] not in ["admin","master"]:
        return redirect("/chamados")
    for c in chamados:
        if c["id"] == id:
            c["status"] = "Em andamento"
    save(ARQ_CHAMADOS, chamados)
    return redirect("/chamados")

@app.route("/finalizar/<id>")
def finalizar(id):
    if session["role"] not in ["admin","master"]:
        return redirect("/chamados")
    for c in chamados:
        if c["id"] == id:
            c["status"] = "Finalizado"
    save(ARQ_CHAMADOS, chamados)
    return redirect("/chamados")

@app.route("/responder/<id>", methods=["POST"])
def responder(id):
    if session["role"] not in ["admin","master"]:
        return redirect("/chamados")
    for c in chamados:
        if c["id"] == id:
            c["respostas"].append({
                "autor": session["user"],
                "texto": request.form.get("texto")
            })
    save(ARQ_CHAMADOS, chamados)
    return redirect("/chamados")

# ADMIN
@app.route("/admin")
def admin():
    if session["role"] not in ["admin","master"]:
        return redirect("/dashboard")
    return render_template("painel_admin.html", usuarios=usuarios, departamentos=get_departamentos(), role=session["role"])

@app.route("/criar_usuario", methods=["POST"])
def criar_usuario():
    role = request.form.get("role")
    if session["role"] == "admin":
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

@app.route("/excluir_usuario/<usuario>")
def excluir_usuario(usuario):
    global usuarios
    usuarios = [u for u in usuarios if u["usuario"] != usuario]
    save(ARQ_USUARIOS, {"usuarios": usuarios})
    return redirect("/admin")

@app.route("/add_departamento", methods=["POST"])
def add_departamento():
    if session["role"] != "master":
        return redirect("/admin")
    deps = get_departamentos()
    nome = request.form.get("nome")
    if nome not in deps:
        deps.append(nome)
        save(ARQ_DEPARTAMENTOS, deps)
    return redirect("/admin")

@app.route("/del_departamento/<nome>")
def del_departamento(nome):
    if session["role"] != "master":
        return redirect("/admin")
    deps = [d for d in get_departamentos() if d != nome]
    save(ARQ_DEPARTAMENTOS, deps)
    return redirect("/admin")

if __name__ == "__main__":
    app.run(debug=True)