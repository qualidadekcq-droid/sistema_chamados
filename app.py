import os
import requests
from functools import wraps
from datetime import datetime, timezone

from flask import Flask, request, redirect, render_template, session
import bcrypt
from supabase import create_client

# =====================================================
# CONFIG
# =====================================================

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

app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

SENHA_PADRAO = "123456"

# =====================================================
# HELPERS
# =====================================================

def log_error(ctx, err):
    print(f"[ERRO] {ctx}: {err}")

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def query_table(name):
    return supabase.table(name)

def hash_password(pw):
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

def check_password(pw, hashed):
    return bcrypt.checkpw(pw.encode(), hashed.encode())

def get_users():
    return query_table("usuarios").select("*").execute().data or []

def get_departamentos():
    return query_table("departamentos").select("*").order("nome").execute().data or []

def get_chamados():
    return query_table("chamados").select("*").order("created_at", desc=True).execute().data or []

def buscar_usuario(username):
    try:
        res = (
            query_table("usuarios")
            .select("*")
            .eq("usuario", username.lower())
            .limit(1)
            .execute()
        )
        data = res.data or []
        return data[0] if data else None
    except:
        return None

def buscar_departamento(nome):
    try:
        res = (
            query_table("departamentos")
            .select("*")
            .eq("nome", nome)
            .limit(1)
            .execute()
        )
        data = res.data or []
        return data[0] if data else None
    except:
        return None

# =====================================================
# AUTH
# =====================================================

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect("/")
        return f(*args, **kwargs)
    return wrapper


def roles_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            role = (session.get("role") or "").lower()
            if role not in [r.lower() for r in roles]:
                return redirect("/dashboard")
            return f(*args, **kwargs)
        return wrapper
    return decorator

# =====================================================
# EMAIL
# =====================================================

def enviar_email_google_script(payload):
    if not URL_GOOGLE_SCRIPT:
        return
    try:
        requests.post(URL_GOOGLE_SCRIPT, json=payload, timeout=10)
    except Exception as e:
        log_error("email", e)

# =====================================================
# ROTAS
# =====================================================

@app.route("/")
def home():
    return redirect("/dashboard") if session.get("user_id") else render_template("login.html")


@app.route("/login", methods=["POST"])
def login():
    username = (request.form.get("username") or "").strip().lower()
    senha = request.form.get("senha") or ""

    user = buscar_usuario(username)

    if not user:
        return render_template("login.html", erro="Usuário inválido")

    if not check_password(senha, user["senha_hash"]):
        return render_template("login.html", erro="Senha inválida")

    session.clear()
    session["user_id"] = user["id"]
    session["user"] = user["usuario"].lower()
    session["role"] = (user.get("role") or "usuario").lower()
    session["setor"] = user.get("setor", "")

    return redirect("/dashboard")

@app.route("/admin")
@login_required
@roles_required("admin", "master")
def admin():
    return render_template(
        "admin.html",
        usuarios=get_users(),
        departamentos=get_departamentos(),
        role=session.get("role"),
        user=session.get("user")
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# =====================================================
# ABRIR CHAMADO
# =====================================================

@app.route("/abrir", methods=["GET", "POST"])
@login_required
def abrir_chamado():
    if request.method == "POST":
        try:
            titulo = request.form.get("titulo")
            descricao = request.form.get("descricao")
            setor = request.form.get("setor")
            prioridade = (request.form.get("prioridade") or "NORMAL").upper()

            query_table("chamados").insert({
                "titulo": titulo,
                "descricao": descricao,
                "setor": setor,
                "prioridade": prioridade,
                "status": "Aberto",
                "usuario_id": session["user_id"],
                "created_at": now_iso()
            }).execute()

            dep = buscar_departamento(setor)

            enviar_email_google_script({
                "destinatario": dep.get("email", "") if dep else "",
                "assunto": f"[{prioridade}] {titulo}",
                "nome": session["user"],
                "mensagem": descricao
            })

            return redirect("/chamados")

        except Exception as e:
            log_error("abrir", e)

    return render_template("abrir_chamado.html", departamentos=get_departamentos())

# =====================================================
# CHAMADOS LISTA + PERMISSÕES
# =====================================================

@app.route("/chamados")
@login_required
def chamados():
    lista = get_chamados()

    role = session.get("role")
    user_id = session.get("user_id")
    setor = session.get("setor")

    if role == "usuario":
        lista = [c for c in lista if c.get("usuario_id") == user_id]

    elif role == "admin":
        lista = [c for c in lista if c.get("setor") == setor]

    elif role == "master":
        filtro = request.args.get("setor")
        if filtro and filtro != "todos":
            lista = [c for c in lista if c.get("setor") == filtro]

    return render_template("chamados.html", chamados=lista, role=role)

# =====================================================
# RESPONDER (ADMIN / MASTER)
# =====================================================

@app.route("/chamados/responder/<id>", methods=["POST"])
@login_required
@roles_required("admin", "master")
def responder_chamado(id):
    msg = (request.form.get("mensagem") or "").strip()

    if msg:
        query_table("mensagens_chamado").insert({
            "chamado_id": id,
            "usuario_id": session["user_id"],
            "mensagem": msg,
            "created_at": now_iso()
        }).execute()

    return redirect("/chamados")
@app.route("/admin/excluir_departamento/<nome>", methods=["POST"])
@login_required
@roles_required("master")
def excluir_departamento(nome):
    try:
        query_table("departamentos").delete().eq("nome", nome).execute()
    except Exception as e:
        log_error("excluir_departamento", e)

    return redirect("/admin")

# =====================================================
# DASHBOARD
# =====================================================

@app.route("/dashboard")
@login_required
def dashboard():
    chamados = get_chamados()

    role = session.get("role")
    user_id = session.get("user_id")
    setor = session.get("setor")

    if role == "usuario":
        chamados = [c for c in chamados if c.get("usuario_id") == user_id]

    elif role == "admin":
        chamados = [c for c in chamados if c.get("setor") == setor]

    elif role == "master":
        filtro = request.args.get("setor")
        if filtro and filtro != "todos":
            chamados = [c for c in chamados if c.get("setor") == filtro]

    return render_template(
        "dashboard.html",
        user=session.get("user"),
        role=role,
        setor=setor,
        total=len(chamados),
        abertos=len([c for c in chamados if c.get("status") == "Aberto"]),
        andamento=len([c for c in chamados if c.get("status") == "Em andamento"]),
        finalizados=len([c for c in chamados if c.get("status") == "Finalizado"]),
        setores=get_departamentos() if role == "master" else []
    )

# =====================================================
# HEALTH
# =====================================================

@app.route("/health")
def health():
    return {"status": "ok"}, 200


# =====================================================
# RUN
# =====================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)