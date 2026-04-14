from flask import Flask, request, redirect, render_template, session
import json, bcrypt, os, uuid, time, smtplib, threading
from email.mime.text import MIMEText
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
# EMAIL (GMAIL)
# ======================
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")


def enviar_email(destino, assunto, corpo):
    """Envio real de e-mail (seguro, com timeout)"""
    try:
        if not EMAIL_USER or not EMAIL_PASS:
            print("EMAIL não configurado")
            return

        msg = MIMEText(corpo, "html", "utf-8")
        msg["Subject"] = assunto
        msg["From"] = EMAIL_USER
        msg["To"] = destino

        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)
        server.ehlo()
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)
        server.quit()

        print(f"Email enviado para {destino}")

    except Exception as e:
        print("Erro ao enviar email:", e)


def enviar_email_async(destino, assunto, corpo):
    """Não trava o servidor (IMPORTANTE para Render)"""
    thread = threading.Thread(
        target=enviar_email,
        args=(destino, assunto, corpo),
        daemon=True
    )
    thread.start()

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
    data = load(ARQ_USUARIOS)
    return data.get("usuarios", []) if isinstance(data, dict) else []


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
        if isinstance(u, dict) and u.get("usuario", "").lower() == user.lower():
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
        chamados = [c for c in chamados if c.get("setor", "").lower() == setor.lower()]

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
    descricao = request.form.get("descricao")
    setor_nome = request.form.get("setor")

    emails_destino = []
    for d in get_departamentos():
        if isinstance(d, dict) and d.get("nome") == setor_nome:
            emails_destino = d.get("emails", [])

    assunto = f"[{prioridade.upper()}] {titulo}"

    novo_chamado = {
        "id": str(uuid.uuid4()),
        "titulo": assunto,
        "descricao": descricao,
        "setor": setor_nome,
        "prioridade": prioridade,
        "status": "Aberto",
        "criador": session["user"],
        "anexo": filename,
        "respostas": [],
        "created_at": time.time()
    }

    chamados.append(novo_chamado)
    set_chamados(chamados)

    # ENVIO EMAIL (NÃO TRAVA + SEGUR0)
    for email in emails_destino:
        enviar_email_async(
            email,
            assunto,
            f"""
            <h3>Novo chamado aberto</h3>
            <p><b>Título:</b> {titulo}</p>
            <p><b>Descrição:</b> {descricao}</p>
            <p><b>Prioridade:</b> {prioridade}</p>
            <p><b>Setor:</b> {setor_nome}</p>
            """
        )

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
        chamados = [c for c in chamados if c.get("setor", "").lower() == setor.lower()]

    return render_template("chamados.html", chamados=chamados, role=role)


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
# START
# ======================
if __name__ == "__main__":
    app.run(debug=True)