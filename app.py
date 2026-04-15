from flask import Flask, request, redirect, render_template, session
import json, bcrypt, os, uuid, time, threading
from werkzeug.utils import secure_filename
import requests
from supabase import create_client

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static")
)

app.secret_key = "super_secret_key_123"

# ======================
# SUPABASE CONFIG
# ======================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# URL do Google Apps Script
URL_GOOGLE_SCRIPT = os.getenv("URL_GOOGLE_SCRIPT")

UPLOAD_FOLDER = os.path.join(BASE_DIR, "static/uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ======================
# FUNÇÕES SUPABASE
# ======================
def get_users():
    return supabase.table("usuarios").select("*").execute().data

def get_chamados():
    return supabase.table("chamados").select("*").execute().data

def get_departamentos():
    return supabase.table("departamentos").select("*").execute().data

# ======================
# EMAIL
# ======================
def enviar_email(destino, assunto, corpo, nome_usuario):
    try:
        if not URL_GOOGLE_SCRIPT:
            return
        payload = {"nome": nome_usuario, "assunto": assunto, "mensagem": corpo, "destinatario": destino}
        requests.post(URL_GOOGLE_SCRIPT, data=json.dumps(payload), timeout=10)
    except:
        pass

def enviar_email_async(destino, assunto, corpo, nome_usuario):
    threading.Thread(target=enviar_email, args=(destino, assunto, corpo, nome_usuario), daemon=True).start()

# ======================
# LOGIN
# ======================
@app.route("/")
def home():
    if "user" in session: return redirect("/dashboard")
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def login():
    username = (request.form.get("username") or "").lower().strip()
    senha = request.form.get("senha") or ""

    for u in get_users():
        if u.get("usuario", "").lower() == username:
            if bcrypt.checkpw(senha.encode(), u["senha_hash"].encode()):
                session["user"] = u["usuario"]
                session["role"] = u["role"]
                session["setor"] = u.get("setor", "")
                return redirect("/dashboard")

    return render_template("login.html", erro="Usuário ou senha inválidos")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ======================
# DASHBOARD
# ======================
@app.route("/dashboard")
def dashboard():
    if "user" not in session: return redirect("/")

    role, user, setor = session["role"], session["user"], session.get("setor", "")
    chamados = get_chamados()

    if role == "usuario":
        chamados = [c for c in chamados if c.get("criador") == user]
    elif role != "master":
        chamados = [c for c in chamados if c.get("setor", "") == setor]

    return render_template("dashboard.html",
        user=user,
        role=role,
        setor=setor,
        total=len(chamados),
        abertos=len([c for c in chamados if c.get("status") == "Aberto"]),
        andamento=len([c for c in chamados if c.get("status") == "Em andamento"]),
        finalizados=len([c for c in chamados if c.get("status") == "Finalizado"]))

# ======================
# CHAMADOS
# ======================
@app.route("/abrir_chamado", methods=["POST"])
def abrir_chamado():
    if "user" not in session: return redirect("/")

    titulo = request.form.get("titulo")
    descricao = request.form.get("descricao")
    prioridade = (request.form.get("prioridade") or "Normal").upper()
    setor_nome = (request.form.get("setor") or "").strip().lower()

    # Buscar emails do setor
    emails_destino = []
    for d in get_departamentos():
        if d.get("nome", "").strip().lower() == setor_nome:
            emails_destino = d.get("emails", [])
            break

    novo = {
        "id": str(uuid.uuid4()),
        "titulo": f"[{prioridade}] {titulo}",
        "descricao": descricao,
        "setor": setor_nome,
        "prioridade": prioridade,
        "status": "Aberto",
        "criador": session["user"],
        "created_at": time.time()
    }

    supabase.table("chamados").insert(novo).execute()

    # Enviar emails
    for email in emails_destino:
        enviar_email_async(email, novo["titulo"], descricao, session["user"])

    return redirect("/dashboard")

@app.route("/chamados")
def chamados_view():
    if "user" not in session: return redirect("/")

    chamados = get_chamados()
    return render_template("chamados.html", chamados=chamados, role=session.get("role"))

# ======================
# ADMIN
# ======================
@app.route("/admin/criar_usuario", methods=["POST"])
def admin_criar_usuario():
    hash_padrao = bcrypt.hashpw("123456".encode(), bcrypt.gensalt()).decode()

    novo = {
        "usuario": request.form.get("username"),
        "senha_hash": hash_padrao,
        "role": request.form.get("role"),
        "setor": request.form.get("setor")
    }

    supabase.table("usuarios").insert(novo).execute()
    return redirect("/admin")

# ======================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)