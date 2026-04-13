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
        return {"usuarios": []} if "usuarios" in file else []
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"usuarios": []} if "usuarios" in file else []


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
        if u.get("usuario", "").lower() == user.lower():
            if bcrypt.checkpw(senha.encode(), u["senha_hash"].encode()):
                return u
    return None


# ======================
# LOGIN
# ======================
@app.route("/")
def home():
    if "user" in session:
        return redirect("/dashboard")
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login():
    u = auth(request.form.get("username"), request.form.get("senha"))

    if u:
        session["user"] = u["usuario"]
        session["role"] = u["role"]
        session["setor"] = u["setor"]

        if u.get("trocar_senha"):
            session["trocar_senha"] = True
            return redirect("/trocar_senha")

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
    user = session["user"]
    setor = session.get("setor", "")

    chamados = get_chamados()

    if role == "usuario":
        chamados = [c for c in chamados if c.get("criador") == user]

    elif role == "admin":
        chamados = [
            c for c in chamados
            if c.get("setor", "").lower() == setor.lower()
        ]

    return render_template(
        "dashboard.html",
        user=user,
        role=role,
        setor=setor,
        total=len(chamados),
        abertos=len([c for c in chamados if c.get("status") == "Aberto"]),
        andamento=len([c for c in chamados if c.get("status") == "Em andamento"]),
        finalizados=len([c for c in chamados if c.get("status") == "Finalizado"]),
    )


# ======================
# ABRIR CHAMADO
# ======================
@app.route("/abrir")
def abrir():
    if "user" not in session:
        return redirect("/")
    return render_template("abrir_chamado.html", departamentos=get_departamentos())


@app.route("/abrir_chamado", methods=["POST"])
def abrir_chamado():
    chamados = get_chamados()

    file = request.files.get("anexo")
    filename = None

    if file and file.filename:
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

    prioridade = request.form.get("prioridade", "Normal")
    titulo = request.form.get("titulo")
    setor_nome = request.form.get("setor")

    # buscar setor com múltiplos emails
    emails_destino = []

    for d in get_departamentos():
        if isinstance(d, dict) and d["nome"] == setor_nome:
            emails_destino = d.get("emails", [])

    assunto = f"[{prioridade.upper()}] {titulo}"

    chamados.append({
        "id": str(uuid.uuid4()),
        "titulo": assunto,
        "descricao": request.form.get("descricao"),
        "setor": setor_nome,
        "prioridade": prioridade,
        "status": "Aberto",
        "criador": session["user"],
        "anexo": filename,
        "respostas": [],
        "created_at": time.time()
    })

    set_chamados(chamados)

    # 🔥 AQUI FUTURO ENVIO EMAIL (loop todos emails do setor)
    # for email in emails_destino:
    #     enviar_email(email, assunto, descricao)

    return redirect("/dashboard")


# ======================
# CHAMADOS
# ======================
@app.route("/chamados")
def chamados_view():
    if "user" not in session:
        return redirect("/")

    role = session["role"]
    user = session["user"]
    setor = session.get("setor", "")

    chamados = get_chamados()

    if role == "usuario":
        chamados = [c for c in chamados if c.get("criador") == user]

    elif role == "admin":
        chamados = [
            c for c in chamados
            if c.get("setor", "").lower() == setor.lower()
        ]

    return render_template(
        "chamados.html",
        chamados=chamados,
        role=role,
        departamentos=get_departamentos()
    )


# ======================
# AÇÕES
# ======================
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


# ======================
# USUÁRIOS
# ======================
@app.route("/criar_usuario", methods=["POST"])
def criar_usuario():
    users = get_users()
    role = session.get("role")

    new_role = request.form.get("role")

    if role == "admin":
        new_role = "usuario"

    users.append({
        "usuario": request.form.get("username"),
        "senha_hash": bcrypt.hashpw(
            request.form.get("senha").encode(),
            bcrypt.gensalt()
        ).decode(),
        "role": new_role,
        "setor": request.form.get("setor"),
        "trocar_senha": False
    })

    set_users(users)
    return redirect("/admin")


@app.route("/excluir_usuario/<usuario>")
def excluir_usuario(usuario):
    role = session.get("role")
    users = get_users()

    if role == "master":
        users = [u for u in users if u["usuario"] != usuario]

    elif role == "admin":
        users = [
            u for u in users
            if not (u["usuario"] == usuario and u["role"] == "usuario")
        ]

    set_users(users)
    return redirect("/admin")


@app.route("/reset_senha/<usuario>")
def reset_senha(usuario):
    role = session.get("role")
    current_user = session.get("user")

    users = get_users()

    for u in users:
        if u["usuario"] == usuario:

            if role == "admin":
                if u["role"] != "usuario" and u["usuario"] != current_user:
                    return redirect("/admin")

            u["senha_hash"] = bcrypt.hashpw(
                "123456".encode(),
                bcrypt.gensalt()
            ).decode()

            u["trocar_senha"] = True

    set_users(users)
    return redirect("/admin")


# ======================
# SETORES (MASTER ONLY)
# ======================
@app.route("/add_departamento", methods=["POST"])
def add_departamento():
    if session.get("role") != "master":
        return redirect("/admin")

    deps = get_departamentos()

    nome = request.form.get("nome")
    emails_raw = request.form.get("emails")

    emails_list = [
        e.strip()
        for e in emails_raw.split(",")
        if e.strip()
    ]

    deps.append({
        "nome": nome,
        "emails": emails_list
    })

    save(ARQ_DEPARTAMENTOS, deps)
    return redirect("/admin")


@app.route("/del_departamento/<nome>")
def del_departamento(nome):
    if session.get("role") != "master":
        return redirect("/admin")

    deps = [d for d in get_departamentos() if d.get("nome") != nome]
    save(ARQ_DEPARTAMENTOS, deps)

    return redirect("/admin")


if __name__ == "__main__":
    app.run(debug=True)