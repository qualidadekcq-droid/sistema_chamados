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
    try:
        return query_table("usuarios").select("*").execute().data or []
    except Exception as e:
        log_error("get_users", e)
        return []


def get_departamentos():
    try:
        return query_table("departamentos").select("*").order("nome").execute().data or []
    except Exception as e:
        log_error("get_departamentos", e)
        return []


def get_chamados():
    try:
        return query_table("chamados").select("*").order("created_at", desc=True).execute().data or []
    except Exception as e:
        log_error("get_chamados", e)
        return []


def sistema_sem_usuarios():
    return len(get_users()) == 0


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
    except Exception as e:
        log_error("buscar_usuario", e)
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
    except Exception as e:
        log_error("buscar_departamento", e)
        return None


# =====================================================
# AUTH DECORATORS
# =====================================================

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
            role = (session.get("role") or "").lower()
            roles_norm = [r.lower() for r in roles]

            if role not in roles_norm:
                return redirect("/dashboard")

            return f(*args, **kwargs)
        return wrapper
    return decorator


# =====================================================
# EMAIL
# =====================================================

def enviar_email_google_script(payload):
    if not URL_GOOGLE_SCRIPT:
        print("Google Script não configurado")
        return

    try:
        r = requests.post(URL_GOOGLE_SCRIPT, json=payload, timeout=10)
        print("EMAIL STATUS:", r.status_code)
        print("EMAIL RES:", r.text)
    except Exception as e:
        log_error("email_google_script", e)


# =====================================================
# ROUTES
# =====================================================

@app.route("/")
def home():
    if sistema_sem_usuarios():
        return redirect("/primeiro_acesso")

    if "user_id" in session:
        return redirect("/dashboard")

    return render_template("login.html")


@app.route("/primeiro_acesso", methods=["GET", "POST"])
def primeiro_acesso():
    if not sistema_sem_usuarios():
        return redirect("/")

    if request.method == "POST":
        usuario = (request.form.get("usuario") or "").strip().lower()
        senha = request.form.get("senha") or ""

        if not usuario or not senha:
            return render_template("primeiro_acesso.html", erro="Preencha tudo.")

        try:
            query_table("usuarios").insert({
                "usuario": usuario,
                "senha_hash": hash_password(senha),
                "role": "master",
                "setor": "Qualidade",
                "trocar_senha": False,
                "created_at": now_iso()
            }).execute()

            return redirect("/")

        except Exception as e:
            log_error("primeiro_acesso", e)

    return render_template("primeiro_acesso.html")


@app.route("/login", methods=["POST"])
def login():
    username = (request.form.get("username") or "").strip().lower()
    senha = request.form.get("senha") or ""

    user = buscar_usuario(username)

    if not user:
        return render_template("login.html", erro="Usuário inválido")

    try:
        if not check_password(senha, user["senha_hash"]):
            return render_template("login.html", erro="Senha inválida")

        session.clear()
        session["user_id"] = user["id"]
        session["user"] = user["usuario"]
        session["role"] = (user.get("role") or "usuario").lower()
        session["setor"] = user.get("setor", "")
        session["trocar_senha"] = user.get("trocar_senha", False)

        if session["trocar_senha"]:
            return redirect("/trocar_senha")

        return redirect("/dashboard")

    except Exception as e:
        log_error("login", e)
        return render_template("login.html", erro="Erro interno")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/trocar_senha", methods=["GET", "POST"])
@login_required
def trocar_senha():
    if request.method == "POST":
        s1 = request.form.get("senha1") or ""
        s2 = request.form.get("senha2") or ""

        if s1 != s2:
            return render_template("trocar_senha.html", erro="Senhas diferentes")

        try:
            query_table("usuarios").update({
                "senha_hash": hash_password(s1),
                "trocar_senha": False
            }).eq("id", session["user_id"]).execute()

            session["trocar_senha"] = False
            return redirect("/dashboard")

        except Exception as e:
            log_error("trocar_senha", e)

    return render_template("trocar_senha.html")


@app.route("/dashboard")
@login_required
def dashboard():
    chamados = get_chamados()

    if session["role"] == "usuario":
        chamados = [c for c in chamados if c.get("usuario_id") == session["user_id"]]

    return render_template(
        "dashboard.html",
        user=session["user"],
        role=session["role"],
        setor=session["setor"],
        total=len(chamados),
        abertos=len([c for c in chamados if c.get("status") == "Aberto"]),
        andamento=len([c for c in chamados if c.get("status") == "Em andamento"]),
        finalizados=len([c for c in chamados if c.get("status") == "Finalizado"]),
    )


@app.route("/abrir", methods=["GET", "POST"])
@login_required
def abrir_chamado():
    if request.method == "POST":
        try:
            titulo = request.form.get("titulo")
            descricao = request.form.get("descricao")
            setor = request.form.get("setor")
            prioridade = request.form.get("prioridade", "Normal")

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
                "assunto": titulo,
                "nome": session["user"],
                "mensagem": descricao
            })

            return redirect("/chamados")

        except Exception as e:
            log_error("abrir_chamado", e)

    return render_template("abrir_chamado.html", departamentos=get_departamentos())


@app.route("/chamados")
@login_required
def chamados():
    lista = get_chamados()

    if session["role"] == "usuario":
        lista = [c for c in lista if c.get("usuario_id") == session["user_id"]]

    return render_template("chamados.html", chamados=lista, role=session["role"])


@app.route("/alterar_status/<id>", methods=["POST"])
@login_required
@roles_required("admin", "master")
def alterar_status(id):
    try:
        query_table("chamados").update({
            "status": request.form.get("status")
        }).eq("id", id).execute()
    except Exception as e:
        log_error("alterar_status", e)

    return redirect("/chamados")


@app.route("/admin")
@login_required
@roles_required("admin", "master")
def admin():
    return render_template(
        "admin.html",
        usuarios=get_users(),
        departamentos=get_departamentos(),
        role=session["role"],
        user=session["user"]
    )


@app.route("/health")
def health():
    return {"status": "ok"}, 200


# =====================================================
# RUN
# =====================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)