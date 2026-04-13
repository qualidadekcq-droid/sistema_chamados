from flask import Flask, request, redirect, render_template, session
import json, bcrypt, os, uuid, time
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static")
)

app.secret_key = "super_secret_key_123"

UPLOAD_FOLDER = os.path.join(BASE_DIR, "static/uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ARQ_USUARIOS = os.path.join(BASE_DIR, "usuarios.json")
ARQ_CHAMADOS = os.path.join(BASE_DIR, "chamados.json")
ARQ_DEPARTAMENTOS = os.path.join(BASE_DIR, "departamentos.json")


# ======================
# HELPERS
# ======================
def load(file):
    if not os.path.exists(file):
        return {} if "usuarios" in file else []
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {} if "usuarios" in file else []


def save(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def get_users():
    return load(ARQ_USUARIOS).get("usuarios", [])


def set_users(users):
    save(ARQ_USUARIOS, {"usuarios": users})


def get_chamados():
    data = load(ARQ_CHAMADOS)
    return data if isinstance(data, list) else []


def set_chamados(data):
    save(ARQ_CHAMADOS, data)


def get_departamentos():
    data = load(ARQ_DEPARTAMENTOS)
    return data if isinstance(data, list) else []


def auth(user, senha):
    for u in get_users():
        if u["usuario"].lower() == user.lower():
            if bcrypt.checkpw(senha.encode(), u["senha_hash"].encode()):
                return u
    return None


# ======================
# LOGIN
# ======================
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


# ======================
# DASHBOARD
# ======================
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")

    role = session["role"]
    setor = session["setor"]
    user = session["user"]

    chamados = get_chamados()

    if role == "admin":
        chamados = [c for c in chamados if c["setor"] == setor]
    elif role == "usuario":
        chamados = [c for c in chamados if c["criador"] == user]

    return render_template(
        "dashboard.html",
        user=user,
        role=role,
        setor=setor,
        total=len(chamados),
        abertos=len([c for c in chamados if c["status"] == "Aberto"]),
        andamento=len([c for c in chamados if c["status"] == "Em andamento"]),
        finalizados=len([c for c in chamados if c["status"] == "Finalizado"]),
    )


# ======================
# ABRIR CHAMADO
# ======================
@app.route("/abrir")
def abrir():
    if "user" not in session:
        return redirect("/")
    return render_template("abrir_chamado.html", departamentos=get_departamentos(), role=session["role"])


@app.route("/abrir_chamado", methods=["POST"])
def abrir_chamado():
    chamados = get_chamados()

    chamados.append({
        "id": str(uuid.uuid4()),
        "titulo": request.form.get("titulo"),
        "descricao": request.form.get("descricao"),
        "setor": request.form.get("setor"),
        "urgencia": "Pendente",
        "status": "Aberto",
        "criador": session["user"],
        "respostas": [],
        "created_at": time.time()
    })

    set_chamados(chamados)
    return redirect("/dashboard")


# ======================
# CHAMADOS
# ======================
@app.route("/chamados")
def chamados_view():
    if "user" not in session:
        return redirect("/")

    role = session["role"]
    setor = session["setor"]

    chamados = get_chamados()

    if role == "admin":
        chamados = [c for c in chamados if c["setor"] == setor]

    return render_template(
        "chamados.html",
        chamados=chamados,
        role=role,
        departamentos=get_departamentos()
    )


@app.route("/atender/<id>")
def atender(id):
    chamados = get_chamados()
    for c in chamados:
        if c["id"] == id:
            c["status"] = "Em andamento"
    set_chamados(chamados)
    return redirect("/chamados")


@app.route("/finalizar/<id>")
def finalizar(id):
    chamados = get_chamados()
    for c in chamados:
        if c["id"] == id:
            c["status"] = "Finalizado"
    set_chamados(chamados)
    return redirect("/chamados")


@app.route("/responder/<id>", methods=["POST"])
def responder(id):
    chamados = get_chamados()
    for c in chamados:
        if c["id"] == id:
            c["respostas"].append({
                "autor": session["user"],
                "texto": request.form.get("texto")
            })
    set_chamados(chamados)
    return redirect("/chamados")


# ======================
# ADMIN
# ======================
@app.route("/admin")
def admin():
    if session.get("role") not in ["admin", "master"]:
        return redirect("/dashboard")

    return render_template(
        "painel_admin.html",
        usuarios=get_users(),
        departamentos=get_departamentos(),
        role=session["role"]
    )


@app.route("/criar_usuario", methods=["POST"])
def criar_usuario():
    users = get_users()

    role = request.form.get("role")
    if session.get("role") == "admin":
        role = "usuario"

    users.append({
        "usuario": request.form.get("username"),
        "senha_hash": bcrypt.hashpw(request.form.get("senha").encode(), bcrypt.gensalt()).decode(),
        "role": role,
        "setor": request.form.get("setor")
    })

    set_users(users)
    return redirect("/admin")


@app.route("/excluir_usuario/<usuario>")
def excluir_usuario(usuario):
    users = [u for u in get_users() if u["usuario"] != usuario]
    set_users(users)
    return redirect("/admin")


@app.route("/reset_senha/<usuario>")
def reset_senha(usuario):
    users = get_users()

    for u in users:
        if u["usuario"] == usuario:
            u["senha_hash"] = bcrypt.hashpw("123456".encode(), bcrypt.gensalt()).decode()

    set_users(users)
    return redirect("/admin")


if __name__ == "__main__":
    app.run(debug=True)