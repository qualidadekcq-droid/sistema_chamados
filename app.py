import os
import requests
from functools import wraps
from datetime import datetime, timezone

from flask import Flask, request, redirect, render_template, session
import bcrypt
from supabase import create_client

# ================= CONFIG =================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)

app.secret_key = os.getenv("FLASK_SECRET", "troque_esta_chave")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
URL_GOOGLE_SCRIPT = os.getenv("URL_GOOGLE_SCRIPT", "")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

SENHA_PADRAO = "123456"


# ================= HELPERS =================

def log_error(c, e):
    print(f"[ERRO] {c}: {e}")

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def db(table):
    return supabase.table(table)

def hash_password(p):
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()

def check_password(p, h):
    return bcrypt.checkpw(p.encode(), h.encode())


# ================= USERS =================

def buscar_usuario(username):
    try:
        res = db("usuarios").select("*").eq("usuario", username.lower()).limit(1).execute()
        data = res.data or []
        return data[0] if data else None
    except Exception as e:
        log_error("buscar_usuario", e)
        return None


def get_users():
    try:
        return db("usuarios").select("*").execute().data or []
    except:
        return []


# ================= DECORATORS =================

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/")
        return f(*args, **kwargs)
    return wrapper


def roles_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            role = (session.get("role") or "").strip().lower()
            if role not in roles:
                return redirect("/")
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ================= EMAIL =================

def enviar_email_google_script(payload):
    if not URL_GOOGLE_SCRIPT:
        return

    try:
        requests.post(URL_GOOGLE_SCRIPT, json=payload, timeout=10)
    except Exception as e:
        log_error("email", e)


# ================= ROUTES =================

@app.route("/")
def home():
    if len(get_users()) == 0:
        return redirect("/primeiro_acesso")

    if "user_id" in session:
        return redirect("/dashboard")

    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login():
    username = (request.form.get("username") or "").strip().lower()
    senha = request.form.get("senha") or ""

    user = buscar_usuario(username)

    if not user:
        return render_template("login.html", erro="Usuário ou senha inválidos.")

    if not check_password(senha, user["senha_hash"]):
        return render_template("login.html", erro="Usuário ou senha inválidos.")

    session.clear()
    session["user_id"] = user["id"]
    session["user"] = user["usuario"]
    session["role"] = (user.get("role") or "usuario").lower()

    if user.get("trocar_senha"):
        return redirect("/trocar_senha")

    return redirect("/dashboard")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ================= TROCAR SENHA =================

@app.route("/trocar_senha", methods=["GET", "POST"])
@login_required
def trocar_senha():
    if request.method == "POST":
        s1 = request.form.get("senha1")
        s2 = request.form.get("senha2")

        if s1 != s2:
            return render_template("trocar_senha.html", erro="Senhas diferentes")

        db("usuarios").update({
            "senha_hash": hash_password(s1),
            "trocar_senha": False
        }).eq("id", session["user_id"]).execute()

        return redirect("/dashboard")

    return render_template("trocar_senha.html")


# ================= DASHBOARD =================

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", user=session["user"])


# ================= CHAMADOS =================

@app.route("/abrir", methods=["GET", "POST"])
@login_required
def abrir():
    if request.method == "POST":
        titulo = request.form.get("titulo")
        descricao = request.form.get("descricao")
        setor = request.form.get("setor")

        db("chamados").insert({
            "titulo": titulo,
            "descricao": descricao,
            "setor": setor,
            "status": "Aberto",
            "usuario_id": session["user_id"],
            "created_at": now_iso()
        }).execute()

        enviar_email_google_script({
            "assunto": titulo,
            "mensagem": descricao,
            "nome": session["user"]
        })

        return redirect("/chamados")

    return render_template("abrir_chamado.html")


@app.route("/chamados")
@login_required
def chamados():
    data = db("chamados").select("*").execute().data or []
    return render_template("chamados.html", chamados=data)


# ================= ADMIN =================

@app.route("/admin")
@login_required
@roles_required("admin", "master")
def admin():
    return render_template(
        "admin.html",
        usuarios=get_users()
    )


@app.route("/admin/reset/<usuario>", methods=["POST"])
@login_required
@roles_required("admin", "master")
def reset(usuario):
    user = buscar_usuario(usuario)
    if user:
        db("usuarios").update({
            "senha_hash": hash_password(SENHA_PADRAO),
            "trocar_senha": True
        }).eq("id", user["id"]).execute()

    return redirect("/admin")


@app.route("/admin/delete/<usuario>", methods=["POST"])
@login_required
@roles_required("master")
def delete(usuario):
    user = buscar_usuario(usuario)
    if user:
        db("usuarios").delete().eq("id", user["id"]).execute()

    return redirect("/admin")


# ================= HEALTH =================

@app.route("/health")
def health():
    return {"status": "ok"}, 200


# ================= RUN =================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))