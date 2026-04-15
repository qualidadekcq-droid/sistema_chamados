from flask import Flask, request, redirect, render_template, session
import json, bcrypt, os, uuid, time, threading
import requests
from supabase import create_client

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static")
)

app.secret_key = os.getenv("FLASK_SECRET", "super_secret_key_123")

# ======================
# SUPABASE
# ======================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ======================
# HELPERS
# ======================
def get_users():
    try:
        return supabase.table("usuarios").select("*").execute().data or []
    except:
        return []

def get_chamados():
    try:
        return supabase.table("chamados").select("*").execute().data or []
    except:
        return []

def get_departamentos():
    try:
        return supabase.table("departamentos").select("*").execute().data or []
    except:
        return []

# ======================
# CHECK PRIMEIRO ACESSO
# ======================
def sistema_sem_usuarios():
    users = get_users()
    return len(users) == 0

# ======================
# HOME
# ======================
@app.route("/")
def home():
    if sistema_sem_usuarios():
        return redirect("/primeiro_acesso")

    if "user" in session:
        return redirect("/dashboard")

    return render_template("login.html")

# ======================
# PRIMEIRO ACESSO (MASTER)
# ======================
@app.route("/primeiro_acesso", methods=["GET", "POST"])
def primeiro_acesso():
    if not sistema_sem_usuarios() and request.method == "GET":
        return redirect("/")

    if request.method == "POST":
        usuario = request.form.get("usuario")
        senha = request.form.get("senha")

        hash_senha = bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()

        master = {
            "usuario": usuario,
            "senha_hash": hash_senha,
            "role": "master",
            "setor": "admin",
            "trocar_senha": False
        }

        supabase.table("usuarios").insert(master).execute()

        return redirect("/")

    return render_template("primeiro_acesso.html")

# ======================
# LOGIN
# ======================
@app.route("/login", methods=["POST"])
def login():
    username = (request.form.get("username") or "").lower().strip()
    senha = request.form.get("senha") or ""

    users = get_users()

    for u in users:
        if u.get("usuario", "").lower() == username:
            if bcrypt.checkpw(senha.encode(), u["senha_hash"].encode()):

                session["user"] = u["usuario"]
                session["role"] = u.get("role", "usuario")
                session["setor"] = u.get("setor", "")

                if u.get("trocar_senha") == True:
                    return redirect("/alterar_senha")

                return redirect("/dashboard")

    return render_template("login.html", erro="Usuário ou senha inválidos")

# ======================
# TROCAR SENHA
# ======================
@app.route("/alterar_senha", methods=["GET", "POST"])
def alterar_senha():
    if "user" not in session:
        return redirect("/")

    if request.method == "POST":
        nova = request.form.get("nova_senha")

        hash_nova = bcrypt.hashpw(nova.encode(), bcrypt.gensalt()).decode()

        supabase.table("usuarios").update({
            "senha_hash": hash_nova,
            "trocar_senha": False
        }).eq("usuario", session["user"]).execute()

        return redirect("/dashboard")

    return render_template("trocar_senha.html")

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
    elif role != "master":
        chamados = [c for c in chamados if c.get("setor") == setor]

    return render_template("dashboard.html",
        user=user,
        role=role,
        setor=setor,
        total=len(chamados),
        abertos=len([c for c in chamados if c.get("status") == "Aberto"]),
        andamento=len([c for c in chamados if c.get("status") == "Em andamento"]),
        finalizados=len([c for c in chamados if c.get("status") == "Finalizado"])
    )

# ======================
# CHAMADO
# ======================
@app.route("/abrir_chamado", methods=["POST"])
def abrir_chamado():
    if "user" not in session:
        return redirect("/")

    novo = {
        "id": str(uuid.uuid4()),
        "titulo": request.form.get("titulo"),
        "descricao": request.form.get("descricao"),
        "setor": request.form.get("setor"),
        "status": "Aberto",
        "criador": session["user"],
        "created_at": time.time()
    }

    supabase.table("chamados").insert(novo).execute()

    return redirect("/dashboard")

# ======================
# LOGOUT
# ======================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ======================
# RUN
# ======================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)